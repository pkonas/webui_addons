#!/usr/bin/env python3
"""Engineering MCP 2.9.18: verify models, JSON, SSE and the installed LangChain.

Sends two small model requests, or five with --langchain. Does not submit a
PhysicsNeMo job or call tools. Credentials and model response text are not printed.
Use --runtime-env with the WSL <linux_install_dir>/config/runtime.env file,
or specify --base-url and --model (key from PHYSNEMO_AGENT_API_KEY or a hidden prompt).
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import getpass
import math
import importlib.metadata
import ipaddress
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

PROBE = "Reply with exactly ENGINEERING_MCP_BRIDGE_OK. Do not call any tools."
KEYS = {"PHYSNEMO_AGENT_API_KEY", "PHYSNEMO_AGENT_MODEL", "PHYSNEMO_AGENT_BASE_URL",
        "PHYSNEMO_AGENT_TRANSPORT", "PHYSNEMO_GATEWAY_PORT", "PHYSNEMO_GATEWAY_ROUTE"}
LIMIT = 32 * 1024 * 1024
PROTOCOL = "buffered-sse-v1"


class ProbeError(Exception):
    """A diagnostic message constructed locally, never a provider response."""



def read_runtime_env(path: Path) -> dict[str, str]:
    """Read only the known Base64 variables, never source/execute the file."""
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        match = re.fullmatch(r"\s*(?:export\s+)?([A-Z0-9_]+)_B64=(.*?)\s*", line)
        if not match or match[1] not in KEYS:
            continue
        parts = shlex.split(match[2], comments=True)
        if len(parts) > 1:
            raise ProbeError("Malformed private runtime.env assignment")
        encoded = parts[0] if parts else ""
        values[match[1]] = base64.b64decode(encoded, validate=True).decode("utf-8")
    return values


def windows_host() -> str:
    if os.name == "nt":
        return "127.0.0.1"
    try:
        result = subprocess.run(["ip", "route", "show", "default"], capture_output=True,
                                text=True, check=True, timeout=5)
        match = re.search(r"\bvia\s+(\S+)", result.stdout)
        if match:
            return str(ipaddress.ip_address(match[1]))
    except (OSError, subprocess.SubprocessError, ValueError):
        pass
    try:
        for line in Path("/etc/resolv.conf").read_text().splitlines():
            if line.strip().startswith("nameserver "):
                return str(ipaddress.ip_address(line.split()[1]))
    except (OSError, ValueError, IndexError):
        pass
    raise ProbeError("Cannot resolve the Windows host; provide --base-url explicitly")


def resolve_config(args) -> tuple[str, str, str]:
    values = {key: os.environ.get(key, "") for key in KEYS}
    if args.runtime_env:
        values.update(read_runtime_env(args.runtime_env))
    base = args.base_url
    if not base and values.get("PHYSNEMO_AGENT_TRANSPORT") == "openwebui-chat-api":
        port = int(values.get("PHYSNEMO_GATEWAY_PORT") or "8200")
        route = values.get("PHYSNEMO_GATEWAY_ROUTE") or "physnemo"
        if not 1 <= port <= 65535 or not re.fullmatch(r"[A-Za-z0-9_-]+", route):
            raise ProbeError("Invalid bridge port or route in runtime.env")
        host = windows_host()
        host = f"[{host}]" if ":" in host else host
        base = f"http://{host}:{port}/{route}/openwebui-api"
    base = (base or values.get("PHYSNEMO_AGENT_BASE_URL") or "").rstrip("/")
    parsed = urllib.parse.urlsplit(base)
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or not parsed.path.endswith("/openwebui-api")):
        raise ProbeError("Use the bridge base URL ending in /physnemo/openwebui-api (or your configured route)")
    model = args.model or values.get("PHYSNEMO_AGENT_MODEL")
    if not model:
        raise ProbeError("Model is missing; provide --model or --runtime-env")
    key = values.get("PHYSNEMO_AGENT_API_KEY")
    if not key and not args.non_interactive:
        key = getpass.getpass("Bridge secret (hidden): ")
    if not key or "\r" in key or "\n" in key:
        raise ProbeError("Missing or invalid bridge credential")
    return base, model, key


def parse_sse(content: bytes) -> list[dict]:
    text = content.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    frames: list[dict] = []
    done = False
    for block in text.split("\n\n"):
        fields = []
        for line in block.split("\n"):
            if line.startswith("data:"):
                fields.append(line[5:].removeprefix(" "))
        if not fields:
            continue
        data = "\n".join(fields)
        if data.strip() == "[DONE]":
            done = True
            break
        payload = json.loads(data)
        if not isinstance(payload, dict) or payload.get("error"):
            raise ProbeError("SSE contains an error or malformed event")
        if payload.get("object") != "chat.completion.chunk":
            raise ProbeError("SSE event is not a chat.completion.chunk")
        if not isinstance(payload.get("choices"), list):
            raise ProbeError("SSE event has no choices list")
        frames.append(payload)
    if not done or not frames:
        raise ProbeError("Expected completion SSE events followed by data: [DONE]")
    return frames


def check_http(base: str, model: str, key: str, stream: bool, timeout: float) -> dict:
    payload = {"model": model, "messages": [{"role": "user", "content": PROBE}], "stream": stream}
    if stream:
        payload["stream_options"] = {"include_usage": True}
    req = urllib.request.Request(
        base + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"), method="POST",
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json",
                 "Accept": "text/event-stream" if stream else "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        content = response.read(LIMIT + 1)
        status = response.status
        media = response.headers.get_content_type()
        marker = response.headers.get("X-Engineering-MCP-Bridge-Protocol")
    if len(content) > LIMIT:
        raise ProbeError("Response exceeds diagnostic size limit")
    if status != 200 or marker != PROTOCOL:
        raise ProbeError("Expected bridge protocol header is absent: verify that the 2.9.18 gateway is active")
    if stream:
        if media != "text/event-stream":
            raise ProbeError("stream=true did not return text/event-stream")
        frames = parse_sse(content)
        usable = False
        finished = False
        for frame in frames:
            for choice in frame["choices"]:
                if not isinstance(choice, dict):
                    raise ProbeError("SSE choice is not an object")
                delta = choice.get("delta") or {}
                if not isinstance(delta, dict):
                    raise ProbeError("SSE delta is not an object")
                usable |= bool(delta.get("content") or delta.get("tool_calls") or delta.get("refusal")
                               or delta.get("function_call"))
                finished |= bool(choice.get("finish_reason"))
        if not usable or not finished:
            raise ProbeError("SSE lacks a usable message or finish_reason")
        return {"mode": "stream=true", "success": True, "http": status, "content_type": media,
                "events": len(frames), "done": True, "protocol": marker}
    if media != "application/json":
        raise ProbeError("stream=false did not return application/json")
    data = json.loads(content)
    choices = data.get("choices") if isinstance(data, dict) else None
    if not isinstance(choices, list) or not choices:
        raise ProbeError("JSON response contains no choices")
    if not isinstance(choices[0], dict):
        raise ProbeError("JSON choice is not an object")
    message = choices[0].get("message") or {}
    if not isinstance(message, dict) or not choices[0].get("finish_reason"):
        raise ProbeError("JSON choice lacks a message or finish_reason")
    if not (message.get("content") or message.get("tool_calls") or message.get("refusal") or message.get("function_call")):
        raise ProbeError("JSON response contains no usable message")
    return {"mode": "stream=false", "success": True, "http": status, "content_type": media,
            "choices": len(choices), "protocol": marker}


def check_models(base: str, model: str, key: str, timeout: float) -> dict:
    request = urllib.request.Request(base + "/models", headers={
        "Authorization": "Bearer " + key, "Accept": "application/json",
    })
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read(LIMIT + 1)
        if response.status != 200 or len(raw) > LIMIT:
            raise ProbeError("Invalid model catalogue response or size")
    data = json.loads(raw)
    items = data.get("data", data.get("models", [])) if isinstance(data, dict) else []
    ids = {str(item.get("id") or item.get("name")) for item in items
           if isinstance(item, dict) and (item.get("id") or item.get("name"))} if isinstance(items, list) else set()
    if model not in ids:
        raise ProbeError("Configured agent model is absent from the bridge model catalogue")
    return {"model_count": len(ids), "configured_model_present": True}


def usable_message(message) -> bool:
    return bool(message.content or message.tool_calls or message.additional_kwargs.get("refusal"))


async def check_langchain(base: str, model: str, key: str, timeout: float) -> dict:
    from langchain_openai import ChatOpenAI
    versions = {}
    for name in ("langchain-core", "langchain-openai", "openai", "nvidia-nat", "nvidia-nat-langchain"):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            pass
    llm = ChatOpenAI(model=model, api_key=key, base_url=base, timeout=timeout,
                     max_retries=0, streaming=True, stream_usage=True)
    try:
        result = await llm.ainvoke(PROBE)
        if not usable_message(result):
            raise ProbeError("LangChain ainvoke returned no usable message")
        count = 0
        usable = False
        async for chunk in llm.astream(PROBE):
            count += 1
            usable |= usable_message(chunk)
        if not count or not usable:
            raise ProbeError("LangChain astream returned no usable generation chunks")
        event_count = 0
        event_usable = False
        async for event in llm.astream_events(PROBE, version="v2"):
            if event.get("event") == "on_chat_model_stream":
                event_count += 1
                chunk = event.get("data", {}).get("chunk")
                event_usable |= bool(chunk is not None and usable_message(chunk))
        if not event_count or not event_usable:
            raise ProbeError("LangChain astream_events returned no usable model stream events")
        return {"success": True, "ainvoke_streaming": True, "astream_chunks": count,
                "model_stream_events": event_count, "installed_versions": versions}
    finally:
        # Clients are constructed exclusively for this diagnostic.
        try:
            await llm.root_async_client.close()
            llm.root_client.close()
        except (AttributeError, RuntimeError):
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-env", type=Path)
    parser.add_argument("--base-url")
    parser.add_argument("--model")
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--langchain", action="store_true",
                        help="Also test the installed LangChain client (three additional requests)")
    parser.add_argument("--non-interactive", action="store_true",
                        help="Fail rather than prompt if the existing bridge credential is missing")
    args = parser.parse_args()
    report = {"success": False, "release": "2.9.18", "protocol": PROTOCOL}
    stage = "configuration"
    try:
        if not math.isfinite(args.timeout) or args.timeout <= 0:
            raise ProbeError("timeout must be a positive finite number")
        base, model, key = resolve_config(args)
        report.update({"model": model, "models_url": base + "/models", "chat_url": base + "/chat/completions"})
        stage = "models"
        report.update(check_models(base, model, key, args.timeout))
        stage = "json"
        report["json"] = check_http(base, model, key, False, args.timeout)
        report["chat_choice_count"] = report["json"]["choices"]
        stage = "sse"
        report["sse"] = check_http(base, model, key, True, args.timeout)
        report.update({"sse_event_count": report["sse"]["events"], "sse_done": report["sse"]["done"]})
        if args.langchain:
            stage = "langchain"
            async def checked():
                return await asyncio.wait_for(check_langchain(base, model, key, args.timeout),
                                              timeout=args.timeout * 3 + 15)
            report["langchain"] = asyncio.run(checked())
        report["success"] = True
    except urllib.error.HTTPError as exc:
        report.update({"error": "HTTPError", "http_status": exc.code,
                       "note": "Inspect bridge/Open WebUI logs; response bodies are not printed."})
        try:
            data = json.loads(exc.read(65536))
            code = data.get("error", {}).get("code") if isinstance(data, dict) else None
            if isinstance(code, str) and re.fullmatch(r"openwebui_[a-z0-9_]{1,80}", code):
                report["bridge_error_code"] = code
        except Exception:
            pass
        finally:
            exc.close()
    except ProbeError as exc:
        report.update({"error": "BridgePreflightError", "message": str(exc)})
    except Exception as exc:
        # Do not echo exception text: third-party clients may include credentials or response bodies.
        report.update({"error": type(exc).__name__,
                       "note": "Check connectivity and installed client versions; no provider bodies or credentials printed."})
    if not report["success"]:
        report["failed_stage"] = stage
    print(json.dumps(report, ensure_ascii=True))
    return 0 if report["success"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

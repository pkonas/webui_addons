#!/usr/bin/env python3
"""Run in the installed NAT venv. No shell sourcing, dependency installation or secret output."""
from __future__ import annotations
import argparse
import asyncio
import base64
import ipaddress
import importlib.metadata
import json
import math
import os
from pathlib import Path
import re
import shlex
import sys
import subprocess
import urllib.parse

CONTRACT = "PHYSNEMO_NATIVE_TOOL_DISPATCH_V5"
PREFLIGHT_CONTRACT = "PHYSNEMO_NATIVE_TOOL_PREFLIGHT_V5"

DEFAULT_REQUEST_TIMEOUT_SECONDS = 300.0
DEFAULT_TOTAL_TIMEOUT_SECONDS = 1800.0

KEYS = {"PHYSNEMO_AGENT_BASE_URL", "PHYSNEMO_AGENT_API_KEY", "PHYSNEMO_AGENT_MODEL",
        "PHYSNEMO_AGENT_TRANSPORT", "PHYSNEMO_GATEWAY_PORT", "PHYSNEMO_GATEWAY_ROUTE"}

def read_env(path: Path) -> dict[str, str]:
    """Decode the installer's private *_B64 format without sourcing/executing it."""
    values = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        m = re.fullmatch(r"\s*(?:export\s+)?([A-Z0-9_]+)_B64=(.*?)\s*", line)
        if not m or m[1] not in KEYS:
            continue
        parts = shlex.split(m[2], comments=True)
        if len(parts) > 1:
            raise RuntimeError("PHYSNEMO_NATIVE_RUNTIME_ENV_INVALID")
        values[m[1]] = base64.b64decode(parts[0] if parts else "", validate=True).decode("utf-8")
    return values

def windows_host() -> str:
    if os.name == "nt":
        return "127.0.0.1"
    try:
        cp = subprocess.run(["ip", "route", "show", "default"], capture_output=True,
                            text=True, check=True, timeout=5)
        m = re.search(r"\bvia\s+(\S+)", cp.stdout)
        if m:
            return str(ipaddress.ip_address(m[1]))
    except (OSError, subprocess.SubprocessError, ValueError):
        pass
    try:
        for line in Path("/etc/resolv.conf").read_text().splitlines():
            if line.strip().startswith("nameserver "):
                return str(ipaddress.ip_address(line.split()[1]))
    except (OSError, ValueError, IndexError):
        pass
    raise RuntimeError("PHYSNEMO_NATIVE_WINDOWS_HOST_UNAVAILABLE")

def resolve_env(values: dict[str, str]) -> dict[str, str]:
    env = dict(values)
    if env.get("PHYSNEMO_AGENT_TRANSPORT") == "openwebui-chat-api":
        port = int(env.get("PHYSNEMO_GATEWAY_PORT") or "8200")
        route = env.get("PHYSNEMO_GATEWAY_ROUTE") or "physnemo"
        if not 1 <= port <= 65535 or not re.fullmatch(r"[A-Za-z0-9_-]+", route):
            raise RuntimeError("PHYSNEMO_NATIVE_BRIDGE_CONFIG_INVALID")
        host = windows_host()
        host = f"[{host}]" if ":" in host else host
        env["PHYSNEMO_AGENT_BASE_URL"] = f"http://{host}:{port}/{route}/openwebui-api"
    for key in ("PHYSNEMO_AGENT_BASE_URL", "PHYSNEMO_AGENT_API_KEY", "PHYSNEMO_AGENT_MODEL"):
        if not env.get(key) or any(c in env[key] for c in ("\r", "\n")):
            raise RuntimeError("PHYSNEMO_NATIVE_AGENT_NOT_CONFIGURED")
    url = urllib.parse.urlsplit(env["PHYSNEMO_AGENT_BASE_URL"])
    if (url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password
            or url.query or url.fragment):
        raise RuntimeError("PHYSNEMO_NATIVE_BASE_URL_INVALID")
    env["PHYSNEMO_AGENT_BASE_URL"] = env["PHYSNEMO_AGENT_BASE_URL"].rstrip("/")
    return env

def validate_timeouts(request_timeout: float, total_timeout: float) -> None:
    if (isinstance(request_timeout, bool) or isinstance(total_timeout, bool)
            or not isinstance(request_timeout, (int, float)) or not isinstance(total_timeout, (int, float))
            or not math.isfinite(request_timeout) or not math.isfinite(total_timeout)
            or not 1 <= request_timeout <= 900 or not request_timeout <= total_timeout <= 7200):
        raise RuntimeError("PHYSNEMO_MODEL_TIMEOUT_CONFIG_INVALID")


def progress(event: dict) -> None:
    # The plugin callback supplies only host-authored metadata; no response bodies.
    print("PHYSNEMO_PREFLIGHT_PROGRESS " + json.dumps(event, ensure_ascii=True), file=sys.stderr, flush=True)


async def check(root: Path, env: dict[str, str], tool_transport: str = "auto",
                request_timeout: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
                total_timeout: float = DEFAULT_TOTAL_TIMEOUT_SECONDS) -> dict:
    validate_timeouts(request_timeout, total_timeout)
    from langchain_openai import ChatOpenAI
    from engineering_physnemo_nat.register import NATIVE_TOOL_CONTRACT, NATIVE_PREFLIGHT_CONTRACT, native_tool_preflight
    if NATIVE_TOOL_CONTRACT != CONTRACT or NATIVE_PREFLIGHT_CONTRACT != PREFLIGHT_CONTRACT:
        raise RuntimeError("PHYSNEMO_NATIVE_PLUGIN_STALE")
    env = resolve_env(env)
    llm = ChatOpenAI(base_url=env["PHYSNEMO_AGENT_BASE_URL"], api_key=env["PHYSNEMO_AGENT_API_KEY"],
                    model=env["PHYSNEMO_AGENT_MODEL"], temperature=0.1, max_tokens=8192,
                    timeout=float(request_timeout), max_retries=0)
    result = await native_tool_preflight(llm, root / "physicsnemo-source", root / "run/native-tool-probes", tool_transport=tool_transport,
        request_timeout_seconds=request_timeout, total_timeout_seconds=total_timeout, progress_callback=progress)
    result["client_policy"] = {"request_timeout_seconds": float(request_timeout), "sdk_max_retries": 0,
                               "configured_by": "installed_preflight_checker"}
    result["versions"] = {name: importlib.metadata.version(name) for name in
        ("nvidia-nat", "nvidia-nat-langchain", "langchain-core", "langchain-openai", "engineering-physnemo-nat")}
    return result

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", required=True)
    p.add_argument("--runtime-env", required=True)
    p.add_argument("--tool-transport", choices=("auto", "native", "json_actions_v1"), default="auto")
    p.add_argument("--request-timeout", type=float, default=DEFAULT_REQUEST_TIMEOUT_SECONDS,
                   help="SDK request timeout in seconds (1..900; default 300). No automatic retry.")
    p.add_argument("--total-timeout", type=float, default=DEFAULT_TOTAL_TIMEOUT_SECONDS,
                   help="Whole model phase deadline in seconds (request timeout..7200; default 1800).")
    a = p.parse_args()
    result = {"success": False, "contract": CONTRACT, "preflight_contract": PREFLIGHT_CONTRACT}
    try:
        result.update(asyncio.run(check(Path(a.root).resolve(), read_env(Path(a.runtime_env)), a.tool_transport, a.request_timeout, a.total_timeout)))
    except Exception as exc:
        # Third-party exception text may contain credentials or private model content.
        safe = str(exc) if re.fullmatch(r"PHYSNEMO_[A-Z_]+", str(exc)) else "PHYSNEMO_NATIVE_PREFLIGHT_FAILED"
        result.update(error=safe, exception_type=type(exc).__name__,
                      failed_stage="load_runtime_or_client", note="No provider bodies or credentials printed. Inspect both model-events.jsonl and tool-events.jsonl in the reported probe directory.")
    print(json.dumps(result, ensure_ascii=True))
    return 0 if result.get("success") else 2

if __name__ == "__main__":
    raise SystemExit(main())

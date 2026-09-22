"""
title: Engineering MCP Tool Router
id: engineering_mcp_tool_router
version: 1.1.0
required_open_webui_version: 0.11.2
author: OpenAI
description: Deterministically attaches installed Engineering MCP routes to explicit engineering requests before Open WebUI resolves native tools.
"""

from __future__ import annotations

import re
import asyncio
import contextlib
import json
import logging
import time
import math
import uuid
from html import escape
from urllib.parse import urlsplit
import unicodedata
from typing import Any

from pydantic import BaseModel, Field

LIFECYCLE_CONTRACT = "PHYSNEMO_OBSERVABLE_DELIVERY_V1"
_LOG = logging.getLogger(__name__)
FILTER_CONTRACT = "ENGINEERING_MCP_TOOL_ROUTER_FILTER_V1"
PROBE_MARKER = "ENGINEERING_MCP_TOOL_ROUTER_PROBE_V1"
INSTRUCTION_MARKER = "[ENGINEERING_MCP_TOOL_ROUTER_V1]"


class Filter:
    class Valves(BaseModel):
        priority: int = Field(
            default=-1000,
            description="Run before ordinary policy filters so Engineering MCP tool_ids are resolved in the same request.",
        )
        enabled: bool = Field(default=True)
        require_chat_context: bool = Field(
            default=True,
            description="Do not route headless/internal OpenAI API calls without chat metadata; prevents recursive PhysNeMo-agent calls.",
        )
        force_native_function_calling: bool = Field(default=True)
        inject_tool_instruction: bool = Field(default=True)
        automatic_progress: bool = Field(default=True)
        automatic_result_display: bool = Field(default=True)
        progress_poll_seconds: float = Field(default=2.0, ge=0.2, le=30.0)
        status_timeout_seconds: float = Field(default=10.0, ge=1, le=30)
        gallery_timeout_seconds: float = Field(default=120.0, ge=5, le=300)

    def __init__(self):
        self.valves = self.Valves()

    @staticmethod
    def _flatten_text(value: Any) -> str:
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            parts: list[str] = []
            for item in value:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    for key in ("text", "content", "input_text"):
                        if key in item:
                            text = Filter._flatten_text(item.get(key))
                            if text:
                                parts.append(text)
                            break
            return "\n".join(parts)
        if isinstance(value, dict):
            for key in ("text", "content", "input_text"):
                if key in value:
                    return Filter._flatten_text(value.get(key))
        return ""

    @classmethod
    def _latest_user_text(cls, messages: Any) -> tuple[str, int]:
        if not isinstance(messages, list):
            return "", -1
        for index in range(len(messages) - 1, -1, -1):
            message = messages[index]
            if isinstance(message, dict) and str(message.get("role") or "").casefold() == "user":
                return cls._flatten_text(message.get("content")), index
        return "", -1

    @staticmethod
    def _normalize(value: str) -> str:
        return unicodedata.normalize("NFKC", value).casefold()

    @staticmethod
    def _has_chat_context(body: dict, metadata: Any) -> bool:
        candidates: list[Any] = []
        if isinstance(metadata, dict):
            candidates.extend(
                metadata.get(key)
                for key in ("chat_id", "message_id", "user_message_id", "session_id")
            )
        embedded = body.get("metadata")
        if isinstance(embedded, dict):
            candidates.extend(
                embedded.get(key)
                for key in ("chat_id", "message_id", "user_message_id", "session_id")
            )
        candidates.extend(body.get(key) for key in ("chat_id", "message_id", "session_id"))
        return any(isinstance(value, str) and value.strip() for value in candidates)

    @staticmethod
    def _matches(text: str, *patterns: str) -> bool:
        return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)

    @classmethod
    def _route_request(cls, raw_text: str) -> tuple[list[str], str | None]:
        text = cls._normalize(raw_text)
        routes: list[str] = []
        forced: str | None = None

        operation_names = (
            "physnemo__environment_info",
            "physnemo__solve",
            "physnemo__job_status",
            "physnemo__list_artifacts",
            "physnemo__get_artifact",
            "physnemo__render_artifacts",
        )
        for operation in operation_names:
            if operation in text:
                routes.append("physnemo")
                forced = operation
                break

        physnemo_explicit = cls._matches(
            text,
            r"\bphys(?:ics)?nemo\b",
            r"\bnemo[\s_-]*agent[\s_-]*toolkit\b",
            r"\bphysics[\s_-]*ml\b",
            r"\bsci[\s_-]*ml\b",
            r"\bphysics[\s_-]*informed[\s_-]*neural[\s_-]*network(?:s)?\b",
            r"\bpinn(?:s)?\b",
        )
        if physnemo_explicit and "physnemo" not in routes:
            routes.append("physnemo")

        # Viewing a known job must not start a replacement solve, even if the text says "artifacts".
        known_job = re.search(r"\bjob-\d{8}t\d{6}z-[a-f0-9]{12}\b", text)
        if known_job and forced is None:
            if cls._matches(text, r"\b(?:show|display|render|zobraz|ukaz|ukaž)\w*"):
                if "physnemo" not in routes:
                    routes.append("physnemo")
                forced = "physnemo__render_artifacts"
            elif cls._matches(text, r"\b(?:status|stav|progress|průběh|prubeh)\b"):
                if "physnemo" not in routes:
                    routes.append("physnemo")
                forced = "physnemo__job_status"

        if "physnemo" in routes and forced is None:
            if cls._matches(
                text,
                r"\b(?:create|build|simulate|simulation|solve|train|training|visuali[sz]e|artifact|model)\b",
                r"\b(?:vytvo[řr]|sestav|simul|vy[řr]e[šs]|tr[eé]n|vizual|artefakt|model)\w*",
                r"\bk[áa]rm[áa]n\w*",
            ):
                forced = "physnemo__solve"

        route_patterns: tuple[tuple[str, tuple[str, ...]], ...] = (
            ("matlab", (r"\bmatlab\b",)),
            ("weknora", (r"\bweknora\b", r"\bknowledge[\s_-]*base(?:s)?\b")),
            ("ansys_mechanical", (r"\bansys[\s_-]*mechanical\b", r"\bmechanical[\s_-]*workflow\b")),
            ("ansys_fluent", (r"\bansys[\s_-]*fluent\b",)),
            ("ansys_mapdl", (r"\bansys[\s_-]*mapdl\b", r"\bmapdl\b", r"\bapdl\b")),
            ("ansys_aedt", (r"\bansys[\s_-]*aedt\b", r"\belectronics[\s_-]*desktop\b", r"\bhfss\b")),
            ("ansys_cfx", (r"\bansys[\s_-]*cfx\b", r"\bcfx\b")),
        )
        for route, patterns in route_patterns:
            if cls._matches(text, *patterns) and route not in routes:
                routes.append(route)

        if cls._matches(text, r"\bansys\b") and not any(route.startswith("ansys_") for route in routes):
            routes.extend(("ansys_mechanical", "ansys_fluent", "ansys_mapdl", "ansys_aedt", "ansys_cfx"))

        return list(dict.fromkeys(routes)), forced

    @staticmethod
    def _insert_instruction(messages: list, user_index: int, routes: list[str], forced: str | None) -> None:
        if any(
            isinstance(message, dict)
            and INSTRUCTION_MARKER in Filter._flatten_text(message.get("content"))
            for message in messages
        ):
            return
        route_names = ", ".join(f"server:{route}" for route in routes)
        action = (
            f"Call the native function `{forced}` once if it has not already returned a result in this turn."
            if forced
            else "Use the attached native function schemas when they are relevant."
        )
        content = (
            f"{INSTRUCTION_MARKER} Engineering MCP route(s) attached: {route_names}. "
            f"{action} Never print XML/JSON/pseudo tool-call markup and never claim a tool was called unless "
            "Open WebUI executes a native function call and returns its result. "
            "PhysicsNeMo progress and result presentation are automatic. After a tool result, explain its actual "
            "answer and delivery status, do not call solve again merely to display it. Do not equate an "
            "agent report with a completed numerical computation. Never ask whether to show existing outputs."
        )
        insert_at = user_index if user_index >= 0 else 0
        messages.insert(insert_at, {"role": "system", "content": content})

    async def inlet(
        self,
        body: dict,
        __metadata__: dict | None = None,
        __user__: dict | None = None,
    ) -> dict:
        del __user__
        if not self.valves.enabled or not isinstance(body, dict):
            return body

        messages = body.get("messages")
        latest_text, user_index = self._latest_user_text(messages)
        if not latest_text:
            return body

        probe = PROBE_MARKER.casefold() in self._normalize(latest_text)
        if self.valves.require_chat_context and not probe and not self._has_chat_context(body, __metadata__):
            return body

        routes, forced = self._route_request(latest_text)
        if not routes:
            return body

        existing = body.get("tool_ids")
        if not isinstance(existing, list):
            existing = []
        tool_ids = [str(value) for value in existing if isinstance(value, str) and value.strip()]
        for route in routes:
            tool_id = f"server:{route}"
            if tool_id not in tool_ids:
                tool_ids.append(tool_id)
        body["tool_ids"] = tool_ids

        if self.valves.force_native_function_calling:
            # Open WebUI calls apply_params_to_form_data() before inlet filters.
            # Native-vs-legacy dispatch later reads the shared metadata dict, not
            # a newly-created body["params"] value.  Mutate __metadata__ directly
            # so the current request resolves external tools through native FC.
            if isinstance(__metadata__, dict):
                metadata_params = __metadata__.get("params")
                if not isinstance(metadata_params, dict):
                    metadata_params = {}
                    __metadata__["params"] = metadata_params
                metadata_params["function_calling"] = "native"
            embedded_metadata = body.get("metadata")
            if isinstance(embedded_metadata, dict):
                embedded_params = embedded_metadata.get("params")
                if not isinstance(embedded_params, dict):
                    embedded_params = {}
                    embedded_metadata["params"] = embedded_params
                embedded_params["function_calling"] = "native"
            body["parallel_tool_calls"] = False

        if forced and not self._operation_returned(messages, forced):
            if isinstance(__metadata__, dict):
                __metadata__["engineering_mcp_forced_operation"] = forced
            body["tool_choice"] = {"type": "function", "function": {"name": forced}}

        if self.valves.inject_tool_instruction and isinstance(messages, list):
            self._insert_instruction(messages, user_index, routes, forced)

        return body


    @staticmethod
    def _operation_returned(messages: Any, operation: str) -> bool:
        """Only inspect tool results in the latest user turn, not old jobs in chat history."""
        if not isinstance(messages, list):
            return False
        calls: set[str] = set()
        # Real callers retain the shared execution metadata; this also handles a reconstructed turn.
        for message in reversed(messages):
            if isinstance(message, dict) and message.get("role") == "tool" and message.get("name") == operation:
                return True
            if isinstance(message, dict) and message.get("role") == "user":
                break
        last_user = max((i for i, m in enumerate(messages) if isinstance(m, dict) and m.get("role") == "user"), default=-1)
        for message in messages[last_user + 1:]:
            if not isinstance(message, dict):
                continue
            for call in message.get("tool_calls") or []:
                if isinstance(call, dict) and (call.get("function") or {}).get("name") == operation:
                    calls.add(str(call.get("id") or ""))
            if message.get("role") == "tool" and str(message.get("tool_call_id") or "") in calls:
                return True
        return False

    @classmethod
    def _job_result(cls, value: Any, depth: int = 0) -> dict:
        if depth > 12:
            return {}
        if hasattr(value, "model_dump"):
            value = value.model_dump()
        if isinstance(value, str):
            try:
                return cls._job_result(json.loads(value), depth + 1)
            except (ValueError, TypeError):
                return {}
        if isinstance(value, dict):
            if "state" in value or value.get("status") == "configuration_required":
                return value
            for key in ("result", "data", "content", "text", "output", "response", "structuredContent"):
                if key in value:
                    found = cls._job_result(value[key], depth + 1)
                    if found:
                        return found
        if isinstance(value, (list, tuple)):
            for item in value:
                found = cls._job_result(item, depth + 1)
                if found:
                    return found
        return {}

    @classmethod
    def _html_result(cls, value: Any, depth: int = 0) -> str:
        if depth > 10:
            return ""
        if hasattr(value, "body") and isinstance(value.body, bytes):
            return cls._html_result(value.body.decode("utf-8", "replace"), depth + 1)
        if isinstance(value, str):
            if value.lstrip().lower().startswith("<!doctype html>") and "PhysicsNeMo" in value:
                return value
            try:
                return cls._html_result(json.loads(value), depth + 1)
            except (ValueError, TypeError):
                return ""
        if isinstance(value, dict):
            for key in ("content", "text", "result", "data", "html"):
                if key in value:
                    content = cls._html_result(value[key], depth + 1)
                    if content:
                        return content
        if isinstance(value, (list, tuple)):
            for item in value:
                content = cls._html_result(item, depth + 1)
                if content:
                    return content
        return ""

    @staticmethod
    async def _emit(emitter: Any, event: dict) -> bool:
        if not callable(emitter):
            return False
        try:
            await asyncio.wait_for(emitter(event), timeout=5)
            return True
        except Exception as exc:
            # Error type only: event payloads or exception strings may contain private results.
            _LOG.warning("PHYSNEMO_UI_EVENT_FAILED type=%s event=%s", type(exc).__name__, event.get("type"))
            return False

    @classmethod
    def _fallback_html(cls, data: dict, gallery_error: str = "") -> str:
        job = escape(str(data.get("job_id") or "—"))
        state = escape(str(data.get("state") or data.get("status") or "unknown"))
        text = escape(str(data.get("answer") or data.get("message") or data.get("error") or "Výsledek nebyl vrácen."))
        links = []
        for item in data.get("artifacts") or []:
            if not isinstance(item, dict):
                continue
            url = str(item.get("download_url") or "")
            if urlsplit(url).scheme not in {"http", "https"}:
                continue
            links.append('<p><a target="_blank" rel="noopener noreferrer" href="' + escape(url, quote=True) + '">' + escape(str(item.get("name") or "soubor")) + '</a></p>')
        warning = '<p>Galerie není dostupná: ' + escape(gallery_error) + '. Níže je skutečný výsledek a dostupné odkazy.</p>' if gallery_error else ''
        return ('<!doctype html><html lang="cs"><meta charset="utf-8"><title>PhysicsNeMo výsledek</title>'
                '<body style="font-family:system-ui;padding:16px"><h2>PhysicsNeMo — ' + state + '</h2><p>Job: ' + job + '</p>'
                + warning + '<pre style="white-space:pre-wrap;overflow-wrap:anywhere">' + text + '</pre>' + ''.join(links) + '</body></html>')

    @staticmethod
    def _return_context(data: dict, raw: Any) -> Any:
        text = json.dumps(data, ensure_ascii=False)
        # External OpenAPI tools return (body, headers). Preserve that envelope so Open WebUI
        # does not interpret an ordinary dict as the pair; inline HTML is emitted separately.
        if isinstance(raw, tuple) and len(raw) == 2:
            return text, {"Content-Type": "application/json"}
        return text

    async def request(self, body: dict, __metadata__: dict | None = None,
                      __event_emitter__: Any = None) -> dict:
        """Runs after authorized native callables are resolved, and on every continuation."""
        if not self.valves.enabled or not isinstance(body, dict):
            return body
        metadata = __metadata__ if isinstance(__metadata__, dict) else body.get("metadata")
        if not isinstance(metadata, dict) or not self._has_chat_context(body, metadata):
            return body
        # State is per request/turn, not on the Filter instance (which is shared between users).
        lifecycle = metadata.setdefault("engineering_mcp_lifecycle", {"executed": [], "results": {}})
        forced = metadata.get("engineering_mcp_forced_operation")
        choice = body.get("tool_choice")
        chosen = (choice.get("function") or {}).get("name") if isinstance(choice, dict) else None
        if forced and (forced in lifecycle["executed"] or self._operation_returned(body.get("messages"), forced)):
            if chosen == forced:
                body.pop("tool_choice", None)
        tools = metadata.get("tools")
        if not isinstance(tools, dict):
            return body
        solve_tool = tools.get("physnemo__solve")
        if not isinstance(solve_tool, dict) or not callable(solve_tool.get("callable")):
            return body
        original = solve_tool["callable"]
        if getattr(original, "_engineering_lifecycle_wrapped", False):
            return body
        status_tool = tools.get("physnemo__job_status") or {}
        render_tool = tools.get("physnemo__render_artifacts") or {}
        status_call, render_call = status_tool.get("callable"), render_tool.get("callable")
        properties = (solve_tool.get("spec") or {}).get("parameters", {}).get("properties", {})
        correlated = "client_request_id" in properties
        if self.valves.automatic_progress and not correlated:
            raise RuntimeError("PHYSNEMO_LIFECYCLE_SCHEMA_STALE: Refresh the PhysicsNeMo OpenAPI connection after installing v2.9.18.")
        poll = float(self.valves.progress_poll_seconds)
        status_timeout = float(self.valves.status_timeout_seconds)
        gallery_timeout = float(self.valves.gallery_timeout_seconds)
        automatic_progress = self.valves.automatic_progress
        automatic_display = self.valves.automatic_result_display
        emitter = __event_emitter__

        async def run_once(kwargs: dict) -> Any:
            request_id = uuid.uuid4().hex
            params = dict(kwargs)
            if correlated:
                params["client_request_id"] = request_id
            started = time.monotonic()
            async def status(description: str, done: bool = False) -> None:
                if automatic_progress:
                    await self._emit(emitter, {"type": "status", "data": {
                        "action": "physnemo", "description": description,
                        "done": done, "hidden": False, "request_id": request_id}})
            await status("PhysicsNeMo: zadání předávám nástroji; průběh se zobrazuje automaticky.")
            task = asyncio.create_task(original(**params))
            last_seq, last_emit, unavailable = -1, 0.0, False
            latest: dict = {}
            try:
                while True:
                    done, _ = await asyncio.wait({task}, timeout=poll)
                    if done:
                        break
                    now = time.monotonic()
                    if automatic_progress and correlated and callable(status_call):
                        try:
                            raw_status = await asyncio.wait_for(status_call(client_request_id=request_id), timeout=status_timeout)
                            current = self._job_result(raw_status)
                            if current and current.get("client_request_id") == request_id:
                                latest = current
                                seq = int(current.get("progress_seq") or 0)
                                if seq != last_seq or now - last_emit >= 10:
                                    description = "PhysicsNeMo: " + str(current.get("message") or "úloha běží")[:240]
                                    description += f" · uplynulo {int(now - started)} s"
                                    metrics = current.get("metrics") or {}
                                    for key in ("epoch", "step", "iteration", "loss", "residual"):
                                        v = metrics.get(key)
                                        if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v):
                                            description += f" · {key}={v:g}"
                                    await status(description)
                                    last_seq, last_emit = seq, now
                        except Exception:
                            # A failed status read is not a solver failure and must never resubmit solve.
                            if not unavailable:
                                await status("PhysicsNeMo: detail průběhu není dostupný; původní volání pokračuje. Nespouštím další úlohu.")
                                unavailable = True
                    elif automatic_progress and now - last_emit >= 10:
                        await status(f"PhysicsNeMo: čekám na výsledek původního volání · uplynulo {int(now - started)} s")
                        last_emit = now
                raw = await task
                data = self._job_result(raw)
                if not data:
                    data = {"state": "failed", "job_id": latest.get("job_id"), "error": "UNREADABLE_SOLVE_RESULT",
                            "message": "Nástroj nevrátil čitelný výsledek; úspěch není potvrzen."}
                lifecycle["executed"].append("physnemo__solve")
                gallery, gallery_error = "", ""
                if automatic_display:
                    if data.get("job_id") and data.get("artifacts") and callable(render_call):
                        await status("PhysicsNeMo: výsledek přijat; načítám galerii a skutečné soubory.")
                        try:
                            gallery = self._html_result(await asyncio.wait_for(render_call(job_id=data["job_id"]), timeout=gallery_timeout))
                            if not gallery:
                                gallery_error = "INVALID_GALLERY_RESPONSE"
                        except Exception as exc:
                            gallery_error = "GALLERY_" + type(exc).__name__
                    if not gallery:
                        gallery = self._fallback_html(data, gallery_error)
                    emitted = await self._emit(emitter, {"type": "embeds", "data": {"embeds": [gallery]}})
                    data["presentation"] = {"state": "emitted" if emitted else "unavailable",
                                            "gallery_error": gallery_error or None,
                                            "delivery_confirmed_by_browser": False}
                    if not emitted:
                        data["presentation"]["message"] = "UI event could not be delivered. Show the returned answer and download URLs in the chat."
                terminal = str(data.get("state") or data.get("status") or "unknown")
                labels = {"completed": "výsledek připraven", "incomplete": "běh skončil, chybí požadované výstupy",
                          "failed": "úloha selhala", "cancelled": "úloha zrušena", "configuration_required": "chybí konfigurace"}
                await status("PhysicsNeMo: " + labels.get(terminal, terminal) + f" · {int(time.monotonic() - started)} s", done=True)
                data["display_instruction"] = "Present the actual answer and delivery status. Do not rerun solve just to display its result. Progress and display were handled automatically."
                return self._return_context(data, raw)
            except asyncio.CancelledError:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task
                await status("PhysicsNeMo: sledování bylo zrušeno; zastavení vzdáleného výpočtu není tímto potvrzeno.", done=True)
                raise
            except Exception as exc:
                await status("PhysicsNeMo: volání selhalo (" + type(exc).__name__ + ").", done=True)
                raise
            finally:
                if not task.done():
                    task.cancel()
                    with contextlib.suppress(asyncio.CancelledError, Exception):
                        await task

        execution_lock = asyncio.Lock()

        async def wrapped(**kwargs):
            # An identical repeated call in this turn returns the previous result, not another expensive solve.
            # Store only a digest in metadata; no submitted text or credentials in cache keys.
            import hashlib
            clean = {k: v for k, v in kwargs.items() if k != "client_request_id"}
            key = hashlib.sha256(json.dumps(clean, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()
            async with execution_lock:
                cached = lifecycle["results"].get(key)
                if cached is not None:
                    return cached
                result = await run_once(clean)
                lifecycle["results"][key] = result
                return result
        # Do NOT copy __function__/__extra_params__ from Open WebUI's old wrapper. Doing so would let
        # get_updated_tool_function unwrap this lifecycle bridge on the actual execution path.
        wrapped._engineering_lifecycle_wrapped = True
        solve_tool["callable"] = wrapped
        return body

#!/usr/bin/env python3
"""
Engineering MCP Unified Bootstrapper

Detects supported engineering applications, installs suitable MCP adapters,
exposes stdio MCP servers through MCPO/OpenAPI, installs persistent background
startup, verifies OpenAPI schemas, resumes interrupted installations, and
removes the complete MCP environment on uninstall.

The proprietary engineering applications themselves are never uninstalled.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import csv
import getpass
import hashlib
import hmac
import mimetypes
import html as html_module
import json
import os
import platform
import plistlib
import re
import secrets
import shutil
import signal
import socket
import sqlite3
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
import types
import zlib
from xml.sax.saxutils import escape as xml_escape

BOOTSTRAPPER_VERSION = "2.9.18"
REQUIRED_PYTHON_VERSION = (3, 12)
REQUIRED_MCPO_VERSION = "0.0.20"
REQUIRED_MCPO_MCP_VERSION = "1.28.1"
WEKNORA_PACKAGE_VERSION = "1.1.1"
DEFAULT_STARTUP_TIMEOUT = 180.0
DEFAULT_ENDPOINT_RETRY_TIMEOUT = 30.0
DEFAULT_MCPO_PORT = 8200
MECHANICAL_STATIC_TOOLS_OPTION = "--static-tools"
MECHANICAL_REQUIRED_TOOL_GROUPS: Dict[str, Tuple[str, ...]] = {
    "status": ("check_mechanical_status",),
    "lifecycle": ("launch_mechanical", "connect_to_mechanical"),
    "scripting": ("run_python_script", "run_python_code"),
    "solver": ("solve_analysis",),
}
DEFAULT_WEKNORA_HEALTH_TIMEOUT = 120.0
WEKNORA_CATALOG_PAGE_SIZE = 1000
WEKNORA_DEFAULT_WEB_PORT = 8088
WEKNORA_DEFAULT_API_PORT = 18080
WEKNORA_PACKAGE = "tencent-weknora-mcp"
WEKNORA_PACKAGE_SPEC = f"{WEKNORA_PACKAGE}=={WEKNORA_PACKAGE_VERSION}"
WEKNORA_COMMAND = "weknora-mcp-server"
WEKNORA_KB_TOOL_PREFIX = "search_weknora_kb_"
WEKNORA_ALLOWED_SCHEMES = frozenset({"http", "https"})
WEKNORA_REQUIRED_TOOL_GROUPS: Dict[str, Tuple[str, ...]] = {
    "catalog": ("list_knowledge_bases",),
    "details": ("get_knowledge_base",),
    "search": ("hybrid_search",),
}
WEKNORA_RUNTIME_CAPABILITIES: Tuple[str, ...] = ("retrieve", "chat", "read_agents")
WEKNORA_DISCOVERY_CAPABILITIES: Tuple[str, ...] = (
    "retrieve",
    "chat",
    "read_agents",
    "system_tenants_read",
)

PHYSNEMO_ROUTE = "physnemo"
PHYSNEMO_LABEL = "PhysicsNeMo (NVIDIA NeMo Agent Toolkit)"
DEFAULT_PHYSNEMO_NAT_VERSION = "1.9.0"
DEFAULT_PHYSNEMO_VERSION = "2.2.2"
DEFAULT_PHYSNEMO_SOURCE_REF = "v2.2.2"
DEFAULT_PHYSNEMO_NAT_PORT = 9911
PHYSNEMO_MCP_TOOLS: Tuple[str, ...] = (
    "physnemo__environment_info",
    "physnemo__solve",
    "physnemo__job_status",
    "physnemo__list_artifacts",
    "physnemo__get_artifact",
)
# The MCP server exposes the five NAT tools above.  The shared OpenAPI gateway
# adds one response-aware HTML operation which Open WebUI can embed directly.
PHYSNEMO_OPENAPI_EXTRA_TOOLS: Tuple[str, ...] = (
    "physnemo__render_artifacts",
)
PHYSNEMO_EXPECTED_TOOLS: Tuple[str, ...] = PHYSNEMO_MCP_TOOLS
PHYSNEMO_OPENAPI_EXPECTED_TOOLS: Tuple[str, ...] = (
    *PHYSNEMO_MCP_TOOLS,
    *PHYSNEMO_OPENAPI_EXTRA_TOOLS,
)
PHYSNEMO_REQUIRED_TOOL_GROUPS: Dict[str, Tuple[str, ...]] = {
    "environment": ("physnemo__environment_info",),
    "general_agent": ("physnemo__solve",),
    "job_status": ("physnemo__job_status",),
    "artifacts": ("physnemo__list_artifacts", "physnemo__get_artifact"),
    "native_gallery": ("physnemo__render_artifacts",),
}
PHYSNEMO_LIFECYCLE_CONTRACT = "PHYSNEMO_OBSERVABLE_DELIVERY_V1"
PHYSNEMO_ARTIFACT_GALLERY_CONTRACT = "OPENWEBUI_INLINE_HTML_GALLERY_V1"
PHYSNEMO_OPENWEBUI_AGENT_BRIDGE_CONTRACT = "WINDOWS_LOOPBACK_REVERSE_PROXY_V1"
PHYSNEMO_OPENWEBUI_CHAT_PROTOCOL = "OPENAI_BUFFERED_JSON_AND_SSE_V1"
PHYSNEMO_OPENWEBUI_SCHEMA_SYNC_CONTRACT = "OPENWEBUI_TOOL_SERVER_LIVE_REFRESH_V1"
PHYSNEMO_OPENAPI_OPERATION_ID_CONTRACT = "OPENAPI_PATH_AND_OPERATION_ID_UNION_V1"
PHYSNEMO_OPENAPI_CANONICAL_ID_CONTRACT = "OPENAPI_CANONICAL_MCP_OPERATION_IDS_V1"
OPENWEBUI_NATIVE_DATABASE_SYNC_CONTRACT = "OPENWEBUI_NATIVE_SQLITE_LIVE_SYNC_V1"
OPENWEBUI_MANAGED_API_KEY_CONTRACT = "OPENWEBUI_MANAGED_API_KEY_V1"
OPENWEBUI_DLP_PREFLIGHT_CONTRACT = "OPENWEBUI_DLP_GLOBAL_FILTER_REPAIR_V1"
OPENWEBUI_PHYSNEMO_READINESS_CONTRACT = "OPENWEBUI_PHYSNEMO_TOOL_EXECUTION_READINESS_V1"
OPENWEBUI_ENGINEERING_TOOL_ROUTER_CONTRACT = "OPENWEBUI_GLOBAL_FILTER_TOOL_ID_INJECTION_V1"
OPENWEBUI_ENGINEERING_TOOL_ROUTER_ID = "engineering_mcp_tool_router"
OPENWEBUI_ENGINEERING_TOOL_ROUTER_FILTER_CONTRACT = "ENGINEERING_MCP_TOOL_ROUTER_FILTER_V1"
OPENWEBUI_ENGINEERING_TOOL_ROUTER_PROBE = "ENGINEERING_MCP_TOOL_ROUTER_PROBE_V1"
OPENWEBUI_ENGINEERING_TOOL_ROUTER_SOURCE = r'''"""
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
'''
# The proven WSL transport/runtime implementation is embedded so the public
# installer remains one self-contained file.  It is loaded only when PhysicsNeMo
# discovery, installation or service management is requested.
PHYSNEMO_COMPONENT_SOURCE_SHA256 = '0f39f381bf2fec3325e12c171d70e433fd2fb8b117e7d9e1657d08fd02a96ea6'
PHYSNEMO_MANAGED_ROOT_PROTOCOL = "ENGINEERING_MCP_PHYSNEMO_ROOT_V4_ARTIFACTS_ALLOWED"
PHYSNEMO_MANAGED_ARTIFACT_ROOT_CONTRACT = "MANAGED_ROOT_ARTIFACTS_DIRECTORY_V1"
PHYSNEMO_SOURCE_CHECKOUT_PROTOCOL = "ENGINEERING_MCP_PHYSNEMO_SOURCE_V2_SELF_MARKER_EXCLUDED"
PHYSNEMO_NAT_FUNCTION_CONTRACT = "NAT_1_9_GENERAL_AGENT_ARTIFACT_GALLERY_V2"
PHYSNEMO_NAT_DEPENDENCY_CONTRACT = "NAT_1_9_FUNCTION_REF_DEPENDENCY_V1"
PHYSNEMO_NAT_PUBLIC_FIELD_CONTRACT = "solve(request: SolveInput)"
PHYSNEMO_NAT_TOOL_FILTER_CONTRACT = "NAT_1_9_EXACT_TOOL_NAMES_REPEATED_V1"
PHYSNEMO_NAT_ENTRY_FUNCTION_CONTRACT = "NAT_1_9_GENERAL_AGENT_TOP_LEVEL_ENTRY_V1"
PHYSNEMO_FORBIDDEN_MARKER_SCOPE_CONTRACT = "EMBEDDED_PLUGIN_ONLY_V1"
PHYSNEMO_AGENT_OPTIONAL_INSTALL_CONTRACT = "NAT_AGENT_OPTIONAL_INSTALL_V1"
PHYSNEMO_COMPONENT_B85 = 'c-ri}+jiSlmMHqpuRxGf$7Di5l5^=q36m{Lw8M%lX-l$`l&nTWBqSlC2sS~=mKFWMu5q6G)Keb!L;b)Wqx;3lf1P<-H(-IJY^S^SI6I@tB7k*YbImpH^TQ8TXT@aoG#jm^qw8RNGrh=1pESZS?2U?PG8_iUXb=>$aXPuqiWHuLtjLGSG#v!{7dJ)LFLu+XdGK^=KgdSY^n8*`vwRda8b=pt@Iy8l<S&brA{(T^X`WAu=_DCLTfwYIiy$8jZ-Ob5+ox^==x{VhCWBy@olcU;O%w#!cw_TC9ZiFyJRe?W)3(zujt=_X3zA6+1E3+p&|oNeaFvXbb9ngSaOYugolT~*WY~aNW|Mq$1uYiPK8|vC^C&1_elV=82!?q+K27?UD>OQ6e>^)KX2k^zI0;}R=_DDtW1!)^%%&GG$JuBAUB1jGm&G{gr_?|)nPz86e;Q0-3NUT#305Lau9DMX8hm$jv=2ksghBLkDDI4)L9-iA@_t$r0epwb(*jm4nbM+9^4T<nhG`x5#_4EtzZab4lPmZRi#!NUZ|HUKLwfqG7vat}&L;U)5XWb;>1>k5agbe&^T`y3I?AWCeMO_8-c8QO$)rft^J!9~pMR>J`o*>Sd65(sux;w`=OQ1e-+7^ajRA0QZ0dQU+l8r5(y1;8ZKbcw!)%%j^;32}O3YK<zf7n4X?7|rrQh7>pVRbee3lJ$m(vT_fk8Gp*Dtaw{c$!K!fc{+GRY^Ucg}jqyGi=5v$W9Tn9Z^QuW~;Jc<j@fs%0KvS^heJbA-L>Px9QRvAoVlQf{0~adB0#eR$*#)0;6&K)v4_-L!+=6aW;!stwzY{lZ#N(N|Z)s7PMn|8Y6>aMGfmi~&vyED`flqw#2O@96O8U~_-Jdk{bG9vt@ec7sk3u161}^|i3Ezu7y8pKcy}-#x(B-Q6d>-EQ}wxBFxTpmJsZyPpnsyHEGN3Z!m_D}IHCZ3Pb`7K6`Ey1U(j&7Bo|y$KITAMfoSL3wz!v-9+0`rO-E**rMvJ>J|pI)u;N-5<J-p7mB9_jbA~j}Cg<Pr6}ayZd<a+0Ic6?YP7JGFmfV)v)X$4`E;rJw*=po*is;<Ad&FEOlKfhNHJzS&P=9himRQ_V*5s;M<p9uCMF&ID9yv>f09&t#5}%FwJNC@lo$-ckdZ~{$vf>ZT!&N-QN4*Fh1Hm{2m&9+J!HZusb@>Mrk_1{YONA7zxo)*f@a7T~#m~!~0Qs1@F5*?svD2y4&&5-rmk3d}}rW_)nLJV+%RP+2||}+vO5~`>)gL>!0(}7;x`&R#d+M?wrO71$w@pr{*(!Z8ZQq;=`?j-aafLEPwAuoJMM<yK>bZuc-PfMSqfwry<pX;s@RT{;YS{g9Y$HCvKeCV=f;*f5_E)+W>&Qqo0<ks>?oK=gLnvcL9L6;{!N3%QQgco_`u^(2h5EcJ_YgZifx0Df4}6Zx>GF76L|CQ)Ih$09(9wz{7G1sZYJ`;YKi>jfd$m+(GRiilP$(3(+;ez{)6@s(s=Yu;K<7hBMd-^#nK4S$3|TPR)m5ey%rrG8@_Z4i_hHT|S%iH8j~E(rVxVdi-p63z2~{bNsL#e;EtrhzV=xC5WHEDt2-Hu%}pby9*}{_G;@VZ!5YB05rQSE+4n7@KM~`g#)^?Q)#BA7`A|)51#Gffre^N_cxDvk9s=@HT#=e-$TWDTQN*V=lzQ$8?E&7N%{?7&`+ba_SX*q)2z`FHFoy4Hg^C;Z*LxLLOr||nt2h)DURS^HAA~h*rqbkMShhwTfr*q?lA8s!w`QK7eGRVtyTjH$KUM{@^CtUG8WDOSf*+Qy}-IW?ma;`gPOXLRShCAT;ErMlLoAk=NrOJ1C|p`Gh+MFS422zgp@|ukW~j@XUtJ5YGIEUU^&*<r=P<uI0AgPa?Ll?icokfMAb#(o3KH6_s6F@(55xV)j2q6niQ82T&FPjXK;Z&?;Y+P#QVK%H48OcoP?0p`6L==1Dx&NzNc7JO!F}=;nw%QMzD!~io1CkHuM!4_nzWC18{x#Jv3Vxe-3ov%k*@XtuQTMCNM~gOXyG*x7r{KgV5X3?ID>qk>;S%ZkJD8Z}&MI9>7;~+R}{x9F3TkayK2$u3V=I!l1tJ0xOdgN1}TEt_$nuE8f3If#7xuTU!SO-Qw1+0sQg>00$fp?sm2C%VG#)zXEn-z@;B=_7GC7dyYZhs&keAr8-!_s(iu08ENeAJcG+5-v4R;VDHae!a$P;4;~!DDh&rKK<WaCd(uE!G@Ago(g}_MG6262+wo23^H0N*2A4(lA_Z2X6Idl8`W9cM(*!y@21@#8SniX?C;<w!bOq~8!K<PHJV^oDViSk}K{Rf8{iK#}LI#P>T-G;?(&;1{oTtdg1iR0B+r3R<1OtZ=4E0P`m~F*=zUh1tt*^JghJQcBK>!pD(osL-<v4+9;Z!4Q(!ix%!bpnf44BoE#><OzlJe3``r(OL2SBUS$<4|*&yaI`0P~LcCM+JDG;I8$aSIeFEt~TVn1*v8jnYZjfKAl9+uQBo#=<LL)qF&rT0Uf3c?1!Zd@-^cIp{v=9UjpUMF_bM!&ltEa^*GrUJfk&tLZgxKs9{d#Z}T*zxfZcM+j2D+ax~j@CrB`U}MtaUhJaF5?0whhe@n(dRNFmDPC=q^>g6at>M{B<NM_a<@f81InjGFcRLw!cf*F%ycr~;DV!TA@(4ETDa>Wq4z}pd-Ol>ccJMe$hl6(TJQ-#K+U+jRpdDOc(fFEQ!<4vDgiJyNfUo7RZl52k<<4d!!pp=osM3$+We?t&D*a)m0Y64D$=NV}8R!j`52`^^5BDdg5f_oZwBt#7R_^W~J%e@Hc?y61wN=~Yinw~bY>mcS5}Z4|$K9=;wsyJ>k*G=jy+?;|qijBc@7vv--t(@|>B#vVJv)r?c83ZYT%&^>xHp@v#yb$Pf8Kipyb63lRFKlr0pv9&;qm6mUy_yAYb#%#n4fX9a&r4m?JqyO3tJ7OGl-46SM9a-`e$Ea^{1OZ0y5iwc0>dV@|&MLv|c{?>4;uF{Ot4KqhNjQ;ivM4${Yf}1iiaOKmXKIQZqluYJcv$TF^&tcL!KAplM)7b<y>Qo{~p<N4W9jX02jQ>F$p}_IHn-9RTO@-R1!|yB4pltx0QpJ2CL+I5qYCA%3M2jTpBKw;7t*uu*Qb#lN2?lj8xLY-Sn&FPsFw1iNq`ka_Tz7nZ_%6(R2~wSYkwq-V)&IPGA2$Ya1AdKSc^{3S39E8n1Cb%WZPzzsSX;d2vlWQ6}TTe<>b_$Hv1S-OEEq`EL%r!JO>2D7Vi!6n;4Ix6sjN{W7#bsi_f0^VhKfloUR&CsA7-47tHtE|u6AtK!%{MinqYj>Gw6gV*+29`(6jdcFi<sh3h`Jw0>O=vW)P;!x9(qoINpbRlb(KM_yRY$3Bj095iER1gH6+YcXw}|f}{O8kVE4oNu-9^)@aad|5dN~1%9^=|Ktu<=}9|v%whqxkeIl*>y!rAm}<qN3~OdgP`!=#@!byIB`kY1P~IZJt9vJ|umAGL!spo)?Fqc?~}@Foh~4HAlv7)p4_O$0!Ug}@-v1c4s`>aN+civxmyn;4P9KRYPlW0*%6!#`NAB{jn+mdRvi0gxf|k$bnARD)Fohv}$Etpwi$>z}Wg@<{rs5vy*}tK$tgcPFOM?CdOiRVqgBjyLRbs`Ky`8@apXGIyapTpKyUl`<RxP0^P|&9Ej3Dovi_^3kOWQ1WbqTNB`_)0Bf-THOyOcd{OGI`E^jnRrgKfwi6Pp79=ag7SVjJ0*kHmx48N2D~{#4|^k`6#^cJJ6fu(hKq+HbI;=>&!_yGMtusTH+Kazwds@24-oVyWQ0>QNr3>&uHk&-O>Dq?YMEhj|9C{{UHYn@j;BF$?@*{5GXr~aT#HbQv&gzj9Ex*vN;AM8g3XebbCz8n)bPa%JO`^T)MI6+0DqtYus;Q^T@y=DJ1<_Xt%ZOBvB12o*@VVMD}V~7H-VZ0ttM);giTUA)(4IYDLy)~xT-$`OGDHB=ok>-l(;VX!Tm<Xc$iIjOfYKtf<uR|%@C&)g{>1ksbqB1q#_+aEm0IYt<kxICR>Phrv=Rsn^F*?hsMi27aFlGfSv?-Phc!zp4bxLi~MC;0#4nm+G?b)%6A6ss(W8}AXJ?)y1RyXGANn?w9q1<@e0PSz$&)^Yn2rwr5N>7bpc}ktpKRhG`PL<!!z~#=fl0-?G*Wz8pwv)3al>@Ab-je)o5do0q=`^sxWeql;=^CQj;c#@|b2gIRzj{3Mf1p3@vp1@&eEq9YXUC|2svA6g7_JX_cB5xzutB%aNcuZZp&rRK9fH^3bE%7`L`b)tqgY?{N3>ucp2nk>{*k5vi^D(&!x6xFW{iO?|<)j@M4;geGG+9erY}R`dQeovyHEH`MD7tY{1@VG~(t{2};+HJ<XoC{-TJ)u8U|LH=@tz_vk%(;aU5YAn(oq0&AM{t1?s*7)-^`iIJ0!6cG%x!1VAyVYCO7yOil?!t&b7%-Miau7$2;se}GVDh6;`m)J$D3@=mzS<?AYB_tM5I)i%t07^brp-=A|2oU3DIpVBEkMp4K&uWqY4SA8ipg06zMCjCr!{zxacUsC4Q0;ZhFV5IXL_daR{w_gY7^k~I>M@Y=Ht4?$JGHqSZKBB(S+}V2dfWSu+}*5yKir4pm!Qna60&<XevQiY;GL~NJ_{GzYDg)3NUr2fne1oA^49o)LXqMA=ZF7;-9v83s=N!TF84Au+j^wh&Fn#N||?7L8Iw01<MLTDkv&NQ;J`(fYvH^m5j18fGVq`dQ~YaVi~Kbys4BV`DC1oikIoc9x1+F;n&gCKx$}w+n-I4iBK$6v-Vz5SBcH<k<P{;5Nhs-^38ZK8zBcKcjM6oT!$#$#A`9RPO>2xnvg{cqw11Im&k<KXax7x9J)?T4dDk@qgkeexQ=EUs%vo^s=DDxt7Yi9au2K-eCtlE>i&Mnq^Hkn>)F*6uun|}tuo8l4iq4jzX;C_8;E~ucNw|{o)t=2Crk)vJjn#kq^MI=bqV~_QZasKmjV=w=2*ZAmx@{+?DBkHddgcL?DB%lONG^2yCg|QOXc`oOC1vY7g6|Sdcy={f0(f#kIo>jK$|8GO~a4zBtM_v?OUY(YCq#|xSl6jpMIvV(*BGDkg}Wja*z&z3g+Lu3-M((qW1A<*hT3X+Mee9e26dj=p&#}Pb4U{%3o_yYAo|J=Mm1WOim!mp;>q!$57&gm<B9CPwLETaBGyRgfEi`p3fr0ni{>)BI{2?Q6HaF>gwyDp97+x7Lb*8TQMkDnrYRx;~PY!x_w-^0e$>r8=JJzLgxrXDXQnAJ`jySDj4~Zk=%q~xQ{9)AYAz*2SA>(<sq;F=`{**2-~%TQHs`ftZIVu04N@1>dbO6icBWwGd2fA+c@Ho7?Ui-%~GyReA|=_p(!cnAiwf$X2@+@8f*(Vuq+PAWnNk~;CT=Q0^)6mg4<yVhZ~_c8>vTpVof9d>f<eg=9A%F8EEyiXejBw!Z=X!XZPnERf2#uq(#?tHQE+LgdvvLz-I8IAr@lFRUdr9AV@x1xJQ27l@>%%{{k$nn$Of;M_QGpI+{u~h_9nYV$Y@n|1URuY)}!NgyWCAYoQNPn`eJ=yz<4`hB=-U@nu_@Zy8RtpHBv{MsQ6&NDCyJ{|A8Q12AK97z?hVvvbv(gtqYZu2rrL$Z(3nSHXpJ9Qcc%L-o~n7Vsh><@>DPPtyU67-!FW%hh?v$ge;HoldaEY=)X`Wi;5LZyfmEHv&D2VN&4rt9v^kNv?k&25>b7w^r;d8=;vrZN;PC{&pc|-80~nF7wfEe@#bU1@L1!$%nI_v*7y8zZWo-^fE#@cX{1A^4CcE`AS9#uTHN3`1|`b9g`_E0ND`uLc9-{RBsc+i>3J_9Z#B@y{C);Xnl~DBuY+S16~OYGG7~BiB4J2Dq^0(I+s?Jd3}^9e1~4jXH($2h(=+?q)i4^Q&=3LWLS$M1dmOZxU>l`VMWNIuts^Yi9~5tibH!Y{-_>0DsZ34qq%5xg;5*AA_5vBE=h(W|I8An@uv-U_*kmda(Ej1Gk`c8)QRfcT1tWi4ShmPA{!Nxtx!`a){P)MMBbt|;%%v87uxE?c~Q5Yb3oKjb}O%F!mn_)bu?ESuNhp0S8{Cgp<s^C8hc3QHd3U>ULyisLuHC+KTwE*J>I@L4)J$*67`cJJ<ErKX3GphhQ^mMYe%>m-4?HuR>f4HcDXn%=Lr21hO}QEO@;#~yy<;vs*g=s_8Jkl1Jh`RyN|!$hRI-)){tB3rn76o<#C!J8QAO#VDteA7CZyP&5Va62e}QSF>u8w=l*%D{-*rnWqLZMALrQ_{VlHf!+3BO-dUW{`6M}eUu|VqOcC9?F}socbdtPIFW<G9>#UgJ1`z4}wiCRVUJ=t3U5!62wf>r0@2Bs*Z8r7eX0PbVil&S@X~CVkgS`LBsr-68Nv@N(tlTfIxhDR&gCaye(Hr`Ouh^hXCVk^nhx31BEw`F5&QDh2$_$`VQLW@s)%d_(Wd$JVb0CvPg!$3|nbNfthleLKeKk(|Q*yitlsHYjGq(Tccn_1)bO_A|B2Y!u73$E0HJVmcr$s1@5RZN(_@{FD>3%GvCaNsLP}Pe}CLf{K+Gt>UFkH<L)zUN_XhjgohEK22)QIx`R^^VV;z{dm`(0{jP%WP(6L>!fkK>gSqPC=f+wq6N)1-fqjnWk)(Me=z-5o)1yC63^lxfp)wFR{*umGa4NTYi!I^P!~R@M_Bjm&NFR*O=Uh#EaOe<dQi>%f&(kCe20-I<n40||fs_cy-|MsNN-7y(`R=GWKs8|mBWY#dzQOt16b|1HILM0vneo5>6~KRCwyOL)t;C`f|8^!9-*##Zv*{`%(c)8ywje+PP0j7E~;(i|BzY<$b#85b)_8l6(q7B%hte{tIUc0-W%aq;>j{RMBiUlgL9{ruwPN55R(Tmtzx%<%VXx+vh+i{fLbiuV|NN4otN`tl27l@^p}y*R}S7{_C1;PRN%lG=yit#8FS2&`4VS^N3#|B(#x>tyui*TA}BVA)S^hKbp)B=|YG%$+?g^4V!VQ9ELomc@%+WLGnEoBd@vNwU!|#W?Q+Y5FrPCj6RaztH#D&+s`N!JlG012VY0q5z}AWQ4|=H?<v68R&rxuus!pF7lVSW!LF+nEf)&$64{qD7l_oj56Pj`R1fH&F)^kb9i3E&MvY3Z+;!+0nGFFU#GwQZS>~vcwi9jr?YmD3}ril*U4){2e4P8;LZOk#=rgT_g`@*PAvvA3hQ)PN`h{S3`ok#V-lWPYe;PEk3;d3)O3Snrh*JmS|zRE2Vh#7NW@2Iath2+(UgxZNA#|+QOwweZLgue{$NYf^-koc<erQg1KRVtHMhI6MASt;AJZZ{Ce06=?G*T}Rbw$ieKWcf{y2S=p>${<PTF7bR`*d<pPglW_%wlan2vydjw}TjU2DN1%H^kIh}_gB$pR28N@tHC^!d<c%7B>RWOPEf1Wri_0Hi=n<UsuL0!|7k5ycWub<{QPifCj^ELhX(UHTjVkCzR3?VwLGhi-~>q2;E~345dda5k|0$i+E8nkW#^^ejoobVz5fu4mHkDnmQ&H;N))60=bZuyj7X=&U2l_)0&0zQ&*o_iVDE%)O687>!m$h{hv9aHiitVbWhA8c~2l6?nm+aTW#?8z>yo19`aC4$f2Tf0%Z@SSwHL04RXEX*otx_nF>jYcf5ub&7{TYPf@1x5lJRVq1D5SfM<PPwjcEQ*kwuAC&TW2ae}kOeTy%|L_6!XOjXd8K5FdGBr+g70D_iU0Y(L|GO;vr_N*^`X}=P8n@QX=0gEALNh2PL*9HN803s=@Z>|&WCy>BcjgfBwLt}>!b!<|HXuWhB6=SPhW4@bo|apLNxr(KbZNaYI0VhA1X@){nT;4(*DWw3w)owrp%r9&&!L>^M7JSE*)dYgKo@kdgwxC?4~2ZquF`xqjXB6g37kH0!0D6E37oLje=9kuH1W9;CTHk3)zShb`JTpltj!`Fo{?NBtXZ<q(b=NiB3|#>j<ZEJ#;`B0A*T6G{E7%4;XQO0>E26>Rn>a23yhXt*x(9?z2Gzr68M?JPwKXRkxXDw(+S_q2uukwM|rUOY$vQ(72*Iil+Xn6y7$0^HZ8mFoupkdW3;zYrbxyPf*aH0!ncMXaT_%6oeS6mDj}1uAR9!%fpTX=seUdYEdt=5E|3`MQzRNH%szvP9N{4=bGz~&X>9hGKGg?M3ndrVaZj$C_LyDfmTTh6HPgm@;2qi#8yO4E^`={p&4oyaOb}Yx!!|=MER_7h`O8mtMkkJ<Zg$nw3JyfrG*9<LaM!KigHEu%;5<}V{jmEAV1IanGY#^yz%y<dGKu_AH0%sjAE;u6=9#v>%)mz7*)igL&*7<<t1NK_P?ZYXH|k8ne?CrD&d_P<_LGNq|5sRZ42~wrs1S$C3FB{cR|7_@K!Zf&$dvd1=)4;Y@uQ;u$my{{F?|)}SJ_ll2f*tFSf_B039^9qK?z@2U{7{{v@7a<&~SK<TcYGFrrF)H1o02Mf!4o}E9jForq4c&KedUPKj){1q$jR}49hyR=GdFn{K7>7pSSJ-TMIzy{&*xCFjtpOEL`GF*S#v42So%ShNP%vGA}FBSa=y8;wim>?RJhlH%^DUVk0*H1jFE$*`+#IukMa&_(?k56i|G>9Wa?CHd=3eL1!bR)MLKEgnA^$7&U$sBd9k*;7Nu|9XG2Uu<WbVF;RLlsi6cr+TO}Asg~4*%`aIl<=FFzT_%wAUc+IE73BX?Ux%pWno6@#EL<^v=R3?Y52baktPfoQ%P$TGMUs_a<udP~<&*51i&`a_RhdoFfrpt?A1zx$?YCDArLeQ}R9(lW)zCj>`(=7&-jyuRE3X|d2KSTY(NLlnnKaYYaP*<Sh}8y{DsRm`+50WOH*6m`2W-P?&?~mkRq?EXupGfE2%VT!C;w$D%n(GVzO=CX#c68Js;46qa}H`)PPOz0Fy7@Cp3KCQ)Xy^Qq@Y-H!dmE9AOzCnzLpGbj5`glsCMZBM$cY&_LN}hnKCROlEHG3xJt$pSi#Zui)d{F=w#EL3UDL=t0>@+6g+VxwIYnG*4Cfw@+7dUmZjHrIjserH>P&5OqVDReA{*^U+jV2*^>8TG8$wT9rQgMskJ`F9XVn5!RbXrp4COOb)t8bt_sD{Xw#aCjI|w9cDvSoMtK1#O&L8~N=VB*U(uCrGbbD}Ms#Z#Yj@b0O56-%+xCSt^`w$wi-1YN76CVjSOVP0Um)H22RodI@qn?7$5V@IHy_s9dSbY?C37*g{Mb}9IUnYy&F~|SH5e;2XbD=uH)gFYsWB2@YWh%u;}|UCo+oN=+VHF(4xvewcIr(53zCg4t(Ux<5w7jTXo<^<UF{sXzicEPz}i()2K{lzGJCWId&-C3b~CmXxD_QuJkE>kRnxV6Lqr#orX5;fC?m56Zlw%iniC&o<8fMMVJutyk}o{>;4#s&-BC+*c@g2>YNAR#Mgy<lo1hfY!e6^~8B3;t3%p(10TC%hCltTuuxd3ZF0JCx>K{(+P{>GNc6Evdok;EC(x>nO@AZ@{%Gh6-WY%cOz22%_F1>eH*xI-H6;hk1l$mGYEf3~yBe=y@jyFDATRXY)%(`^yR7=D>eNx|J{n;{5h}NqLx*An8OghGD#J3^tAiA>&yrNnOTcPVqHFM`!;4Fb9N^ZY;z)B?>(ppou7B)sJRw!z{#z$?wN}hlGt4+3Mc%I>%{JL}8x&3#C)~DR(<`C0&Uqk>kPUo%Dwqszw1oA6;@}b~lH=jPnNYcz7d;8Sg_|N>Ob!XngeX|;dWT<#F(*es`KMkH{kBIt$^Kq3;1*Yj>y%i#G4yMsZSy!~tPX#N2w1Kf_%d!sle9Uz=r0&NKFj9$=8e0H?`(;tS>xU=9vLMyGv?;;SK$TPDqr)zfup6D`(`3ja7Rv(q?RfTyG4h6G{!BqhxMhrt^9qgn74o^`Xbbe-haL4WS|y)VmjO3tsH#A1o6zP94iQl?9V-&LWozX?vJ*&xEi&$L@^t&oxg)wqQJE^r1igf#hmn5hrF!w6&LZ-Y(;OL`64~WWT~x<BQyv1;q(QONQz?(<lcYA8r@G!KV{K`xg0)p2jrwawp%(x8c<<<Wgq7JRA6X^iQJ0j{&23dVP`<*dB`{h8o*P)!l*GcJJt2kwaj3~0yB~At(K>#^i(ajk1hG?7uENVON0qn$x1r1z;|}mIblsQ$Q=RY)x5VCg4ljk*s2*PH4qW!|-v0*lpTqyM`|pe8??1gx)hqA|x&n#vt=xm}Mh~l7v_i1{<J^nh6Z`+qTaiS}o|9z^T>f*9mLo*5%#^vhF(L6BtuED4!N|xWFd34FjpN<Hy>sgw$6Yw5`=*ztuVR3?5uIpgD40`$t0<ro1_hlBlS#mF>fSbTp9xKcm7I}ENEs40j_kGztYxB^;VXML=1vAd1LrcmnB=qbi$J<7{DG?e$hd-PH|5;CO-#Y}i#SeirgXYJnA=7#6fy{%!>tHb^+(jGdVDvaWB9|7be7-)StY;Vu=>obOb-%9OJ6Y^4q8+Vk7EZZu`W;recX!;eRE@@Nj@cx9B!;3fDnQk15*@DOiQJRbX>{3w9Px`e9P;S)b0Ze{5HM`=MB)eXgo~OM&DQm9~u*Lpb_25uz-QJaH1%q`08Zma#KWXJI!fu!j(sC?I(-aY6l-3*O_q{IfPhpoty|!ehqC~$rbwf_(l`#*DB6H!%wt^`#&9hx3~N3=<yeLZLOE+P5Ip0>+WvtZTEJcU?HI&d<D1nc8`8I=pA)25G~Z``WsbYhcN^IrU0SqccS61RagFpy@T%$_cyn?Qo+DnT@4)>ce{5`>cx%iWVK+&%Yqd=R%^8T=-K1P-GlBn8#1qlh9V+rhoa41<p8SrDC;*{3j-do|Go-+*eAa;DKBwy=xt098Wee!pT}}ho3pzbSl;d{A<!6QT#WHXPcU{X#rfx^s;=_v>vA~G(e>fY->;O>{dF*&B>nt)gzu68)Oqvk@BfwsZ~oUXzqm0@4!!^osDQXLAsE#7C2ZeI3ERic<8-jCpqrDtkFjWU5cO!EYRQpm2mP0Wj@nMVJ+3?Oe>_nGXs=_n*`6!K<ZT4hGwE1;9Ug7(Jv(ZPY4Rw285i&x&7d%q2}NQ>gn~O`*hPeaK@2@R%5t;ALxL3d3&lC$V~T2=XsuBzQI`-|Fv4h@4~GCk6)%3{ah8k=FI)npE<jsVS6G82yBUE?GV`RLglZ9Zt8!#}?y7f-Lo69N`CRr*_i!?FbAAzYRrIX<grw^gXJJu6<ZtN1U=O2@5!Idbfl?W!7{KWUmsTa%8$^_k4<qyFbB3Ud3wcu@dN!9<<n2XbLitXI<xeAHS8GJE-Dc<;$nQ~SaOc;7)ahR84xWmaiLONRW&BtoD$?|_2@G2kZO~LpCEj)=_+tIbhppD!*3espIKyiRx=D4SL23tTTt-*pjX{x)bF}M07BD66JeEIYtj!$e9G?piRW_IzlcBo*MEk%2q%jExkjCW9h8Pz61YS0LQG9f~(K&%X&Et<(PQGn^yYXUx9*Hla7lV&l-~NJsKW@Q`<FtE1MezCC7CE?OL)4Z=z4?nq(YI(U8w(K`5DXYebC|>4NTuVI^^?}ZirfjZL>Mk*N?|Wri~F;HTLlk;ir#9=sMnZ@Dhlt%x*JPp>3s7mnp^+&x8MKc&ELNYe*0^B`Q}&5vk?58UgSY>Ih&@x{Z+ZZ>JTq7{EqzfFO`d><v@CIU<56v<K|kl{+Vft0=^7yDthjvaQQsVYUwVjUsWi0nGJ{I^CtI67S@!FBs%OpIqDuf^-sL&y6o%~wgrdm3g$OWoBk%K(90y_i2Qgre^RS_HSvV4yZDH!btx3;pav@E;=uc?)Z*3pzPGbef1>8Em|hTUzh=SS`J_}={IgbL(Oqz6S?41{@6@4s1J%yOAh&=wlZ16GFkOa7if;ga`6aIeUldC#Fw_RGgn6T59vEr`?RXX8Ap-N}`om8thLA2quh&0WbD~Pt+}8C3S3CH`Za_jNZOD>TzQnfVUF65!)v{{hmO0!jN-Nbi+QJacZTV#(dg@SL|8_!|ZJ1@VEw1V!!?o(8E~<dV6ph*hq8_9ubrY*dEf3L&J}7$fz!OcGeqcM6To8*!1>A;!091^J@M1b8Dgpl%;hm8TQt44T9p?Rc!U7^3lhYy}Vya_oWn*;}TcHN=H~An0&klAtKm~ez<Om2FdWkkRb5O+c0sn21E6D|%k`zGyHhfm3lNHJ}hK#kF^l-(pRa{+<9)@=+J~kcYHFNw+eZeE)0eNmKcZAOR!!^PSuvz1LBu>d{M@kIbedDgHHs5pPb(-wQ97EKKyKegjnPXH<<>N6@@g$p&Ep-$!pR-ZI81{!GLbgIi{U@>JS!Q323Qw4|d?H-;A{OJ=PHt`Sm?)hTeqFL|c3#?1-W%@0Qj4x@Ydy77bzY!nR~%FFo?AhOp+2PzuNZ|#f%sgow^zw~3dWI)q;7_hUtk;H{JOod(-pTzd!xMOCk+13f;Aw_N)B{u6qYoi9Fl#2jvgfp!_nVSlq4I`GEv}{JJsg?3~$XUyOG!la}X>QtG8w_ca|{C;DsMoEL=c&t{+je7?;7`vpd_j>i-~y_lp=DFE_*y6|L=iMiLY?Hs)~m&4n&+ZLOekq!46&{x;~sX9TjLM55<tvp?TVgcPb8{$@x>aj2`HNVOGep##HOno<>C(P&DodAoL%k}%0iI)#;q4=@R*I%k|SAikvzY#T{2XQc3cW`r(eL4$371}FMbN$FHE*>wk~k~^u<=p;{ORAwkqG8k~<w!@}6ilVbCj#W;ClVFw8H+c%*Q*EijWa4s?gxhkrbr;C)!_xlgnss_V*Haip?i54R4Kzlrlx~UIk$5>ojP4+oQJ;SroqqnQFdm+k+uEJKv=A20)}=qV_<;Q2-4dANOee6C2{5c{6mm-nR!lL1StFrMpRqhnqxCNM>r5yctIK;Muj*ElN|gs!v#C61-?k#<QM;Ee)1b;bH&I=WP%fMknQcDt<sSVB_grxTZ#e^LTd1||V$>S<Z+F0z=EE|hZZCWdug>@uu0ZE4GP(4DA*U8(s@L5SRbw!vQP{wOc`XrIP$OCf6uusowWy<DuN#E5+O_s}g1~`N;-gY;HRtN`>vj4z82QT6-e7z5V=3c0p0|z~t)1<NU3PNPIZ2o5voqD22UIT=lO9Uk-UeAhiKDQXPC6wvER*y)OJ5S<-|?i0Qe#l#WCuHw3(5{vV;|DDYs?_ps-1@yHbOHwiq5YdYzvNB3(6(UJQ()OI+2`7KRFI{X8z%ZvmCxsSIOiO9|)w6w^be|hU$~%tzG}FWxEz<MXbW_nkhS(`{?s(ST<B4!8FX=xREv&5{fo_YLn^`-RKaE<e5fM!EFlC2f8N4rKVl1)E;h;Wl0s1&oDV;n#Uvo@*e%-6yvMkDJwENVu`nzrsQ4XSeZ52_b*uaex(FIx*LlilEh8I1<uQ~D#wA0P#kKX_Nb1;R=HTbeqOfGc0nSlrdelg2Hr+ixid_zP6vs~WXmDuDfOxq-g?7luFclX$|`Vy5w{wy@o3uRppPOy)&|s2l8FSZt=$N0!?b{mAtmI#6+E$!CWfRu)U#cUT>5`W143;=EJ<k1!HdF0=IQe@w;J5NXn_td(MbyJs3?=Gnv$K;)vQa2bgK+XD2sXGf0t`^vrsQPRy{~G4pnr+y#~4zVdG1bJ%5Oy3aBCNFnI$bUJssRkG_KQca>1Ec3R#dfU}zh1<$H9WLF&F99-2~CE*CWwpk^~+}_D6zU=rZNGOwGXf58qs2L!m@)^n>N;vK;bdqwbERE6YY;2`hfhQbk^p|W*5x%&ob`ZV{QIdCs0Y1rqMi=bu$J^b<JDW${Z4wrtJGEnwV521$;Wa!Srl{KEPOJQmG%bRav3TS6DK<cfIx?}tr;{XB{C~5Qj?a^CkMnh{aGED7W`bk7Z%ap+dNMa2C$fQcHzTOVu7)oL`z)F-6*m($?P?VXuUpxs<Ll1cqwNJ{Zb_u54tG@nQ4A|B0H=?a%|0NrsSyMNFy0=B@G*AO)B$9f!E8imTB6(<N}!y&qI&Pu02tSy<Rc!M-4L#2lD1W9;h0ljkntdoRlELBoFZ8V(mzU`H^~KH7t>S-I|<n-G|C<7b>>GEHj~qIxGGc9jG?>hdfSr?P-a+@*-tW4RkLXNqZ8L;+vLx7upE^-ZbQS3qh>5;sDg8&vu#@05gpz^y#(U-zrk(;8I;0yOURHWYYm8U?)U=|wHirrGwM@>DqUYiAd>nUHNlJkKxWx+fF$rE{-L7)57nn~ycR3X6|@jJ4xv`+NM%09rF1A6%CX{xJTg#iCgPNs6XK$p3&pj`dEhkkpdCEepX3+AbnxcaYc#`oJ(%P_162}?fB&~Pf4>}}XNRS;j2^T+sj&jy-~??Mc+6QIP4jqqLHYqVK8KDx;rczBc5g6fl@5M{p_wTxc6>H!dPFbMxXawLq?pf3ry2&NEDkfV^SBhDHvmHv1vt@V)C^Q`6GC)@yidm7yq$=v5)MNH^azH=i!2tf9C>Uhu%O^obAZBi+$(vmFAEUZ2!g|J|6@8cP%y|Zd2ape-NC?ew13|~fK4w10prP74**yO=6#AbBCz=r%nQgO-DD0#1Vo4sOc0^@_FG;GX6D=V<=w3p?!DU-ZvXct!y0ERxKRe=Z?)xa2iC58vH`!v?w6Xc2LO*NdOZwa8Q~YiXG8`YWPr^nWULJWC_bfopegcA%g<)DZSkzF_W>5Q$Y6O#-g|(BgB7kZA;}G9R>+O7fdZ3vg%3Kxe;j-)KoA~p=Y=?eQ^}#0MSHGKb3eE!5NSiNm?QuhQkFCa0yFOeG&q#ueArm*i+T^}pvDk9{*sKd0&zweEErfMm(9C^2zB=d!U(s&1dv#cyR}f_2};Z&uD1f5DA=D(wMU-g%0M*83~kN;%TRV=61^2AiyM|<du3@~qabQU$)CQ7O5u**1I{vmG#6m5<=rqBf~ht>CnERvf6FlI8r^GF(ioKj=3SAO9`_%K!b~U2ATrl!^*(UgrIkZSbv!|}r#GIHX*#NSg4W)a<Z?+?U7D~GE2YQ>rRc>YU0x+O2-{Xp72AMv|K=!1a$WMQFgZ?spq$ykkt4$qv&F~vgK>}b+*$Z+q)kNw#b4SnLT}5*;*Ju)d>HJiL!SeOprUo_<P~TyuINg#hE`7CNpO&EqNo$`2bsA|qQ>s#QSW(|t&P!f@nCc7h~m2{?@GJCcJFY1^Jwe4`1xmHgWeqOcef6;n4!#w22D>4Ma3l5lfy+6JSz}>iVF-wKIB-b0eT>O6}(O-x%S%0V9(fIL#&NCDO`ey+|DKmobOqGiY9`XxETIMN;T&4Mrxc^tP*ugQzl=HX9??)l!kW~hJSif;v^YVIWSu~;P@D(-!g$7G<{)?n1;l|u=VWVpu2mdG5JQ|p%MvjE$F1>a}2~g526Q>x3=IL!80PY7{1soi>a3KNNr+8#>|2}<3;BggAgIsAnY&~atBhZZXSvl@8BRz!(WSU`1s}<GAA`x6^{HH0WUN%onlP-KOgSx2KnjFaJTX1mE7rd>;fIzA_}(ourZ>bV}_}!6biFbKYLf&y3y?QE=3A3sC2|SPs&2$ohIW)<u}d%VX!3jfOU;NEi1G)J9=mHxv{n;I80z`6)gbMGT!IM54^6|4^A*$MluL2M+_W>sPaxz0KXJ-Pi9v{zs|_QmsaPl6782!99h9HAM|&`n?_<)C4C<buOuAy&d$?=^sGKwGKQ+bftQoRJfy(<4=FCc9gdxccmzmzf09r0em-QxZe#hDP7S_E=EKlQDaB>Veo(l5=z;?D$90C+qB4;+IVJ#^U~qy2(<g*FBC*VwuWt;9GS_NTMasR^A*z&Mlycdt-y0qSjA}IYI7U4<n{tE}O@KBK=E*juNG4DibIPDm4UIVBOaVwJ$sClF`R<ORZBp}1{^n#%YavvcO9&O%S9VliydK%DzG+>mv?7><!WiF-F94+E_eX6y%%$81)!16b7!X~0aWOqrXfupe8|)f6ljzX^ih$)v$T$%lkzrv_+C2CQ*dA1r>f_uN41-{iz*1pCLzO4q3O=9+MtP+IMBoyT53()EXEheOC8^P14mVs0v~$6~r3r_!Xz&@nUZ4%R*v!a>hz;0*N=0*sL3WN-@U7#G_0Lc4452@;R7Eth<B*O(Os-rf6dhrZntYJX5?5+EpQ*O{%8q%YgzUI9$Dtys!;==7iBPz8*7_M`XMA|HdGzcs-r3vwe#5qHgR;2bB$3q03CsG8QzW9z9_Id%#wpwbL8W{TIXXm$*)*=kq#{{Ezh<3Nk)M%v;Rh=)D!L})o{G~M9#Gv(sSWGFZcY8Vqk++uJIZP3p=1QjqgEckfCijgkno!3vxZhJ>*cjL4#~NefDUVGu(P{#!J}Hc4pQ`nHRo<}RdL%AM~1{_g5&dSs95h~JJDcvH7=UeGPY9yr5PthKg(DxDONtt>e?{Dc|u$4uck7E(q>tSL(SGX4tk|T#lm#BpnB{=9ogLTZ(XpWX=_W}mM=+A8S<XzL-N6X^DE%M{O1Y)?#c($2jrvQ{+f<lNYvkpba;^r!@FYwM-!deatf!Z;Kjp83f*h0kzv?1i(i6bz-R@{TLhK6R;YkX6sr-2^=Mf7zIc!U{R6y(x>vEcrcQ~{wzJW}wdx7$>s~IkCUAhgpNp9}&}nBtZc;HIBKxUC;usEzSVuGl{2@Yt(Grz7Wu)R%P?^xASx~|hx<sQ1+}+pdc#@uFubST5yro<r9MdL$NnXI&=yHUnj0#_yPR0My+|LG1?VDM*px3P(Xvk_UUqv5{K4ltuw)_3=-VeLPwN}&h+=lrjfSn{^weKH*MW-qnc5wCx`b12rkZ6NoWU=A2Y7#}?OL^4K&v94~E3vE~i3I>d(;@;8LcHmW>PXR$mVfi$$+M@xnH|Qvdq?r!qd#}Ij%-tHBCRl4kKU_eJ?xX?wG(Ukl+T+(yeWSPGgQ;K4#d>)$+PTf>n<JOlk*iCi$d$fX>-GSt%+t{4)>lNY<1&jyPMB9dpnztcDkW|M00iQ5|3j>=2Y*Z!FHV^meJ%c)%9Yn>Aa3>^@&UMU8}xx1Jo_-`)%f3s~Wmz-({@`2e_HQ#eKgxn$>Qt^NztGRj@s7yzPYQ1J22|2GLO?r);!l;?cF8cxSCTm!R6ip`)+G6yhyD+}hhmC!^<^JH73&GWIIV!4wVP$WvrW@m3C7^$tE9o2kdrSzdjrT42}#mZ-3Vg@r1wQrbwg!3X?XOb5V)s5pSWFj4-9-yhifyGqEKI>oSo%wstrE3tfap2zMSPyF#a7NMepy+^pl2fh8H_-XI(DGFCht9%bYFDtlwkY09#dQY1uJeD`QWNC?g8#Onc<<c9b@1OekICHJK>jNpbmIH#;KLQkZl}WYOhb{YQzpaoeG+$4iorR=Li4NnaigEYH?$)!T9{hR?H*I&@6Y6Uj(yXpEow6eoPlftWfHpZt!b(IeA_kTKEr@66wTgO*l*c4pfpuk!L}@HJIci^`>;fsC%nD5bE=L7w4ylenWoMVt-0m8dBdP*~EyWL(VhIuCHJ0*R9i$kktgurAD)(PQj6#ieAdCw%V#_#<>HdKH8JU{g`mXzQGp5^P)84X@K2ddjd>fvj)D^cUlIYs#fcc7VyjSEAejE<-J{-2T4zv%iSO9d_m=i&cBX7UzM;v9S$?6GluI~uQsh6|KP<-4dtma9{b+xo4HD}wuG&musH4iIG$=gaedRQ0sAOTAL@!qpt1pZQBZB?ZEWAE_jF!Y~=eT?QshWe_`e)j-y&mr#7c6YZ&$I7^ZLIEKH;{DB|@8Z1!+|*}Xksjgd)12C}@x7<}J6&Wtc-OlJ2YUxK{M-_F1pjH5M0*|GXB3l!KaTIk=y9865#mNrZPw!&daaK@Oz>Ke%$uOtQ`*8gySd4pjH49KCRhT1&?^j$vUQR6F9rV~leJ1$Am?Bwj3ek~IQ)v#LRaJIO~Cwx3Y4XTmlJDBvqsF+XrQ7i-rS-sfm`QjZ)<PIQTEyep09_bZ8pap+8-ww-nVR@It4lnrQIe(2+OUZSel>`iU(jgJJen0I9Y-{;GIeHMve-7h5)lT6oCcP(2veB;6sWr4=L(PI_Xne&R7kC@hY*YtX1fsyT92xpeds3gWc5T(NXv5{t+s*KQTFdi+r?6Lo6Y`=KPZ%hT$QqeFj-_KFW(JMF(XWJ_n1sfR`w`L1cm~J})5g)mrmIXkU~*j4pv@i!pv<98=QcwlryU7zA0UUviUbdT;>-1;g1mZlKv{da_9S5isCaB7mUFVX3n1UpX6NnC?iA-w%6LhJ%tjn`QLHSal-=A(4h)1*dKSq?F=H^IC>#pDJHvWvPJtF2|Kt?n-)XU75B!6(Ay2ITFq4C%Y+G?D_2oD#Awir&5KHu?H*J_@Fg8OEWEBDdRVw+>1Qxn{=soB*UcynTVKBMG0^{8}Z2<$Ppi1rx<654c=LiJ<AHjSg3Vp+(M^9%P(=@cndUT8yv7!x3ylY4ksq(X?IFM$Mkpo8CE@*=FQGpUFcuBAO6!a#}d(FLE$0_yMG<O@UBq`Y1=lz->FuGIg_xr5_h|rkPufW9L&bU3}Xn!P&_Q#qG3%dY^#$p$qCe_W|48El33v-iB)fT>`|{H)WTyF*_e%8LgS@Ul3{WL7?g*X+fY|W3^j=L@(D#b(|Evvok++nsz$|~wQLgi*(k%0B}$mPQ!|@!8IyZJx|ox$vNT?}+2SEeYTWz<oKc6JyUTUys*Y6)Ds_NLud34V45c=EuE9hp{2>M>*3QC{@L&GrUz*=;;DK&^dmOx&o_zFT^6iUJ^Y}&a;_&37Z(H;Tr7!@oH6%S&ZrF^FgfL^IF7|eJenM*+AZPHAEKd-+G6}?$PNHC!ZmCp^Q#kw@5CnAAqx#6^Tpy=HS~CoCP&9cY$Ll9;F~N!H5XBdHe%Ya)Z8lcZ;Mgg{r$tFid|5-d*3#zf;DD2%`PmpV);a8u6cWii=c18!qU}YRl9FtO@}2}107hrCA{mC1C0BaF_e87NZ{Je1O*h`tz3uK!{0NoT4$IBZsKQXhv;m=w{q&Y-V02{ix9Y$-8_XArySIGq-)&oEOKY+B9A=kBf=jWTYK&0fdp`_d5z!sfSgR$d+L=v~;mQ#1uo;l<fovE_!6Xv$u&q-B302HeC`<V&)`tj1`kdQKiE9Zw$T9x&Vs@6Eo!#1r26&^`Hs)qDO<skpIo8dx5)SY%-|d7y?Ts`=OZ1z$)NVt`jfIRc{v73~U(ScKtC75g2YQ*GofYX+UP23Z&IUPW?g-%Cd&=4ldaj^Ing++_iiHJi)!ZqHV<;)b1Wo5~o#2(iuqTat2y{yYn+3`6CC2yH@vVv3NJqiTi*!U9SWUdZ-d`m{VbpY9CmP4{$6d~ed)oP>qXuj)Y8bH%hR)-1^zjzuk%SOfCZ-6xP>D*~n!K$_O2}l;>QgsGO?z3#auusbs$`zMy;XKowL&9oF~wkYa;!d`==;oP{h*c@_B&Q1uxMZHAC3*1U59H7_E$o*2}+hxHQpQg#jejs*=sWW>(s#x8Of00>b<tZ2a#5-5B#;tM@Q9&fk!8DBXkL4Gl7<`Lk9#tutA_oN~tf)c6FIij-~3V*(qNao&jx)#?7hqb`GC?u0G(nfxyz<vMnU(*hJG%w!h)2v2;t&hLRB3b8{mLN+>S{<kZQ@9FqXHiKN3J3XSEAHfo1TaxS@kEkdDeLUN4scTLkLe$DwDGm!Ea09(6h>E_}6V`~deyp|E%v@T`e2K76E=0U{$n)u<w{t6^vVuFy(j_dcG8}P%l+gpV|uCu_X7+Uz&08wIpTIxbB=Mv524O>Y@H3F;>m36^*6#HA13Ypj&jsTweetRLjhy5ils7^&$;F9UDNTNlDg)|7xOqquInuL(wgo{(57(E0|K<Of?#=#_Omgsv@lywyTN$5BpMgu~BEhUF(kyP6bLwKC5ypB(9*V~_edZ+RzP+4WEWl5}=?6_;qIWA(0U4h+-<U?yjG%_XEhvl#-`$w3V{JvApMNV9FSN>Y%xXqMkJQZZ@JMteWVb?qGTx@W)B|_%^{;YSP?|xUyBkSGQs)rK(bx0W{$0I66iy*{aexCepp4bjOLM`p5a^G=8b!>cS+)BjmP^*<mnU0w{E^-WQVx)J~%XouqTSrA%Agkz*JNLG>i<{SXe0g6dlMLnMZipY0U*HHUJ`vWci-!Z^Hz<8<Tpmu!x3T)-yN}=Qj;I7RQ`0a<UwLKdiz-Y8gN%Iz0PX+>PdRb7N1TsKZ3^6e^wBBV$Er5Xax%Sx>n*Mw<`a#2ZX!MF&e^cm$a3vCxvPlGWmPtU<0TlBDvfn=XTpOco)IiWwoh`vsRCmI;2WBnOEL^kDO_O*U$KI1E*|(t**+Zkoh$*qSDhjb<WyO}(d>{s6JtHyz1wzBH);cnT6L7}osmTXFTtIIp~xqdj3=6+`c!HnL_iB%lu%`sLaP|Bl;Yp40$)ZhYiN9-Tw{bnu>GaPF@~&pCfPNLRF!v)MoU@}Z=nqtB0`fMZH>H7zWXh4sc8)hm#{btux<EZ+E#8#1cQt{C}LRKq!zc%027oz78lMFZqeP{JOcu36Q&6~QZfaSNDo|}GNqGl`KsN97qhEmM2TPvI8q468M&Ag=%EBVE_#0~-=<m>!y-@D_VC+f&0uK=jHKKEdc*n67K<A-<9COP$p$)VD>ee2mX+(h+N-r$VJTmuldW)xo%D=XnR`|GC6y6P(q~4;(OUgk<Y0<^B~TT3v8+Fn(}#hiH(5R0{$9D4iX;W-f|nP#&aAyA%edeIy-14`uLlm#ipHF$vjI%3Aaj5e*wu8RnhGfK*A1Eua4X8>T#~{_1Oerxfl_m0T)+aCqu$f*9_GyQ*#U47B+R;pNAaU)+fTYjWCgI@eZ2W>=crUbwRPBq*0#wcU=4G(x~2CIx{r5yPrmb&U;lzCaKRrodq?qi-OYoeN8L@Q)Mrpe*%~~>iOVuePP_$H1|EZedQJIq%6RWO)T`sk(@j07yC5rK<`ZRe(W+)6K>uBBg+_M)S}17Te;`tyRL4bwO-5jQIYH>06xvmGkRq@W#vh?u2HHLMDP=bn&oGI+@rEImkB&HIaDjc0WP`*C!GYY|ue?I@KzWCcTlr`Nm%8<ae9^7veVB)Oyt9u_*;>r*sl}ju)9h<|Bh8``CLxm6HcGmh<Y?-oRQqIrs@<c=q^h#zem_*SJy`)l=YsOGJD#WjhZtmo9sBdKIIAKBl9T5@MXi_^A5=-Q;&no`jfvGbV^zb5_wfz#nN9V{0@RA2M3v$BR>U0|zT8?A83VNddL|MUf`figk}9%VFbRNHF%Q+4_6}ek?nE@<iCmvCo*ILC0$f~vnKmg-iTH?lXdtp?aJ`bnWM)woYb)M|;_skAYhxAu#ewvx`LBZf6mD@q#ArNB3ND@Mc_@~5;&2R9?+RO`Wz&eY`G9Z+GiI8|v7Xl6oI(T;M)k@O`7%w%_&S@Im<4bmSAWh=*&`oAycU>j86fQ<9gfkMmd(6WoEFCu0Li{c&2KrEXO1FUO0>=!q=?*7rfSO)fa+G#v?_j_?5}BeBemCRe^v7Ke2l_evCM_8(IOiu(-=R=2u((Ld`Wq;OJnEkzVswnJ@LjH<mZ%G8OwYez_o$!{Dj=lU?ULmCA64*3d_L<m6TYBPShoPmQ9qN($M^v$*dI8o=1uvF194t{B|V0j+9q~PPF8_XGqCg%fi8BV|?4JSxw8VW=bI=nlSc$er37pFXw^plYdxAfo^S6F+UAa7EPE3kF}>>5)5+SEFKbm>iD9isrv0{q%Q3!WnqmdLAM4QlX|q}<{oueJ|EC;FeF*iQ$S`FQLlWNSqSs#AnEm^)gIY=2)W(>E?81NpI{z$GoQLy$o6w8Rs7XvKAr4EV?tYg)|$u4#Ddw4*iezGnq$3J7kfZ~&Jy7Ve1h7|mA{azR(`Cld>NnIuC>4XlH|5dbtSv)zG6iSlO|=9gkv#BMMbT)Vp?E<1tbC4WQ*90w}@@C#m8E&S;vB94Za-%$Z}FUZZ4=Yk#buKG!cCC5mvZ!;&&Sbp>mg1tv5rt$GmnZb-4#kDF2Sez8@Q;x>7;Jjvtw-`?c3ChDF3a!d;D6%|*j}tCUoW%opQ|hYzK9zC|>7XHqjllg)V?McWLxRhi4+e%Z%$9GVUXBW6~xS)1B>acVT>b>?Fa=H#MZyvD`gQneK><1J8=YprTd<gSMcoXFB*IuZ*ywSXSVrf{ML<;`|EYbx9DWUH${dt=@}R4G31t(vfgf`Coov+%e7kzP{th9t-b<NW%!zy0?AFbz3F5-hlNFR{BQtfNs&msUrxWa%n9F(${Q`>114I|5Fg{jLC3c_kbeu$a_Vy`|VfKdMp}CjN%mcJr>)dK(9<3S=o47}bH2b;jt#GR%<dO@&!q0@yu6BGLD-8hwBcI^v14MvXr3JS_|W4ApRm1SYbKP=Y-h2#=vd%VvO491S8t&tByxl1Q+0eHBmUn2$1M#2(80o+DGJ@_a74<}nFs!u`B}S-Y1}JmD3z9RyN58v%0yM1X2oBoo1RC}Dl7<a&oUm=9DQCCw{a?=jJB!fb{=<uh7fauGsZl^sAaH7SCHU7Hnb(nxmrVgaQuY&(8tNDP_c#0rtYGjWeR7;F2mSKNZOcH<#~c*GIYn_x1-P?==8q}k>^ib<d`r>}kV;?8G<9Yll0qpNJ?8Azhad;*lylw%0$1<{GtQ%vH{K^Vz=OQ|!Qz781GQqVvQzXjaEcnJIA#Qh`s47(|*S50WPr(!V6w$lYWBVAEUmdTCN;Z{Dru~n;TRK#~HJ*&le5x8J^;5oVnPxlV>SEpIFy6$7+=o~*BRN4S63PlRuGf|r$qpf_&hz^ID7ox?5v9WWJN0V#!{FueBhS|fIs*Gu1-y{xS_eTr_NIW3sx00BYIv`;|Ik_qLh%%gIja9WLCw!vmOT8V)mk#vz3==->9{$ih_$m<VAqg9R)|-|+4uuMZLtE)hY%>FucVPzSN85(#zO_Xl`2wS=N%elv-2^Zao6*6HPoBW7m<IcHF`M*fR}`5oafe`z6`aMif9X`_Fr|ScK_06^#1bC~v`E5uboydajnB#qINTX!R@>e@+H8yJ+8n6TvfxS*jG+4G0m6EAPODFBygCuZ>=f?R>5OGc2tFgpsU*@fIwLCJ<7^~iC>5*K?G%ISltLM};X*CPcDI)(c#HxKC4tuAI4J<;=qBj1BGq&?Mc5FROWU3SMuw~!rLmexq$L~zY*==7W6q2$G$%xIF{pU-DN8LrXg_?nx6?HjphUtHsSpZ(EiDFImw1{64(t+4Oj#5LEhba?S^;I-D>Y3AC?IWXuTiO+3TUnhM!=QSH;ERgo8j1yn_Cz_a$2ze7H=uf?gDeh&qg{zDm#M)X)*zlg-|AkH#2P&9K!)+vZTt@2STDOE9331vfReW!v%eOf>!_~9ODZM_Gty1VDQgI;#$@YcK42g^I?7pdk33_Rtk}{sRv0qaji~XLF<t0jC^$EI*=31V3od_uF!(+XXBLHA}JQi=7v|%X*L=(X_TE~u?@2&XuPY-2IP{`ONQjq-YP~3k8;vFy}WWWVra3wT__O^M-(InG$ad}b<VP`ZAG09fGI~7El5NsUrY_B*a@X&#0>F1t1Lg=-fWdaR{7<d2mpwUZ;VGXU7P^HN@P01fNZ5uSrq!QY-8j%f1P9cYT7y`^)m-&=A`%Pn<UA$&6Jcm656gXWccE9Id)e*YpXdD&A>KeMMru1;pO?LqzUF)uwGn~AWFu`aWuRQl&CF?PrAU!O_Aa)M_8vJxHd|Sv~V1Huq3<8%7e=}dxT=4j1aGO#Z822SRGj|ugq+rb*Yi5g%*2K#MkR~@C4tO?lq3(`msbm%zD*py4u09!@)GgJfdUK7_G(Am;Y?mNVjAK+SKNUPN+>b6mFd?-ObytOmUHLR&D=Ih=XTauVBYSNN{(j@yCu6ZEta?$I1gK#@mw6D&D#BjYU|o@~t7OI9c_WugkZzh?Ud<%9h~qvqQ%Z(TvVFf}vQjy;aZLC9qSN>Hg^8+3psmANBTaOmR4qp}jK7Be7EE9V~>O?RI~J+W>~6)@N&TXJ@HpQTC?n>mCAoH?G8gUEt~-&PM60F_CPs+x#521nt`C2_(SL);VgHvQ{$CZkb7uI<D0YJea&J&Z!-~SEgLDLg|wr*(>&QOGmRYJ5w-`(^16E$H97=g2AhJ%AH!Or<C8dUuzMw+?8VAOgjF}AA75`EvBJUw`L+1v_nmpFc@@RthG}ajC~7MqdA!`tG2}Hc;lj_&0bkfJpwX1|NYlt5?pcux_m}_&YNGSv#)~R|KrWCgVCFRm!y=*>)>^O*?UIm=?zI|t}(QJy<FSc7vcTgrQqY)7H&WG0F=9)9|j)#8*XNmEt_p)9K_cF5++~4E@;zMCqIB2{LrH2Z^g%S!`i&IrJ|0-hksD7IMt+@b(M4UG!+EMu$B%JsYghWx$*OE_Xi!a*r0(Z*vCr=?Nc!3vEjv)@JI!~0oGW_WyoF!IHDWnsu`6WS}Vrd^`}mJFciz~Idt>RPh+{8+xA&hCZS<#85VGU50(Q-M|s7tGTOON+)s`l@gERi!1Z0ZceCXfKzLvV=@}4vP@63u0x=uqo>+i@U6e)rGx3b4OKOpn-xJH*%?aY>4CAC8%CuF3k1br6L`@XSn<$4uG_xZ1CK-aZqO&lcWQJx55!)8d0E_*da_r(Uyo6EZ*U9M3|70n)!fZFBvcoGkXWW=yGu}(#@K-S$5jG1+Ns<wfA)}H5=ykEU@_ECjL@qcC$)c79gJk&ouYiM1#=px+j=63FAt<2r4t4smov-@7L$Ax%;0Z=uP6Ocz5i$<r5MLxkte#^nf^3@j)K0bsU7(cm;Z7tXz8H|2+7hO#Mqg!sSmP_>+M$BqW+qAmYpfO^g|hQr<un_gyJ~bJ8Lu~lzU$lE4*VXh<^V3u#HlpqusACi?%zZT(9#VH6>{7l9f3x%lbkuM%1vUvnX?2wVk8Y`?a&ii8fyjL1nZx##cOLN%Mfp85|U61?g<Fs1;$NesWO1{Y}BX3>u~J&x>BJ)mspb!V-TXVDEEE5vi=#5?BveNF6$;0FhxL4pbx;Yc80K=CLEs#Yf>r}ho^&i-ejf=a`rF|X=P}!dX<UY$)+xQv1~r+?gA(H>|i(E={@Zog{8a?bhvEs22dbl>%u5!5VG<>xC-DUHpzF-)VN6*F_w5G)@5OG)2Zmq)ShW-p_Mz2Sx`%}?8M>Ls1<G#l(nD?Jqe2JYBm(rz`kfuY{jY(eQK)jjI>Ee5n8$gj`3nE2zA6bJ8v9boG&jj7y)X4BnsvrjRKgn$uVG`E`cD)N@Y7M>fip8&=P;Dw@1I&r&#wcl~Ms2eSaQ>DspT|8JuR5yr>tYU~npIG~QBn!?CGV28nWX>ZMRWZ^c4{zZ4Gt&&E=<7)s#F+fV&{(o$$kIO_5(@YdVpi@B>qZHuQ!E#>04;K*%{FPe3F9BIWgQc0tOgtwiI&%&gDWPvFbG`f)FMwhFH^Kt4&?Gi2MG1AdQ`#W0Zv;*7>+f3)f;QKTk6Ru)okIkNZ20*q7b7)B9=ed^z-E`Ot3bX%UK3qVSSJGyN^gE@RDJTv(9;$IN;7Iioc;^_&kTV2{#&AC<wvaw%k#lZP+vFG2*BBVhwJqX2n&JUc$%(_}Ji+FE&tw0Pq5}g@V%0mB#8?-k><0y{QLuGXIhAdRSbSg^EEIjfw_mB0xa3ucE)f$k<2}7m_6ih`<eJ^g#>2d1l%RqlPSRlt+?L8dqg4OhYVc)cnncMh&t^mUni`K8$zAL8!)Z-Ter_k5X&d$F1RZ!a@_@u~sc-^AlidSn5n(&6>`FOXy0!vjE-|BQMr0vji7lzC99A0!DWHnxT_}*o3`8l3pJ0pOfiypu=5Cmi2Hr~ci7~5-ua>mAP`iQx9^Y_uIBV7|Vo+H?sTgP$74$_uoK;K}cs)%QP9|qQTskLg$;5*q`6ZmusSvJiL`jE>>~&g(Jmz>+SX=a6W#dQXmY`x~o+YOfiqMLQfm8gc?Q?K-)4@Po*VP<H{nRxrL5CR!{EVTGGW;pX^p}l$F0%8Bbh0v@WI3$G%^YJN(gGNAP0*OW#I!9B^R;d9-=f}C&i6uDbYTpGydY^N+JL~lU~sortH-xNOA|ycCa*@=VEhsawP5r6clW<M>DD|t*xWtb-#a)e1)Z)A1{vgXuQd*09?6qUFgkRPk)<@2u`wvynGlgxNP^U&)vyH?u_~;sI*K$M0X^lgEf}%e1SdwxewG%*eU5T-$3uy=e{gA#vU%wElA6DNc@SN2|2Z-tBhKMY*$mOy<ci0l7ZChV)3&Y6EHTo3Z4SHwC?2s_2vxB#XqG4CYlS|wYTPg1k9z*T6ZwZ%w0l&u73FqK{ET}J!ekq)2JzQwt&VR%TG6M9!Fb?Q@Zqp0qr<w;c`2!}{}YS{n6UNEp}Lqj{NqYAM=Da%va`7}fbIQM>J3lQGY3(4t}y~%%aodf$@-ymfyIH^6Lkj!D||bw1nV{4a_=a&tLBf}%@yAv!W&GfV!S(};AwJ+wC-;Ahqj6Tt8NQVgM!$;(tau=Y=a{`)ouo4e8|z!HPeOe0I-lzowL^xv;o|2$7-)n>IemEiEFY6;-20+_n%&L)Ybo_&htSRsH5G(Zs-BDh?$$_By4_r)%xcb#YfD`HNV|>QG84cUF%zTyMY%u4XX9_qjE0w&7GaYa)3SC0=4c+u6F;<)Ie$R-}bJTJH3YZ`Z`#z^UtiQ@o~pW!fpRok)avf;w90W^(FyFr5wa)IXlX2?suQ<^(|ZdBVp1l?o5AWHiFCvM9f>?H;NwQ)GzHeKtZR4gJxFG;dY9-9g3;AL<k|N2MI@%SA_C)P$up)+uoV-DH&>81x~Fk=~7U39%#o1$<@?qc_NB>%^Ey7|9ze?$_Tdmq~dzY=!{NuSt~|28|%d0?)ru9<ENXuKUw1lZD&I#-3&*Z(sZN_UMW5nB5+V{7UUd|o}Iz|7m<^Sh0|@1eD`uS1Thv;IUlN_OYtk8?qqUaplWY%Ns=nJ$|+L*01AwNDC2|#s&gmibIpvifg6Dp+kl_6;TfqwAAa^Z9f6GEGHO2attYenY=5VRlo#fjQ@Q6fNW_&{sUDAE1Sc}TO6<<EVoU*!4PS?dm*AMexi;7|xy~~T8PDlxS5YiAL5U){nI$F+VM?-*(;S5<IjpYZ(YgT8+#H{NWr{tkw#<>htV}HMCs+HeW9N`u-O^Za(#+)*;P!Fn_G*>jwS9^r+{!=tZhCN~`IgQs&3844yPF%DWnT&Nl_<L+1g{*U$Ro@E!Z1IN!Uei?AEa5T0DZH{-*#Y!1MHZc6URz>&s*<7?fu^->3Ieh?<7`kB{-t9?3~TWP~?yDer}y)HCyz#WodYH6ONXLo7o6zn`j58vkd)9H-bm}qh;x3psh&0M`svM7WXNJ>+?#fW_EU-K2{&P@SY<k4X^a6QPnZ*61<lYMes9bm7Ro<<EfULi*`15pKN`%+1nLaoH<d@1L~(#gLeLOlb4(0mzY&@7ROS2xjHG5uT)fR#MnrzQ}Gi;5{t${{&FP02V8t%XsHK<4tX_4E?HL0DV<yygYZl(@g%i*Lk6mk1#)_$vpmAhi_b<)yJ5r}tj|F6$I#Xz3Dstj)2xsbo88svEW$)rNP{!5Q83BabsoitU|FlFRR~6J*hibNF-4z$7AoB+g}9L6>sShP@d|6=X&+9}=5{DS*VtKegH3kjayZQg8KsxeF(4!{8cX#tE)1D6VjDvfOPh{@73+F>%7KQW7`gg>inhLS+%Um!pn%s6O0vpMPowE+Osz&|ln&M0P$JMb&<<31KabV>R)qih!fC6L?spowwnA~^5M!GZ<zBk1jg^EUlA^D_S;6r3>uYOw6qQ)UV}<W0YnX3JCXOn*5zkrj8<obPeCtd+>-l5(`Wt&BQf2N)tWdqQc|4jC6t&DKd?_uLN>59SDS&_mJ)8-xJY0fk`PGnw1OSUhXho4ILwXz9A!SkTL4DvC%6FBGrsZ6Q$5QcxlN*e3`hGE;j$_SFyB+asPQL5w&Z?_Ar4tX!jAA6aX?XnX%P*@#vdYlFtmj5eDr--8nO3!76{d!5=}#89nW$>)G#`7Sgq5l)S%FiINbS%GO4_QMMy<n)XEK#U5Oe2K4ggHpvMx}Voqv|;YO?uIDP+AdRO)Rzyx}o*TUBchr5bE3VJq)#(yUD7C@#u{s}46sI+$O3Zc2u9f<{b+pCys3iq1(YeZU#3c!*Y=fajCsrE!<wh$iO#5c0(%)G`4cCD4HKDYlXv)Fn6|f^-nxsU&pt#F)kxgO;#af|gS8D1X^RLcbIQuH<%X4XZA0qR!;R>+ZkwXf$+&QTuqJ<7zcb%xsn3dR~3+u`w^*R9F)H4_8jvjp-}}%J1T?(uGx*TDP7X%X*eeQ(Cr0TqCvST8PpGCqU+>72ZY1!I~w1?RvFSsg?JkEaF1~EzDOLm81M~StYn}<0|+CBr1h)lK`G>G}g|vm{_M_`2089T3J;I60b-LdSh8NDqUgO^;69?B%UB_RN3#v+9b;r6OLI80GOl}@#RaBKKRz2Kv6kamON-XMpD=gYP@WzjC`x}f<kntRIMGhS+taAN;c7I2hNUne3`wib#yei+$=ALGJoW3j;&VZF2+I**jSPQ;%wr>qs^mdhcWt0ne9V!DNOQ<h`OX_m}|9w^(?hFs~FUEZtEe$rrps&C?tX8;+l1$)UySQ@Z!!<C(lE;)=-YaVNy)(n9Cj<tdgZ)P|BcAC0cD*({!mA(|kZSHl>7{k5HGQ$*;B0kYs-M;)1)NcV&n-zjs|~+1?j)i``WeJl;iT5*?3XU4LQ@QQM({ig`U+utLSurCau!pF3U|$btd;eKxHup^|j1n%B|k(>CPt@10X(;l9;4aL?<#RJtCDYD@b@RbAO-NEiQnN-<96O~x%cZzAQAzDek|i*(4r3S1)w#v$s-#QsGT+f-<jklqS`5+hSU*%6RIqh^TI0(lZ)uws=(9u@i*07t_TGUIm<N&cIb1e;neNrEZ+B1|QGF)En{S=gA=f6$+{Zqz}sLL!jVBM|{A5P%h5v~=-v)5j$wk1Hg<UH|%InqOsobAhy_0f*t^1L*R5>>gE&l5ueX+ymM8+GIXTj84eFg0`&U872133lr0Ao)&2S8sukWUqSmv5+9)AV8;V8#^u+_ElCW#iT!yDC3o}bW0dB1S)VG5P~8;@Yp28pEyKaYaw|&-geq9nRYof=SeZ(em<~gT>vk}T6;8oPMu(z4j5e5!?2<G#qF*Wy8WrPVHYGV>*_44AaI>#txkZXSfniTRtG7@*cAulRVQ242jp9+(OvHg!>W=d~M{ePkNk&fWn^V$a3iL-)%QPscg_Xo2#6_~%mocZfQ@&iN-S=&{w*NMJ$^dSgcQC+~06{B{DmBM9p<Ru2`yIO#0|snyWqp~m?Kn3sDv^YZN$xVnCZP&sB7~h;C4N>{6%ct1WlLL>+NN2)TeB3^lEbfK_LxD_%`l5;3=j@VndZcn1ezf_9KlyLBv(G|a7UvZdtrG8@P#ozDcRk$@#^^o2%8d%5lSzy3UMaSC^N-YW5tY7rUOhr%6_Y*(Ucms$3<b&%p)~i-oOppHpbnA4c@2nsGU1tBY4kDKs99{=5ff-`y`kCCQS!nmY0<g-7r7b7P1>&G<oMblsQ+>AMT;MtdDNnvZn`V#y-k^yZ3iED|?u|ljrXOi>^ACUy3}d!}MA{zguJiEe^jZkmO*cqSDj)lf3M{q8!DHGqCai=D5__4OrUNu3PCKn~IvuI0CmB7qh>NYbU16w8XBJC_*;Zgu==^%<FkZg1Ja*HaF16m>1u;8UtBZ60>dqp$Fw`H&ZnizngJut{X?i=fgG4H`zY5)~fAjup9?yl_GLU<9!z4dSgs!ci-g$0vd0ZMe*xIa4%QxyW8$BoW~zvt^Xb@_3s%D@4Z;Fn?9Eab@!gk(B4+E?6;hMU$%{|_2LIW5Y!m#6~}8QmPwy_W!v##b^P^?qx^2Kx7Ce-!HK`y+ubvE&f<2YdT!JkDSFHh-~V>jSrh&tR)p`{dT_Z&4NgQv%~bd!FxWPEZV(1bwk{DE&9!&Wcn)?(kwq~Q-&e#3H(L(tx^N*r=y)dd2L+r^01+jF0f9_ou~p|if>g}2r>yJDXV|w~Fo?3<AD#{}_#?}f|B^rv71K50Zqu`2c79=paqtkxk`2zhSx9Iv2;H!_fto}@8=O568d@r^?-CI-bD)x!?WHy!@Zx?d`B7~Hin+#TDh}Nsono?pQAY0bWJwnE_W10wKop3hi~`m5_Bgo-x=KwmAR&!itT7(=$MVT$e(4H;OAW5+C}F+O&?eCVT{>1_@0LnYXP>HMKy5$G425X~6|F^$)bziwi7RH4IhA(ZP+I=d-afs(tOZ}!9WJ!L`f_c}S8GlUZ`b(YpB}EQwceJjwGwqc?v=%kBCpn&R<U!qMPZ=%DC;Zh7p-704w6+sUNRbhwuPYs!Q4Bt!gaY-wfqF7iyC_dtAXT8rf5jig1YfV#)ZZ-^d31q{ENghFv-Xne*flI415a=>;n{74bulC0ecY+^4aMyeE~cyFFy&NMN+CWMF0WEhwNvvXUK~eBf=fXa1XOnbp#Q=zZjLhrNVJ?gR*B_LKyiZ9i#alk6CF&%2mkDG%uobbe&D|(eVRgynb-hdyF}SwtEK;;68p(64E|su}+4irk<ut!NFv3HFvR=x;`MO>w}hWdJ|M>JwVA*XPv^Hbk?FZ!^;XkjF!Ko33`Ahc~)GoT1cyeus$gYbo<Rv?o)QCM0<)5juMH~Y};u>vS^Sk{%Y`b{mzoG>1I%vOpQ#^p-9dW<Q{|Ypu4&Kv>ROwR8yo)fG-c-hK!2@O1u1RMPXeX+82K%6W7L-oIBC9BxOVp=GW<j8&fG-YkI7oab1VCEopy2YENXe_nAjE&F=bV_aC>3P*YY;sJ2dozGceEV{d1K=i<#{r#kip$uMIKHPIJW>r~C{+qJ@A_12odUZBN^mm5puFy>6zbvL2agd`tEg;8xY{wvaI#AF;+g=#VnSJd{_Z0$J5bY(FmZmlLBP21GLQnu7ZSGT$*x{pDIgo0H-koK(H$JK>;+v+|&#(mU9Hl(;JkGE{4tQC2CwMRuQB)Tk1k2P0ARECi{`-Tk<VWLTG%XTuRz*U(qfV<3^%9<USQ=U9-5cBLPt^w(W64SsVSoLO;WVHc?=MrvYcoS9PhLVKUgzqxvLxpe$g6*6Y9%v~t5v5P4gL4XstePIUcGjZGyi7;V3tN)&VQ};^2VQ27A}3E#>4E&BhAEz!QM6*t(%tU!?m>W=jS5Ky$7%NnpSVt*_yKvOrgIS6?!jtRtT<@eSGGS+dCru|D?jB2gIn8j;tjn>Avwt1r{iJ+AyIi(OXQ_Jh0FAYXFzJawsqfyZR>7ggOxEE)>Z8X?4ch+izm_5B@DNT+d7&SL>8gJ2v8Vte(7_g#G$Zv5RRp4dC~Tp`BaC}bjD(=IoPXdn$P+d&3OZH%x2uSl<f#n3uM{@XUGb7Wr)IB2i6cbl@f9Jh8an;(f5Z}-wS@FnUT06#AJMT?t-bK7yo(h5nXKEACDqb`QL`h0YOLv-;@!HS|TPXX?tCICSyR<*RW-`(Q-i8SJ*NS@%7}SsM`Q!fMgtoFzk||s%2aytRShf`3fMIur$POwHGc|kqM#8METuaIYI;C<6}G;C#5_$=|GNMiC*i}Zbik0$ctF2M~*Vu0bYI84w{zc&xo|iribDo;`oRws!0H^?*yyIsH*+;B(GmA`dz44w}xC23ZDtuy`^d1g{`_|_w!}A)nS|66C+wO++^=LB<=0CtWT}_CYKbe?CfoA?vx#6wSd@7_Fkl(Jzv7yp_=R3=QuwnRIN%-OX<VQrU!j1iHx!)sEg~uDX%dzuy+2>>SLg*I00wbD~fP=ou!y=SVG+JDX#5lH@9dY3i-*2W-(wC88WaVw+aD^K}59^4+Vs&1};j|kuf_#4N^L7Rv};jn2D?mJ33n?I>*cX6k|4(CR~8P%QR6$Gmi_ZwCxEHEyzZtZu0VEon<+;#s66ZRjg*(Q9oK<l;k_tq-;d|vjF{A-7STFt|Z=Y$85vO;%%tIBBs6iz-s2O+peSaZTjS&#+kCdk4lob3hhTISIre4Fpx)co+Vd%8JufHQH29Q3FTx}>am|_N^8)cH>+IvKeVJr@u+1<>Zbx*^~QE8>X+;9Q1+Xu*{Eho{``Rs<A)3t`&pCa!7?@v%jKP9p+1gQj6f}KD;~D_R(7fL<|=G$EY|2%62eu(^F0*<P(t-=6Ha0IjCUjkB16WL5>W%{B@xYnR-u{+<AZQfw3ROy21w;_G{V4MB}0rW1=yds@Tf6gNlDjv=s>>l#87)Tw~gi06iW?bo=Ziwn*~k2M+Em4i0<A9ZxM2;O#^c;)U+5W`H83h>d`6J4$J(m<nv*pJmcx1JUbTiAgUp+TY~y{tmTa-@9dJm<|JbMRx&1;=UG{U+dcL4)R6P<IIcWIHgp6v(wmZgs2y<SL7YrG>=*wQQU}|8r=Bva<W;Ydiw>)fXdVec;Nty^z2gzho2}O3_Hsj`8(ZXca(sEh(j~YXoJM`#3uTM<c3F_yE{kL5h+f+z<NMZKt7h;5e6m5Zht9V85opIFv2DzwT5BY;(s8}0w=<t+bBx2B=tUJm$Kwx#;Y6CcMq6W{E#-a2aYcMFq8s+~g0kF^ec;a1h!pY#@=~sNv}KDXZK1D3ugOtM-qe(iCk#prR#2f;EAf0z@E?rmbMi5rR&LpYv3X!6+XKtYXYXiJ>#joI$n2}Bw*9Tm-L38pa@xKoYBplwU@I!S3ODb9Kdp3!{%r>=?u+>l(7*2k{O5qS=$Gan5GnN0NA+>LT8{JO-0j%#-CCZQKeypxbtOeF1YAKPU|Zd&s3VU}+q<YGZFQuhhP*2$dej<(TAzI{N9Vi5-;OqDHRg-C^qmh&O;cDZQu8wRbp2heJ!<c9;N*O1zud|tzkpg@c)spSBfJxxAlHO*MVJ^+v6n4YN5n3tPf5*@blY?er<Nu=TIYI&)E`VJw7lW%rFR=->*8@!2~>8GoYn$yd^Zm()c{=GO-m7lhBwY_&a_$W5f@^xtd%*hP=Xl#iObeRbA2^^XL?eBQ91+!f`>p*9<3X02j-P&u0?C@isc^gn2vEDAi_^tRsF8(>aK0=N)c8ZwVk2!m=6_}S>q=6@cX<WZ9QKQnzL(1zEVlq<>obFe1|NpAHKHDQ8VC%9LjI+u*Mxg=EQ&FF^3#Ohx^5+*g3j>s#)%4#&VwdQB=D!adOZlW8WVRdPiNCKGE^#NEWed=-NXJ$2uoyEr)9@N2|4J)yApiAf*=b!zTp;rE=gQe!!@v6*Ai?=lTa3&h}t7LTFd)tQ9tu1|6vOb;L42aA<O2`h}rS1JenXLA~FNonl&MQH_~fT2^bYZy6Dnx)WupubT61ZpHbw17u-Yj=#%oiJoC2pbh4%6qNwHzCE(m6b}+DT1}cIf>J)I6@+=~*9ghQOi0Jt)7Zq=^Vc(@s@m|lbfpe@Ewgg_VG_h&6+@Gfbcs~^^*Ir?Fe@E-)b5Sp;`t#xeb(db4x9Tux-^;fk_3jqY(x~i(y}QB-8oqoR@CXl4ygTSlVLlkzTO;X-={Yi{Db<`1t|J7#rd2=nuVBHlZC%QqRfA=>CN5>UJ0;bnBYarhiTMq7szST(3Y7D)p+X>dtBIE^?^C*Y*zwj?hLIiR&MDg1;9TeLF|J+{q(1+KMjul^xdDH{^{^959FpjzhW_M>u%+?Y`1>AvHtMnE_6bdmCTZyQ`?pyv>J1*i^PVg-p;5*1}$q+#Au<yLEM(ZGNA7r8bP-$Qyl(*Mzh0=Xhf5acta^?qsq5(#0QT-P@hgsnJDm)3YE4vhJDh<8=1obS)uLU{J+EeBB8{3KPS`VD=Wob7F-w8+4v?Z6D^7q5j~A#(PKRWb@s1h0#vH~-Yk;t8npq6<}xvo{KUHzr92*Jqk)&6a~lCQ6=`Eo^t`BT4gD8<xqqnLh~e)(z*x(36LR5JIa<}Lx@c8rejemZVpZ`H-j*TyuI1$c5fOE9s09%p8_V&~nh$1*FWlPcq2H$RwCiodPjYhC3J55J`D(?)0@f9?btOaO>2L7v7<`36(?{t`xpDFCz#>BHN8tkYcPYNNa%;!q+366QfF%-GmI#X0Y8n2igh0wT!~JSmu+5E)B1q6FDeo#}OEz?K+b!G0`3&OR8fD|Sg;sI*GS*vcK37^lk0~8R1F|!ay*O=tyFsahe^CjAe-VqD^cQ1#^9z8}FWgWH1=G>&=U<BPteA2cc)GqB=lyirdU5I#)&UC0Ga!#SnG0TGK+{kp6O1l9$|qOJFngUg!`;W<Zxd(6=mb+lMSY+V&hp`)$)Q7$;IwN4rEy9FZ}u@xhz~i|T2%^YT7l-vsKv_2iWdnAL(HwaU%n|Y2P^F0X+F7$s`|2X@<DU;l+!%sjcl?!OIkNeK+hE3r;q?H_p$U*L@c7jmnrZp@#!QRKsPfay6Qd_DO|P{#U!J2AoB7F`_e5S0C4lHJ0Bkx4L!7c;>}r7EmS|Yo#T%Sys!rk8FANGgcfyJ&~|AZ+%@8iAVfEY%O`}VLxEXJZsn$l8jUCED4irj<_d7-HX66~Lf$nRo7ZrOPzFU>0!eS(R31^7j~u&J=}&+ZyyZFZLSd|^17$0>s(mEwoZq@e{RU7gGb+0t1)Of1tV$>u{khD-n)0eF#mdtinpYI4&_e}WASopr8v~b?o<R-Z%HamTKxUo1dtbJL{q1hsWTXd-37dI-L)JXVr%rG&wbR6GG{ijP6apTT%_)*4$fi-_VH8vn)w_}d#Ki4jkoU<lAkq0$(pL$}y9$*rt$&f{5?d`u#sCCK{~~I95(PiNUBQX@B)5D9gCvI#JO7`)QBeF(dB9KEQ^I^8`D@hp6q>Yi-mjMA8knNpc-V2Mw;==33Tzh+k)ecnH5!+j)qO_uKsgqycQQ4(%A>|-QBcYPWl{t}BXT=%UU-#kjsak*?LGBwbIw0pFX@}<y~5ct%x?p$Ihgg4`Gqa}JPP(F=^5;@y-~n47no9v&zhu?$88u-(EH{qN?r;8qtcEMD8OZk<2X$jZU!cmyW+CZN@<*&X2Wcn;r#z83JxSI5F*Y#%AH7>EOIue*dNX)BR#<~3I7Tt;9%whJ5fTL6U^#FhP1#KxYI0`UKZM~sPTnfImv5eNe(E;XNGR@<0736a$Y!65dw-IX5-U5nV2Rqw$y|KV1xYS2;G@4alK))apABFF;-JRYesdIjIuLC1dT5#N#k`^%<$sYVl{1i3muD)gTtMShxv3BYF}|t!BzXaPgW0~KUsa!d%XH||5HL5X5(64Ner?gxuI31RurI!xIVElRunu(Z6}`|?t`|~b<0)9mX%LPKsDCa5VH89$Cin#Ma5L0HHD}(PzRHbquLQ=Ha*4=5=D{mc|fcAVRB=VWF9b-s4&C<90#a{LE9)FE)*Um=u)7Q3lGsPOQs160q_C;Ga(rp>ws~)9=sj&wmGAfAW1aQo)l<QPA1bAH)A*lY%I-L<APJ5um}h@c<(20eUO=WZ<~?GfWg(;oPhG678Kr2T~@qXd`U<;r(&7`0s`DWFe!xX+!3ST2GFdMiZ|8)DId)6gcVnaxr_n~c570g^Fa1WaLFng#;;N+u2q;~b}dHjvchc~^GG8moPf!ms;>~7A7I_-3XC3Q@dyuUXVpPS?19kDM%Cfo)UmW}?>xXLvPCK$h=-bFVW}nGAOTkJ`@f~X{|Z#(>tyieS0E?93V!=*dimy8%<~o$moSmv{yKW|KVfJ|KfgwL^Kz13R;bOA4@bo+j(XS0;F)e|u^<azqN7QTdA97{)Z5(gTO?S1jwuaAfX}IvISt=I_wd=y(S~Ac2?L`?WiH5<TP;oBT4x1qK)5^pci*E~0&EnL?l;rx92OqeRjBtMal}ABr$1+K9A4+AljJp&`+Ir46{|-JAwxQ`11<2o2w)g)?xqUs;E_<c`49!+&SM*B8Gw1RsN%{J*YFKKzT09Nw9E(b191!sOETwBEyvSu*T`G%6=vGFXb{H3I6tw4{bF*bRU~U$FJU`aF2(d5W5udU!U!s@_~QugYH-I&g|4-rmQ9?uITlJ<){iyXP}KvxQ$IZo@^OqWv(dnbj!+t;vwj@GP=?DJ$NE{H6^@akKKku%7l5Ji(QkjvfVWIAwfn`*DPX8^{`-F<gB&PqIAGUr{#|6M^VjJ)lmj9xy@bQ3&my4nOXn1NhNNV(p_uK*-5>Y6TSwh(9UA3ue%JnNReJ4Yfi^T`9hX0qG!1vH#=D8#tO%m@0yhKc{>sOpLQ9BD+$7X)Il1*%-*u&&=R%WtGMp<vR)B+E7Ih<0>op_bq2z8=-(yOYZqd0zm|g#-PYf?GecEXO^9&T~##3aML$?{W1BnWcswreOF(n;BYRTZz|F6Aw-B06M`h>r86`hXr2pk%a>^KQF-lIs^VIoT!9g>}qwL1tJiN^>C4U)A9&lSu~ych7^z<iyV`<hjUb?ns*a-98pK8$y^fbMlZ)T*jg^)GSmfaq{5qzl0A)qEXFx$IFGyn&m}v1V~V$b+&#vqJFKCBMaf@fdoPw&L7CG-2g_8E0C|l8k5`(RYX*-{p(B<Bs9)L5FDyEzh=3P&9N*Fecy{FCQNOQdk^@R4@1^l4Frz<f{lQTxE1(ka4<KLKdGfFAh&aufs0f52nbbqxd<zh9e%t6U5{v!Bh7buH2P?gyJ=5Pyj9gfSdFzg!!9T4*g4x630@N7NxY@)DwS@an49rwXonkv-ITIh}nF7;J04#+8=FTI`rr>bd7<ZHsm%QWen?#I|{x_yLuRPgMZEz|L6Y`Vnxlk=1{h}f0`s(rqe!qyo?dvzib#EW6D5>z0WX8C0l#L={t<2NM`Cuh=WG$M{$kv1RaFSY~a*YGgyiTt8nw{^c>5*P2z95(OMoChx0E!ax4Gx1GJE&WK0{2tqIq~rPlZVa5h$rIE8Q_LAw8zHV)DW%n;W0W(ePcd`?O`T#Vp#@BzdcpQ;#WuDO0mUHl6w@x~C;9F!y4uE#xOLsI4uIDxc7B89Iwij?x)Qq8ksS8A{5$PzMo%4)+1vZIV2x)*t)g;wpQb5yo;XII1d41&w4!x_%v4VW5R>*UnM97wA0EUKiOVYQK{pATx{OY)hLg>|ZC_z0(3r65%@II$Nh=s>!-x)s$BD@AM*9?k~Sggg@Brd})FsWWhE60*H#c9lxlU|Uq*EJb)Ejlqm)or3ZRS`HdCr!pXg&>SfK-QID4+OL^$v@^8@px+G*DUXq06j)LcMah^_n)z~VDFHl*U;T@13mwZ%%}0V6Is;L{MM*pqWW=yV*8|`t(nf}D{RW6oj=3SJGI}2<poj*t(qW0w<z!XL;j{b6T+Fr~b4B4L<=FNK7IoN-#^MyNu1gW!_NE)8Qh*<8(oTs&!7j~9Dd-L0UuItBxQ-XX5Xb?(fDyrfbf{+?4X<h{9_$_1Ka16`O<Z%p13Y<;seCKg*dtnFIZ)<yhCx$sT(U~5MZcS|M$saIJQ}3E1Qt?*Ob}>Cy)IYs_^^I*H|!-!PXOqrMj7T?ZyBq#z9wD=6WJ@P0}^@AX;Q;5r<Wdlt3Pj?Yq)x4u_*1OZ921Uimqu(jRZC-+W(Ns^+=K4$`uGUk&{atf^b6&Xi)sMCcotJ)sKbLvN9zDZAz@4<z%vGuY}mL=y6`gYcdL2=9|%47SOn`EwgQc<pb`)dMs7H1^6=LHl%xLlvj{R7VPHB*EQqb$mzc}VF3}I?O1ft84DL7mx>M2&odSmTM06YkGyrnWC_+0f8AUj+Jx!Gt?wL{RmXzT;KP0AXVp=cYpy)xyGV7rD;QdX53Y-C2wX4R{#2QB#%n;SJfT5E!6`9yu%?>}kdI=P0R<{H=l3uR`n6^g{_EuG6dx5Z2%Fosn)a=xcjTWpb*+?g;LNbPJRdlN;u_9XfU+q~pg-NDI&bT0mBIi1AL^bFZK0F-|N8%f|MfpdlbeU&4k$AKSLa+IDd#8pStdJNie5{0VU<mA(ENqT9=ay+pJqt^NeUi`wSh15ZZI<;RLj1)jVrxu?ee8t|At1l`VIhOXN-RFc&elKT>-tZH)0{B!Io2#weFd$1z37D5MzNqfmrbJZjWb5+RGR}wFIvvR#F3dC>j$n(X~$}S716~nk9NjmYu{RTLlE`U$yE#Y31?Cm#>=}`IoPCEHCCR^Eu4*X5(HBYc`BDT&s>hj3@VkSQivvTA^NC7O_B@j_&HKBetiKH}w7BA;}XTvq)wI6d-%kx9R4#S7`ADU$?anz?RCR<03dqFp}e&?!RhBn)g87{b(l8yYX!@mvi)4cO{1$m0rNN%7;>`RI>8&r)_0Bwz3_S8S3zDVJDI@Txju=^x+n)0Lv==O$@rep$v5Habwv02+a0aGzTk&jaaUTk2n>3BY2Gn{VICN55JzZPdBj@+SLZ6;4ej{qYx19-SCG1NRn9dx5K$>SOduHsI`N!zXiuVXjB%oSEaKMc<|1%9uh{5uQ#t+*qzSdLFcd?ci!#3ZRd3fEr8H707Rb`&udpNp3}3k4sm_;Fo)>nl^O+rEr%F}CCsI)gAjBr&82St>LnFlU2=u1@R6PMVOp>+K&;m+KH`-lT>*0KiE`|RDmgV>@TGJC+=-pghz1&j9q5O(OtyD$l~CGfO5n7#US5)RoE|}2VQ<JAY4}|Wi%&J5e}EyHaQo0P3Kmh>1L^CX4aiaVOuXFB>0&S#eyoiq_sOhWp_pS5@F1)`bZ<xWg+J#L{?beD@RMTPa7>ok{Np@y#MtaIVDGLq0onN$IBfxl!U!CwJg~dQ03#_KUXS6spGSD?veFBZpy6e0=wi6${QVblEk-QjLXJZ&4=_biKdOZaAPy9S_ux$+P;f06pR~`;PY&a~A9qhqFV`0kGpZ*lk{}8xx==9z&lFfto;llK#%BE7B$qT{$D8VleSRD)F^KbJd1;ons(cQ<>vNO2$MbI{M^nJPxhzgT7nfbfLS%!BzyPh!kz^{pkKs0A++kMbAW1ZEqz6Rcs$^5eZWA7Z9LLrN-4RHR8$U3*x2)bZw^_$FdZ0lD;rTdSOs5!rCL@$KgQd%7uEIy$`<)1Wt>D%V*tyJ|pU$(<jh_S6fkm?H(WD^3E-$MX0@*iC4t5;!Yq-`JfLKwB{qM-Db(5<{l^NJ^fwvYINpEd!i2*D@W0e9rmPbPwo2!vQbU-_>$`N_Gi;)o7j(<J-@#ygU><t_u;WnQeg^4>y?ZdsJeL!snQO_`~9uV+z(!IsoJ{eCteMk{-xj$LVWf<*hka;VPF!|ODznG}L86mo<77S{kUdzm;Cq7*A<AsuuuCfuzoJ#)a!<KKA%8YkZHCSrT0YB}gshC9H1oGSpNje^;ld`@3c<q7x5<+Bv@e+Lbrx=3TV%~$>Wo%vfcGv^w5%4l-H7Y_VnZS(<u+&@uM;{avD0NrOfLR}$&)wtW_{XDn?P|c$E%!So)!^WWznq*O!WW~D$hB+&l7r1)Ln6blAM(psz6kvl;FYu-Ar+ff0uWeD$I2fEf-t|GN?r>XLJ~9wVQq<z@a(H)@JCiPku6jOn2rhX$8bZCU(_CxGbFN+DCivurS_3SaR=*(qaIJuH7B84C&{@xBjF#|su_tAi>#sweLQdNcq3A>Uxf+-%~d0djT+pCRNePkZ1w$cY)Uwp4Tq!KySbh8%Z<s4Mk8a%$ver-g&T*C0aH6Bhl$BnQyizH7QL_o5?-#0Vr(@OM@ZzrK||Bo@*1YR;vSt`hHb9LBM<d6k|UbjapO(Li40xArhq;0J_@cbg^?7(QydK&$-6N-XT{{ORz~4AK%v;CIIQcy_iiORHZ$V}zy<tO`2J&~5d!-Pz<FX-0Y?i7DnY#-d{?w4G<oYPxg3Ud`^6~nQQ+E$ynn*?i$O9NgqbyTPOt`f3rP|?If(=YBnf`ln{MxX(@@`b!bi5<-ufFg3nYT!n1!dj;qaeEG`&RSV-D$3=Feu(nUgmPMrrXLD(T{i7ex(}nmfH)go-Ugj<O&kw-pMdB)-8oamkmmVj;p1>#M4SQm{JWE1%K_dK1}{i(ho7V9Tjq=@4b?G-vE-M5C2knGzAZjw{$mh`;TGz5BkAfI{|}?*$L!r5?}|osx!7580m7%^uSO>^P0@hx_jAI`u_H)j<zMqu4q@d_z<Y@#*uP0lP4fQvAheJ(^|fO{NcJPjpj|PU)NR4hIV@Y1E+6+m+G}^K7U*)C+Cd4t!n97=Yu>aT^8+I6CwB>Dm6#`I&@KMCU2255hd?RIqw@;Q*pCRVKp}Lsb~s!AH5wGHaYxjLcOSR*Zf~|BsU8%ULjgx;0h>v{%R}gDNxmPpA);H^a@LIi}75QBfLhh;d7rve9P4J!%3Qmj~r#rpQ%A2p#?{Us=5$FR6(&_K`Fcln$&V6wCW~-kZjV_jEH!CGSO%eK91w+Kada#TYhf-{4+=UF$hP(a1HO^gbl>8rcAYdD1u`p${vmqCpoThZ-KU{8{l*S*2gf;}tj^sWho$a@};{CbT>q_OVA!+kwLw_MLbiR$-iKQ@%&7HCW*n2;st!ti$@7P6)x<jywB7@_Vop6|d;|5q#{O{*1p4e>5-rtSK`WS4%V**WF+%q@uR)IOCLhXGkX~YnlWh`7j)fU|6a_BU9a{jQ1S8_s1~dqR?1~ZhFwGaFX<j`B!<#;?7!z*Lm!W@cw|nZa5v#Zyabb4~)ML)xeXp&_YV4Mmy&<7FO#{!K$Pz=FUX4*F>%2Yjpk$fD)%Ws-1S;{?s`*P<0a((=X53C+{kS^WyT$qI82@#vxZnotPLO56n}Gdo+*t<;xREXmVIruSm?rqZKMObTqk+)5SEI-3h66met1SHDbxIB}Hyd&yU+DKX*=#PGTXaGJ0J%551239d(1~H)Gcg!ljbLS6aV=5|QMmr=!V3oF=0|d2RE^UQybI$7EX<yT;`G1PuE5S~ln$o}TT3k5_!UchWgN(}`hSWZn{*N14S6_qEzA)Q~S)W@UN|(woJ6I6|Icrz~-M+_EZ~u+9ZNkHtRgPwx3X)LCSieO<g;<-I8`IN2lb#!m%pacJ!Q&7^xf#4Qa#J@{oXK{lSQWa{G^NmA{VKDif#0O)L4q{M}u%*q#KU58CZ<#IP;lcspZElRqGwlA%1a5|q%kqalcmJV2S`8R_#PQ$)6Jf~6UPmg^!IJ{oBhY0f$HxCKgaD0=9bqz9TlLqE`)*a8`yY_ktpDsnMt7iF41(G~Hjkcq2qV4bK0jASjKV#zY+?PLPvI|)v^jVg=T?4T9c99Y$Bics%Le&Sya7lLxK`mcWXzcD7LE_l<5<OrDt_+F-nB8Aa4|Zy5GspL-4D~@4>6V}*wE?_4&}&!pAsvY&$^rB;ue9a_27;70h5hB?5Ni@`UEmG?k+q=b*j_T%8VBcBBIg2pfy6qzS}+jMES=YE*mA7Z?IA?a8w@{|G517MS0%MkGs93?oFTT<^<9KmR-zf|Af<u`@#yLSPMm~pgQflfqm0%hbc-5Au`sD}XFFvEETG$qa_^=Kj>Y^Ckq`L^>KxwB-g{P)VcLL~6|(i#s38n`u%zaEF<aT=cad2ZVp~LTt;>3xFpA)<;1+n08GtcOFemBw%k-f~nq*Zu%57rfx)3YrhVjVoI0JfvIA*Az02d6o-0RQ}m=n>^Xxg12)Q)eMIrfQCJ%%_`RnqL4Pvx`B6bLc1&wJJ$WUA)t7Us(=x*FSEs0#yQ5fVCMI$B(pS+|+FZjpTefX&4fgiHFzZuH-~(LW(tQZ2%GNnyl9PAwJKLJ=>{up*aL7&*HlFT+LiyM~%b;_I-zoFEqLN!e6rU_VGuD%5{yUY&Sg(g&juYvg9oVj~I13rlahJKwzElxrCcu`=Slqj&Fi5BHG=dYnoexhS`Yd^XCXjoN^*dOvOnnZ;zU$Txn8A1gT$ttEe12@$9D-h@4N3M8&1KK*eQ2Wn{z+^Q%ice7BI&d=Tcd*@7KHKcMYwb({H%a-I|6+#KThNAQ;cmH{d3#|rZO~dWPuf`K8W^rw=4gNL;U|Vo4;vhj8f+lrtq(w5fgJ<dD!Ue978bm=hVpwWCd;6V}jW2G*p($#^>zjfbF$FUp+A#B>kJ<J%2%HoQ_GqapUPVinl;KxEthf43aP_tHCM;>~i%~P*ACXa-IjkNo)y$T;KPi+0O`WnXM9wpyPeNySDQu?9HFdVd%G&i>+D9o>fiGE%(WU}ULAibf<Anhd5OWV*-U*Nouqlk2YK&AuLC@8J=~H@2ZOg*38j;FD`yr_QTAolCTx?5gwAC$wt?cp{py1fFGKyOEpoWhx15ti`I-F|5ixl8EgL(G@FchN+cw@un2;L1b7>{7ihBG-d1Z&GB^+eu@7(p7xSt211hXksNT%AVl6GtKAw@P11a0jL^#BxR~E$cBJBBk766ynuz>}r+q?o9XJj4S2SkmsnT&G%jvwNBBy@3-tSlkr_EN7t@+rJN?3X4GO)DveeR`)Z~v8K}oP1ygCG^h!>`-e{64fAmaUz(%^2^==m94=HbMbyae4$&>=bUqS`pBvu$tPRgW=^-HXjclZ<Ug&8d|*b^StTWA>E%3JM6i5%~wa^1l&qu(9uO630FuPK%KJN#A2v&ZybK;-4ga|s7wnEOLhYXhd|Bpr+v>5Zq~86}%}x0vItt_}mE0B?j=pa=@Tl-7fWTOE!KQjj`YdcAby&|=UoV_}K$)PVbE1id&H!b}2SnQA4GWoavvs2UNl>hwymo&BzOG&WcQDw<Rb<w~9|ll0}J(c}dNSdeA+>cKiv4SFHtc7B{9CWh-jo;7vge5l`jgq?#uoP_u<+xU$xhv|6U`n*!X0&uCD1`2C$piD6z67`|7pgREElO;Dr@a+U<TFgE>B`>LU7twc(Mx$wl@~MzYM~qHsP3J$U<HLbX+1z3L8o=h?k1zNqFIJ|4OEc?5<8pNw=3Jo{-6!fRM7hZ63XvEw;K3BbVQ6PeY0!A^pXFLz^Zj6)WlGda{GC0-7y>S48iGQuNWJ|joS&^I5u{|YxW36MsX%m`pgR?)rE5fiK&L33snq&rE%Fc{vlFtrodm!A=E%Xn{Z<Qh$pek-N2o6Wi%F>gLyirkSOS7r{`Q+!xPbE7Fe*%JhVuy4MzpOdEx5hG@IlD3$+(vUS4po6-W1TmNw3#UaaKkT3dsj_apqMwowZ073HUpmPedpCwiZlkn+PHv5*h@)CI_FnJJk8L^7M%nQ*|Nl`-{|Km8`Bq<hT(d2v{fdz?O`_46i@D7J`htTtO*JI*obdGE6t>Vzi0WHWOR7_$;Ut8Cps_10$zxy2AD>aj>7;=5r5?uqh)3aqW(;6UeFxgQVtJbvqF<Aun*CO7;2ew7xW!4@A@M{M{2CO^cfFZ!twn@K#oixp+#m1~&m$!*RXe#~bO%ptZEB$9w6kwDscoPZ+`;-9KC733v{DHX-OmBVYb8XWnO~E~q;7GT+{UaO(>6d5#mV424W9>gynEQVpRGv>A(P0h3(jcAx=EHOJ)zn%9CQlWDXk3mp<I&~b8d>lVs`4b7S}{>&z@wpq*iRfH&QNPewN^+Hu+TRIA%%DT9tS?7km$znuyr@W>S!%UHQpohF)vYruxu)NF+HyY4nhjnX9-9}`17b@$Nj=QDqok+N^2S}dNOFd{gB}pqEu?|IY=d@YnA)*?w5jNP@s3(G*`=ZgnXi&!9{(KwwStDm_>c$ptPrSo)nm)TlCI2AXY`aB9D=MFH&-2I?Z+WACn{9jVfD~_iBg_BW{?g{)vHRaU?nDE;<NKeV4j9%<RtmX`Y-~o{QCEVga^r7C(Rd=p6nJFct69%^YHdaR>axf_nvFF4isrT2Rg(nqXEs5hK6N9VYIfNh>>^%8qOD|hlk!z-uDRWxCP(=+D0jRZs*^Dq%%?aknEuOX3rgialg4JA)39eEzJz#Ef(#Hys-O($?syM`WijUchX6N7CqNilOv#!KR#VMwkmS{0X$~EBntvprvD?ZkhA-`ybTqx|w3d#NWLmx*j>|i>M(|YDQVqVTH9UY<mTQ3N?S_(n*7N(Xq}JF6QIsg!?yA)1;L7)0EQUD%6vc#JE2FS|Cbj)ywvzVIcxw#;G=k;_9&72EkMdg7_YpcQo%e_@QUD6|{dftV1*t#baCrOyk?VKuY#T4cwck1Nui(vGEY3VnN#jbxB**T3Ms_#+WxHTA-D%NsWi6_tEh|lBoQ0fGof<=6t?ppW(yC>O+H^@-hBHR>(qb3x=3z8R`NL*_cxB{x-!)5Fqj;}%6`Ev6chXLCHo2GgR9SyMzOVxQ%B*{zYxQmzI(<Yj2yM;);1uqZECW*v)X{>{ETc5zq6t$#xre*&+9A{lPihNsxC2TEM&|greRA44I?TK+aQVU-(pXx~wJ4uyGWpatEzyaa4lWh;06s3Zo0pkx2ol%3A=4`STAqdfDA%6;t@1wox_m-G)c!anE#V(zd|3Wl6M(({5R13+w?EFuY>WvGZjk9>d*`z9L<}pz6bwe)>$D|`@4P)cI%)6ip0+cCh&8(xA2U>|VZUbtKTAR3cQPCUI2L013doYr2(d-{1k+mvhYXhCHq7)+xN2^8qVlc>P_t^lFu3R+EDA0#smaNPJ*-{NCW~omj6N)9c`>#$@k!)7Rc)*_urcI98UL7nQQ#_^e|Vu5!^$$@!`)NTY|_D`$M|W?yAH%WUUlIDfkJ1J#(6YEZb|Caqu&XPU-oX88bwMR2UJ7fLD0ydj=MS>M{Mc&A(@R6getrOH8x-xs6u{U43kZW!tbU(jJfHtfKT4@2I81+-^<|yOVRA%m^YusJSu!VYc6SR8*_-7mzC|GB}$i&4-gqQF=%aBMPO8SFQMb!35L-v4~^#QA;B5<yQHAkA|!fwn(m(129xfH=NHt|OCzAT-gbTP`I<%jB>f<$2z1(h5`kMQLm^$3Y%r(9z?GGR3eED%nRXfNFKAV(rHeMhpL@U~a_G_~Y$~1k)|JXqRSPG-W7DkyPB%U3imwC2i^2;`vs*d6ujJ_mZp3;~l&F*?UMj)H15B`wa>aTFkqZ_4nQa6jua1)03<288A=$7;JI`y4=g?vKd&m0i$k2A1vw_Z3Cu9r)UFRpQ9i+_WvdL7L4RKd69!N#u@G_<k<;SMKmpa)+<8sqs-bkVLZh|qMyV{V>TD?Oft_#H51%C@<P9y1&v5&;$uV2clv$Xgm{d9-Ti%^u^lvLEk7Bpk)as|kADfE8(rH#Eq&Mm2O5@BPGD>x(MH9eQbT|yXCSai|sWiSV9*eD6=AOzRbhqOLOL2eq{&g0u*+5`K21pS#zgFpTVuEkj;4%uNq*e#R6oO8<FnsStiBqrLi6Vb66VcSfs4)OC*4#*&#77dh`A@<ASkmBf$Lbcb2+!d<UHnvC4c59@hxq}S&8;b*Z@evU_*ZKq4=KckqBTX+DhfGF1f%YhY!rsr^2V?!9z_%nkfaXgFC4$f4kkJUEd^PO%lQBM;LAbk{E<|V$6YF!fF!_B6is^s*AN4|ymr!|5!6vX8hYnO?C3mkd)Dm_UOQs$EAN2w!BKAP!DdS?n{lN4lss?LW6Lc=3@J6P$7NMd+(BK6+y`cY49pY_+b5)A^J!Q!OK_ela6vrSJlpeQjD(H&rFnipk6EI`Neq;1xh$)|FQwa)!jWllrW<C!_;Cc?+o+cv-4(^f^+c-i8#cp|*w|Za6@I6J7n~W$Nx53L?>@*FPJ6g}hqF=*n3|s(416yoU7d`<Hr?9@n!IbTw5-Y1MW(@o+n781N3$_cC9b?^r&1(3{vD;U#jX*Sk5ahF@ZiFs_2tbiE0t~kdV-f7+)>bM+hp3$_Cc$(#O+dv`T4w57l@R%ubRH47O?5}O8D7`>$z6TC5SwG?^}lVS^B}lY@<Q*6=9N|A=r)L=Abdi_hn28|180}pN8G&)%caD=auIL<I1l|?EJo~p{b|K4N4|aelFY&?K_Un)1UDU{2*~>kjpd;i(%46Kt1jEo3{+XK|83_bDWYC{PX#Aww^terOH(l^^FgrnRr-Ez{C~U^ycemqP?gl#Zy%m@&VG&G?VkM9K3Q#vK9t1)5-rA+P<_X*vL7MB+gU0idCn4Lk@~nQ-&4ElMRhE4i4ktQXb1>b!}&u5J!QJa8WNj@w0R`pO>B*sDG@=O(=_Rq{mLd&$jnA=1UA~(>Ym|3;4Kqn*~E4UP22MUpbRRV38_pVYc+VL2n=wWln!+z&o_r5LH0?GUmceYu|O(n-EfRVPWiIg4B*!y;dJI7q>E?=Zwo4pq7jiulNkoogTDZYAkTj4g{9p{Y6G#uq#Em@5q*!IfeRZfB9AqceRI3j9jl%#0JmZ({%Y6I!t+}64h9@wR)SZ-cH>XEusV&_x8QP9cLQbbXrA$+%~+4s>IFEci=((<0KDUFcBcK}i_73N@4O?98L=saNIRUT%GVcW>}5vJ?DNIGABtvPCB`YcK$ui&b4FPm;!!XDQ*fhz?+KAE$*M3Q1`O(lR3!1C;Nq&Wky=AKcK`<A#nVgdt1b)XU3{#9vKY7)tbtX<%NPM)WE_Pw{uvHdvcor{<YVpk#RQ?0*g@Yk049GhL{hL=DphPXVDMo6b&Gzb%x1kn05%60aYhF&RCg>}SYgLdQ&09DaRIoG+PuK@fXg1XF9USi3!-VTv_=6-UzsaHtcKfZYw3(t1rZf%PoBIK$K5=59lRGu+U@jxD1L(p4iu}$40>Bx8EJ0sf@q+A2iek1$2<2(QKs3xGv!62YFQ2Nu)Chk^57YSICT-P_6VjhS{eh6CL+qa61=t(wuaD*YmB6*Y&Zw!!W9ah^BBrN{*(np4DQ*ziXiCA?GS-^O|F>eoD34D{NFy?c?c_v^~#@m79O9pPul<OymQ()Yk$V`@Y}re@ViHzho13#+;Ny0qr9U~S1u1lO|(#8i6<Z8S@&K)zDve;nTOZIdFENKn|-vHjWQ3p9$s9T=a%(J#Xg}$IWb-Y*=TpF<q+-7-;0pDAyRld6jG1GYhTww(YIa#FxNxCRZl6Ur^6xl7=zO}eP5|tMbhLmkmp$Uss?M<x<nWbIGNIeHwa>RwN^Vf*mz|TAiMW;x95tYY1ofc!=BZ)@oG$b?(pX`vzeRSa2K^#a8L^a9h?PhZir~U-7@G$DWmnX7g^KQ)Z4FpjF`!F*{S{P7tokbRsF9Y3}DlE9F%MI(r%VD4tgv&R9X>=B%zovquhd3x6$e~7Q2iJZ_f-y`>-GRQcHgyBQ-y=Q^UCE7^RRphveG|M96L8hnRz%Vyr9~wapzQ2jfqo=Z}mi7#P0Oh-!sVcI;b5e>`J@mN|Bll7KmnnQl2xJ@m>=!Gy{+v3BshGb3a3kD}9nw?Qm7`Gn=N7Bo>=Ez6>$`rK-ixSQe|^-O$0It!oFWbw^j4lTiPOdrHb!Y^10u!P~0^6dvOfeE61B`k^MF%7n6w?Q-;1mP2vF5C(LaifI0S6&+E-3??+f8Ehvx8+xeuU-mFeNFg86%@KU8_>)fh5{;KjO~9?)>(t77i@8y<n$qZsicbK(g>-Gfk$h%-G86VR;!xt)o={2!pfGYU$;dxV-9|<p;ic4ZBcq5=;|NPb@=m4u3?>4O~R9M&Ja{2{Sid=;sVBAt#N{xyu4JJEQb|oZRfBDEwj0jQW$AzH0>Uhq>UPX$*zSutUjZ))<j0P$U0=xXQuey{teYua;rJ%(bSEjBWLEA4u{i+R4m-~N5N?}pdICB)$Q#Hz=*ojd(qsv3|?V^=Zw*}EoM4TQJ6oxa^L+018)1utKruQz&;q<8H-2keBYQdLD-gS*USR6!IwwU44p}=z-SiKlX<V6rlUHL$+X_<Mkc+i^~8K!USa`VJA00%a$cml^qfVgy)^bg_(alo@s(*hE<gE&$u;J}?WwY>$ylrFG%2uOI{jX2JWZ-^-2|$Dl7+%%uHpJ{?RlF;^W@XoVASk`=hLMvvQ0uyjq$aH#bcfdXkUaU0A6BsF>(rAA;Dx-VL?`1wGu8wjM8l{DGszFue@PUqQl9t(G;#bYgKv7oF93ZE@?0_%q^V`sB-EkOFG%JAlvV9y68`W+wOzBqCt_LG*xgPdk@jkYBhOnCvWA{`91UBk^r?Tx6eEKNZKnEMS4!p_m5hFJCv6YdhcRGJjWz)qIB(mY2a>-?$FVfdZ;lBoxV|=+3{o?p-vHDJK^?0`9udVzAq7zO3i}eD{v7JK3T$(i~n-D3IPWv65LxrAmt?)NW4`B0_DsvQksh7Omxx;G8W3l4cFAO09grGUCcaydw{5{*X_Zz;LYS-GJ;Q*oOM-n%&f~BdCw{1RLC^jQ+-aUv^*q*7ek2D9GAh9<(E#uFs|;x$kfezmE^Cmn(XAjQM}*&p|g7!zd1QNJZm5Bg9kBM4G2L1ZZ_ro$%PU<2&%a>+Y;h~Y#TK(b!n)*4{Rzbjnv88Q4!Vc?;4t{a()CJu@-Gu`Adm+g!bVPSO3{aIYlGgn4CYJJkOHbF5nuC6~F=+x_75@>ps2~pk2Z)My)*)a>$3_TwB~YL^_YWYpYYF@Gm7KDw>l82WO{1f><+37O4hw<_=#-e<}fYBvVx9lJyW=Qp@ETr_-cYR!R@j;*+PH=YD|S5cCluR&d-&!={H42>Bku;f0>SWaGPGf7p$T#<W_RF1RJ3GN`v8C6M^El|cDrUM#tU)n%r5zafgWtCBTK6BOu&*dd|`uvoDP8S5Y}-!KiT2BYp(GWwHdLf*^6^52^8YxK3U+^#-bi3b-7d9?O*bosRMHwph*j5xc*My{l*3g6W6+Awrsjw;V%bfboX@VLd69efr;DR%^PKjV6IDZ0PC(^#p_LP6O}&xmwwq2N9?F_uz5yymL7#{ECoXe?OSp>$H?J6p|hhe2Fuuh|Mj4~l#khI<GKO&s5}I|OD#URM(5D9G7pfgysx5n$LIQ6$@mAjZ;d#{?2Y&}+EYvnsE+`pGpHy#`vbtuxeG#j6L8($T9@q_Lzs1h^w?AHMAzw%aG2!?*Ffz2o@!$6rqm+wYFzpWBB&$45Vf&i&s&bkD;+!thv^d3gA*N*Jn>T4CSy*(0(l-6Y-7{N|z6D3P`y`pB}CC3YJc2Nd(Oa(U;k63u~YW46s#?=6f)5Jg;)!K2BZfrOsO&>_Sfw*k!**?qanhO_xXtSUwrMB^y9?pCMhONdSgs}w`vJz@S3Ib^|TiT|XohHDMsT5H=JH`bn@iIG&BginllGBqYLfhhHhM|RtvnszMZSxm2I-F~8){;!<Q(gvL|bq1gq*jm!IS&7_k2q6otOCxqw^D!<BPOy}Pz-gF3mB<<rV0|>1MMRsTad%FfyaPbVdz&wK@|@8h!Q8#$#c5J$Tpw~#_LXQ1CLpx(xEX)O*N}Os;Z&KHicxm#AaLp=%&_3FQWK&ULx>or5}BYy&j2vjJ_XRQppV=dFxa6qST|@_HV7J~&bO5C8cLX!5MHARWuYN^p{z7qLy9b6t*qo~Rx%X0UV$A<B%aC@9#NPofOd!opezEZ<6113G`i}}g2`ZD)f7bpK$ZsIh@?E8!S@Zln}ek}f-6=E1oI>bqOR3H)vd=HW#kBK67E6SU_e);;I?$e66l9Ez>u7T!MGEDWv@5pxx{SQ50GKO2S!9A=SIbXuG5?bDJj@Lj>B3+ll!r=;W$zYjsgIIY6Lq-J4<iGT=UK!qGgJ7!W$tPU6<5EGCSF9r4zy6^piPgAo?0U5Z(iBusE8?Gz$XaUXRgHkc2oC)@O_9ob0&LT5vi9Kst>5K&>EZlp1{!5+1-3;~gj%dBMHk2e45Y;u)8G1l9^%a{%`7?QqT#71^<B2nR4Pc>s*S6x3hheEjXV=p+Ff?%#e3?$IW00Lubl@bK6`TVlB39bYGmU-vc{FTl=)+ko>R8zfUo5f-*<grK_6>JgwAh$`Q}Jc}CH`!V@A9SwU!h~W)4-6J7m+Q#6M+3<P@UOeH=d_GN^^}1kmZx&ZIvB2wxKX>*!yLDsr)x_J-X4UlC0~?rn%{7Z=9wKy%qW%1uF3e)f^kc!2QO(wSdL-UacdU2xNW2r9!B?nwEM6MHj;XMiC%#+>mY_ML+2V(2`qm1c=yug%Wa@CR*EtPzSP{_hiP*3+yrT`Dn1#@7)_k()-MDWge?yKpZ+`z6Y~_ybmYdmB#xc9_e*9(7*4YEWR_l%B?$-C?+`540c>UVbTEQ!=#7Huu3_aE369S|9MG*Ca%&1xHGclki$$)$-7GueRGNDn<7lO+)ODA3vb+O+zG{d>JK2CNZl2OOuEoh6y(=Whi&wVcE<M&|eAKbS1>Y<hA4De)2mtf3^(@jCu63KJxE}L{#PL#LXy5oEw*6jhi4tJ;^wnlr-R1g{l1TK%@dVy&`-gT~I-KkLI+`}i7C$#TcsaNM?L3PM5*X#l15bc-c<g{H>=WX;TMQg=Woau;f8^J(<^KITbEznOp!><Q7w=8iIEL6V$zlVvkkZ{GBP|NL29$6^?D?Xb)<jxW6QU&7!6n!Kpe(P=<_!)T~&}g*8A!f`{G#15R!Oqms>*cl+tgo>mWFY6tJZIG)!H#aavwrYndw0Jmac`7}MI8<LA4>|&Aa5WH`BP5KyMiqMu&egrNyjjGiUK>~QaP8nHT869@<_L=YV>phxmdJ&DIT(f<0OVt)F?(0*n8uUhKsN(AXjNm43{`{trFE5;Z=fvyyG}XV2KMZIhoFHTHA83hT_yp>w=w3>ra5mvww!}UM2;>qbk61@>->)0`dW$MwAk>@Lc+jKBJI|EM4$0g5}XIh@z`mcZ}yD_C*sLD}T}EGF*T*pwaKgEO)e)KO7yMot~ZS9v`<)Vg^WA;en^gc!?~&g^XrAlhrMkA&3Uzlxc=vrC}8&N`B==4zI_PnP7;TKw(!aT6KAZ`VJ#!CAi<%7fFn9uAIM#8<KT@Wbk$o)f~ym^#x+R6|)V<2zJo<a#8p}%e)$}PweoUzJT#o_`wW-y;m7oAd_S*RAn!k3WbYWF61s7-5t~xoR&PhohhtH#kn0PVy)_;sI}6G85j5LmRL@_?VSuzk)fjux^yk)3P^TAxyOPdOFTvtG1x$5BlxG5A<c(MjwGlnxTY4Tcns2-?>TDi1ZUxUmx7+qgAm_^o3<D{Cq~Lq<jGR0eRtos56|LvNBixARcPk0>hfm#VfVBhpP#6F5ai`Pxmpb4tJ$!BotyjUxPACb`-k&R{KH9S|1Fl$jB-mcI<~H$)Ars;`%ITbJyF!G??J=2li(GljC~@VmnBTSyk(IJ4;j=IcUpgOJ53FFsw!0s7$cW77Zo$Rn0jws@qBGwYoXYsSg$rONX~XnVe<9n1=6hL6h|-D7p9l4Q;>eKVIevFv)-*ON-t}>7~jI*v@qW|<!phqMS51TU9gTxl(*{fj4`PwrVI`a-bsqAcT;EvN^%=!DXBqy1ef)ulC-RXyTtN+Eblne1R(nma^8Ai`2G}S2df4nGyYtc6)eWmX}1R+`xK|$d9rx{vU=yq<^`ZDnOy=sdPEx*V|l$}w?sd;0$EKLS0e;V^iEK0+)v>p3ly4p=5Jm6?~|*Tgf7Ts{K`p>h*gqQU>@g5PCoSc=R}ap`fYWVRzDo~vqg{MrdjIyQw2={7HM08O)}&jh#eoGZgbcJg)15(P9-R{_G-<tBGsTj=`CQqDD0r-Dng2;)`ja81!+O36BM^Ya2hw0el6Iam>3q_F<t`;-eZWD!iiw+fnfm@zR7(xINonpL7=8sZlbr{d2;=Lh#%0y83?Sm3u%{QG>5g-(A5a~2F7#D`eFbmwVvvv+ZCe}iDA}(_b`>3v3f0NBcvNaAW4e`vqps306-EMkOW6_I-A@LK}UQA$XVK#Xf951FeJJ|-Siz$C{-DB??@2P;Fsj;yo2Fig3f+gGcO&GX*O<-G?*k9__<7j1rM3ll8<x1d$WP}vlvUG(QVrFAjpS7pw_HNlanL};`zfgX(Bt+9eNUNkwM`w{*XL0J>1#uaVP$%{p%{+%E_x4ydu^vFE<{(F}WV)@{?OReFMu0xEsJ=K#kgV-Wc3=KgRRP2XVSIgYUM#-|?k$o?SYuI?Wkl^o7!JOw3GW{d{XLDivWdKpQurw^`&(|Kjj35V~Lsq*tG(Ywl9W5d54xgOK@XYO)Z<)b~|k7I|Kx^s%(qTwlh^9N@D@Z4+ZR;6$w34=VK-F>EMPULLW(c!`=@&Xf9+`mdKL1Yc?f&pv&9x`Sm8lsQN-l5TgDyd#7uorKg;TJjwI+~5zl?77(TZ4V>%rjH+86;x;nV#_Vi(iGINg|~WJ{_?!?+A^OF_LuUA`L;8lxtf;aa{6pb^Gl!XwkD@0(aSu6ZA}SMcwYMDGk<QsAivB=K^x|F+h9F5%eXYX`Tew)_|#83l8dRWcMDN<xddZl8v9A~<xy+y&#k-9v-bY{`g17;tF4w<g}}O;p5|N6a|wE8`3nB)Y6K(;2v&%3-97t*h}N1CkfeR)0|94wlj8sqI_Zd$OVSjB*@W)(j%B7x5)bPG(8H(Oe{eZG_q0RF6NC{@3pZ$Am_r;`{|X?DWUYmR2DUw>B9<l`jD*pK*zX^1gAyVVQ5UYR?m$36qXx@3Q^iUgk+?(4n8lszI}kp8-F<gpp{t}eR=wcYZGZC6&$%0Y4|CY_f+Wa+d*A!iubU+#^{TW#Y#Q1hxM2VrIM`h;p4YBkJZGF7Wr<Gy^`h^H#a(f6bSgCp=2{MsnFw8Ok{S3xxD-XK;vZf-Z!Ni6$6nlB6bK+Q4l^oxkRidsVh$^1cFn;H?B&3rGo}feF&*xn1>3dn!4MAe5@b5ToWQ(N@K4w`@R|_S4YMt64kh;l#IGH7!R=)LUQn!p0gUXCkZecF%Y~E*<6Z)B?k9Yq3#$y45;;bquuS=X`%UwTPk;N3+Ytx}9Gb^C?{||S2-PHJV|lW3*oz2n6=`r3Vh~3Y{g5P63=J=pdPEVR&#Bxvwkedn9TK~M$~90G+J8T8@13>x<FliqgVVLX32`k#j5ow-xYQxov4YLa>P@0%PnI|;xFmN;Nuy9Oh&1Nj!luF|t-^xdRc!Kf+nY}0MG-7Wuw6rte=l^HPm8;>iKQs;6hd~-(y-~ggMTMS=V$F0;#T<Hk`_i#WPq#}l_%X>v>pZPwLIBW9D5@504>~__4@YCx3z}&-*$5;`?IQxMtQQYO8#Ffopd+`fWFp_1Q?Rr*c?Kj?TE8qOxlS6*;qu1%AFh?oyl+u7hwk4)(mv2Gl|_2A0M4i##xy&%U*|<l{|V1v^|><l|0j7QRcV1XYF5he^rNrYB8&T{Oz<4lx8pyoCTd`bnTjV^4JjubB~|31?q#UxI{Xw))vQyT3%V+ldYgo|4F!U>3keMrUH3_>N-{hY=VK_!)K@ucxny7tT(@I5z$m<am7J8+T{Fx#EJc=Q`;X_#h1Os2$35e_a>c41z8;Sq*rcPU9a0@!sQ4Mak+qBFq;7=IbVKJU!*g1F#&H0h__hsnBp#O;Rd1c?YAW$JvNZCXjo-c0#B?ror88Od;&@8bV$@0L9>QFIs}gqK9Omq8Rc>*Exi~~z(}ESeZT$gWw2V6z9bHpyaL!?pmn;p-T1!27Q<!@C4+ml$Y+qDi-DKu1$oqrz3auY15zfsy~G*E730|8Etg+#vSzeeImUQwEQGi=Koi0E42^)aE!vh<29)pzuX=(X(ysB?mtW-^)W8D<d~i$`B1q#;AU?yAU@wmB*Kp?Jd-#Ic<GrK9H=Vc6R7)1F_Ha9*a{TF_m>RGKVd>!LEyR_V2}YCaG%TH*ADR!v3JObx0U753^CwOjme9a(F_q@ouz<e?77-@kpE!8foa4^EoB&vMAHa1Wd?H_2hH_SB993^#ev_ZoSMPmStmaRwm-FV-3x0D0Juon%wdt^Lj1`SOJOlG=#I54NL!_#pb9fe<wNKual8@+@aQy4pk4J~+XK%i1ZS#-LQTuT3Xuos#wuNL>raAoK{LP#8Nqb+Ug!Y}a58ChAXD7eLVmJM8AfBTtL6t1`)#=gs$zB^brJVDuAzE0%PKSYLe*mO0K|97MqD6&f=R7X7=t6!kgpYZkxIBJ{4G5oPStEWg#$}w6JD<%}@_RC1bX5<L$){6MOP2z#@bT-{Y8}HI!4|8D#UC>EMv14l_2i3^YmusE{<UYG4G&eIdofVGC*?HxJ=hMmziU)9BFGoCf}=*xV#?S@gRJF>AwZTP2Et-SceNO$RNJ;<)J;JEw|5#rPJcyGg?^-rVYdzIZ*JYMh-MYCkEP(@N5iWcW6QjBe%HiLU{1?h86JO2oV36lWM>}E;H^3h-<CFy+yS)VZogb90yr_9XDzf6L5U!4s^}0BXWQqMO|7l-&o{{Is>m%e55#Re4~dXGYPnlXJ*N>Yc?9RAk<4Y^tsN%`n7P}`WsP*kT+@==`4+V%g|EG&illg0CA@-*7jI@vWn@=cu;v)<;24?(ddafQrHB*-MLy#qt+@xt7n{ACPo`^lyG_`%MJ_`I1VDmj=%Z8*s`*gT4<21Ofne*QFAuL#16NR_L`1&sT&2l#7a>SKsIB!M!9NJ5;z_ndK20&9r>GK17Zy2tM%2uhIA3nuj4ydA8nqqBGFCN4-xpPiDb<O((fAqDOd()nX>pD=*<xZy5n}pla^Sm(&kPoU$QZ>T?)E1Xcvc#Ovdvl%-uB+8JG=$Bs^q?o5&g)i60B*u18_gYLPY}UK8aBjC2j<(6j&j+t8pYu-%9rs1kVWY%oJP&8zc$I3305*z6b~#4}uJxGo4Jqq6f`^(2NKyo3k#XDV#JE-|LrzTb_ciT-PZNoiXkOd1gmUt)5KA5OiCVgqGcCz%!qTp;O=nIOJesLx|QIOT*{;It5RGbWRSQ%9!W3-*i(b9#S#{mlT>(d!&uQt6RobGSWA>f}w$s)Os>3P?Qe)iHcCbZls2bXLljk{n_xJ37`t0?<(j+fkM=Ra|-XsJ||$m1<lmMlnNGpIR4;uFNKt#z8#|_6L^o^xqhUyZb8c&5VS8`n0wbU-#|5_8!2rTHGDwOKw}HV{J|pgyWPXxx9xr87vY#_@0}f;blRttjRNgxK^8WGk8ZL@Y4`+wXZ;?fl%ri)#Yr%q^d=*#Fu)A3T1wE2qI_#0T1!1vs}k850@7>(CS>DYf}nO|^k#>z9F`NlmY_Sa@(+}vkK@b+Fm-_V@?dxpN^g79dlK)lm~mrxwdI#wF<_Rh3`{lcC3R-)E0I(%Sd#gZX@akQC-K!REzBfC@Ct<yVl;xgoZpD^vEllSKGLW%-=IZi(d%18BYS3&0g4L(x~zVJ@L^z!EOrGNz6M;p41Q4y-c2MyRFtX<o4CrMQgx_823gz(lY9jFLDNYF64SW}ZUg-e9V%RNonRebT$*p~g-gFPuD8<j4i62cL=ebCAw=b^p{(!i!G^V{m}gfQE9T+$Y63Sz9PKHm4z47xGlup6-<2dfokT3@b6hOR_!wTkfDQYneSBqYie_MKUqDEE-QegJt`DYSj<?14?nm_<SEOjbLiAUKUJPoP(s83JpS$!1&c{g1lwfMEN0TeT`pn^zxhXyh$FlzVQ|A82%CaT*?8BE|KCQ19{{s0r#BxJaH?hnFw`4u3$x*W+R`YKBx>e@H6~hq~*9KM<y1u8phg7~MpG-;-Yt_Q=zYIA|jT*|Lmbs_PN^5ncm$+&T^e@v0u{<MHilGzccxFMc_SE=eZ3+xA^VDwHV5621l0ddmPb-=9VMV@1tmHs)$63<Lz?x90eejgDs&l|gsXiSou2JDAj>dl%qg0zuZbx!mFg_J6<M!`C_>YT=CK_fpFE5{hX2ty7GJjmWe;;mLnj@!1O>j%})=d8-EN+ph<lqArhK3SHDlrbGJe91D`ZS+8-Q2ReNp>XW6Iq7U{;i^la#|1i6-ut#jgiL}<8d<68y<y8@eqctmfnQ!W4?cYSBfy0{m0@mB(hK^wx#n~yWDKP3`WH1<T}<U-`F8urv|PAO>;(Xm<4$V81cYzw$I7^SabwMdzMSeSgitUp=i)k15breD$Pot{$adtdfr#;Wok4RI_d6Z?~2tLe}MWP-_?49Yh(lv%g#xXgKEc$xq`$|@aomp@vp}xM?bVPfbk{P;?V~v?vx{OHw|t}RsahL<_UKb)xZPoNnSmEiXaihY_DaByhhd!rvLG6?U=wW4=3|C;Jtxn7)JbY^RUTcyj4n>XWNw$4+AyCzvdN6TE#*Euy}D!ZV_WKZ3M<)iWFHiJ;`V7YsOJV`$b6^upDN0hIme<B^0x6Jdsj&M$*?pDg=wCK=GQ7c8&?zqc4LK6d4&Y!B8Zyn2%94NGL_iA!+_IOLRl89<U^oYZW(M3l1j?{xF>-k-|`6{u}iN2|>ZJ##&0DHFb4@h=arqZFoZG=&Kx-ldrY{Rb?z5w2XIkMfb#$NT!OOlqp)rBKZ2NU%$Hjs(<#?k6*p}>h!-?YV(iC$S#+b)UpY}fe>u0JXjkTo6h6Kyw_qR!O*HZ`sy~q+M8d!YeM~@T?8u|(3sdL!M8l6;#;g<&Mx&z5o<Fd)@F#|<P@gTBvR|nX@nA*b^V<;r>*MCz`aUUyXomAUaq+XvBbT;9F}R#V#M|YCAK-y2v1?)M7ZxH1J4r?qDVtwW*DK6;thtS$4&DZB#Zas9;gSMna5}B?kGp#J>qW`uLnS@ARkHWKSaN=z%lRv#Xh7T24IGTVmY_}sOqJj#jNQuQ~aoT{8O=g4X|`l14riW{!bdy*Q2faPZQVooiTg?F3`^t()YPPq_13QRo<CZby{P@Jt@t?k4%(bhH6rw>!gAK*c6n{#TTgt5MSk%U#&3&EgAtM`mYQs#yId9U~0pdkhf4%_R(<c<u)}HhJQ;xG}6gI5eYAJkYHv0WsaF#5>-G+;kbjQ@gI+9UP*eq*A=9QL^H@))Y62F1K48lT1ie}x6ac7^GuDwN^}5m%h9BfeutOpI!C|q*k{slgK{R~A1=|sg~im+(94_lpCTD0Sh<31GbkS)oWJcH#>j2{*Y@6-SX(ciKR2xcjqK^HXGW}#O$Wt#ESfr;$8l}?U=-Xr?EHx`XUR2Ol+5fhPug!gr)OeHeC5)J_ypgkLnd=DY-}$ZIl@^PFKg+`^QOI+OheU7k%rs9CsEeUm`dL=?Ps?xSM{Z~buKPb+R)lwNp2G>j#moAS+4pBxjWR_JWGtT$L!l<H_TC-^UE}?0ClO#61u1ak2*q^;IWZ}vc4@S3+~->3UhAci%MF5E#xlJLHJp~$3h+|cP4cJSh#+w24$9dDB5-fs3;PYtTnDTgm;yTu}jH@Z{&&fQ_LcuVSP*eIS8p0)upvAzGPL0&=iHr;_QGqm&`QfUE|A=aG?+=bnZz~G0?Mg>vCb7tHspHOPy$>sUp~!2z_oGEJ{to7p<_L{b|U^GaI9iBXn4!M3&=DsJMz5#V0rTMO8J^4STURqiVcAClV%t+`!JsdRCSZtQrL~sVX^})<t;F#n9K)S92U82Zm1TV$>a9_innwF$AXJlYv@{bU+*o8GmJ+8zyVRY)`>X>g4?Jtn;o7VD`tmXPqB92c5HD<Kx}Ep9GV1YG=p|55&vQe6M2fs>NyLrVu)okI1EmrlJ}I(9of0Cd@QQ$=Ub=-|ol&1eMP)Lm}eJ_me4t_e8MIT&}FJ&6FmmsoS60RAYr2Z5@Eu)I?7_FIzqH=vMW*wO!l(w)$$PxZ%o9&(rMh>}F$Ns)u-;iG^tfp~o7~{z)smwMGG4MZYnb$XE#S(Ol5Fn-W^^n9BrRtkc@<Xv!rAZx*A`!`@^(Mxfr(WYmx6H(<{RhXj@a6f7PuZsqfGrKFU_lpu8y+z!WOqo8WA!zTqL7j$UR9SO!n2<F@0av&Q9gR`4c9**Ndf_kj9^&BEZJpdCj{Abeot_sque!C;6rDy`CNWmtxH(it~wM0li?9q`T43p}WII~kBHeOr^ma__WZ{NUQ@n^f%5S#R3n;w6o-!(49^FG{4wWtUTKk;mb&o%@%!sp{j3^5c;4uT|aQ8{+BOl?tO|9l~Sl_`y2xVqB>#sBgS3>};mc-apJGF3242OxjQER`ArzpfzPQm(8IL*#{<PH!h4l4uTrD5aWUx%4z_CB<b5cxm`AvYJ)iK!C6zSUi1~VBS+mI%lK>4mvMAY(Z}xbvESY)G6Hj<_(E2xA|V>RmF)Db(Yxq)Vm1ZsXR;^t+e^~F)EjFKG0?rC5XM)odb`dUkXwdOVSp{g0g`Cu1diLBQny$F%rrIIPWn{ag0+O5`vaJ?RIinej=d;+yv93l6Vf-X+^}rAPjKvQ$PwS@ChmptyBiZcas(PR0M8C$lHNMJNxx)L18LpkW_9`q`@8mm1I?%7QOdtI-eQn!IV5wXmV1UFSisk5q`ZVJ_Ydwzrf9(*|-ATCTbQ@=_nC~jksmYuwtq#mn%zYDT8v__{C;BZQWUDiwI3y?oil`pf_XeyiisFiTSJ2Jdqh^+*`~bV2+^t{jzKS&AMlpl#B5GX41VK!s%YeptJCWPz`(O9sU~M01Kw)iJL#Um*XuGqCZ0-&W1vqW-0!#+Ex@%30?&|l3a`50N!kk^=Y&wU{kn<fltU>Zl26;F}Mi?e4!DLhOG$A7o2wXZPg{$$)hJYwbA532wJpP%2#4^uV-)tX`4smh(c7ICSUXdq#xd9w(xNoLUHM*;O>DCR66dUE*VW<A^mjJodXP^)&F~-!c8Z_IgGq6y#^`K4_``6_fWT?V24<j>IInFl^wTN9t=)oj*qT}hln)Kv0P^Wj2M5s9hDtLW{M~W-ql#LJ0dd2N!k+>6J2ccr+^k;#j(hBvUd(o&vp+435!qnPCCbDoLol1&ZOTxK8}Apde`Q3{e%i8(q*I#T?d-7CwQwMFc4Lh%(Ky-<64Z>eOFp@iSn4ief2l^F4Z!j;G9D8Jr<2@h398)qU{&q-(Htqoq=Jok?wg2rHs>-Q~{=9W8QWJgF5WZCh24_M>7x}__`1gp4S^Y_1odR4pSAr77clIf_hWJXzGjylh?2Ib-!OPjX_wws++G~)iYV4ytCQx`dYN{^{a!)^<>OHU%zS-+Rtmay?#}fzh0e-o!IHWUW(Nq%I9CN>UQ3`Dimrs7N>r1I2C*Ewf-J}$H*?;5r=uDQlWwYecjPvmd^l4QC0}=UI~(N04B$;50Y*=7d6}o+45R6TD^ExSM{3Tsd=Z#9E<|+hxqwUP{5&J13MC}<QS|?A6|D5)BP~He^t**LIvy(Q@q|j1xnBv9F2cKo5Ep|zQ&VT%u0R=D&llLnRW(mC!$%N>^W~K>n;@hV|Ug+LvkvXFwdapg{(}p;+LCbyn82PHJE13;dx=yfp3q-`w8e-%sT8Blp|*`{W$FRlQBQ#A26Lq<IzKB(CLdBxzF}PE)>a|Sj%VPKsgwSZSwl~tZ^#J&%S_#H<=CR53j$)1wh}aoRcJ_CchEg6w=k}SGe4SC?(3<e)p=be!ddt)p-8;`|rPhRj048shr%frt0RRdbP{wynCQJ{Wv$)J+u@`MP=1%j(d8)g3{^HtKHc(V(q4{!zJzIRVes2R#%H5SMOi_LUdBu^t@g&<rL**-q9$D4{n?wS9PFQuN5oUolgW^Vnr~tyL`5L`cwS(cL!A<V^xFZfzz*`c~TpU=ZZY6;Any4w`oO}-SEidgAC7Y>*PoFN03jb3iUJf|F%eGc$Hc|I}{(kbPo5AemRY?&2WQq2?sf32HXZTmr~w$bP<Kep?ehOo|x2{Y%>URxS$>IMvNf?S;!%Un}zxtmsgXF4VWl-n>Ta@+ZefQ)7s;H;rJBg-N!bp>6U1}Y%|`R=;L4B1{_T(z~6<f_6Ou*6yxmPvBtMQoJp99)3c*vL~*ELNHoooedbY^A_oL~aV)-;PtT9rCqH*ik50f16dRyJnh%K!gwHQp0HPv<R>)*DV=hT9lorotNm3SHSVeCl;1e6u?XyILH)MF50?x?a=?fZiel^~{(%G;v<cb=1A&er_<?xJ{6<r|9joOaQY_7{%*cUBh;Ec<Q8gf|?qX|+~S#Wu0ZF>|k6<r?iZ4WVG#`Ek|kI^zCaG)KG6xE@btXr2#6n1X^wkk$2SIbJ&4D)G#9?8q8iZ%e!@o)`r7_ujA;|I8G+N$+#O6DS-l~!Af!M~w=OGqg3#HJ2NJwI`)X}bKl*`fg9P)(t9r;JCb)L|NMA6}wMsO3Ky48$&%hDCat=k-0iY`Tm21jm9`P98<DC1{H@h}LgNASI+8ip%b?qD3T8%{q}tpE6>$2!&6U0sY(XoOBCF7gxNGYkMbcn7_mJFY)oo(O&!XG=6(>bbcKCVW!$|pY87bC?qdV!zxd5Xt&BcMj!=!^`HaASLjH~NO5p`B6pa1^N`L3_t3H$@$=#N!GV<m_R*Ro$!u1bq<7zMS>mD@@Z+v!z+Uwx(}%M0+8WlD^{bl2@stgKli;;tFS@<o7lP|jh6$rd?}J>B*#quIEM3$@931WaL|XvIJM4aar9GrJT^4-lahu-tX7hZiMwQmmB>7NoRN)9aZMT1l+lTuZGeJ%|Pe22Y%e|SgM&UHbIF_%%hJ&ePBpHkrsXWBJjj>-*KWZ?7f*6!#A>u3?PsFsz_XlFX{&2AOQ#IJm(BGp|$AI6c61|z7*6`FGl5>grO*te3xfsjYCH`zUp4(LQvBVU@J*SH)l$oNMtUKmZvpFN?p*@a4Qo{^&BAa^{EYSl0DpU$RNF>VAte3A9yJIq?*JNG2RM?(SN_T{yy69fyZCPV2cUMIAvvP^&(8Rl1gBK$^87;AxU~j+yOi95+f(C1oKr}%37_<W_gN^y(7NISxK|Git?7TQq9i|oUlP6;eKq-qh$d#(=Od{NP#(EH*B)wz^jtywqJ_?ppJ%;|4c0J+|>cuHZ?X>e2aGI)t{@pn|Gucpg<8wm#fMTjvmovMk{4*F=atuD+N|hW=1`axi!`|YBXjM)OEUjrC5ID2pfnEfDb!Xw8LKq83U}e$vDp@r3r)a<fno=<L84N#qdAo`SWgEFifL-xHaD(lDv~tLKJ?nWb`Bdc|(<X!k^x41VVR8GmG3sYv#D6(Gu&+d^yk-!JYT#%=>q#8Cvb3kMsUuzjml@wDs0X1KOVuo}AgIXG>ng-RjnEdNo!Mh!6K=yZtA0?|^}L0X8u$#|y4++AuW@>|e{_E4PhG%v*r=6-EQnR2#g1&k<E`ZtILvRhzU-MzdsZ<y6XXE+&``Vg(c9T8k$#h{eK^o%i%q_9u^wqvvuQaJxK)5lGd)YT1`vE@Wh2w@m&7#Gn6@*@(f&9cS^;}LtrPl$v}+y0E(Y1eZf?a8_TAaUMFHjx^1UJAh{11U*uuw7jrQHmJph3^F)5L#a!78l5lhvr)k_e=U|FMc1)n;r)L}Y}<;6+t_xiK~YaaRQX|Pibq!e#m_WO_1#~)2np-^-XXbnR)m8t63?BsB*ojs-MtNdzCY@`jf8IRRys5~1ng5Eg*RyM=QZ`fSLo)TXVmvl6Z_|^_sEAhBw<T4#))fmBMfHqU&#Wt8-l{iH5&7`j~yj771rrifHH(0B=VR$dJRk}cCRJ=veo6V<h@H!tIMZ(=4bQ!?VyHmh{!t<k!w)`s<IgI<D289c_;Cl-8;S4WPz4k-Woe3de$+-+|nacL}X!p1i{RC*<AbL<jVhSfhE@)|S3P=!jTLQ?~j5Mb=tgbkD2FE$uiajz^kKmFJ8<HIYo^|ASMFIyj@`OIi7zUM#ZSiL{0OQ0Kw6Drj+M*9nRBWVMIf#_}TPqFu6WJv}*`|}Riz-b%X7U}OQ9c*6YP+!`KOEvGge1t(y;oq@G-^U30v0}Pg|h@gfg~=~^c{ZWgJl`WKm~SA-f_O@-T5V|W#Pz+a1yERk^@?WLB*@sIn!gG#~C|T`|<4T7%TNe2`5909*v)O>^^DSGGn%Oyfz*y?>HG_1igW*`GZqtp{;5U)A`9kUNChgiB%4j2B(ZjAeGO+NyLKvi1F4c&*#IYhWTzEc^4nI-H&A?pt2-(m+hu=w=y7lMA(Y%NDLiE7k553-*#Q8vik-(p1Uj}C{09GQaw*TgnpYGNK*2!AUl@c5L2;%PPQHE&jWE5S#7n#gXfO+BQ*Z9*z8biLpp3Z`i+ajW<0r%1si9|F)&EYz=)}=JWdl3yi*8&*fhLw%&gLY7s2aOX|L%-B{7|za;_+_8y6w2c{&mNsx)(!t%0@X*wRDcxb6Me-uo#&X#<FEm8+}DU@{KlqOK4ik@8Xj1SULXvp#~b!40<#@)4AmRnl{Cv;4N7Va0Yd3=II|SUNk?Px%=$VblzgYCCY5lql3k+IJNdm>^X};xGPKQ(!;2T3pvLWu3!XD`D#!X;KE3RH|_LDL=EtYeRK&;GiykK<<uu4KfqcGPrCNv80mqli0DmB#c-)W`y2hDz&C%9t_xEbbIB#BSJ&#Uyyeg1yiwSRRC>7cYe$RkHbpE0t&!#F1WZ$r!A0(n?g;M%r{QMrs0p^4ST%n)?J!&bp-%)7H=nK%@dCkg-m>HGKwUq8k20bm(xGK!A1iw4FXtOOabm9H*gWGSzh~1!Fp3zA^*<6{TVBNduO+Wz*efqt7^6yNeHt6kbKo<_fIyP-5_hLW)tff<+Sv}lTwn@roD<hDWT6X!oDQ;ss%8o7tQTPqk*fGqH|eV3X+JdFig&P@s2JUtxc&w&S=@hCwCCktl10HH@?I92#m&gN6<#5;Ph}(FIN?&2biwnY+$*Kh??Y#l5fn7jbseE-gb`}b-aF;rd8<tY+cAZskP<@R9qr)q3MmzyfUaPZ=wlYcUc<>t|@mK4VSLUGffj+Ae{7+hL<OpL;Z~=_sOhWAq)?R*<VG*W>qrz3-JJ$3*==?v6Nb;j}*jL*87Z`X}t%6WNjSlt+noa+4B}fZXJ}$7*rLQNq4P~p;C8)hr4HWw4$~=O8P^puQvgQFbGY#=z)R}qCP!@r9z(T&+%J;0wS15Wyy!0?PdYCX92Ng#FWdBhp~=`ijMOefr2oXz`oKM)`2uXa7o_^G>7I!Qqwn*=<@~<9dvL2A9L@;cd=sQNvh~<L?;&B5~^A?mlOogViVmRELikd77nF&-oq>RIp{8p_V_3+nD*SLvaeA8<R*d9Y|6oQ-ZAtgoXHfzmL0iVl7$4;drBZl(w+BEQslClf$M4DJ39;ueK$vcnDziI8q|4&4IuU}$UY)%)e7K>*gmwUU=Lq`K@lP!4Ft7?d-(ayY_hn%2@Zem?00s9tiwYs%q8F}x!%$b^T`w#C|q`-k|sjt4EvKF;Pa^juv%*LuqFd*%Cy7rov0n41}(W!#S_h!90ehrgWJMXoDs^gyczi5FpONH`{=Ugo3>Cz^MM(Fa3F3_AF;2HdL4;nxqI9(F^<@GGtLhinGw_6_>l&y__$&u16eXx6HHQUvM{1NetglmyujUfS&)T@zAsY|FBH-|XDY_0-g;phizUEk0q#e4Qv+-HAsOqfy!tdX0H#MGo!QW``y9Gb$2RP|gJU4xZ=e2jc697=DAcdqOh<bF<zICpfUZjZlPj;*s+<GgF}6uD*p4dC!e)i+9UUHu5fr;8?i~KyK0G@*`L(LItFI6VDudQ1`F+W4p07&NQO<W(Lw!>1D30J!ANii73?a0d5Vd;Roux_b5CjoGOGdRA!Q`)jn^7@L@^0>i1Bthf%r7e#6-o_3^`jjLJ;OHD_&r|xAxa8X;@CKok0tY3`ofO%``~pLXD;*du_3TpvlMUL9y@AohN-iVREPNzELuH-OC$S%E0fz*DrBf?u-|^Odwy`Hqij_y1(s2z-7PDDtlxfE+y;xK((Nz<UsbY<Z+Sa-)zX6@zQ6e9n`htPp^LAqCdk(WVxUIQPE~9(4TljF&Ib?jhAD+WxPmYd13ciF0SM0ajwwZG0{!3#DMpc*ghW1ahSW^#T`5KaS|jG<@ri2^T#r|!%x*bZ6UVc8Lp{JU{s#LHXsm{-KxUrSn~a#R*&1ERY_WdoG}=h+ZL0y+<Zq%3g4ljzu1hv5V|jvxhaXL5LH=+^V>H_9g!C^(+EO99k276W*@TKmzOn0<Vh-6pASPW}!vh|;9*D_OekQR}<aLAzM=AM|ZDW=gJd?OZyE@|)qljdANmAi`c4l+h9nNBgu5AX#yPXpYT9P;jqWR4X+4fN6rg<1Rd?T~1@~e5pVv@L~MRc4pbjOTeW`8^zsp)Rqob+;~HRVDv?|by3ZyFoQNMRxui8OLoU<khKxXTsh5&be~h)v%Lb<z~9)aTz>z!54Z;`agrzci-I57%h;sPI)6?qBs(oomLE;zLarSf$&(iha2@o5$S&_%?FeWWDx97Lu!MV%NwkFP+&)+Xx`rU|*ZK>0U@-KNMeXFTBaU{qUxIOi%nRE9#46XBk9})?+c^gl8xO@gn^J7m#(gF(ePx0g>Gq@y@c{lUYnm?ISs8<=lY1o+;nhawW&ApFE(%4jT>1Hm!Hrcv)MEKA1C<NecZaTz^xYOPbvok_)N{N8PJrgaS+!zqCq90Z`yns)1iASEZ<*b*Uk!*x~HwJrb}@tx1(^Dn<5+zQJtNp1Z~aJ{YSdws%FkLej^Xz80b%3y}#ombS(O4?7v-O*&wiXjX&p;^`&AUeKX5yjoB=NvV6FqY4n@ve{&eE-=(If_^RYeJ&O9G)E|G<>H1)n^sLE3C+@2KNq0{6S^dCKKPy^;_B7HaD+ag)+=?o>#SH8Z2Ki%806W~%Ub^CB}reJh6k|W@V&VO2J6%dm>X;sXhc3VgFD;{AFATZkST;jf`uM@0B2@(zM5(nIqXe2=<bn&w>_?<2ik{-=lbSo<qVeZXt=cYl=6YfxVx_3K?c+iovg4oEbj+(1!Xxb(G7>}*QM*X!)7l4m*X*os*=T1S)ZJXX)JA+vbE3{T}pc-43T1Wo*(B~9c33j9}XMdk!%9IpAnTH(2F{nC_s$d-`3R+06~hTJ7D~TKzW)Z!P2~pSyh9jb}QL(+)B2@YmkwF@&IaO0Lt%~x8x#fgou~5&|~8KX9m(sM(pe+Ee$WezRU#p=62G+4O2Y#9%>E^hVOhzHG_?n(AhHh04pe?5SQFi5Bp0Geo3y*JL*1xyix@f%F`UKip$xjTL*S-^_GKrMqe>|u!Cf1T=QSkS%5auSVKG8&ll;Vy*zoU-;Z0ZRwibWMTF#4ZYwPE59RU>(OiYMUe?WW+v@$#BvZ))8fnOuPuc|p1bg7<gs1q_W^U#Va?(2-0cFYV!%Xh17RfHc1U1fNHU`tq<&kIs0kNEyhGkcgrsB4b_FQm&a*(@cbW3s1RD63+YWUWdW9`4n=KJqdoEQCtSQ}`2A;x1%8)R%{P*X_A*`n)yl}rurhKMMtZgreuz2pkKWdWvSfJV#~aE8@#uoaX=6@up-_E!~E0wq<=)90|qgw}4^iRW~JHXiSuo?`LlDZ4fKuqE5|X18;oDqMdetNNICE2J-Oy;v62yUny`G3ISk-b4<2yvSq>Rh9w$3=k~}xWCX($%E+P$CUnT!MatTU?<G)AAg94e?HK!6MlO>;Q;9vetQOMc7uq?Mj%etf6E(f4no(>Aa<SLwlVr^lwt%z74BGqd~FVD<HLG=(P*gUA>CX(UVrJ05GzNu*)6&*Dt}m)3o1Go@6j8E0?P*waa)~9EVJTLT#RSQ2;*O80u$1JrNMnNBRkLANndP#QJnvzC*1^UL}s+%l!8P;t{vk`zC*<C;O*p3RW__XS|JDX&hUN8Xd@S%GSv9t;LwR>*Sh_Fe7l%0z&%lr^WI1-wYwySeLXGf44AIV%_@gcq!n=89yLrXE<s6P355muNImoDY>I$AI;S$kdt5e>r#_)F)Tcf+*JS$m29jk`K{jKCt=d?b<IM?X`lD$}tweEFAD^^OPYX-r9S;TwgYIH9Z-vDz;HiY5*PCa;Fb;J8in#LVy(se{DpgT#=5+o<2^3Y8ul6==v>9>b@tGwC1Xu|G0cw@$@(nPW7u!4h`3&@o8+U^)P9nHP*|;I*O#!bNwLpFlG$!eerJvC*+na6P9w;|L%}ti3e70KTigOk2e@Sl^(})i_xzbRRql=LjQ-Z5HIXgd&A&QFN$_q<I9cIyPmq1dOoe!eh?r;nWq&veA3=E$@4QQjeX^s$m8__xnZWbW(#dh<O?>_EqQ*L-tvClC3>?_IJ6@B2~2Xrkhi@H1>uj;mlAw_)7aTaV+CZ{?qym<{?xa7H^f`Es<Y*KvB<iV4|&B8!&wm@NP%Q8VBC>JRD`(n}|Oozvr#S1ajkY+}sc~%1O-oiC=i^(WS3ksS{T@V9XEbuorJA!zWJpvEGy_NH*IW|;xc-0>A-zExsS7O^IMOFQ3CgdrlY1%+xl_`icRWO<fnB#A%v06LYMSH`4!Kd!lvW~1+BH#0ULV=E*JyQr6ff)FZat<&VdnEsqJX}q>vwla0{my8)F21+~?ca>Gp*lP`1Y{CZ*#a6z&^%cc*t15-2LO@rbIx8{;!|`TZ@Ctvq{_~{W-;yT;R79}YccvrsX!#ks1<!Dn#!>{W4lfv)S5ulUB4H<s@i~K0?*=zT)fG8mwJ@%Bf+<OV#Jr(mam$CyV6?~jk~F9-5++Z$Aak?_L`P9-)Ys>YJ-V<E>1(SRAo~z{%jn>*%-&6JoVt_;uPiFwh*1mcybD2`+or`qjN_'
_PHYSNEMO_COMPONENT: Optional[types.ModuleType] = None


def physnemo_component() -> types.ModuleType:
    global _PHYSNEMO_COMPONENT
    if _PHYSNEMO_COMPONENT is not None:
        return _PHYSNEMO_COMPONENT
    raw = zlib.decompress(base64.b85decode(PHYSNEMO_COMPONENT_B85.encode("ascii")))
    if hashlib.sha256(raw).hexdigest() != PHYSNEMO_COMPONENT_SOURCE_SHA256:
        raise RuntimeError("Embedded PhysicsNeMo component failed its SHA-256 integrity check")
    module = types.ModuleType("engineering_mcp_embedded_physnemo")
    module.__file__ = str(Path(__file__).resolve()) + "::<embedded-physnemo>"
    exec(compile(raw.decode("utf-8"), module.__file__, "exec"), module.__dict__)
    if getattr(module, "WSL_MANAGED_ROOT_MARKER", None) != PHYSNEMO_MANAGED_ROOT_PROTOCOL:
        raise RuntimeError("Embedded PhysicsNeMo managed-root protocol does not match the unified bootstrap")
    if getattr(module, "MANAGED_ROOT_ARTIFACTS_CONTRACT", None) != PHYSNEMO_MANAGED_ARTIFACT_ROOT_CONTRACT:
        raise RuntimeError("Embedded PhysicsNeMo managed artifact-root contract does not match the unified bootstrap")
    if "artifacts" not in tuple(getattr(module, "MANAGED_ROOT_DIRECTORIES", ())):
        raise RuntimeError("Embedded PhysicsNeMo managed-root allowlist omits the persistent artifacts directory")
    if getattr(module, "NAT_FUNCTION_CONTRACT", None) != PHYSNEMO_NAT_FUNCTION_CONTRACT:
        raise RuntimeError("Embedded PhysicsNeMo NAT function contract does not match the unified bootstrap")
    if getattr(module, "NAT_DEPENDENCY_CONTRACT", None) != PHYSNEMO_NAT_DEPENDENCY_CONTRACT:
        raise RuntimeError("Embedded PhysicsNeMo NAT dependency contract does not match the unified bootstrap")
    if str(getattr(module, "BOOTSTRAPPER_VERSION", "")) != "1.2.10":
        raise RuntimeError("Embedded PhysicsNeMo component version is not 1.2.10")
    plugin_register = str(getattr(module, "PLUGIN_REGISTER", ""))
    # These literals are expected in this validator.  They are forbidden only
    # inside the embedded PLUGIN_REGISTER source, not in the unified bootstrap
    # that performs the validation.
    forbidden = (
        'ToolCall="python"',
        "upload_file_to_openwebui",
        "physnemo__start_" + "pinn_" + "karman",
        "physnemo__pinn_" + "run_status",
    )
    present_forbidden = [marker for marker in forbidden if marker in plugin_register]
    if present_forbidden:
        raise RuntimeError(
            "Embedded PhysicsNeMo plugin contains problem-specific or fabricated artifact code: "
            + ", ".join(present_forbidden)
        )
    required_markers = (
        'class PhysNeMoInternalConfig(FunctionBaseConfig, name="physnemo_internal")',
        'class PhysNeMoSolveConfig(FunctionBaseConfig, name="physnemo_solve")',
        'from nat.data_models.component_ref import FunctionRef',
        'agent_name: FunctionRef | None = None',
        'class PhysNeMoPublicConfig(FunctionBaseConfig, name="physnemo_public")',
        'async def solve(request: SolveInput)',
        'agent = await builder.get_function(config.agent_name)',
        'async def job_status(request: JobStatusInput)',
        'async def list_artifacts(request: JobInput)',
        'async def get_artifact(request: GetArtifactInput)',
        'return f"data:{media_type};base64,{encoded}"',
        'download_markdown',
        'openwebui_file_id',
        'MAX_INLINE_IMAGE_BYTES = 12 * 1024 * 1024',
    )
    missing = [marker for marker in required_markers if marker not in plugin_register]
    if missing:
        raise RuntimeError(
            "Embedded PhysicsNeMo plugin is missing the generic agent/artifact contract: "
            + ", ".join(missing)
        )
    if "register_function_group" in plugin_register or "FunctionGroupBaseConfig" in plugin_register:
        raise RuntimeError("Embedded PhysicsNeMo plugin unexpectedly uses NAT FunctionGroup entries")
    renderer = getattr(module, "render_nat_config", None)
    if not callable(renderer):
        raise RuntimeError("Embedded PhysicsNeMo component is missing the NAT config renderer")
    rendered = str(
        renderer(
            "/tmp/physicsnemo",
            "v2.2.2",
            "/tmp/physicsnemo-artifacts",
            "http://127.0.0.1:8200/physnemo/artifacts",
            "x" * 48,
            agent_model="test-model",
            agent_base_url="http://127.0.0.1:9000/v1",
            openwebui_bridge_url="",
            openwebui_bridge_secret="",
        )
    )
    if "function_groups:" in rendered:
        raise RuntimeError("Embedded PhysicsNeMo NAT config still declares a FunctionGroup")
    configured_public = set(
        re.findall(r"^  (physnemo__[A-Za-z0-9_]+):$", rendered, re.MULTILINE)
    )
    if configured_public != set(PHYSNEMO_EXPECTED_TOOLS):
        raise RuntimeError(
            "Embedded PhysicsNeMo NAT config does not declare the exact public tools: "
            f"expected={sorted(PHYSNEMO_EXPECTED_TOOLS)!r}, actual={sorted(configured_public)!r}"
        )
    required_config_markers = (
        "_type: physnemo_native_agent",
        "max_turns: 32",
        "physnemo_agent:",
        "agent_name: \"physnemo_agent\"",
        "physnemo_internal__source_search",
        "physnemo_internal__workspace_run_python",
        "_type: physnemo_solve",
        '${PHYSNEMO_AGENT_API_KEY}',
        '${PHYSNEMO_AGENT_BASE_URL}',
        '${PHYSNEMO_AGENT_MODEL}',
    )
    missing_config = [marker for marker in required_config_markers if marker not in rendered]
    if missing_config:
        raise RuntimeError(
            "Embedded PhysicsNeMo NAT config is missing the general-agent wiring: "
            + ", ".join(missing_config)
        )
    rendered_filter = str(module.render_nat_tool_filter_args()).split()
    expected_filter: List[str] = []
    for tool_name in PHYSNEMO_EXPECTED_TOOLS:
        expected_filter.extend(["--tool_names", tool_name])
    if rendered_filter != expected_filter:
        raise RuntimeError(
            "Embedded PhysicsNeMo component does not expose the exact public NAT tool filter: "
            f"expected={expected_filter!r}, actual={rendered_filter!r}"
        )
    if "nvidia-nat[langchain]" not in raw.decode("utf-8"):
        raise RuntimeError("Embedded PhysicsNeMo component does not install the NAT LangChain/ReAct plugin")
    module.WSL_COMMAND_LOG = PHYSNEMO_WSL_INSTALL_LOG
    module.FAILED_WSL_SCRIPT_DIR = PHYSNEMO_FAILED_SCRIPT_DIR
    _PHYSNEMO_COMPONENT = module
    return module
DEFAULT_MATLAB_HEALTH_TIMEOUT = 240.0
MATLAB_REPAIR_TIMEOUT = 900.0
MATLAB_PREFLIGHT_MARKER = "ENGINEERING_MCP_MATLAB_PREFLIGHT_OK"
MATLAB_TOOL_PREFLIGHT_MARKER = "ENGINEERING_MCP_MATLAB_TOOL_OK"
MATHWORKS_SERVICE_HOST_SUPPORT_URL = (
    "https://www.mathworks.com/matlabcentral/answers/1815365-"
    "how-do-i-uninstall-and-reinstall-the-mathworks-service-host"
)
# Used only if the support page cannot be parsed. The executable is accepted
# solely from ssd.mathworks.com and only with a valid MathWorks signature.
MATHWORKS_SERVICE_HOST_REINSTALLER_FALLBACK = (
    "https://ssd.mathworks.com/supportfiles/downloads/MathWorksServiceHost/"
    "v2026.8.0.4/reinstallers/win64/ReinstallMathWorksServiceHost.exe"
)
WINDOWS_TASK_NAME = r"Engineering MCP Gateway"
SYSTEMD_UNIT_NAME = "engineering-mcp.service"
LAUNCHD_LABEL = "cz.engineering.mcp.gateway"

APP_HOME = Path(
    os.environ.get(
        "ENGINEERING_MCP_HOME",
        Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local" / "share"))
        / "EngineeringMCP",
    )
).expanduser()
VENV = APP_HOME / ".venv"
# Keep the OpenAPI gateway and the MCP-2-based WeKnora server in separate
# environments.  MCPO 0.0.20 is tested with the MCP 1.x SDK, while the
# official WeKnora 1.1.1 package explicitly requires mcp>=2,<3.
MCPO_VENV = APP_HOME / ".venv-mcpo"
WEKNORA_VENV = APP_HOME / ".venv-weknora"
BIN_DIR = APP_HOME / "bin"
CONFIG_DIR = APP_HOME / "config"
LOG_DIR = APP_HOME / "logs"
ARTIFACT_DIR = APP_HOME / "artifacts"
MATLAB_ARTIFACT_DIR = ARTIFACT_DIR / "matlab"
MATLAB_MCP_LOG_DIR = LOG_DIR / "matlab-mcp"
MATLAB_REPAIR_DIR = LOG_DIR / "matlab-service-host-repair"
MATLAB_REPAIR_REPORT = LOG_DIR / "matlab-service-host-repair.json"
MATLAB_MCP_RUNTIME_REPORT = LOG_DIR / "matlab-mcp-runtime-health.json"
PIP_LOG_FILE = LOG_DIR / "pip-install.log"
VENV_REPAIR_LOG = LOG_DIR / "venv-repair.log"
MCPO_PIP_LOG_FILE = LOG_DIR / "mcpo-venv-pip-install.log"
WEKNORA_PIP_LOG_FILE = LOG_DIR / "weknora-venv-pip-install.log"
AUXILIARY_VENV_REPAIR_LOG = LOG_DIR / "auxiliary-venv-repair.log"
STATE_FILE = APP_HOME / "state.json"
CHECKPOINT_FILE = APP_HOME / "install-checkpoint.json"
MCPO_CONFIG = CONFIG_DIR / "mcpo.json"
WEKNORA_SECRET_FILE = CONFIG_DIR / "weknora-secret.json"
WEKNORA_KB_CATALOG = CONFIG_DIR / "weknora-knowledge-bases.json"
WEKNORA_RUNTIME_REPORT = LOG_DIR / "weknora-runtime-health.json"
WEKNORA_CATALOG_PROBE_REPORT = LOG_DIR / "weknora-catalog-probe.json"
WEKNORA_WORKSPACE_PROBE_REPORT = LOG_DIR / "weknora-workspace-probe.json"
WEKNORA_STDIO_PREFLIGHT_REPORT = LOG_DIR / "weknora-stdio-preflight.json"
PHYSNEMO_RUNTIME_REPORT = LOG_DIR / "physnemo-runtime-health.json"
PHYSNEMO_MCP_PREFLIGHT_REPORT = LOG_DIR / "physnemo-mcp-preflight.json"
PHYSNEMO_AGENT_BRIDGE_PREFLIGHT_REPORT = LOG_DIR / "physnemo-agent-bridge-preflight.json"
PHYSNEMO_WSL_PROXY_LOG = LOG_DIR / "physnemo-wsl-proxy.log"
PHYSNEMO_WSL_INSTALL_LOG = LOG_DIR / "physnemo-wsl-install.log"
PHYSNEMO_FAILED_SCRIPT_DIR = LOG_DIR / "physnemo-failed-wsl-scripts"
PHYSNEMO_AGENT_SECRET_FILE = CONFIG_DIR / "physnemo-agent-secret.json"
PHYSNEMO_AGENT_DETECTION_REPORT = LOG_DIR / "physnemo-agent-detection.json"
PHYSNEMO_OPENWEBUI_SYNC_REPORT = LOG_DIR / "physnemo-openwebui-sync.json"
OPENWEBUI_NATIVE_SYNC_REPORT = LOG_DIR / "openwebui-native-sync.json"
OPENWEBUI_DLP_PREFLIGHT_REPORT = LOG_DIR / "openwebui-dlp-preflight.json"
OPENWEBUI_ENGINEERING_TOOL_ROUTER_REPORT = LOG_DIR / "openwebui-engineering-tool-router.json"
OPENWEBUI_DB_BACKUP_DIR = LOG_DIR / "openwebui-db-backups"
PHYSNEMO_OPENWEBUI_RUNTIME_DEFAULT = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "EInfra-OpenWebUI" / "config" / "runtime.json"
PHYSNEMO_WSL_PROXY_PID_FILE = APP_HOME / "physnemo-wsl-proxy.pid"
OPENAPI_VERIFICATION_REPORT = LOG_DIR / "openapi-verification.json"
WEKNORA_CA_FILE = CONFIG_DIR / "weknora-ca.crt"
OPENWEBUI_CONNECTIONS = CONFIG_DIR / "openwebui-connections.json"
OPENWEBUI_IMPORT_DESKTOP = CONFIG_DIR / "openwebui-import-desktop.json"
OPENWEBUI_IMPORT_DOCKER = CONFIG_DIR / "openwebui-import-docker.json"
INSTALLED_SCRIPT = APP_HOME / "engineering_mcp_unified-v2.9.18.py"
SUPERVISOR_PID_FILE = APP_HOME / "supervisor.pid"
MCPO_PID_FILE = APP_HOME / "mcpo.pid"
STOP_FILE = APP_HOME / ".stop"
WINDOWS_TASK_XML = CONFIG_DIR / "engineering-mcp-task.xml"
SYSTEMD_USER_DIR = Path.home() / ".config" / "systemd" / "user"
SYSTEMD_UNIT_FILE = SYSTEMD_USER_DIR / SYSTEMD_UNIT_NAME
XDG_AUTOSTART_FILE = Path.home() / ".config" / "autostart" / "engineering-mcp.desktop"
LAUNCH_AGENT_FILE = Path.home() / "Library" / "LaunchAgents" / f"{LAUNCHD_LABEL}.plist"

OFFICIAL_SERVERS: Dict[str, Dict[str, Any]] = {
    "weknora": {
        "label": "WeKnora Knowledge Bases",
        "package": WEKNORA_PACKAGE,
        "package_spec": WEKNORA_PACKAGE_SPEC,
        "isolated_venv": "weknora",
        "command": WEKNORA_COMMAND,
        "detection": "weknora",
        "args": ["--transport", "stdio"],
        "required_cli_options": ["--transport"],
        "required_tool_groups": WEKNORA_REQUIRED_TOOL_GROUPS,
        "requires_healthy_application": True,
    },
    "ansys-fluent": {
        "label": "Ansys Fluent",
        "package": "ansys-fluent-mcp",
        "command": "ansys-fluent-mcp",
        "detection": "ansys",
        "product": "fluent",
    },
    "ansys-mechanical": {
        "label": "Ansys Mechanical",
        "package": "ansys-mechanical-mcp",
        "command": "ansys-mechanical-mcp",
        "detection": "ansys",
        "product": "mechanical",
        "args": [MECHANICAL_STATIC_TOOLS_OPTION],
        "required_cli_options": [MECHANICAL_STATIC_TOOLS_OPTION],
        "required_tool_groups": MECHANICAL_REQUIRED_TOOL_GROUPS,
    },
    "ansys-mapdl": {
        "label": "Ansys MAPDL",
        "package": "ansys-mapdl-mcp",
        "command": "ansys-mapdl-mcp",
        "detection": "ansys",
        "product": "mapdl",
    },
    "ansys-aedt": {
        "label": "Ansys Electronics Desktop",
        "package": "git+https://github.com/ansys/pyaedt-mcp.git",
        "command": "ansys-aedt-mcp",
        "detection": "ansys",
        "product": "aedt",
    },
    "ansys-cfx": {
        "label": "Ansys CFX",
        "package": "ansys-cfx-mcp",
        "command": "ansys-cfx-mcp",
        "detection": "ansys",
        "product": "cfx",
    },
    "ansys-lumerical": {
        "label": "Ansys Lumerical",
        "package": "ansys-lumerical-mcp",
        "command": "ansys-lumerical-mcp",
        "detection": "lumerical",
    },
}

COMMUNITY_SERVERS: Dict[str, Dict[str, Any]] = {
    "paraview": {
        "label": "ParaView",
        "package": "paraview-mcp-server",
        "command": "paraview-mcp-server",
        "detection": "paraview",
        "note": "Requires the matching ParaView MCP plugin inside ParaView.",
    },
    "freecad": {
        "label": "FreeCAD",
        "package": "freecad-mcp",
        "command": "freecad-mcp",
        "detection": "freecad",
        "note": "Requires the matching FreeCAD addon/bridge.",
    },
}

SPECIAL_LABELS = {"matlab": "MATLAB", "weknora": "WeKnora Knowledge Bases", PHYSNEMO_ROUTE: PHYSNEMO_LABEL}
DIRECT_INTEGRATIONS = {
    "fusion": {
        "label": "Autodesk Fusion",
        "default_port": 27182,
        "note": "Enable Preferences > General > API > Fusion MCP Server.",
    }
}

_PIP_PREPARED = False


def configure_process_encoding() -> None:
    """Use deterministic UTF-8 streams while keeping integration IDs ASCII."""
    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    for stream in (getattr(sys, "stdout", None), getattr(sys, "stderr", None)):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass


configure_process_encoding()


# ---------------------------------------------------------------------------
# Generic utilities
# ---------------------------------------------------------------------------

def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def ensure_dirs() -> None:
    for directory in (APP_HOME, BIN_DIR, CONFIG_DIR, LOG_DIR):
        directory.mkdir(parents=True, exist_ok=True)


def atomic_write_text(path: Path, text: str, encoding: str = "utf-8") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temp.write_text(text, encoding=encoding)
    os.replace(temp, path)


def restrict_private_file(path: Path) -> None:
    """Best-effort owner-only permissions for secrets and generated credentials."""
    if not sys.platform.startswith("win"):
        try:
            path.chmod(0o600)
        except OSError:
            pass
        return

    # Windows ignores POSIX chmod semantics.  Use the current SID so localized
    # account names and spaces do not make the ACL command ambiguous.  Keep
    # LocalSystem access because Task Scheduler launches the same user process
    # through Windows service infrastructure on some managed desktops.
    try:
        sid = windows_current_sid()
        result = run(
            [
                "icacls",
                str(path),
                "/inheritance:r",
                "/grant:r",
                f"*{sid}:(F)",
                "/grant:r",
                "*S-1-5-18:(F)",
            ],
            timeout=30,
        )
        if result.returncode != 0:
            log_supervisor(
                f"warning: could not restrict ACL for {path}: {(result.stdout or '').strip()}"
            )
    except Exception as exc:
        try:
            log_supervisor(f"warning: could not restrict ACL for {path}: {exc}")
        except Exception:
            pass


def atomic_write_json(path: Path, data: Dict[str, Any], private: bool = False) -> None:
    atomic_write_text(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    if private:
        restrict_private_file(path)


def read_json(path: Path, default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if not path.exists():
        return dict(default or {})
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else dict(default or {})
    except (OSError, json.JSONDecodeError):
        return dict(default or {})


def run(
    cmd: List[str],
    *,
    check: bool = False,
    capture: bool = True,
    env: Optional[Dict[str, str]] = None,
    timeout: Optional[float] = None,
    cwd: Optional[Path] = None,
) -> subprocess.CompletedProcess:
    kwargs: Dict[str, Any] = {
        "text": True,
        "env": env or os.environ.copy(),
        "cwd": str(cwd) if cwd else None,
        "timeout": timeout,
    }
    if capture:
        kwargs.update(stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        result = subprocess.run(cmd, **kwargs)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"Command timed out: {format_command(cmd)}") from exc
    if check and result.returncode != 0:
        raise RuntimeError(
            f"Command failed ({result.returncode}): {format_command(cmd)}\n"
            f"{(result.stdout or '').strip()}"
        )
    return result


def format_command(cmd: Iterable[str]) -> str:
    return " ".join(f'"{x}"' if any(c.isspace() for c in str(x)) else str(x) for x in cmd)


def format_command_redacted(cmd: Iterable[str]) -> str:
    items = [str(item) for item in cmd]
    redacted: List[str] = []
    hide_next = False
    for item in items:
        if hide_next:
            redacted.append("<redacted-api-key>")
            hide_next = False
            continue
        redacted.append(item)
        if item == "--api-key":
            hide_next = True
    return format_command(redacted)


def which(name: str) -> Optional[str]:
    return shutil.which(name)


def path_is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except (OSError, ValueError):
        return False


def tcp_open(host: str, port: int, timeout: float = 0.35) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform.startswith("win"):
        result = run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"])
        return result.returncode == 0 and f'"{pid}"' in (result.stdout or "")
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def terminate_pid_tree(pid: int, force: bool = False) -> None:
    if not process_alive(pid):
        return
    if sys.platform.startswith("win"):
        cmd = ["taskkill", "/PID", str(pid), "/T"]
        if force:
            cmd.append("/F")
        run(cmd, capture=True)
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return
    deadline = time.time() + 5
    while time.time() < deadline and process_alive(pid):
        time.sleep(0.2)
    if force and process_alive(pid):
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass


def read_pid(path: Path) -> Optional[int]:
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def write_pid(path: Path, pid: int) -> None:
    atomic_write_text(path, f"{pid}\n")


def log_supervisor(message: str) -> None:
    ensure_dirs()
    line = f"{now_iso()} {message}\n"
    with (LOG_DIR / "supervisor.log").open("a", encoding="utf-8") as handle:
        handle.write(line)


def server_label(route: str) -> str:
    if route in OFFICIAL_SERVERS:
        return OFFICIAL_SERVERS[route]["label"]
    if route in COMMUNITY_SERVERS:
        return COMMUNITY_SERVERS[route]["label"]
    return SPECIAL_LABELS.get(route, route)


def integration_title(route: str) -> str:
    """Return an ASCII-only title safe across Windows console/code pages."""
    return f"Engineering MCP - {server_label(route)}"


# ---------------------------------------------------------------------------
# Named stdio bridge and MATLAB image promotion
# ---------------------------------------------------------------------------

MATLAB_EVALUATE_TOOL = "evaluate_matlab_code"
MATLAB_VISUALIZATION_TOOL = "evaluate_matlab_code_with_figures"
MATLAB_VISUALIZATION_MAX_FIGURES = 6
MATLAB_VISUALIZATION_DEFAULT_FIGURES = 4
MATLAB_VISUALIZATION_DEFAULT_RESOLUTION = 150
MATLAB_IMAGE_MAX_BYTES = 12 * 1024 * 1024


def _jsonrpc_id_key(value: Any) -> str:
    """Return a type-stable dictionary key for a JSON-RPC request id."""
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _json_line(message: Dict[str, Any]) -> bytes:
    return json.dumps(message, ensure_ascii=True, separators=(",", ":")).encode("utf-8") + b"\n"


def _matlab_visualization_tool_definition() -> Dict[str, Any]:
    return {
        "name": MATLAB_VISUALIZATION_TOOL,
        "title": "Evaluate MATLAB code with figures",
        "description": (
            "Execute MATLAB code and return newly available MATLAB figures as renderable PNG image "
            "content. Use this tool for plots, charts, surfaces, images, diagrams, animations or any "
            "request whose result must be visible in the chat. Do not encode PNG files to base64 in "
            "MATLAB and do not print binary image data; the Engineering MCP bridge exports figures "
            "and returns proper MCP image content automatically."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": (
                        "MATLAB code to execute. Create one or more figure windows normally; the bridge "
                        "captures them after the code finishes."
                    ),
                },
                "project_path": {
                    "type": "string",
                    "description": (
                        "Optional absolute project directory used as MATLAB's current working folder."
                    ),
                },
                "max_figures": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": MATLAB_VISUALIZATION_MAX_FIGURES,
                    "default": MATLAB_VISUALIZATION_DEFAULT_FIGURES,
                    "description": "Maximum number of figure windows returned to the chat (1-6).",
                },
                "resolution": {
                    "type": "integer",
                    "minimum": 72,
                    "maximum": 300,
                    "default": MATLAB_VISUALIZATION_DEFAULT_RESOLUTION,
                    "description": "PNG export resolution in DPI (72-300).",
                },
            },
            "required": ["code"],
            "additionalProperties": False,
        },
        "annotations": {
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": False,
        },
    }


def _matlab_code_looks_visual(code: str) -> bool:
    """Conservatively identify MATLAB code that creates or modifies a visual."""
    # Remove block comments and line comments before looking for function calls.
    without_blocks = re.sub(r"(?s)%\{.*?%\}", " ", code)
    without_comments = "\n".join(line.split("%", 1)[0] for line in without_blocks.splitlines())
    visual_calls = (
        "figure", "plot", "plot3", "fplot", "fplot3", "semilogx", "semilogy", "loglog",
        "scatter", "scatter3", "bar", "bar3", "area", "stem", "stairs", "errorbar",
        "histogram", "histogram2", "heatmap", "imagesc", "imshow", "image", "surf",
        "surfc", "surface", "mesh", "meshc", "contour", "contourf", "contour3",
        "slice", "quiver", "quiver3", "streamline", "patch", "fill", "fill3", "polarplot",
        "geoplot", "tiledlayout", "subplot", "animatedline", "drawnow", "exportgraphics",
        "print", "saveas", "volshow", "pcshow", "pcolor", "spy", "wordcloud",
    )
    pattern = r"(?i)(?<![A-Za-z0-9_])(?:" + "|".join(map(re.escape, visual_calls)) + r")\s*\("
    return bool(re.search(pattern, without_comments))


def _normalize_model_matlab_code(code: str) -> Tuple[str, List[str]]:
    """Repair harmless Markdown-style escaping often emitted inside tool JSON."""
    notes: List[str] = []
    normalized = re.sub(r"\\([_:*])", r"\1", code)
    if normalized != code:
        notes.append("Removed Markdown escape backslashes before ':', '_' or '*'.")

    # A common model pattern manually base64-encodes a PNG and leaves the final
    # variable name as a bare expression. That floods the tool result with a very
    # large text value and still does not create MCP ImageContent. Suppress only
    # this narrow, unambiguous trailing expression; the image bridge handles it.
    lines = normalized.rstrip().splitlines()
    for index in range(len(lines) - 1, -1, -1):
        stripped = lines[index].strip()
        if not stripped or stripped.startswith("%"):
            continue
        if re.fullmatch(
            r"(?i)(encoded|base64|base64image|imagebase64|imgbase64|encodedimage)",
            stripped,
        ):
            lines[index] = lines[index].rstrip() + ";"
            normalized = "\n".join(lines) + "\n"
            notes.append("Suppressed a trailing bare base64 variable; figures are returned as MCP images.")
        break
    return normalized, notes


def _matlab_string_literal(value: str) -> str:
    return value.replace("'", "''")


MATLAB_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,62}$")


def _matlab_bridge_identifier(token: str, suffix: str) -> str:
    """Build a collision-resistant MATLAB identifier valid on every supported release.

    MATLAB identifiers must begin with a letter and are limited to ``namelengthmax``
    characters (63 on supported releases).  The previous bridge used temporary names
    beginning with underscores, which MATLAB rejected before PNG export.  Prefixing a
    compact request token with ``emcp`` keeps the names valid and isolates concurrent
    calls without exposing private paths or data in the identifier.
    """
    compact_token = re.sub(r"[^A-Za-z0-9]", "", str(token or ""))[:16] or "request"
    compact_suffix = re.sub(r"[^A-Za-z0-9_]", "", str(suffix or "Value")) or "Value"
    value = f"emcp{compact_token}{compact_suffix}"[:63]
    if not MATLAB_IDENTIFIER_PATTERN.fullmatch(value):
        raise RuntimeError(f"Could not build a valid MATLAB bridge identifier: {value!r}")
    return value


def _append_matlab_figure_capture(
    code: str,
    run_dir: Path,
    token: str,
    *,
    max_figures: int,
    resolution: int,
) -> str:
    """Wrap MATLAB code with figure tracking and post-execution PNG export."""
    max_figures = max(1, min(int(max_figures), MATLAB_VISUALIZATION_MAX_FIGURES))
    resolution = max(72, min(int(resolution), 300))
    directory = _matlab_string_literal(str(run_dir.resolve()))
    image_marker = f"__ENGINEERING_MCP_IMAGE_{token}__:"
    error_marker = f"__ENGINEERING_MCP_IMAGE_ERROR_{token}__:"
    appdata_key = f"EngineeringMCPBeforeFigures_{token}"

    # Use per-request, MATLAB-valid identifiers.  Keeping the names in Python
    # variables also makes accidental reintroduction of a leading underscore easy
    # to catch in unit/static tests.
    after_figs = _matlab_bridge_identifier(token, "AfterFigs")
    before_figs = _matlab_bridge_identifier(token, "BeforeFigs")
    new_mask = _matlab_bridge_identifier(token, "NewMask")
    probe_index = _matlab_bridge_identifier(token, "ProbeIndex")
    figs = _matlab_bridge_identifier(token, "Figs")
    numbers = _matlab_bridge_identifier(token, "Numbers")
    order = _matlab_bridge_identifier(token, "Order")
    count = _matlab_bridge_identifier(token, "Count")
    index = _matlab_bridge_identifier(token, "Index")
    file_name = _matlab_bridge_identifier(token, "File")
    capture_error = _matlab_bridge_identifier(token, "CaptureError")
    capture_message = _matlab_bridge_identifier(token, "CaptureMessage")

    setup = f"""% --- Engineering MCP MATLAB figure tracking (automatic) ---
try
    setappdata(groot, '{appdata_key}', findall(groot, 'Type', 'figure'));
catch
end
% --- End Engineering MCP MATLAB figure tracking ---
"""
    capture = f"""

% --- Engineering MCP MATLAB figure capture (automatic) ---
try
    drawnow;
    {after_figs} = findall(groot, 'Type', 'figure');
    {before_figs} = [];
    try
        if isappdata(groot, '{appdata_key}')
            {before_figs} = getappdata(groot, '{appdata_key}');
            rmappdata(groot, '{appdata_key}');
        end
    catch
    end
    {new_mask} = true(size({after_figs}));
    for {probe_index} = 1:numel({after_figs})
        try
            {new_mask}({probe_index}) = ~any({after_figs}({probe_index}) == {before_figs});
        catch
            {new_mask}({probe_index}) = true;
        end
    end
    {figs} = {after_figs}({new_mask});
    if isempty({figs})
        % The code may have updated an existing figure rather than creating one.
        {figs} = {after_figs};
    end
    if ~isempty({figs})
        try
            {numbers} = arrayfun(@(h) h.Number, {figs});
            [~, {order}] = sort({numbers});
            {figs} = {figs}({order});
        catch
            % Some specialised figure types do not expose Number; keep findall order.
        end
    end
    {count} = min(numel({figs}), {max_figures});
    for {index} = 1:{count}
        {file_name} = fullfile('{directory}', sprintf('figure-%02d.png', {index}));
        try
            exportgraphics({figs}({index}), {file_name}, 'Resolution', {resolution});
        catch
            print({figs}({index}), {file_name}, '-dpng', '-r{resolution}');
        end
        fprintf(1, '{image_marker}%s\\n', {file_name});
    end
    if {count} == 0
        fprintf(1, '{error_marker}No open MATLAB figure was available after code execution.\\n');
    end
catch {capture_error}
    try
        if isappdata(groot, '{appdata_key}')
            rmappdata(groot, '{appdata_key}');
        end
    catch
    end
    {capture_message} = regexprep(getReport({capture_error}, 'basic', 'hyperlinks', 'off'), '[\\r\\n]+', ' ');
    fprintf(1, '{error_marker}%s\\n', {capture_message});
end
% --- End Engineering MCP MATLAB figure capture ---
"""
    return setup + code.rstrip() + "\n" + capture

def _cleanup_old_matlab_artifacts(root: Path, max_age_seconds: float = 86400.0) -> None:
    try:
        root.mkdir(parents=True, exist_ok=True)
        cutoff = time.time() - max_age_seconds
        for item in root.iterdir():
            try:
                if item.is_dir() and item.stat().st_mtime < cutoff:
                    shutil.rmtree(item, ignore_errors=True)
            except OSError:
                continue
    except OSError:
        pass


def _prepare_matlab_tool_request(
    message: Dict[str, Any],
    artifact_root: Path,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Rewrite a MATLAB tools/call request and return response-processing metadata."""
    metadata: Dict[str, Any] = {"visualization": False, "normalization_notes": []}
    params = message.get("params")
    if not isinstance(params, dict):
        return message, metadata
    tool_name = params.get("name")
    arguments = params.get("arguments")
    if not isinstance(arguments, dict):
        arguments = {}

    is_explicit_visualization = tool_name == MATLAB_VISUALIZATION_TOOL
    is_base_evaluate = tool_name == MATLAB_EVALUATE_TOOL
    if not (is_explicit_visualization or is_base_evaluate):
        return message, metadata

    code_value = arguments.get("code")
    if not isinstance(code_value, str):
        return message, metadata
    code, normalization_notes = _normalize_model_matlab_code(code_value)
    metadata["normalization_notes"] = normalization_notes

    capture = is_explicit_visualization or _matlab_code_looks_visual(code)
    rewritten_arguments: Dict[str, Any] = {"code": code}
    project_path = arguments.get("project_path")
    if isinstance(project_path, str) and project_path.strip():
        rewritten_arguments["project_path"] = project_path

    if capture:
        try:
            max_figures = int(arguments.get("max_figures", MATLAB_VISUALIZATION_DEFAULT_FIGURES))
        except (TypeError, ValueError):
            max_figures = MATLAB_VISUALIZATION_DEFAULT_FIGURES
        try:
            resolution = int(arguments.get("resolution", MATLAB_VISUALIZATION_DEFAULT_RESOLUTION))
        except (TypeError, ValueError):
            resolution = MATLAB_VISUALIZATION_DEFAULT_RESOLUTION
        max_figures = max(1, min(max_figures, MATLAB_VISUALIZATION_MAX_FIGURES))
        resolution = max(72, min(resolution, 300))
        token = uuid.uuid4().hex
        run_dir = artifact_root / token
        run_dir.mkdir(parents=True, exist_ok=True)
        rewritten_arguments["code"] = _append_matlab_figure_capture(
            code,
            run_dir,
            token,
            max_figures=max_figures,
            resolution=resolution,
        )
        metadata.update(
            {
                "visualization": True,
                "token": token,
                "run_dir": str(run_dir.resolve()),
                "max_figures": max_figures,
                "resolution": resolution,
                "explicit_visualization": is_explicit_visualization,
            }
        )

    params = dict(params)
    params["name"] = MATLAB_EVALUATE_TOOL
    params["arguments"] = rewritten_arguments
    message = dict(message)
    message["params"] = params
    return message, metadata


def _augment_matlab_tool_list(message: Dict[str, Any]) -> bool:
    result = message.get("result")
    if not isinstance(result, dict):
        return False
    tools = result.get("tools")
    if not isinstance(tools, list):
        return False
    changed = False
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        if tool.get("name") == MATLAB_EVALUATE_TOOL:
            guidance = (
                " For any visual output, plot, chart, image or figure, use "
                f"{MATLAB_VISUALIZATION_TOOL} instead; it returns renderable PNG image content."
            )
            description = str(tool.get("description") or "Evaluate MATLAB code.")
            if MATLAB_VISUALIZATION_TOOL not in description:
                tool["description"] = description.rstrip() + guidance
                changed = True
    if not any(isinstance(tool, dict) and tool.get("name") == MATLAB_VISUALIZATION_TOOL for tool in tools):
        tools.append(_matlab_visualization_tool_definition())
        changed = True
    return changed


def _strip_marker_lines(text: str, image_marker: str, error_marker: str) -> Tuple[str, List[str], List[str]]:
    retained: List[str] = []
    paths: List[str] = []
    errors: List[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(image_marker):
            paths.append(stripped[len(image_marker):].strip())
        elif stripped.startswith(error_marker):
            errors.append(stripped[len(error_marker):].strip())
        else:
            retained.append(line)
    return "\n".join(retained).strip(), paths, errors


def _looks_like_large_base64_text(text: str) -> bool:
    if len(text) < 100000:
        return False
    compact = re.sub(r"\s+", "", text)
    return bool(re.search(r"[A-Za-z0-9+/]{50000,}={0,2}", compact))


def _promote_matlab_images(message: Dict[str, Any], metadata: Dict[str, Any]) -> bool:
    """Replace private file markers with MCP ImageContent dictionaries."""
    if not metadata.get("visualization"):
        return False
    result = message.get("result")
    if not isinstance(result, dict):
        return False
    content = result.get("content")
    if not isinstance(content, list):
        return False

    token = str(metadata.get("token") or "")
    image_marker = f"__ENGINEERING_MCP_IMAGE_{token}__:"
    error_marker = f"__ENGINEERING_MCP_IMAGE_ERROR_{token}__:"
    run_dir = Path(str(metadata.get("run_dir") or "")).resolve()
    retained_content: List[Dict[str, Any]] = []
    image_paths: List[str] = []
    capture_errors: List[str] = []

    normalization_notes = [str(item) for item in metadata.get("normalization_notes", []) if str(item)]
    if normalization_notes:
        retained_content.append(
            {
                "type": "text",
                "text": "Engineering MCP normalized the generated MATLAB tool input: " + " ".join(normalization_notes),
            }
        )

    for item in content:
        if not isinstance(item, dict) or item.get("type") != "text":
            if isinstance(item, dict):
                retained_content.append(item)
            continue
        text = item.get("text")
        if not isinstance(text, str):
            retained_content.append(item)
            continue
        cleaned, found_paths, found_errors = _strip_marker_lines(text, image_marker, error_marker)
        image_paths.extend(found_paths)
        capture_errors.extend(found_errors)
        if cleaned:
            if _looks_like_large_base64_text(cleaned):
                cleaned = (
                    "A large base64 text payload produced by MATLAB was suppressed. "
                    "The Engineering MCP bridge returns figure images separately as MCP image content."
                )
            retained_content.append({**item, "text": cleaned})

    emitted = 0
    seen: set[str] = set()
    for raw_path in image_paths:
        if emitted >= int(metadata.get("max_figures", MATLAB_VISUALIZATION_DEFAULT_FIGURES)):
            break
        try:
            candidate = Path(raw_path).resolve()
            if candidate in seen or not candidate.is_relative_to(run_dir):
                continue
            seen.add(candidate)
            if not candidate.is_file():
                capture_errors.append(f"Exported figure file was not found: {candidate}")
                continue
            size = candidate.stat().st_size
            if size <= 0 or size > MATLAB_IMAGE_MAX_BYTES:
                capture_errors.append(
                    f"Figure file has unsupported size ({size} bytes; maximum {MATLAB_IMAGE_MAX_BYTES}): {candidate.name}"
                )
                continue
            data = candidate.read_bytes()
            if not data.startswith(b"\x89PNG\r\n\x1a\n"):
                capture_errors.append(f"Figure export is not a valid PNG file: {candidate.name}")
                continue
            emitted += 1
            # Interleave text and image blocks. Besides being more readable this
            # avoids an Open WebUI regression where adjacent inline data URIs can
            # cause every second image to be skipped.
            retained_content.append(
                {
                    "type": "text",
                    "text": f"MATLAB figure {emitted} (PNG, {metadata.get('resolution', 150)} DPI)",
                }
            )
            retained_content.append(
                {
                    "type": "image",
                    "data": base64.b64encode(data).decode("ascii"),
                    "mimeType": "image/png",
                }
            )
        except (OSError, ValueError) as exc:
            capture_errors.append(f"Could not read a MATLAB figure export: {exc}")

    if emitted == 0 and not capture_errors:
        capture_errors.append("MATLAB returned no open figure to the image bridge.")
    if capture_errors:
        retained_content.append(
            {
                "type": "text",
                "text": "MATLAB figure capture: " + " | ".join(capture_errors),
            }
        )
    result["content"] = retained_content
    return True


def _weknora_alias_slug(value: str) -> str:
    """Return a stable MCP-safe fragment for one WeKnora knowledge base."""
    folded = unicodedata.normalize("NFKD", str(value or ""))
    ascii_value = folded.encode("ascii", errors="ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "_", ascii_value.lower()).strip("_")
    return (slug or "knowledge_base")[:32]


def _weknora_alias_name(entry: Dict[str, Any]) -> str:
    kb_id = re.sub(r"[^a-fA-F0-9]", "", str(entry.get("id") or ""))[:8].lower()
    return f"{WEKNORA_KB_TOOL_PREFIX}{_weknora_alias_slug(str(entry.get('name') or ''))}_{kb_id or 'unknown'}"


def _weknora_catalog_entries(path: Path) -> List[Dict[str, Any]]:
    catalog = read_json(path, {"knowledge_bases": []})
    values = catalog.get("knowledge_bases", [])
    if not isinstance(values, list):
        return []
    entries: List[Dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_tools: set[str] = set()
    for raw in values:
        if not isinstance(raw, dict):
            continue
        kb_id = str(raw.get("id") or "").strip()
        if not kb_id or kb_id in seen_ids:
            continue
        entry = {
            "id": kb_id,
            "name": str(raw.get("name") or kb_id).strip(),
            "description": str(raw.get("description") or "").strip(),
            "shared": bool(raw.get("shared")),
        }
        tool_name = str(raw.get("tool_name") or _weknora_alias_name(entry)).strip()
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,127}", tool_name):
            tool_name = _weknora_alias_name(entry)
        while tool_name in seen_tools:
            tool_name = f"{tool_name[:116]}_{len(seen_tools) + 1}"
        entry["tool_name"] = tool_name
        seen_ids.add(kb_id)
        seen_tools.add(tool_name)
        entries.append(entry)
    return entries


def _weknora_alias_tool_definition(entry: Dict[str, Any]) -> Dict[str, Any]:
    scope = "shared knowledge base" if entry.get("shared") else "knowledge base"
    description = (
        f"Search the WeKnora {scope} '{entry.get('name')}' (ID {entry.get('id')}). "
        "The knowledge-base ID is fixed by Engineering MCP, so callers only provide the query "
        "and optional retrieval thresholds."
    )
    if entry.get("description"):
        description += f" Knowledge-base description: {entry['description']}"
    return {
        "name": entry["tool_name"],
        "title": f"Search WeKnora KB: {entry.get('name')}",
        "description": description,
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "minLength": 1, "description": "Search question or query."},
                "vector_threshold": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                    "default": 0.5,
                },
                "keyword_threshold": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                    "default": 0.3,
                },
                "match_count": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 100,
                    "default": 5,
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    }


def _augment_weknora_tool_list(message: Dict[str, Any], entries: List[Dict[str, Any]]) -> bool:
    """Expose one deterministic read-only search operation per accessible KB."""
    result = message.get("result")
    if not isinstance(result, dict):
        return False
    tools = result.get("tools")
    if not isinstance(tools, list):
        return False
    changed = False
    known_names = {
        str(tool.get("name"))
        for tool in tools
        if isinstance(tool, dict) and str(tool.get("name") or "")
    }
    if entries:
        catalog_line = "; ".join(
            f"{entry.get('name')} [{entry.get('id')}]" for entry in entries[:80]
        )
        for tool in tools:
            if not isinstance(tool, dict) or tool.get("name") not in {
                "list_knowledge_bases",
                "get_knowledge_base",
                "hybrid_search",
            }:
                continue
            description = str(tool.get("description") or "").rstrip()
            appendix = (
                " Accessible knowledge bases discovered and verified by Engineering MCP: "
                + catalog_line
            )
            if catalog_line and catalog_line not in description:
                tool["description"] = description + appendix
                changed = True
    for entry in entries:
        if entry["tool_name"] in known_names:
            continue
        tools.append(_weknora_alias_tool_definition(entry))
        known_names.add(entry["tool_name"])
        changed = True
    return changed


def _rewrite_weknora_alias_call(
    message: Dict[str, Any], aliases: Dict[str, Dict[str, Any]]
) -> Tuple[Dict[str, Any], bool]:
    params = message.get("params")
    if not isinstance(params, dict):
        return message, False
    tool_name = str(params.get("name") or "")
    entry = aliases.get(tool_name)
    if not entry:
        return message, False
    arguments = params.get("arguments")
    arguments = dict(arguments) if isinstance(arguments, dict) else {}
    arguments["kb_id"] = entry["id"]
    rewritten_params = dict(params)
    rewritten_params["name"] = "hybrid_search"
    rewritten_params["arguments"] = arguments
    rewritten = dict(message)
    rewritten["params"] = rewritten_params
    return rewritten, True


def run_weknora_mcp_launcher(arguments: List[str]) -> int:
    """Run the official WeKnora MCP package with a fixed target-workspace header.

    The upstream 1.1.1 MCP package accepts WEKNORA_BASE_URL and WEKNORA_API_KEY
    but has no environment option for X-Tenant-ID.  Platform API keys require
    that header on every tenant-scoped request.  This launcher runs inside the
    isolated WeKnora venv, patches only the client's session constructor, and
    then starts the official stdio transport unchanged.
    """
    parser = argparse.ArgumentParser(
        prog="engineering_mcp_unified-v2.9.18.py --weknora-mcp-launcher",
        description="Internal WeKnora stdio launcher with fixed workspace selection",
    )
    parser.add_argument("--transport", choices=["stdio"], default="stdio")
    parser.parse_args(arguments)

    tenant_id = str(os.environ.get("WEKNORA_TENANT_ID") or "").strip()
    if tenant_id and not re.fullmatch(r"[1-9][0-9]*", tenant_id):
        print("weknora launcher: WEKNORA_TENANT_ID must be a positive integer", file=sys.stderr)
        return 64
    try:
        import asyncio
        import weknora_mcp_server as weknora_server
    except Exception as exc:
        print(f"weknora launcher: official MCP package import failed: {exc}", file=sys.stderr)
        return 127

    if tenant_id:
        original_new_session = weknora_server.WeKnoraClient._new_session

        def new_session_with_workspace(self: Any) -> Any:
            session = original_new_session(self)
            session.headers["X-Tenant-ID"] = tenant_id
            return session

        weknora_server.WeKnoraClient._new_session = new_session_with_workspace

    os.environ["MCP_TRANSPORT"] = "stdio"
    try:
        asyncio.run(weknora_server.run_stdio())
        return 0
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"weknora launcher failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


def run_stdio_name_proxy(arguments: List[str]) -> int:
    """Relay a stdio MCP server while adding deterministic names and image support.

    For every server the relay enforces an application-specific ``serverInfo``
    name. For MATLAB it additionally exposes a synthetic visualization tool and
    converts exported PNG files into real MCP ImageContent objects. For WeKnora
    it loads the API credential from an owner-only file and exposes one fixed-KB
    search operation per verified knowledge base.
    """
    parser = argparse.ArgumentParser(
        prog="engineering_mcp_unified-v2.9.18.py --stdio-name-proxy",
        description="Internal newline-delimited MCP stdio relay",
    )
    parser.add_argument("--server-name", required=True)
    parser.add_argument("--route", default="")
    parser.add_argument("--matlab-visualization", action="store_true")
    parser.add_argument("--artifact-dir", default=str(MATLAB_ARTIFACT_DIR))
    parser.add_argument("--weknora-secret", default="")
    parser.add_argument("--weknora-kb-catalog", default="")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    parsed = parser.parse_args(arguments)
    command = list(parsed.command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        print("stdio name proxy: missing child command", file=sys.stderr)
        return 2

    artifact_root = Path(parsed.artifact_dir).expanduser()
    if parsed.matlab_visualization:
        _cleanup_old_matlab_artifacts(artifact_root)

    creationflags = 0
    if sys.platform.startswith("win"):
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP

    child_environment = os.environ.copy()
    child_environment.setdefault("PYTHONUTF8", "1")
    child_environment.setdefault("PYTHONIOENCODING", "utf-8")
    weknora_entries: List[Dict[str, Any]] = []
    weknora_aliases: Dict[str, Dict[str, Any]] = {}
    if parsed.weknora_secret:
        secret_path = Path(parsed.weknora_secret).expanduser()
        secret = read_json(secret_path)
        api_key = str(secret.get("api_key") or "").strip()
        base_url = str(secret.get("base_url") or "").strip().rstrip("/")
        if not api_key or not base_url:
            print(
                f"stdio name proxy: incomplete WeKnora secret file: {secret_path}",
                file=sys.stderr,
            )
            return 78
        child_environment["WEKNORA_API_KEY"] = api_key
        child_environment["WEKNORA_BASE_URL"] = base_url
        child_environment["WEKNORA_CHAT_TIMEOUT"] = str(secret.get("chat_timeout") or 300)
        child_environment["WEKNORA_VERIFY_SSL"] = (
            "true" if bool(secret.get("verify_ssl", True)) else "false"
        )
        target_tenant_id = str(secret.get("tenant_id") or "").strip()
        if target_tenant_id:
            if not re.fullmatch(r"[1-9][0-9]*", target_tenant_id):
                print(
                    f"stdio name proxy: invalid WeKnora tenant_id in {secret_path}",
                    file=sys.stderr,
                )
                return 78
            child_environment["WEKNORA_TENANT_ID"] = target_tenant_id
        ca_file = str(secret.get("ca_file") or "").strip()
        if ca_file:
            child_environment["REQUESTS_CA_BUNDLE"] = ca_file
            child_environment["SSL_CERT_FILE"] = ca_file
        child_environment["MCP_TRANSPORT"] = "stdio"
        if parsed.weknora_kb_catalog:
            weknora_entries = _weknora_catalog_entries(
                Path(parsed.weknora_kb_catalog).expanduser()
            )
            weknora_aliases = {entry["tool_name"]: entry for entry in weknora_entries}

    try:
        child = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=None,
            bufsize=0,
            creationflags=creationflags,
            env=child_environment,
        )
    except OSError as exc:
        print(f"stdio name proxy: could not start child: {exc}", file=sys.stderr)
        return 127

    assert child.stdin is not None
    assert child.stdout is not None
    pending: Dict[str, Dict[str, Any]] = {}
    pending_lock = threading.Lock()

    def forward_client_input() -> None:
        try:
            while True:
                raw_line = sys.stdin.buffer.readline()
                if not raw_line:
                    break
                output = raw_line
                try:
                    message = json.loads(raw_line.decode("utf-8"))
                    if isinstance(message, dict) and "id" in message and isinstance(message.get("method"), str):
                        metadata: Dict[str, Any] = {"method": message["method"]}
                        changed = False
                        if parsed.matlab_visualization and message.get("method") == "tools/call":
                            message, matlab_metadata = _prepare_matlab_tool_request(message, artifact_root)
                            metadata.update(matlab_metadata)
                            changed = bool(
                                matlab_metadata.get("visualization")
                                or matlab_metadata.get("normalization_notes")
                                or message.get("params", {}).get("name") == MATLAB_EVALUATE_TOOL
                            )
                        if parsed.weknora_secret and message.get("method") == "tools/call":
                            message, weknora_changed = _rewrite_weknora_alias_call(
                                message, weknora_aliases
                            )
                            changed = changed or weknora_changed
                        with pending_lock:
                            pending[_jsonrpc_id_key(message["id"])] = metadata
                        if changed:
                            output = _json_line(message)
                except (UnicodeDecodeError, json.JSONDecodeError, AttributeError, OSError, ValueError):
                    output = raw_line
                child.stdin.write(output)
                child.stdin.flush()
        except (BrokenPipeError, OSError):
            pass
        finally:
            try:
                child.stdin.close()
            except OSError:
                pass

    input_thread = threading.Thread(
        target=forward_client_input,
        name="engineering-mcp-stdio-input",
        daemon=True,
    )
    input_thread.start()

    previous_handlers: Dict[int, Any] = {}

    def forward_signal(signum: int, _frame: Any) -> None:
        try:
            if child.poll() is None:
                if sys.platform.startswith("win"):
                    child.terminate()
                else:
                    child.send_signal(signum)
        except OSError:
            pass

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            previous_handlers[sig] = signal.getsignal(sig)
            signal.signal(sig, forward_signal)
        except (ValueError, OSError):
            pass

    try:
        while True:
            raw_line = child.stdout.readline()
            if not raw_line:
                break
            output = raw_line
            try:
                message = json.loads(raw_line.decode("utf-8"))
                changed = False
                metadata: Dict[str, Any] = {}
                if isinstance(message, dict):
                    result = message.get("result")
                    server_info = result.get("serverInfo") if isinstance(result, dict) else None
                    if isinstance(server_info, dict):
                        server_info["name"] = parsed.server_name
                        changed = True
                    if "id" in message:
                        with pending_lock:
                            metadata = pending.pop(_jsonrpc_id_key(message["id"]), {})
                    if parsed.matlab_visualization and metadata.get("method") == "tools/list":
                        changed = _augment_matlab_tool_list(message) or changed
                    if parsed.matlab_visualization and metadata.get("method") == "tools/call":
                        changed = _promote_matlab_images(message, metadata) or changed
                    if parsed.weknora_secret and metadata.get("method") == "tools/list":
                        changed = _augment_weknora_tool_list(message, weknora_entries) or changed
                if changed:
                    output = _json_line(message)
            except (UnicodeDecodeError, json.JSONDecodeError, AttributeError, OSError, ValueError):
                output = raw_line

            try:
                sys.stdout.buffer.write(output)
                sys.stdout.buffer.flush()
            except (BrokenPipeError, OSError):
                break
    finally:
        for sig, handler in previous_handlers.items():
            try:
                signal.signal(sig, handler)
            except (ValueError, OSError):
                pass
        try:
            if child.stdin and not child.stdin.closed:
                child.stdin.close()
        except OSError:
            pass
        if child.poll() is None:
            try:
                child.terminate()
                child.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    child.kill()
                except OSError:
                    pass
        return int(child.wait() if child.poll() is None else (child.returncode or 0))


def named_stdio_server(
    route: str,
    command: str,
    args: Optional[List[str]] = None,
    env: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Build an MCPO stdio entry with deterministic naming and optional image promotion."""
    if route == "weknora":
        # Run the fixed-workspace launcher with the MCP-2-compatible isolated
        # interpreter.  The outer relay itself remains in the MCPO/engineering
        # environment and never imports the incompatible MCP 2.x package.
        command = str(weknora_venv_bin("python"))
        args = [str(INSTALLED_SCRIPT), "--weknora-mcp-launcher", "--transport", "stdio"]
    proxy_args = [
        str(INSTALLED_SCRIPT),
        "--stdio-name-proxy",
        "--server-name",
        integration_title(route),
        "--route",
        route,
    ]
    if route == "matlab":
        proxy_args.extend(
            [
                "--matlab-visualization",
                "--artifact-dir",
                str(MATLAB_ARTIFACT_DIR),
            ]
        )
    if route == "weknora":
        proxy_args.extend(
            [
                "--weknora-secret",
                str(WEKNORA_SECRET_FILE),
                "--weknora-kb-catalog",
                str(WEKNORA_KB_CATALOG),
            ]
        )
    proxy_args.extend(["--", str(command), *[str(item) for item in (args or [])]])
    child_env = {
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
    }
    child_env.update({str(key): str(value) for key, value in (env or {}).items()})
    return {
        "command": str(venv_bin("python")),
        "args": proxy_args,
        "env": child_env,
    }

def route_slug(value: str) -> str:
    """Convert a route/title to a stable URL-safe identifier."""
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "engineering-mcp"


def documentation_path(route: str) -> str:
    return f"{route_slug(route)}-docs"


def openapi_schema_path(route: str) -> str:
    return f"{route_slug(route)}-openapi.json"



_PHYSNEMO_JOB_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{7,95}")
_PHYSNEMO_ARTIFACT_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,159}")
_PHYSNEMO_GALLERY_TEXT_SUFFIXES = frozenset(
    {
        ".c", ".cc", ".cpp", ".css", ".csv", ".f", ".f90", ".h", ".hpp",
        ".ini", ".ipynb", ".java", ".js", ".json", ".log", ".m", ".md",
        ".py", ".rst", ".sh", ".toml", ".tsv", ".txt", ".xml", ".yaml", ".yml",
    }
)


def _physnemo_safe_job_id(value: str) -> str:
    value = str(value or "").strip()
    if not _PHYSNEMO_JOB_ID_RE.fullmatch(value):
        raise ValueError("Invalid PhysicsNeMo job id")
    return value


def _physnemo_safe_artifact_name(value: str) -> str:
    value = str(value or "").strip()
    if (
        not _PHYSNEMO_ARTIFACT_NAME_RE.fullmatch(value)
        or value.startswith(".")
        or Path(value).name != value
    ):
        raise ValueError("Invalid PhysicsNeMo artifact filename")
    return value


def _physnemo_runtime_storage() -> Dict[str, Any]:
    state = load_state()
    runtime = state.get("physnemo_runtime") if isinstance(state, dict) else None
    if not isinstance(runtime, dict) or not runtime.get("configured"):
        raise RuntimeError("PhysicsNeMo runtime is not configured")
    distro = str(runtime.get("distro") or "").strip()
    root = str(runtime.get("artifact_root") or "").rstrip("/")
    secret = str(runtime.get("artifact_secret") or "")
    if not distro or not root.startswith("/") or not secret:
        raise RuntimeError("PhysicsNeMo artifact storage is unavailable")
    return runtime


def _physnemo_wsl_read_file(
    runtime: Dict[str, Any],
    linux_path: str,
    *,
    allowed_prefix: str,
    max_bytes: int,
) -> bytes:
    distro = str(runtime["distro"])
    wsl = shutil.which("wsl.exe") or shutil.which("wsl")
    if not wsl:
        raise RuntimeError("wsl.exe was not found")
    resolved_result = subprocess.run(
        [wsl, "-d", distro, "--exec", "/usr/bin/readlink", "-f", "--", linux_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=20,
    )
    if resolved_result.returncode != 0:
        raise FileNotFoundError(linux_path)
    resolved_path = resolved_result.stdout.decode("utf-8", errors="strict").strip()
    if resolved_path != linux_path or not resolved_path.startswith(allowed_prefix):
        raise RuntimeError("Artifact path contains a symlink or escapes the managed job directory")
    stat_result = subprocess.run(
        [wsl, "-d", distro, "--exec", "/usr/bin/stat", "-Lc", "%s", "--", resolved_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=20,
    )
    if stat_result.returncode != 0:
        raise FileNotFoundError(linux_path)
    try:
        size = int(stat_result.stdout.decode("ascii", errors="strict").strip())
    except (UnicodeError, ValueError) as exc:
        raise RuntimeError("Invalid WSL artifact size") from exc
    if size < 0 or size > max_bytes:
        raise RuntimeError(f"Artifact exceeds the {max_bytes} byte gateway limit")
    result = subprocess.run(
        [wsl, "-d", distro, "--exec", "/bin/cat", "--", resolved_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=120,
    )
    if result.returncode != 0 or len(result.stdout) != size:
        raise RuntimeError(
            "Could not read the complete WSL artifact: "
            + result.stderr.decode("utf-8", errors="replace")[-1000:]
        )
    return bytes(result.stdout)


def _physnemo_artifact_url(
    runtime: Dict[str, Any],
    job_id: str,
    filename: str,
    *,
    download: bool,
    lifetime_seconds: int = 24 * 60 * 60,
) -> str:
    job_id = _physnemo_safe_job_id(job_id)
    filename = _physnemo_safe_artifact_name(filename)
    state = load_state()
    port = int(state.get("mcpo_port", DEFAULT_MCPO_PORT)) if isinstance(state, dict) else DEFAULT_MCPO_PORT
    base = str(runtime.get("artifact_base_url") or "").rstrip("/")
    if not base:
        base = f"http://127.0.0.1:{port}/{PHYSNEMO_ROUTE}/artifacts"
    expires = int(time.time()) + max(60, min(int(lifetime_seconds), 7 * 24 * 60 * 60))
    secret = str(runtime["artifact_secret"])
    message = f"{job_id}/{filename}/{expires}".encode("utf-8")
    signature = hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
    return (
        f"{base}/{urllib.parse.quote(job_id, safe='')}/{urllib.parse.quote(filename, safe='')}"
        f"?expires={expires}&signature={signature}&download={1 if download else 0}"
    )


def _physnemo_decode_text(data: bytes) -> str:
    if data.startswith(b"\xef\xbb\xbf"):
        return data.decode("utf-8-sig", errors="replace")
    return data.decode("utf-8", errors="replace")


def _physnemo_table_html(text: str, delimiter: str) -> str:
    rows: List[List[str]] = []
    try:
        reader = csv.reader(text.splitlines(), delimiter=delimiter)
        for index, row in enumerate(reader):
            if index >= 100:
                break
            rows.append([str(cell)[:2000] for cell in row[:30]])
    except csv.Error:
        rows = []
    if not rows:
        return '<p class="muted">Tabular preview is empty or could not be parsed.</p>'
    output = ['<div class="table-wrap"><table>']
    for row_index, row in enumerate(rows):
        tag = "th" if row_index == 0 else "td"
        output.append("<tr>" + "".join(f"<{tag}>{html_module.escape(cell)}</{tag}>" for cell in row) + "</tr>")
    output.append("</table></div>")
    if len(text.splitlines()) > len(rows):
        output.append('<p class="muted">Preview limited to the first 100 rows.</p>')
    return "".join(output)


def _physnemo_render_gallery(job_id: str) -> str:
    job_id = _physnemo_safe_job_id(job_id)
    runtime = _physnemo_runtime_storage()
    root = str(runtime["artifact_root"]).rstrip("/")
    job_root = f"{root}/{job_id}"
    manifest_bytes = _physnemo_wsl_read_file(
        runtime,
        f"{job_root}/manifest.json",
        allowed_prefix=f"{job_root}/",
        max_bytes=4 * 1024 * 1024,
    )
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("PhysicsNeMo artifact manifest is invalid") from exc
    if not isinstance(manifest, dict):
        raise RuntimeError("PhysicsNeMo artifact manifest has an invalid shape")
    raw_artifacts = manifest.get("artifacts") or []
    if not isinstance(raw_artifacts, list):
        raw_artifacts = []
    artifacts = [item for item in raw_artifacts if isinstance(item, dict)][:96]

    status = {}
    try:
        status = json.loads(_physnemo_wsl_read_file(runtime, f"{job_root}/status.json",
            allowed_prefix=f"{job_root}/", max_bytes=1024 * 1024).decode("utf-8"))
        if not isinstance(status, dict):
            status = {}
    except (FileNotFoundError, ValueError):
        pass  # Older jobs may not contain the new lifecycle metadata.
    delivery = status.get("delivery") or {}
    state_text = html_module.escape(str(status.get("state") or "unknown"))
    notice = ""
    if status.get("result_kind") == "answer_only":
        notice += '<p class="warning">Pouze textová odpověď agenta; samostatné výstupy výpočtu nebyly vytvořeny.</p>'
    if delivery.get("missing"):
        notice += '<p class="warning">Chybějící výstupy: ' + html_module.escape('; '.join(str(x) for x in delivery['missing'])) + '</p>'
    if delivery.get("unchecked_expectations"):
        notice += '<p class="warning">Tyto požadavky nebyly automaticky ověřeny: ' + html_module.escape('; '.join(str(x) for x in delivery['unchecked_expectations'])) + '</p>'
    for warning in manifest.get("warnings") or []:
        notice += '<p class="warning">' + html_module.escape(str(warning)) + '</p>'
    cards: List[str] = []
    inline_image_bytes = 0
    for item in artifacts:
        try:
            name = _physnemo_safe_artifact_name(str(item.get("name") or ""))
        except ValueError:
            continue
        media_type = str(item.get("media_type") or mimetypes.guess_type(name)[0] or "application/octet-stream")
        size = int(item.get("size") or 0)
        sha256_value = str(item.get("sha256") or "")
        preview_url = _physnemo_artifact_url(runtime, job_id, name, download=False)
        download_url = _physnemo_artifact_url(runtime, job_id, name, download=True)
        safe_name = html_module.escape(name)
        safe_media = html_module.escape(media_type)
        meta = f"{safe_media} · {size:,} B" + (f" · SHA-256 {html_module.escape(sha256_value[:16])}…" if sha256_value else "")
        body = ""
        suffix = Path(name).suffix.lower()
        linux_path = f"{job_root}/artifacts/{name}"
        allowed_prefix = f"{job_root}/artifacts/"
        try:
            if media_type.startswith("image/"):
                image_src = preview_url
                # Portable previews in sandboxed Open WebUI iframes. Download URLs stay signed.
                if 0 < size <= 8 * 1024 * 1024 and inline_image_bytes + size <= 24 * 1024 * 1024:
                    try:
                        data = _physnemo_wsl_read_file(runtime, linux_path, allowed_prefix=allowed_prefix,
                                                     max_bytes=8 * 1024 * 1024)
                        if sha256_value and hashlib.sha256(data).hexdigest() != sha256_value:
                            raise RuntimeError("Artifact digest changed after finalization")
                        image_src = "data:" + media_type + ";base64," + base64.b64encode(data).decode("ascii")
                        inline_image_bytes += len(data)
                    except Exception:
                        image_src = preview_url
                body = (
                    f'<a class="image-link" href="{html_module.escape(preview_url, quote=True)}" target="_self">'
                    f'<img loading="lazy" src="{html_module.escape(image_src, quote=True)}" alt="{safe_name}"></a>'
                )
            elif media_type.startswith("video/"):
                body = f'<video controls preload="metadata" style="max-width:100%" src="{html_module.escape(preview_url, quote=True)}"></video>'
            elif media_type.startswith("audio/"):
                body = f'<audio controls preload="metadata" src="{html_module.escape(preview_url, quote=True)}"></audio>'
            elif media_type == "application/pdf" or suffix == ".pdf":
                body = (
                    f'<iframe class="pdf" src="{html_module.escape(preview_url, quote=True)}" '
                    f'title="{safe_name}"></iframe>'
                )
            elif suffix in {".csv", ".tsv"}:
                data = _physnemo_wsl_read_file(
                    runtime, linux_path, allowed_prefix=allowed_prefix, max_bytes=2 * 1024 * 1024
                )
                body = _physnemo_table_html(_physnemo_decode_text(data), "\t" if suffix == ".tsv" else ",")
            elif suffix == ".json" or media_type == "application/json":
                data = _physnemo_wsl_read_file(
                    runtime, linux_path, allowed_prefix=allowed_prefix, max_bytes=1024 * 1024
                )
                text = _physnemo_decode_text(data)
                try:
                    text = json.dumps(json.loads(text), ensure_ascii=False, indent=2)
                except json.JSONDecodeError:
                    pass
                body = f'<pre><code>{html_module.escape(text[:120000])}</code></pre>'
            elif media_type.startswith("text/") or suffix in _PHYSNEMO_GALLERY_TEXT_SUFFIXES:
                data = _physnemo_wsl_read_file(
                    runtime, linux_path, allowed_prefix=allowed_prefix, max_bytes=2 * 1024 * 1024
                )
                text = _physnemo_decode_text(data)
                truncated = len(text) > 120000
                body = f'<pre><code>{html_module.escape(text[:120000])}</code></pre>'
                if truncated:
                    body += '<p class="muted">Preview truncated to 120,000 characters.</p>'
            else:
                body = '<p class="binary">Binary artifact — use the verified download control below.</p>'
        except Exception as exc:
            body = f'<p class="warning">Preview unavailable: {html_module.escape(str(exc))}</p>'
        cards.append(
            '<section class="artifact">'
            f'<header><h2>{safe_name}</h2><span>{meta}</span></header>'
            f'{body}'
            '<footer>'
            f'<a class="button" href="{html_module.escape(download_url, quote=True)}" download="{safe_name}">Download</a>'
            f'<a class="button secondary" href="{html_module.escape(preview_url, quote=True)}" target="_self">Open raw</a>'
            '</footer></section>'
        )

    count = len(cards)
    generated_at = html_module.escape(str(manifest.get("generated_at") or manifest.get("created_at") or ""))
    empty = '<p class="empty">The job manifest contains no renderable artifacts.</p>' if not cards else ""
    html = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>PhysicsNeMo artifacts — {html_module.escape(job_id)}</title>
<style>
:root{{color-scheme:light dark;font-family:Inter,ui-sans-serif,system-ui,sans-serif}}*{{box-sizing:border-box}}
body{{margin:0;padding:18px;background:transparent;color:inherit}}.hero{{padding:16px 18px;border:1px solid #8885;border-radius:16px;margin-bottom:16px;background:#8881}}
.hero h1{{margin:0 0 6px;font-size:1.25rem}}.muted{{opacity:.72;font-size:.88rem}}.grid{{display:grid;gap:16px}}
.artifact{{border:1px solid #8885;border-radius:16px;padding:14px;background:#8880;overflow:hidden}}header{{display:flex;gap:12px;align-items:baseline;justify-content:space-between;flex-wrap:wrap}}
h2{{font-size:1rem;margin:0 0 10px;overflow-wrap:anywhere}}header span{{font-size:.78rem;opacity:.68}}img{{display:block;max-width:100%;height:auto;margin:8px auto;border-radius:10px;background:#fff}}
pre{{max-height:520px;overflow:auto;padding:12px;border-radius:10px;background:#111;color:#eee;white-space:pre-wrap;word-break:break-word;font-size:.82rem}}
.table-wrap{{max-height:520px;overflow:auto;border:1px solid #8884;border-radius:10px}}table{{border-collapse:collapse;width:100%;font-size:.82rem}}th,td{{padding:7px 9px;border:1px solid #8883;text-align:left;vertical-align:top}}th{{position:sticky;top:0;background:#555;color:#fff}}
.pdf{{width:100%;height:620px;border:1px solid #8884;border-radius:10px}}footer{{display:flex;gap:9px;flex-wrap:wrap;margin-top:12px}}.button{{display:inline-block;padding:8px 12px;border-radius:9px;text-decoration:none;background:#2563eb;color:#fff;font-weight:650}}.button.secondary{{background:#666}}.warning{{color:#b45309}}.binary,.empty{{padding:18px;border-radius:10px;background:#8881}}
</style></head><body>
<div class="hero"><h1>PhysicsNeMo artifact gallery</h1><div>Job <code>{html_module.escape(job_id)}</code> · {count} artifact(s)</div><div class="muted">{generated_at}</div></div>
<div>Stav úlohy: <strong>{state_text}</strong></div>{notice}<div class="grid">{empty}{''.join(cards)}</div>
<script>function h(){{parent.postMessage({{type:'iframe:height',height:Math.max(document.body.scrollHeight,document.documentElement.scrollHeight)+24}},'*')}}addEventListener('load',h);new ResizeObserver(h).observe(document.body);</script>
</body></html>'''
    return html


def _physnemo_job_payload_from_tool_response(raw: bytes) -> Dict[str, Any]:
    def visit(value: Any, depth: int = 0) -> Dict[str, Any]:
        if depth > 12:
            return {}
        if isinstance(value, str):
            try:
                return visit(json.loads(value), depth + 1)
            except (ValueError, TypeError):
                return {}
        if isinstance(value, dict):
            if "job_id" in value and "state" in value:
                return value
            for key in ("result", "data", "content", "text", "output", "tool_result", "response", "structuredContent"):
                if key in value:
                    found = visit(value[key], depth + 1)
                    if found:
                        return found
        if isinstance(value, list):
            for item in value:
                found = visit(item, depth + 1)
                if found:
                    return found
        return {}
    try:
        return visit(json.loads(raw.decode("utf-8")))
    except (ValueError, UnicodeError):
        return {}


def _physnemo_completed_job_id_from_tool_response(raw: bytes) -> str:
    """Extract a completed PhysicsNeMo job id from MCPO's JSON/string response envelope."""
    try:
        value: Any = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        return ""

    seen: set[int] = set()

    def visit(item: Any, depth: int = 0) -> str:
        if depth > 10:
            return ""
        if isinstance(item, (dict, list)):
            identity = id(item)
            if identity in seen:
                return ""
            seen.add(identity)
        if isinstance(item, str):
            text = item.strip()
            if not text or text[0:1] not in {"{", "[", '"'}:
                return ""
            try:
                return visit(json.loads(text), depth + 1)
            except json.JSONDecodeError:
                return ""
        if isinstance(item, dict):
            job_id = str(item.get("job_id") or "").strip()
            state = str(item.get("state") or item.get("status") or "").strip().casefold()
            if job_id and state in {"completed", "complete", "succeeded", "success", "done"}:
                try:
                    return _physnemo_safe_job_id(job_id)
                except ValueError:
                    return ""
            preferred = ("result", "data", "content", "text", "output", "tool_result", "response", "structuredContent")
            for key in preferred:
                if key in item:
                    found = visit(item[key], depth + 1)
                    if found:
                        return found
            for nested in item.values():
                found = visit(nested, depth + 1)
                if found:
                    return found
            return ""
        if isinstance(item, list):
            for nested in item:
                found = visit(nested, depth + 1)
                if found:
                    return found
        return ""

    return visit(value)

def _engineering_openapi_operation_id(route: Any) -> str:
    """Return a stable OpenAPI operation id for MCPO/Open WebUI tools.

    MCPO registers every dynamic endpoint with a Python handler named ``tool``.
    FastAPI's default id therefore becomes e.g. ``tool_physnemo__solve_post``.
    Open WebUI uses operationId as the LLM function name, so the default hides
    the original MCP name.  The route's final path segment is already the exact
    MCP tool name and is unique inside each mounted product application.
    """
    explicit = str(getattr(route, "operation_id", None) or "").strip()
    if explicit:
        return explicit
    path = str(getattr(route, "path_format", None) or getattr(route, "path", ""))
    candidate = path.rstrip("/").split("/")[-1] if path else ""
    if candidate and "{" not in candidate and "}" not in candidate:
        return candidate
    name = re.sub(r"[^A-Za-z0-9_-]+", "_", str(getattr(route, "name", "operation"))).strip("_")
    methods = sorted(str(value).lower() for value in (getattr(route, "methods", None) or []) if value)
    method = methods[0] if methods else "call"
    return f"{name or 'operation'}_{method}"


def run_named_mcpo(arguments: List[str]) -> int:
    """Run MCPO with product-specific Swagger and OpenAPI endpoint names.

    Upstream MCPO mounts every sub-application with the generic relative paths
    ``/docs`` and ``/openapi.json``.  Those paths are valid under different
    mount prefixes, but some Open WebUI/Desktop builds derive a displayed id
    from the final URL segment.  In that UI all servers then appear as ``docs``.

    This runner keeps MCPO itself intact and replaces only the FastAPI class
    used while MCPO builds its applications.  Every mounted product receives:

      /<product>/<product>-docs
      /<product>/<product>-openapi.json

    Generic /docs and /openapi.json routes are intentionally disabled.  This
    prevents clients that derive an integration identifier from the final URL
    segment from collapsing several products into one generic ``docs`` entry.
    """
    parser = argparse.ArgumentParser(
        prog="engineering_mcp_unified-v2.9.18.py --named-mcpo",
        description="Internal MCPO runner with product-specific docs paths",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=DEFAULT_MCPO_PORT)
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--name", default="Engineering MCP Gateway")
    parser.add_argument(
        "--description",
        default="Engineering application MCP servers exposed as separate OpenAPI routes",
    )
    parser.add_argument("--version", default=BOOTSTRAPPER_VERSION)
    parser.add_argument("--hot-reload", action="store_true")
    parser.add_argument("--strict-auth", action="store_true")
    parsed = parser.parse_args(arguments)

    try:
        import asyncio
        from fastapi import FastAPI as OriginalFastAPI
        import mcpo.main as mcpo_main
    except ImportError as exc:
        print(f"named MCPO runner: required package is missing: {exc}", file=sys.stderr)
        return 127

    class ProductNamedFastAPI(OriginalFastAPI):
        """FastAPI app with unique documentation/spec routes per MCP product."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            title = str(kwargs.get("title") or "engineering-mcp")
            slug = route_slug(title)
            unique_docs_url = f"/{documentation_path(slug)}"
            unique_openapi_url = f"/{openapi_schema_path(slug)}"

            # MCPO does not currently pass these values, but assign explicitly
            # so a future FastAPI default change cannot reintroduce /docs.
            kwargs["docs_url"] = unique_docs_url
            kwargs["openapi_url"] = unique_openapi_url
            kwargs["redoc_url"] = None
            # Preserve exact MCP tool names as OpenAPI operationIds. Open WebUI
            # uses operationId as the function name exposed to the model.
            kwargs["generate_unique_id_function"] = _engineering_openapi_operation_id
            super().__init__(*args, **kwargs)

            self.state.engineering_mcp_docs_path = unique_docs_url
            self.state.engineering_mcp_openapi_path = unique_openapi_url

            if slug == PHYSNEMO_ROUTE:
                from fastapi import Body, HTTPException, Query, Request
                from fastapi.responses import HTMLResponse, JSONResponse, Response
                # ``from __future__ import annotations`` stores nested route annotations
                # as strings. FastAPI resolves those strings against module globals, not
                # this method's locals; publish a private alias so Request is never
                # mistaken for a required query parameter.
                globals()["_EngineeringMCPRequest"] = Request

                @self.middleware("http")
                async def auto_render_completed_physnemo_solve(request: _EngineeringMCPRequest, call_next):
                    """Turn a completed solve response into a native Open WebUI inline gallery.

                    This removes the fragile second-model-call requirement: once the general
                    agent completes, Open WebUI receives text/html with Content-Disposition:
                    inline and renders every generated artifact in its embed container.
                    """
                    response = await call_next(request)
                    if not (
                        request.method.upper() == "POST"
                        and request.url.path.rstrip("/").endswith("/physnemo__solve")
                        and 200 <= int(getattr(response, "status_code", 0)) < 300
                    ):
                        return response

                    body = getattr(response, "body", None)
                    if body is None:
                        chunks: List[bytes] = []
                        async for chunk in response.body_iterator:
                            chunks.append(chunk if isinstance(chunk, bytes) else str(chunk).encode("utf-8"))
                        body = b"".join(chunks)
                    elif not isinstance(body, bytes):
                        body = bytes(body)

                    payload = _physnemo_job_payload_from_tool_response(body)
                    job_id = _physnemo_completed_job_id_from_tool_response(body)
                    if payload.get("state") == "incomplete" and payload.get("job_id"):
                        job_id = _physnemo_safe_job_id(payload["job_id"])
                    if payload.get("presentation_mode") == "structured":
                        job_id = ""  # The authorized Open WebUI lifecycle wrapper emits the gallery, retaining JSON context.
                    if job_id:
                        try:
                            content = await asyncio.to_thread(_physnemo_render_gallery, job_id)
                            return HTMLResponse(
                                content=content,
                                status_code=200,
                                headers={
                                    "Content-Disposition": "inline",
                                    "Cache-Control": "private, no-store",
                                    "X-Content-Type-Options": "nosniff",
                                    "X-Engineering-MCP-Artifact-Job": job_id,
                                    "Content-Security-Policy": (
                                        "default-src 'none'; img-src data: http: https:; style-src 'unsafe-inline'; "
                                        "script-src 'unsafe-inline'; frame-src http: https:; object-src http: https:; "
                                        "media-src http: https: data:; connect-src 'none'; base-uri 'none'; form-action 'none'"
                                    ),
                                },
                            )
                        except Exception as exc:
                            # Never silently convert a failed presentation into apparent complete success.
                            import logging as _logging
                            _logging.getLogger(__name__).warning("PHYSNEMO_GALLERY_FAILED job=%s type=%s", job_id, type(exc).__name__)
                            payload["presentation"] = {"state": "failed", "error": "PHYSNEMO_GALLERY_FAILED",
                                                       "error_type": type(exc).__name__}
                            payload["display_instruction"] = "Show the actual answer and available signed downloads. Do not rerun solve to repair display."
                            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

                    headers = {
                        key: value
                        for key, value in response.headers.items()
                        if key.casefold() not in {"content-length", "content-type"}
                    }
                    return Response(
                        content=body,
                        status_code=response.status_code,
                        headers=headers,
                        media_type=getattr(response, "media_type", None)
                        or response.headers.get("content-type", "application/json").split(";", 1)[0],
                        background=getattr(response, "background", None),
                    )

                @self.get(
                    "/artifacts/{job_id}/{filename}",
                    include_in_schema=False,
                    name="physnemo_signed_artifact",
                )
                async def signed_physnemo_artifact(
                    job_id: str,
                    filename: str,
                    expires: int = Query(...),
                    signature: str = Query(..., min_length=64, max_length=64),
                    download: int = Query(1, ge=0, le=1),
                ):
                    try:
                        job_id = _physnemo_safe_job_id(job_id)
                        filename = _physnemo_safe_artifact_name(filename)
                        runtime = _physnemo_runtime_storage()
                    except ValueError as exc:
                        raise HTTPException(status_code=400, detail=str(exc))
                    except RuntimeError as exc:
                        raise HTTPException(status_code=503, detail=str(exc))
                    if expires < int(time.time()) or expires > int(time.time()) + 8 * 24 * 60 * 60:
                        raise HTTPException(status_code=403, detail="Artifact URL has expired or has an invalid lifetime")
                    secret = str(runtime["artifact_secret"])
                    message = f"{job_id}/{filename}/{expires}".encode("utf-8")
                    expected = hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
                    if not hmac.compare_digest(expected, signature):
                        raise HTTPException(status_code=403, detail="Invalid artifact signature")
                    root = str(runtime["artifact_root"]).rstrip("/")
                    linux_path = f"{root}/{job_id}/artifacts/{filename}"
                    try:
                        content = await asyncio.to_thread(
                            _physnemo_wsl_read_file,
                            runtime,
                            linux_path,
                            allowed_prefix=f"{root}/{job_id}/artifacts/",
                            max_bytes=256 * 1024 * 1024,
                        )
                    except FileNotFoundError:
                        raise HTTPException(status_code=404, detail="Artifact not found")
                    except Exception as exc:
                        raise HTTPException(status_code=500, detail=f"Artifact read failed: {exc}")
                    media_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
                    disposition = "attachment" if download else "inline"
                    safe_name = filename.replace('"', "_")
                    return Response(
                        content=content,
                        media_type=media_type,
                        headers={
                            "Content-Disposition": f'{disposition}; filename="{safe_name}"',
                            "Cache-Control": "private, no-store",
                            "X-Content-Type-Options": "nosniff",
                        },
                    )

                @self.post(
                    "/render-artifacts",
                    operation_id="physnemo__render_artifacts",
                    summary="Render every artifact from a PhysicsNeMo job in Open WebUI",
                    description=(
                        "Call this operation after physnemo__solve or after a completed job_status. It returns an "
                        "inline HTML gallery that Open WebUI renders directly: images and SVG are displayed, CSV/TSV "
                        "become tables, JSON and source code are previewed, PDF is embedded, and every file has a "
                        "working signed download control. Do not fabricate markdown links or file ids."
                    ),
                    response_class=HTMLResponse,
                    tags=["PhysicsNeMo artifacts"],
                )
                async def render_physnemo_artifacts(
                    job_id: str = Body(..., embed=True, min_length=8, max_length=96),
                ):
                    try:
                        content = await asyncio.to_thread(_physnemo_render_gallery, job_id)
                    except ValueError as exc:
                        raise HTTPException(status_code=400, detail=str(exc))
                    except FileNotFoundError:
                        raise HTTPException(status_code=404, detail="PhysicsNeMo artifact manifest was not found")
                    except Exception as exc:
                        raise HTTPException(status_code=500, detail=f"Artifact gallery failed: {exc}")
                    return HTMLResponse(
                        content=content,
                        status_code=200,
                        headers={
                            "Content-Disposition": "inline",
                            "Cache-Control": "private, no-store",
                            "X-Content-Type-Options": "nosniff",
                            "Content-Security-Policy": (
                                "default-src 'none'; img-src data: http: https:; style-src 'unsafe-inline'; "
                                "script-src 'unsafe-inline'; frame-src http: https:; object-src http: https:; "
                                "media-src http: https: data:; connect-src 'none'; base-uri 'none'; form-action 'none'"
                            ),
                        },
                    )

                def _physnemo_agent_bridge_config(request: _EngineeringMCPRequest) -> tuple[str, str, str, str]:
                    secret_config = read_json(PHYSNEMO_AGENT_SECRET_FILE)
                    bridge_secret = str(secret_config.get("bridge_secret") or "")
                    authorization = str(request.headers.get("authorization") or "")
                    supplied = authorization[7:].strip() if authorization.lower().startswith("bearer ") else ""
                    if not supplied:
                        supplied = str(request.headers.get("x-engineering-mcp-bridge") or "")
                    if not bridge_secret or not hmac.compare_digest(bridge_secret, supplied):
                        raise HTTPException(status_code=403, detail="Invalid PhysicsNeMo agent bridge credential")
                    base_url = str(secret_config.get("openwebui_base_url") or "").rstrip("/")
                    api_key = str(secret_config.get("openwebui_api_key") or "")
                    model = str(secret_config.get("agent_model") or "")
                    if not base_url or not api_key or not model:
                        raise HTTPException(
                            status_code=503,
                            detail="Open WebUI agent bridge is not configured",
                        )
                    return base_url, api_key, model, bridge_secret

                def _physnemo_openwebui_request(
                    method: str,
                    target: str,
                    api_key: str,
                    *,
                    body: bytes | None = None,
                    accept: str = "application/json",
                ) -> tuple[int, bytes, str, dict[str, str]]:
                    headers = {
                        "Authorization": f"Bearer {api_key}",
                        "Accept": accept or "application/json",
                        "User-Agent": "EngineeringMCP-PhysicsNeMo-AgentBridge/2.9.18",
                        "X-Engineering-MCP-Internal-Agent": "1",
                    }
                    if body is not None:
                        headers["Content-Type"] = "application/json"
                    req = urllib.request.Request(target, data=body, headers=headers, method=method)
                    try:
                        with urllib.request.urlopen(req, timeout=900) as upstream:
                            content = upstream.read(32 * 1024 * 1024 + 1)
                            if len(content) > 32 * 1024 * 1024:
                                raise RuntimeError("Open WebUI agent response exceeds the 32 MiB bridge limit")
                            response_headers = {
                                key: value
                                for key, value in upstream.headers.items()
                                if key.casefold() in {"content-type", "x-request-id", "openai-processing-ms"}
                            }
                            return (
                                int(getattr(upstream, "status", 200)),
                                content,
                                upstream.headers.get_content_type() or "application/json",
                                response_headers,
                            )
                    except urllib.error.HTTPError as exc:
                        content = exc.read(8 * 1024 * 1024 + 1)
                        response_headers = {
                            key: value
                            for key, value in exc.headers.items()
                            if key.casefold() in {"content-type", "x-request-id", "openai-processing-ms"}
                        }
                        return (
                            int(exc.code),
                            content,
                            exc.headers.get_content_type() or "application/json",
                            response_headers,
                        )

                @self.get(
                    "/openwebui-api/models",
                    include_in_schema=False,
                    name="physnemo_openwebui_agent_models",
                )
                async def openwebui_agent_models(request: _EngineeringMCPRequest):
                    base_url, api_key, _model, _bridge_secret = _physnemo_agent_bridge_config(request)
                    target = f"{base_url}/api/models"
                    try:
                        status, content, media_type, headers = await asyncio.to_thread(
                            _physnemo_openwebui_request,
                            "GET",
                            target,
                            api_key,
                        )
                    except Exception as exc:
                        return JSONResponse(
                            status_code=502,
                            content={
                                "error": {
                                    "message": f"Open WebUI agent bridge connection failed: {type(exc).__name__}: {exc}",
                                    "type": "engineering_mcp_openwebui_bridge_error",
                                    "code": "openwebui_bridge_unreachable",
                                }
                            },
                        )
                    headers["Cache-Control"] = "private, no-store"
                    return Response(content=content, status_code=status, media_type=media_type, headers=headers)

                # ENGINEERING_MCP_PHYSNEMO_SSE_COMPAT_V1
                def _physnemo_collect_upstream_sse(content: bytes) -> bytes:
                    """Reassemble actual upstream SSE; never interpret assistant prose as calls."""
                    if len(content) > 32 * 1024 * 1024:
                        raise ValueError("openwebui_stream_too_large")
                    try:
                        text = content.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
                    except UnicodeDecodeError as exc:
                        raise ValueError("openwebui_stream_invalid_utf8") from exc
                    common = {"object": "chat.completion"}
                    choices = {}
                    done = False
                    full = None
                    count = 0
                    for block in text.split("\n\n"):
                        fields = [line[5:].lstrip(" ") for line in block.split("\n") if line.startswith("data:")]
                        if not fields:
                            continue
                        data = "\n".join(fields)
                        if data == "[DONE]":
                            done = True
                            break  # SDK semantics: ignore any wrapper events after DONE.
                        count += 1
                        if count > 100_000:
                            raise ValueError("openwebui_stream_event_limit")
                        try:
                            frame = json.loads(data)
                        except (ValueError, RecursionError) as exc:
                            raise ValueError("openwebui_stream_invalid_json") from exc
                        if not isinstance(frame, dict) or frame.get("error"):
                            raise ValueError("openwebui_stream_error")
                        # Some Pipe functions send a complete completion in one SSE event.
                        if frame.get("object") == "chat.completion":
                            if full is not None or choices or not isinstance(frame.get("choices"), list) or not frame["choices"]:
                                raise ValueError("openwebui_stream_ambiguous_completion")
                            full = frame
                            continue
                        if full is not None or frame.get("object") != "chat.completion.chunk":
                            raise ValueError("openwebui_stream_invalid_object")
                        for key in ("id", "created", "model", "system_fingerprint", "service_tier"):
                            if key in frame and key not in common:
                                common[key] = frame[key]
                        if isinstance(frame.get("usage"), dict):
                            common["usage"] = frame["usage"]
                        entries = frame.get("choices")
                        if not isinstance(entries, list):
                            raise ValueError("openwebui_stream_invalid_choices")
                        for entry in entries:
                            if not isinstance(entry, dict):
                                raise ValueError("openwebui_stream_invalid_choice")
                            index = entry.get("index")
                            if type(index) is not int or not 0 <= index < 128:
                                raise ValueError("openwebui_stream_invalid_index")
                            item = choices.setdefault(index, {"index": index, "message": {"role": "assistant", "content": None},
                                                               "finish_reason": None, "_tools": {}})
                            delta = entry.get("delta") or {}
                            if not isinstance(delta, dict):
                                raise ValueError("openwebui_stream_invalid_delta")
                            if delta.get("role") not in (None, "assistant"):
                                raise ValueError("openwebui_stream_invalid_role")
                            message = item["message"]
                            for key in ("content", "refusal", "reasoning_content"):
                                value = delta.get(key)
                                if value is not None:
                                    if not isinstance(value, str):
                                        raise ValueError("openwebui_stream_invalid_text")
                                    message[key] = (message.get(key) or "") + value
                            calls = delta.get("tool_calls") or []
                            if not isinstance(calls, list):
                                raise ValueError("openwebui_stream_invalid_calls")
                            for call in calls:
                                if not isinstance(call, dict) or type(call.get("index")) is not int or not 0 <= call["index"] < 128:
                                    raise ValueError("openwebui_stream_invalid_call_index")
                                tool = item["_tools"].setdefault(call["index"], {"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
                                if call.get("type") not in (None, "function"):
                                    raise ValueError("openwebui_stream_invalid_call_type")
                                if call.get("id") is not None:
                                    if not isinstance(call["id"], str):
                                        raise ValueError("openwebui_stream_invalid_call_id")
                                    if call["id"] != tool["id"]:
                                        tool["id"] += call["id"]
                                function = call.get("function") or {}
                                if not isinstance(function, dict):
                                    raise ValueError("openwebui_stream_invalid_function")
                                for key in ("name", "arguments"):
                                    if function.get(key) is not None:
                                        if not isinstance(function[key], str):
                                            raise ValueError("openwebui_stream_invalid_arguments")
                                        tool["function"][key] += function[key]
                            reason = entry.get("finish_reason")
                            if reason is not None:
                                if not isinstance(reason, str) or reason not in {"stop", "tool_calls", "length", "content_filter", "function_call"}:
                                    raise ValueError("openwebui_stream_invalid_finish")
                                # A Pipe wrapper may append its own empty stop event.
                                if item["finish_reason"] is None or reason != "stop":
                                    item["finish_reason"] = reason
                    if full is not None:
                        if any(not isinstance(c, dict) or c.get("finish_reason") is None for c in full.get("choices", [])):
                            raise ValueError("openwebui_stream_incomplete")
                        return json.dumps(full, ensure_ascii=False).encode("utf-8")
                    if not done or not choices or any(c["finish_reason"] is None for c in choices.values()):
                        raise ValueError("openwebui_stream_incomplete")
                    output = []
                    for index in sorted(choices):
                        item = choices[index]
                        tools = item.pop("_tools")
                        if tools:
                            if sorted(tools) != list(range(len(tools))):
                                raise ValueError("openwebui_stream_missing_call_fragment")
                            item["message"]["tool_calls"] = [tools[i] for i in sorted(tools)]
                        output.append(item)
                    common["choices"] = output
                    return json.dumps(common, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

                # Keep the upstream request buffered, but honor the downstream wire protocol.
                def _physnemo_bridge_chat_response(
                    status: int,
                    content: bytes,
                    media_type: str,
                    headers: dict[str, str],
                    *,
                    client_stream: bool,
                    include_usage: bool,
                    configured_model: str,
                ):
                    import time as _bridge_time
                    import uuid as _bridge_uuid

                    # An upstream JSON Content-Type must not override our generated SSE type.
                    response_headers = {
                        key: value
                        for key, value in headers.items()
                        if key.casefold() not in {
                            "content-type", "content-length", "content-encoding", "transfer-encoding"
                        }
                    }
                    response_headers["Cache-Control"] = "private, no-store"
                    response_headers["X-Engineering-MCP-Bridge-Hotfix"] = "sse-compat-1"
                    response_headers["X-Engineering-MCP-Bridge-Protocol"] = "buffered-sse-v1"
                    response_headers["X-Engineering-MCP-Version"] = BOOTSTRAPPER_VERSION

                    def protocol_error(code: str, message: str):
                        # Do not put prompts, completion bodies, or credentials in diagnostics.
                        return JSONResponse(
                            status_code=502,
                            headers=response_headers,
                            content={"error": {
                                "message": message,
                                "type": "engineering_mcp_openwebui_bridge_error",
                                "code": code,
                                "upstream_status": status,
                                "upstream_content_type": media_type,
                                "upstream_bytes": len(content),
                            }},
                        )

                    if status >= 400:
                        return Response(
                            content=content, status_code=status,
                            media_type=media_type, headers=response_headers,
                        )
                    if status != 200:
                        return protocol_error(
                            "openwebui_unexpected_status", "Expected HTTP 200 with a chat completion."
                        )
                    try:
                        completion = json.loads(content.decode("utf-8-sig"))
                    except (ValueError, UnicodeError):
                        return protocol_error(
                            "openwebui_invalid_json",
                            "Expected a JSON completion or a valid reconstructed upstream SSE completion.",
                        )
                    if not isinstance(completion, dict):
                        return protocol_error("openwebui_invalid_completion", "Completion must be a JSON object.")
                    if completion.get("error"):
                        return protocol_error(
                            "openwebui_upstream_error",
                            "Open WebUI returned an error envelope with HTTP 200; inspect its server log.",
                        )
                    choices = completion.get("choices")
                    if not isinstance(choices, list) or not choices:
                        return protocol_error("openwebui_no_choices", "Open WebUI returned no completion choices.")

                    deltas = []
                    endings = []
                    seen_indices = set()
                    for position, choice in enumerate(choices):
                        if not isinstance(choice, dict) or not isinstance(choice.get("message"), dict):
                            return protocol_error("openwebui_invalid_choice", "Each choice must contain a message object.")
                        index = choice.get("index", position)
                        if type(index) is not int or index < 0 or index in seen_indices:
                            return protocol_error("openwebui_invalid_choice", "Choice indices must be unique non-negative integers.")
                        seen_indices.add(index)
                        message = choice["message"]
                        if message.get("role", "assistant") != "assistant":
                            return protocol_error("openwebui_invalid_choice", "Expected an assistant message.")
                        text = message.get("content")
                        refusal = message.get("refusal")
                        tool_calls = message.get("tool_calls")
                        function_call = message.get("function_call")
                        if text is not None and not isinstance(text, str):
                            return protocol_error("openwebui_invalid_choice", "This agent bridge expects text or null content.")
                        if refusal is not None and not isinstance(refusal, str):
                            return protocol_error("openwebui_invalid_choice", "Refusal must be text or null.")
                        if tool_calls is not None and not isinstance(tool_calls, list):
                            return protocol_error("openwebui_invalid_tool_calls", "tool_calls must be a list or null.")
                        indexed_tools = []
                        for tool_index, tool in enumerate(tool_calls or []):
                            if not isinstance(tool, dict):
                                return protocol_error("openwebui_invalid_tool_calls", "Each tool call must be an object.")
                            function = tool.get("function")
                            if (
                                tool.get("type") != "function"
                                or not isinstance(tool.get("id"), str) or not tool["id"]
                                or not isinstance(function, dict)
                                or not isinstance(function.get("name"), str) or not function["name"]
                                or not isinstance(function.get("arguments"), str)
                            ):
                                return protocol_error("openwebui_invalid_tool_calls", "Expected standard function tool calls with string arguments.")
                            indexed_tools.append({**tool, "index": tool_index})
                        if function_call is not None and (
                            not isinstance(function_call, dict)
                            or not isinstance(function_call.get("name"), str) or not function_call["name"]
                            or not isinstance(function_call.get("arguments"), str)
                        ):
                            return protocol_error("openwebui_invalid_tool_calls", "Invalid legacy function_call.")
                        if not (
                            (isinstance(text, str) and text.strip())
                            or (isinstance(refusal, str) and refusal.strip())
                            or indexed_tools or function_call
                        ):
                            return protocol_error(
                                "openwebui_no_usable_message",
                                "Open WebUI returned no text, refusal, or tool call. Reasoning alone is not an agent answer; inspect finish_reason and output-token limits upstream.",
                            )
                        finish_reason = choice.get("finish_reason")
                        if not isinstance(finish_reason, str) or not finish_reason:
                            return protocol_error("openwebui_invalid_choice", "A completed choice needs a finish_reason.")
                        delta = dict(message)
                        delta.setdefault("role", "assistant")
                        if tool_calls is not None:
                            delta["tool_calls"] = indexed_tools
                        deltas.append({
                            "index": index, "delta": delta,
                            "finish_reason": None, "logprobs": choice.get("logprobs"),
                        })
                        endings.append({
                            "index": index, "delta": {},
                            "finish_reason": finish_reason, "logprobs": None,
                        })

                    if not client_stream:
                        return Response(
                            content=content, status_code=200,
                            media_type="application/json", headers=response_headers,
                        )

                    # Buffered SSE, not live token streaming: never re-run the model request.
                    completion_id = completion.get("id")
                    if not isinstance(completion_id, str) or not completion_id:
                        completion_id = "chatcmpl-physnemo-" + _bridge_uuid.uuid4().hex
                    created = completion.get("created")
                    if type(created) is not int or created < 0:
                        created = int(_bridge_time.time())
                    model = completion.get("model")
                    if not isinstance(model, str) or not model:
                        model = configured_model
                    common = {
                        "id": completion_id, "object": "chat.completion.chunk",
                        "created": created, "model": model,
                    }
                    for key in ("system_fingerprint", "service_tier"):
                        if key in completion:
                            common[key] = completion[key]
                    frames = [
                        {**common, "choices": deltas},
                        {**common, "choices": endings},
                    ]
                    if include_usage:
                        for frame in frames:
                            frame["usage"] = None
                        if isinstance(completion.get("usage"), dict):
                            frames.append({**common, "choices": [], "usage": completion["usage"]})
                    wire = "".join(
                        "data: " + json.dumps(frame, ensure_ascii=False, separators=(",", ":")) + "\n\n"
                        for frame in frames
                    ) + "data: [DONE]\n\n"
                    response_headers["X-Accel-Buffering"] = "no"
                    return Response(
                        content=wire.encode("utf-8"), status_code=200,
                        media_type="text/event-stream", headers=response_headers,
                    )


                @self.post(
                    "/openwebui-api/chat/completions",
                    include_in_schema=False,
                    name="physnemo_openwebui_agent_chat",
                )
                async def openwebui_agent_chat(request: _EngineeringMCPRequest):
                    base_url, api_key, configured_model, _bridge_secret = _physnemo_agent_bridge_config(request)
                    body = await request.body()
                    if len(body) > 8 * 1024 * 1024:
                        raise HTTPException(status_code=413, detail="Agent request exceeds the 8 MiB bridge limit")
                    try:
                        payload = json.loads(body.decode("utf-8"))
                    except Exception as exc:
                        raise HTTPException(status_code=400, detail=f"Invalid OpenAI request JSON: {exc}")
                    if not isinstance(payload, dict):
                        raise HTTPException(status_code=400, detail="OpenAI request must be a JSON object")
                    requested_model = str(payload.get("model") or "")
                    if requested_model and requested_model != configured_model:
                        raise HTTPException(
                            status_code=400,
                            detail=(
                                f"PhysicsNeMo agent may use only the configured model {configured_model!r}; "
                                f"received {requested_model!r}"
                            ),
                        )
                    payload["model"] = configured_model
                    client_stream = payload.get("stream", False)
                    if client_stream is None:
                        client_stream = False
                    if type(client_stream) is not bool:
                        raise HTTPException(status_code=400, detail="stream must be a JSON boolean")
                    stream_options = payload.pop("stream_options", None)
                    if stream_options is not None and not isinstance(stream_options, dict):
                        raise HTTPException(status_code=400, detail="stream_options must be an object or null")
                    include_usage = bool(stream_options and stream_options.get("include_usage") is True)
                    # ainvoke() does not guarantee a non-streaming HTTP request. Preserve the
                    # client's requested protocol while keeping Windows -> Open WebUI buffered.
                    # stream_options is a streaming-only option, so remove it upstream.
                    # A non-streaming Pipe may stringify an async generator and lose
                    # native fields. Request real SSE upstream when supplying tools,
                    # then reassemble both text and fragmented function arguments.
                    tools = payload.get("tools")
                    if tools is not None and not isinstance(tools, list):
                        raise HTTPException(status_code=400, detail="tools must be an array or null")
                    upstream_stream = bool(tools)
                    payload["stream"] = upstream_stream
                    if upstream_stream:
                        params = payload.get("params") or {}
                        if not isinstance(params, dict):
                            raise HTTPException(status_code=400, detail="params must be an object")
                        payload["params"] = {**params, "function_calling": "native"}
                    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                    target = f"{base_url}/api/chat/completions"
                    try:
                        status, content, media_type, headers = await asyncio.to_thread(
                            _physnemo_openwebui_request,
                            "POST",
                            target,
                            api_key,
                            body=encoded,
                            accept="text/event-stream" if upstream_stream else "application/json",
                        )
                    except Exception as exc:
                        return JSONResponse(
                            status_code=502,
                            headers={
                                "Cache-Control": "private, no-store",
                                "X-Engineering-MCP-Bridge-Hotfix": "sse-compat-1",
                                "X-Engineering-MCP-Bridge-Protocol": "buffered-sse-v1",
                                "X-Engineering-MCP-Version": BOOTSTRAPPER_VERSION,
                            },
                            content={
                                "error": {
                                    "message": f"Open WebUI agent bridge connection failed: {type(exc).__name__}",
                                    "type": "engineering_mcp_openwebui_bridge_error",
                                    "code": "openwebui_bridge_unreachable",
                                }
                            },
                        )
                    headers = dict(headers)
                    headers["X-Engineering-MCP-Upstream-Transport"] = "sse" if upstream_stream else "json"
                    if status == 200 and media_type.split(";", 1)[0].strip().lower() == "text/event-stream":
                        try:
                            content = _physnemo_collect_upstream_sse(content)
                            media_type = "application/json"
                        except ValueError as exc:
                            return JSONResponse(status_code=502, headers={"Cache-Control": "private, no-store"},
                                content={"error": {"type": "engineering_mcp_openwebui_bridge_error",
                                                  "code": str(exc), "message": "Upstream SSE could not be safely reconstructed."}})
                    return _physnemo_bridge_chat_response(
                        status, content, media_type, headers,
                        client_stream=client_stream,
                        include_usage=include_usage,
                        configured_model=configured_model,
                    )

                @self.get(
                    "/input-files/{file_id}",
                    include_in_schema=False,
                    name="physnemo_openwebui_input_file",
                )
                async def openwebui_input_file(file_id: str, request: _EngineeringMCPRequest):
                    if not re.fullmatch(r"[A-Za-z0-9_-]{8,160}", file_id):
                        raise HTTPException(status_code=400, detail="Invalid Open WebUI file id")
                    secret_config = read_json(PHYSNEMO_AGENT_SECRET_FILE)
                    bridge_secret = str(secret_config.get("bridge_secret") or "")
                    supplied = str(request.headers.get("x-engineering-mcp-bridge") or "")
                    if not bridge_secret or not hmac.compare_digest(bridge_secret, supplied):
                        raise HTTPException(status_code=403, detail="Invalid file bridge credential")
                    base_url = str(secret_config.get("openwebui_base_url") or "").rstrip("/")
                    api_key = str(secret_config.get("openwebui_api_key") or "")
                    if not base_url or not api_key:
                        raise HTTPException(
                            status_code=503,
                            detail=(
                                "Open WebUI file-id bridge is not configured. Re-run the installer with "
                                "-PhysNeMoOpenWebUIApiKeyFile."
                            ),
                        )
                    target = f"{base_url}/api/v1/files/{urllib.parse.quote(file_id, safe='')}/content"

                    def fetch_openwebui_file() -> tuple[bytes, str, str]:
                        req = urllib.request.Request(
                            target,
                            headers={
                                "Authorization": f"Bearer {api_key}",
                                "User-Agent": "EngineeringMCP-PhysicsNeMo/2.9.18",
                            },
                        )
                        with urllib.request.urlopen(req, timeout=120) as response:
                            content = response.read(64 * 1024 * 1024 + 1)
                            if len(content) > 64 * 1024 * 1024:
                                raise RuntimeError("Open WebUI file exceeds the 64 MiB bridge limit")
                            content_type = response.headers.get_content_type() or "application/octet-stream"
                            disposition = str(response.headers.get("Content-Disposition") or "")
                            return content, content_type, disposition

                    try:
                        content, content_type, disposition = await asyncio.to_thread(fetch_openwebui_file)
                    except urllib.error.HTTPError as exc:
                        raise HTTPException(status_code=exc.code, detail="Open WebUI refused file access")
                    except Exception as exc:
                        raise HTTPException(status_code=502, detail=f"Open WebUI file bridge failed: {exc}")
                    headers = {
                        "Cache-Control": "private, no-store",
                        "X-Content-Type-Options": "nosniff",
                    }
                    if disposition:
                        headers["Content-Disposition"] = disposition
                    return Response(content=content, media_type=content_type, headers=headers)

    # create_sub_app(), mount/reload checks and the main app all use this module
    # global, so replacing it before run() is sufficient and avoids patching the
    # installed MCPO package on disk.
    mcpo_main.FastAPI = ProductNamedFastAPI

    try:
        asyncio.run(
            mcpo_main.run(
                parsed.host,
                parsed.port,
                api_key=parsed.api_key,
                strict_auth=parsed.strict_auth,
                cors_allow_origins=["*"],
                server_type="stdio",
                config_path=parsed.config,
                name=parsed.name,
                description=parsed.description,
                version=parsed.version,
                server_command=None,
                ssl_certfile=None,
                ssl_keyfile=None,
                path_prefix="/",
                root_path="",
                headers=None,
                hot_reload=parsed.hot_reload,
            )
        )
        return 0
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"named MCPO runner failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


# ---------------------------------------------------------------------------
# Application detection
# ---------------------------------------------------------------------------

def _has_any_file(root: Path, patterns: Iterable[str]) -> bool:
    for pattern in patterns:
        try:
            if any(item.is_file() for item in root.glob(pattern)):
                return True
        except OSError:
            continue
    return False


def detect_ansys() -> Dict[str, Any]:
    version_roots: List[Path] = []
    for key, value in os.environ.items():
        if re.fullmatch(r"AWP_ROOT\d+", key):
            candidate = Path(value)
            if candidate.exists():
                version_roots.append(candidate)

    if sys.platform.startswith("win"):
        base = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "ANSYS Inc"
        if base.exists():
            version_roots += [item for item in sorted(base.glob("v*"), reverse=True) if item.is_dir()]
    else:
        for base in (Path("/usr/ansys_inc"), Path("/ansys_inc"), Path.home() / "ansys_inc"):
            if base.exists():
                version_roots += [item for item in sorted(base.glob("v*"), reverse=True) if item.is_dir()]

    deduplicated: List[Path] = []
    seen: set[str] = set()
    for root in version_roots:
        key = os.path.normcase(str(root.resolve()))
        if key not in seen:
            seen.add(key)
            deduplicated.append(root)
    version_roots = deduplicated

    products = {"fluent": False, "mechanical": False, "mapdl": False, "aedt": False, "cfx": False}
    product_paths: Dict[str, List[str]] = {name: [] for name in products}

    for root in version_roots:
        if sys.platform.startswith("win"):
            probes = {
                "fluent": _has_any_file(root, ("fluent/ntbin/win64/fluent.exe", "fluent/ntbin/win64/*.exe")),
                "cfx": _has_any_file(root, ("CFX/bin/cfx5pre.exe", "CFX/bin/cfx5pre.bat")),
                "mapdl": _has_any_file(root, ("ansys/bin/winx64/ANSYS*.exe", "ansys/bin/winx64/mapdl.exe")),
                "mechanical": (root / "aisol" / "bin" / "winx64").is_dir(),
                "aedt": _has_any_file(root, ("AnsysEM/**/ansysedt.exe",)),
            }
        else:
            probes = {
                "fluent": (root / "fluent" / "bin" / "fluent").is_file(),
                "cfx": (root / "CFX" / "bin" / "cfx5pre").is_file(),
                "mapdl": _has_any_file(root, ("ansys/bin/linx64/ansys*", "ansys/bin/linx64/mapdl")),
                "mechanical": (root / "aisol").is_dir(),
                "aedt": _has_any_file(root, ("AnsysEM/**/ansysedt",)),
            }
        for name, found in probes.items():
            if found:
                products[name] = True
                product_paths[name].append(str(root))

    # AEDT is commonly installed outside the shared ANSYS Inc version tree.
    if sys.platform.startswith("win"):
        program_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        aedt_bases = [program_files / "AnsysEM", program_files / "ANSYS EM"]
        for base in aedt_bases:
            if not base.exists():
                continue
            found = _has_any_file(base, ("**/Win64/ansysedt.exe", "**/ansysedt.exe"))
            if found:
                products["aedt"] = True
                product_paths["aedt"].append(str(base))
    else:
        for base in (Path("/opt/AnsysEM"), Path("/usr/AnsysEM")):
            if base.exists() and _has_any_file(base, ("**/ansysedt",)):
                products["aedt"] = True
                product_paths["aedt"].append(str(base))

    all_paths = [str(item) for item in version_roots]
    for value in product_paths["aedt"]:
        if value not in all_paths:
            all_paths.append(value)
    return {
        "found": bool(all_paths),
        "paths": all_paths,
        "products": products,
        "product_paths": product_paths,
    }


def detect_lumerical() -> Dict[str, Any]:
    candidates: List[Path] = []
    if sys.platform.startswith("win"):
        program_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        candidates += list((program_files / "Lumerical").glob("v*")) if (program_files / "Lumerical").exists() else []
        candidates += list((program_files / "ANSYS Optics").glob("v*/Lumerical")) if (program_files / "ANSYS Optics").exists() else []
        ansys_inc = program_files / "ANSYS Inc"
        candidates += list(ansys_inc.glob("v*/Lumerical")) if ansys_inc.exists() else []
    else:
        for base in (Path("/opt/lumerical"), Path("/usr/local/lumerical")):
            if base.exists():
                candidates += list(base.glob("v*"))
        for base in (Path("/ansys_inc"), Path("/usr/ansys_inc"), Path.home() / "Ansys" / "ansys_inc"):
            if base.exists():
                candidates += list(base.glob("v*/Lumerical"))

    hits: List[str] = []
    for candidate in candidates:
        # The Python API is a more reliable signature than a generic ANSYS root.
        if (candidate / "api" / "python").is_dir() or (candidate / "bin").is_dir():
            value = str(candidate)
            if value not in hits:
                hits.append(value)
    return {"found": bool(hits), "paths": hits}


def matlab_release_tuple(value: Optional[object]) -> Optional[Tuple[int, int]]:
    if value is None:
        return None
    match = re.search(r"R(20\d{2})([ab])", str(value), flags=re.IGNORECASE)
    if not match:
        return None
    return int(match.group(1)), 0 if match.group(2).lower() == "a" else 1


def matlab_root_from_candidate(value: object) -> Optional[Path]:
    path = Path(str(value)).expanduser()
    lowered = path.name.lower()
    if lowered in {"matlab.exe", "matlab"} and path.parent.name.lower() == "bin":
        return path.parent.parent
    if sys.platform == "darwin" and path.suffix.lower() == ".app":
        return path
    if re.fullmatch(r"R20\d{2}[ab]", path.name, flags=re.IGNORECASE):
        return path
    if re.search(r"MATLAB_R20\d{2}[ab]\.app", path.name, flags=re.IGNORECASE):
        return path
    return None


def matlab_executable_from_root(root: object) -> Optional[Path]:
    root_path = Path(str(root))
    if sys.platform.startswith("win"):
        candidates = [root_path / "bin" / "matlab.exe"]
    elif sys.platform == "darwin":
        candidates = [
            root_path / "bin" / "matlab",
            root_path / "Contents" / "bin" / "matlab",
        ]
    else:
        candidates = [root_path / "bin" / "matlab"]
    return next((item for item in candidates if item.exists()), None)


def detect_matlab() -> Dict[str, Any]:
    hits: List[str] = []
    executable = which("matlab")
    if executable:
        hits.append(str(Path(executable).resolve()))
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "MATLAB"
        if base.exists():
            hits += [str(p) for p in sorted(base.glob("R20*"), reverse=True)]
    elif sys.platform == "darwin":
        hits += [str(p) for p in sorted(Path("/Applications").glob("MATLAB_R20*.app"), reverse=True)]
    else:
        base = Path("/usr/local/MATLAB")
        if base.exists():
            hits += [str(p) for p in sorted(base.glob("R20*"), reverse=True)]

    unique_hits = list(dict.fromkeys(hits))
    roots: List[str] = []
    for raw in unique_hits:
        root = matlab_root_from_candidate(raw)
        if root and root.exists() and str(root) not in roots:
            roots.append(str(root))
    roots.sort(key=lambda item: matlab_release_tuple(item) or (0, 0), reverse=True)
    selected_root = roots[0] if roots else None
    selected_executable = matlab_executable_from_root(selected_root) if selected_root else None
    return {
        "found": bool(unique_hits or roots),
        "paths": unique_hits,
        "roots": roots,
        "selected_root": selected_root,
        "executable": str(selected_executable) if selected_executable else executable,
        "release": Path(selected_root).name if selected_root else None,
    }


def detect_fusion() -> Dict[str, Any]:
    hits: List[str] = []
    if sys.platform.startswith("win"):
        local_app_data = Path(os.environ.get("LOCALAPPDATA", ""))
        for candidate in (
            local_app_data / "Autodesk" / "webdeploy" / "production",
            local_app_data / "Autodesk" / "Autodesk Fusion 360",
        ):
            if candidate.exists():
                hits.append(str(candidate))
    elif sys.platform == "darwin":
        candidate = Path("/Applications/Autodesk Fusion.app")
        if candidate.exists():
            hits.append(str(candidate))
    return {
        "found": bool(hits),
        "paths": hits,
        "mcp_port_open": tcp_open("127.0.0.1", 27182),
    }


def generic_detect(command: str, win_paths: Tuple[str, ...] = (), unix_paths: Tuple[str, ...] = ()) -> Dict[str, Any]:
    import glob

    hits: List[str] = []
    executable = which(command)
    if executable:
        hits.append(executable)
    candidates = win_paths if sys.platform.startswith("win") else unix_paths
    for raw in candidates:
        expanded = os.path.expandvars(raw)
        if any(char in expanded for char in "*?["):
            hits += [item for item in glob.glob(expanded) if Path(item).exists()]
        elif Path(expanded).exists():
            hits.append(expanded)
    return {"found": bool(hits), "paths": list(dict.fromkeys(hits))}


def detect_openwebui_docker() -> Dict[str, Any]:
    if not which("docker"):
        return {"docker": False, "daemon": False, "openwebui_container": False, "containers": []}
    result = run(["docker", "ps", "--format", "{{.Names}}|{{.Image}}"], timeout=8)
    if result.returncode != 0:
        return {"docker": True, "daemon": False, "openwebui_container": False, "containers": []}
    rows = [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]
    lowered = "\n".join(rows).lower()
    return {
        "docker": True,
        "daemon": True,
        "openwebui_container": "open-webui" in lowered or "openwebui" in lowered,
        "containers": rows,
    }


def _decode_process_bytes(value: bytes) -> str:
    if not value:
        return ""
    if b"\x00" in value:
        for encoding in ("utf-16-le", "utf-16"):
            try:
                return value.decode(encoding, errors="replace").replace("\ufeff", "")
            except UnicodeError:
                pass
    for encoding in ("utf-8", "cp1250", "cp1252"):
        try:
            return value.decode(encoding).replace("\ufeff", "")
        except UnicodeError:
            continue
    return value.decode("utf-8", errors="replace").replace("\ufeff", "")


def _run_bytes(command: List[str], timeout: float = 30.0) -> Tuple[int, str]:
    try:
        completed = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, str(exc)
    return int(completed.returncode), _decode_process_bytes(completed.stdout or b"")


def list_wsl_distributions() -> List[str]:
    if not sys.platform.startswith("win"):
        current = str(os.environ.get("WSL_DISTRO_NAME") or "").strip()
        return [current] if current else []
    wsl = which("wsl.exe") or which("wsl")
    if not wsl:
        return []
    code, output = _run_bytes([wsl, "--list", "--quiet"], timeout=20)
    if code != 0:
        return []
    distros: List[str] = []
    for raw in output.replace("\x00", "").splitlines():
        value = raw.strip().lstrip("*").strip()
        if not value or value.lower() in {"docker-desktop", "docker-desktop-data"}:
            continue
        if value not in distros:
            distros.append(value)
    return distros


def _parse_key_value_text(text: str) -> Dict[str, str]:
    values: Dict[str, str] = {}
    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("\r")
    return values


def _read_key_value_file(path: Path) -> Dict[str, str]:
    try:
        return _parse_key_value_text(path.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return {}


def _extract_mapped_port(value: str, default: int = 18080) -> int:
    raw = str(value or "").strip().removesuffix("/tcp")
    candidate = raw.rsplit(":", 1)[-1] if raw else str(default)
    try:
        port = int(candidate)
    except ValueError:
        return default
    return port if 1 <= port <= 65535 else default


def _normalise_weknora_urls(api_url: str) -> Tuple[str, str]:
    """Validate a WeKnora HTTP(S) URL and return ``(service_root, REST_base)``.

    ``api_url`` may be the public WeKnora origin, a reverse-proxy path prefix,
    ``.../health`` or the REST base itself ending in ``/api/v1``.  The returned
    REST base always ends in exactly one ``/api/v1`` segment.
    """
    value = str(api_url or "").strip()
    if not value:
        value = "https://localhost:8088"
    if "://" not in value:
        value = "https://" + value
    parsed = urllib.parse.urlsplit(value)
    scheme = parsed.scheme.lower()
    if scheme not in WEKNORA_ALLOWED_SCHEMES:
        raise RuntimeError("WeKnoraUrl must use http:// or https://")
    if not parsed.hostname:
        raise RuntimeError("WeKnora URL must contain a host name or IP address")
    if parsed.username is not None or parsed.password is not None:
        raise RuntimeError("Do not embed credentials in WeKnoraUrl; use WeKnoraApiKeyFile")
    if parsed.query or parsed.fragment:
        raise RuntimeError("WeKnora URL must not contain a query string or fragment")
    try:
        _ = parsed.port
    except ValueError as exc:
        raise RuntimeError(f"WeKnora URL contains an invalid port: {exc}") from exc

    path = re.sub(r"/+$", "", parsed.path or "")
    lowered_path = path.casefold()
    if lowered_path.endswith("/health"):
        path = path[: -len("/health")]
        lowered_path = path.casefold()
    if lowered_path.endswith("/api/v1"):
        root_path = path[: -len("/api/v1")]
        api_path = root_path + "/api/v1"
    else:
        root_path = path
        api_path = path + "/api/v1"
    origin = urllib.parse.urlunsplit((scheme, parsed.netloc, "", "", ""))
    root_url = (origin + root_path).rstrip("/")
    base_url = (origin + api_path).rstrip("/")
    return root_url, base_url


def _replace_url_port(url: str, port: int) -> str:
    """Return ``url`` with a different TCP port while preserving path/scheme."""
    parsed = urllib.parse.urlsplit(str(url or ""))
    if not parsed.hostname:
        return str(url or "")
    host = parsed.hostname
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    userinfo = ""
    if parsed.username is not None:
        userinfo = urllib.parse.quote(parsed.username, safe="")
        if parsed.password is not None:
            userinfo += ":" + urllib.parse.quote(parsed.password, safe="")
        userinfo += "@"
    netloc = f"{userinfo}{host}:{int(port)}"
    return urllib.parse.urlunsplit((parsed.scheme, netloc, parsed.path, "", ""))


def _weknora_catalog_url(base_url: str) -> str:
    query = urllib.parse.urlencode({"page": 1, "page_size": WEKNORA_CATALOG_PAGE_SIZE})
    return str(base_url).rstrip("/") + "/knowledge-bases?" + query


def _append_unique_url_candidate(
    values: List[Dict[str, str]],
    url: str,
    source: str,
) -> None:
    try:
        root_url, base_url = _normalise_weknora_urls(url)
    except RuntimeError:
        return
    key = base_url.casefold()
    if any(str(item.get("base_url") or "").casefold() == key for item in values):
        return
    values.append({"source": source, "root_url": root_url, "base_url": base_url})


def _weknora_ssl_context(ca_file: str = "") -> ssl.SSLContext:
    context = ssl.create_default_context()
    value = str(ca_file or "").strip()
    if value:
        path = Path(value).expanduser()
        if not path.is_file():
            raise RuntimeError(f"WeKnora CA certificate file does not exist: {path}")
        context.load_verify_locations(cafile=str(path))
    return context


def _inspect_local_weknora_installation(explicit_install_dir: str = "") -> Dict[str, Any]:
    home = Path.home()
    descriptor_path = home / ".config" / "weknora" / "installation.env"
    descriptor = _read_key_value_file(descriptor_path)
    candidates: List[Path] = []
    for raw in (
        explicit_install_dir,
        descriptor.get("WEKNORA_INSTALL_DIR", ""),
        str(home / ".local" / "share" / "weknora"),
    ):
        if not str(raw or "").strip():
            continue
        candidate = Path(str(raw)).expanduser()
        if candidate not in candidates:
            candidates.append(candidate)
    share_root = home / ".local" / "share"
    if share_root.is_dir():
        try:
            for state_path in share_root.glob("*/.weknora-installer-state"):
                if state_path.parent not in candidates:
                    candidates.append(state_path.parent)
        except OSError:
            pass

    selected: Optional[Path] = None
    for candidate in candidates:
        if (
            (candidate / ".weknora-installer-state").is_file()
            or (candidate / "docker-compose.yml").is_file()
            or (candidate / ".env").is_file()
        ):
            selected = candidate
            break
    if selected is None:
        return {
            "found": False,
            "paths": [str(item) for item in candidates if item.exists()],
            "descriptor_file": str(descriptor_path) if descriptor_path.exists() else None,
        }

    state_path = selected / ".weknora-installer-state"
    env_path = selected / ".env"
    state = _read_key_value_file(state_path)
    environment = _read_key_value_file(env_path)
    api_port = _extract_mapped_port(
        state.get("api_port")
        or descriptor.get("WEKNORA_API_PORT")
        or environment.get("APP_PORT")
        or "18080"
    )
    configured_api_url = str(
        state.get("api_url") or descriptor.get("WEKNORA_API_URL") or ""
    ).strip()
    if not configured_api_url:
        # Legacy WSL installers publish the backend separately (default 18080).
        # Their state contains api_port but no api_url/descriptor.  Treat that
        # direct backend as the authoritative REST target instead of guessing
        # that the web UI on 8088 also proxies every API route.
        configured_api_url = f"http://localhost:{api_port}"
    root_url, base_url = _normalise_weknora_urls(configured_api_url)
    bootstrap_path = str(
        state.get("bootstrap_credentials_file")
        or descriptor.get("WEKNORA_BOOTSTRAP_CREDENTIALS_FILE")
        or (selected / ".weknora-bootstrap-credentials")
    )
    container_state = "unknown"
    docker = which("docker")
    if docker:
        result = run(
            [docker, "inspect", "--format", "{{.State.Status}}", "WeKnora-app"],
            timeout=10,
        )
        if result.returncode == 0:
            container_state = (result.stdout or "").strip() or "unknown"
    return {
        "found": True,
        "paths": [str(selected)],
        "install_dir": str(selected),
        "state_file": str(state_path),
        "env_file": str(env_path),
        "descriptor_file": str(descriptor_path) if descriptor_path.exists() else None,
        "bootstrap_credentials_file": bootstrap_path,
        "api_port": api_port,
        "api_url": root_url,
        "base_url": base_url,
        "container_state": container_state,
        "state_core_status": state.get("core_status"),
        "legacy_api_key_present": bool(environment.get("WEKNORA_API_KEY")),
        "https_only": str(descriptor.get("WEKNORA_HTTPS_ONLY") or state.get("https_only") or "").lower() == "true",
        "tls_hostname": descriptor.get("WEKNORA_TLS_HOSTNAME") or state.get("tls_hostname"),
        "certificate_mode": descriptor.get("WEKNORA_CERTIFICATE_MODE") or state.get("certificate_mode"),
        "ca_certificate": (
            descriptor.get("WEKNORA_TLS_CA_WSL_PATH")
            if descriptor.get("WEKNORA_TLS_CA_WSL_PATH") and Path(descriptor["WEKNORA_TLS_CA_WSL_PATH"]).is_file()
            else ""
        ),
    }


_WSL_WEKNORA_DISCOVERY_CODE = r'''
import json
import os
from pathlib import Path
import subprocess
import sys

def parse_file(path):
    values = {}
    try:
        for raw in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().rstrip("\r")
    except OSError:
        pass
    return values

def port_from(value, default=18080):
    raw = str(value or "").strip()
    if raw.endswith("/tcp"):
        raw = raw[:-4]
    try:
        port = int(raw.rsplit(":", 1)[-1])
        return port if 1 <= port <= 65535 else default
    except Exception:
        return default

home = Path.home()
explicit = str(sys.argv[1] if len(sys.argv) > 1 else "").strip()
descriptor_path = home / ".config" / "weknora" / "installation.env"
descriptor = parse_file(descriptor_path)
candidates = []
for raw in (explicit, descriptor.get("WEKNORA_INSTALL_DIR", ""), str(home / ".local" / "share" / "weknora")):
    if not raw:
        continue
    candidate = Path(raw).expanduser()
    if candidate not in candidates:
        candidates.append(candidate)
share_root = home / ".local" / "share"
if share_root.is_dir():
    try:
        for state_path in share_root.glob("*/.weknora-installer-state"):
            if state_path.parent not in candidates:
                candidates.append(state_path.parent)
    except OSError:
        pass
selected = None
for candidate in candidates:
    if ((candidate / ".weknora-installer-state").is_file()
            or (candidate / "docker-compose.yml").is_file()
            or (candidate / ".env").is_file()):
        selected = candidate
        break
if selected is None:
    print(json.dumps({"found": False, "paths": [str(p) for p in candidates if p.exists()]}))
    raise SystemExit(0)
state_path = selected / ".weknora-installer-state"
env_path = selected / ".env"
state = parse_file(state_path)
env = parse_file(env_path)
api_port = port_from(state.get("api_port") or descriptor.get("WEKNORA_API_PORT") or env.get("APP_PORT"))
api_url = state.get("api_url") or descriptor.get("WEKNORA_API_URL") or f"http://localhost:{api_port}"
api_url = api_url.rstrip("/")
if api_url.endswith("/api/v1"):
    root_url = api_url[:-7]
    base_url = api_url
else:
    root_url = api_url
    base_url = api_url + "/api/v1"
bootstrap = (state.get("bootstrap_credentials_file")
    or descriptor.get("WEKNORA_BOOTSTRAP_CREDENTIALS_FILE")
    or str(selected / ".weknora-bootstrap-credentials"))
container_state = "unknown"
try:
    completed = subprocess.run(
        ["docker", "inspect", "--format", "{{.State.Status}}", "WeKnora-app"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=10,
    )
    if completed.returncode == 0:
        container_state = completed.stdout.strip() or "unknown"
except Exception:
    pass
print(json.dumps({
    "found": True,
    "paths": [str(selected)],
    "install_dir": str(selected),
    "state_file": str(state_path),
    "env_file": str(env_path),
    "descriptor_file": str(descriptor_path) if descriptor_path.exists() else None,
    "bootstrap_credentials_file": bootstrap,
    "api_port": api_port,
    "api_url": root_url,
    "base_url": base_url,
    "container_state": container_state,
    "state_core_status": state.get("core_status"),
    "legacy_api_key_present": bool(env.get("WEKNORA_API_KEY")),
    "https_only": str(descriptor.get("WEKNORA_HTTPS_ONLY") or state.get("https_only") or "").lower() == "true",
    "tls_hostname": descriptor.get("WEKNORA_TLS_HOSTNAME") or state.get("tls_hostname"),
    "certificate_mode": descriptor.get("WEKNORA_CERTIFICATE_MODE") or state.get("certificate_mode"),
    # The Windows bootstrapper consumes this Windows path directly.
    "ca_certificate": descriptor.get("WEKNORA_TLS_CA_WINDOWS_PATH", ""),
}))
'''


def _inspect_weknora_in_wsl(distro: str, explicit_install_dir: str = "") -> Dict[str, Any]:
    wsl = which("wsl.exe") or which("wsl")
    if not wsl:
        return {"found": False, "error": "wsl.exe is unavailable"}
    code, output = _run_bytes(
        [
            wsl,
            "-d",
            distro,
            "--",
            "python3",
            "-c",
            _WSL_WEKNORA_DISCOVERY_CODE,
            explicit_install_dir or "",
        ],
        timeout=45,
    )
    if code != 0:
        return {"found": False, "error": output.strip() or f"WSL probe exited {code}"}
    try:
        payload = json.loads(output.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        return {"found": False, "error": f"Invalid WSL discovery output: {output[-500:]}"}
    if not isinstance(payload, dict):
        return {"found": False, "error": "WSL discovery did not return an object"}
    payload["distro"] = distro
    return payload


def _probe_http_status(
    url: str,
    timeout: float = 5.0,
    *,
    ca_file: str = "",
) -> Tuple[int, str]:
    request = urllib.request.Request(url, headers={"Accept": "application/json,text/plain,*/*"})
    scheme = urllib.parse.urlsplit(url).scheme.lower()
    context = _weknora_ssl_context(ca_file) if scheme == "https" else None
    try:
        with urllib.request.urlopen(
            request,
            timeout=timeout,
            context=context,
        ) as response:
            return int(response.status), response.read(4096).decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read(4096).decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError, RuntimeError, ssl.SSLError) as exc:
        return 0, str(exc)


def detect_weknora(
    explicit_url: str = "",
    explicit_api_url: str = "",
    preferred_distro: str = "",
    explicit_install_dir: str = "",
    health_timeout: float = 5.0,
    ca_certificate: str = "",
) -> Dict[str, Any]:
    """Discover WeKnora and retain every plausible REST API base.

    ``explicit_url`` is the public/web origin supplied by the operator.
    ``explicit_api_url`` optionally overrides the REST endpoint.  A local WSL2
    installation contributes its direct backend URL as an additional candidate;
    this is important for legacy deployments where web and API use different
    host ports (8088 and 18080 by default).
    """
    explicit_service = str(explicit_url or "").strip()
    explicit_api = str(explicit_api_url or "").strip()
    if explicit_service or explicit_api:
        try:
            service_root, service_derived_base = _normalise_weknora_urls(
                explicit_service or explicit_api
            )
            api_root, explicit_base = _normalise_weknora_urls(
                explicit_api or explicit_service
            )
        except RuntimeError as exc:
            return {
                "found": False,
                "healthy": False,
                "running": False,
                "installation_source": "explicit-url",
                "error": str(exc),
                "requested_url": explicit_service,
                "requested_api_url": explicit_api,
            }

        effective_ca = str(ca_certificate or "").strip()
        api_scheme = urllib.parse.urlsplit(api_root).scheme.lower()
        if api_scheme == "http" and effective_ca:
            return {
                "found": False,
                "healthy": False,
                "running": False,
                "installation_source": "explicit-url",
                "error": "A WeKnora CA certificate can be used only with an https:// API URL",
                "requested_url": explicit_service,
                "requested_api_url": explicit_api,
            }

        local_probes: List[Dict[str, Any]] = []
        if sys.platform.startswith("win"):
            distros = list_wsl_distributions()
            if preferred_distro:
                distros = [preferred_distro] if preferred_distro in distros else []
            for distro in distros:
                probe = _inspect_weknora_in_wsl(distro, explicit_install_dir)
                if probe.get("found"):
                    probe["distro"] = distro
                    local_probes.append(probe)
        else:
            probe = _inspect_local_weknora_installation(explicit_install_dir)
            if probe.get("found"):
                probe["distro"] = os.environ.get("WSL_DISTRO_NAME")
                local_probes.append(probe)

        desired_parts = urllib.parse.urlsplit(service_root)
        desired_host = (desired_parts.hostname or "").casefold()
        loopbacks = {"localhost", "127.0.0.1", "::1"}

        def same_device(candidate_url: str) -> bool:
            try:
                candidate_root, _ = _normalise_weknora_urls(candidate_url)
            except RuntimeError:
                return False
            candidate_host = (urllib.parse.urlsplit(candidate_root).hostname or "").casefold()
            return candidate_host == desired_host or (
                candidate_host in loopbacks and desired_host in loopbacks
            )

        local_match: Dict[str, Any] = {}
        for probe in local_probes:
            if same_device(str(probe.get("api_url") or probe.get("base_url") or "")):
                local_match = dict(probe)
                if not effective_ca:
                    effective_ca = str(probe.get("ca_certificate") or "").strip()
                break

        candidates: List[Dict[str, str]] = []
        if explicit_api:
            _append_unique_url_candidate(candidates, explicit_api, "explicit-api-url")
        if explicit_service:
            _append_unique_url_candidate(candidates, explicit_service, "explicit-service-proxy")
        elif explicit_api:
            _append_unique_url_candidate(candidates, explicit_api, "explicit-api-url")

        if local_match:
            _append_unique_url_candidate(
                candidates,
                str(local_match.get("base_url") or local_match.get("api_url") or ""),
                "local-wsl-direct-api",
            )
            api_port = int(local_match.get("api_port") or 0)
            if api_port:
                _append_unique_url_candidate(
                    candidates,
                    _replace_url_port(service_root, api_port),
                    "local-wsl-api-port",
                )

        # Legacy managed WSL installations use 8088 for the web UI and 18080
        # for the backend.  Probe the direct backend only for loopback targets;
        # remote devices must opt in explicitly with -WeKnoraApiUrl.
        service_parts = urllib.parse.urlsplit(service_root)
        service_port = service_parts.port or (443 if service_parts.scheme == "https" else 80)
        if (
            service_parts.scheme.lower() == "http"
            and service_port == WEKNORA_DEFAULT_WEB_PORT
            and (service_parts.hostname or "").casefold() in loopbacks
        ):
            _append_unique_url_candidate(
                candidates,
                _replace_url_port(service_root, WEKNORA_DEFAULT_API_PORT),
                "legacy-loopback-direct-api",
            )

        if not candidates:
            _append_unique_url_candidate(candidates, service_derived_base, "derived-api")

        health_probes: List[Dict[str, Any]] = []
        for candidate in candidates:
            status, detail = _probe_http_status(
                candidate["root_url"].rstrip("/") + "/health",
                timeout=max(1.0, min(float(health_timeout), 15.0)),
                ca_file=effective_ca if candidate["root_url"].startswith("https://") else "",
            )
            health_probes.append(
                {
                    **candidate,
                    "health_http_status": status,
                    "health_detail": detail[:500],
                    "healthy": status == 200,
                }
            )
        selected_health = next((item for item in health_probes if item["healthy"]), None)
        selected_health = selected_health or health_probes[0]
        parsed = urllib.parse.urlsplit(service_root)
        result = dict(local_match)
        result.update(
            {
                "found": True,
                "healthy": any(item["healthy"] for item in health_probes),
                "running": any(item["healthy"] for item in health_probes),
                "remote": (
                    False
                    if local_match
                    else (parsed.hostname or "").casefold() not in loopbacks
                ),
                "installation_source": (
                    "explicit-url+local-wsl-match" if local_match else "explicit-url"
                ),
                "requested_url": explicit_service,
                "requested_api_url": explicit_api,
                "service_url": service_root,
                "api_url": selected_health["root_url"],
                "base_url": candidates[0]["base_url"],
                "base_url_candidates": health_probes,
                "health_http_status": selected_health["health_http_status"],
                "health_detail": selected_health["health_detail"],
                "paths": list(local_match.get("paths") or []),
                "https_only": api_scheme == "https",
                "transport_scheme": api_scheme,
                "ca_certificate": effective_ca,
            }
        )
        return result

    discovered: List[Dict[str, Any]] = []
    if sys.platform.startswith("win"):
        distros = list_wsl_distributions()
        if preferred_distro:
            if preferred_distro not in distros:
                return {
                    "found": False,
                    "healthy": False,
                    "running": False,
                    "error": f"Requested WSL distribution was not found: {preferred_distro}",
                    "distros": distros,
                }
            distros = [preferred_distro]
        for distro in distros:
            probe = _inspect_weknora_in_wsl(distro, explicit_install_dir)
            if probe.get("found"):
                probe["distro"] = distro
                probe["installation_source"] = "wsl2-discovery"
                discovered.append(probe)
    else:
        local = _inspect_local_weknora_installation(explicit_install_dir)
        if local.get("found"):
            local["distro"] = os.environ.get("WSL_DISTRO_NAME")
            local["installation_source"] = "local-linux-discovery"
            discovered.append(local)

    for candidate in discovered:
        candidate_urls: List[Dict[str, str]] = []
        _append_unique_url_candidate(
            candidate_urls,
            str(candidate.get("base_url") or candidate.get("api_url") or ""),
            "discovered-api",
        )
        candidate["base_url_candidates"] = candidate_urls
        status, detail = _probe_http_status(
            str(candidate.get("api_url") or "").rstrip("/") + "/health",
            timeout=max(1.0, min(float(health_timeout), 15.0)),
            ca_file=str(candidate.get("ca_certificate") or ca_certificate or ""),
        )
        candidate["health_http_status"] = status
        candidate["health_detail"] = detail[:500]
        candidate["running"] = status == 200
        candidate["healthy"] = status == 200
        candidate["remote"] = False
        candidate.setdefault("service_url", candidate.get("api_url"))
    selected = next((item for item in discovered if item.get("healthy")), None)
    selected = selected or (discovered[0] if discovered else None)
    if not selected:
        return {
            "found": False,
            "healthy": False,
            "running": False,
            "paths": [],
            "distros": list_wsl_distributions() if sys.platform.startswith("win") else [],
        }
    selected = dict(selected)
    selected["alternatives"] = [
        {"distro": item.get("distro"), "install_dir": item.get("install_dir")}
        for item in discovered[1:]
    ]
    return selected


def scan(
    weknora_url: str = "",
    weknora_api_url: str = "",
    weknora_distro: str = "",
    weknora_install_dir: str = "",
    weknora_health_timeout: float = 5.0,
    weknora_ca_certificate: str = "",
    physnemo_distro: str = "",
    physnemo_install_dir: str = "",
) -> Dict[str, Any]:
    ansys = detect_ansys()
    return {
        "timestamp": now_iso(),
        "platform": platform.platform(),
        "system": platform.system(),
        "python": sys.version.split()[0],
        "docker": detect_openwebui_docker(),
        "applications": {
            PHYSNEMO_ROUTE: detect_physnemo(
                preferred_distro=physnemo_distro,
                explicit_install_dir=physnemo_install_dir,
            ),
            "weknora": detect_weknora(
                explicit_url=weknora_url,
                explicit_api_url=weknora_api_url,
                preferred_distro=weknora_distro,
                explicit_install_dir=weknora_install_dir,
                health_timeout=weknora_health_timeout,
                ca_certificate=weknora_ca_certificate,
            ),
            "matlab": detect_matlab(),
            "fusion": detect_fusion(),
            "ansys": ansys,
            "lumerical": detect_lumerical(),
            "paraview": generic_detect(
                "paraview",
                (r"%ProgramFiles%\ParaView *",),
                ("/usr/bin/paraview", "/opt/paraview", "/Applications/ParaView*.app"),
            ),
            "freecad": generic_detect(
                "FreeCAD",
                (r"%ProgramFiles%\FreeCAD*",),
                ("/usr/bin/freecad", "/usr/bin/FreeCAD", "/Applications/FreeCAD.app"),
            ),
            "rhino": generic_detect(
                "Rhino",
                (r"%ProgramFiles%\Rhino *",),
                ("/Applications/Rhino *.app",),
            ),
            "abaqus": generic_detect(
                "abaqus",
                (
                    r"C:\SIMULIA\Commands\abaqus.bat",
                    r"%ProgramFiles%\Dassault Systemes\SimulationServices\V6R*\win_b64\code\bin\SMALauncher.exe",
                ),
                ("/usr/bin/abaqus",),
            ),
            "comsol": generic_detect(
                "comsol",
                (r"%ProgramFiles%\COMSOL\COMSOL*\Multiphysics\bin\win64\comsol.exe",),
                ("/usr/local/comsol*/multiphysics/bin/comsol",),
            ),
        },
    }

def print_scan(data: Dict[str, Any]) -> None:
    print("\n=== Engineering MCP scan ===")
    print(f"Platform: {data.get('platform')}")
    docker = data.get("docker", {})
    print(f"Docker: {'yes' if docker.get('docker') else 'no'}")
    print(f"Open WebUI in Docker: {'yes' if docker.get('openwebui_container') else 'no'}")
    for name, info in data.get("applications", {}).items():
        status = "FOUND" if info.get("found") else "not found"
        extra = ""
        if name == "fusion" and info.get("found"):
            extra = f", MCP port 27182: {'open' if info.get('mcp_port_open') else 'closed'}"
        if name == PHYSNEMO_ROUTE and info.get("found"):
            extra = (
                f", WSL2 distro: {info.get('distro') or '?'}, "
                f"{'installed' if info.get('installed') else 'installable'}"
            )
        if name == "weknora" and info.get("found"):
            source = str(info.get("installation_source") or "discovery")
            location = info.get("distro") or ("remote device" if info.get("remote") else "local host")
            transport = str(
                info.get("transport_scheme")
                or urllib.parse.urlsplit(str(info.get("api_url") or "")).scheme
                or "unknown"
            )
            extra = (
                f", backend: {'healthy' if info.get('healthy') else 'not running'}, "
                f"source: {source}, location: {location}, transport: {transport}"
            )
        print(f"{name:12} {status}{extra}")
        for found_path in info.get("paths", [])[:3]:
            print(f"             {found_path}")
        if name == "ansys" and info.get("found"):
            products = ", ".join(k for k, v in info.get("products", {}).items() if v)
            print(f"             products: {products or 'base installation only'}")
        if name == PHYSNEMO_ROUTE and info.get("found"):
            print(f"             managed WSL path: {info.get('install_dir') or '(auto)'}")
            print(f"             NAT MCP port: {info.get('nat_port') or DEFAULT_PHYSNEMO_NAT_PORT}")
        if name == "weknora" and info.get("found"):
            print(f"             Service/public URL: {info.get('service_url') or info.get('requested_url') or '(not recorded)'}")
            candidate_rows = info.get("base_url_candidates")
            if isinstance(candidate_rows, list) and candidate_rows:
                print("             REST candidates (each includes /api/v1):")
                for candidate in candidate_rows:
                    if not isinstance(candidate, dict):
                        continue
                    status_value = candidate.get("health_http_status") or "unreachable"
                    print(
                        f"               - {candidate.get('base_url')} "
                        f"[{candidate.get('source') or 'unknown'}, health HTTP {status_value}]"
                    )
            else:
                print(f"             REST API base: {info.get('base_url') or '(not recorded)'}")
            if not info.get("healthy"):
                print(f"             health: HTTP {info.get('health_http_status') or 'unreachable'}")


# ---------------------------------------------------------------------------
# Python environment and MCP package installation
# ---------------------------------------------------------------------------

def locate_python312() -> Optional[str]:
    if sys.platform.startswith("win") and which("py"):
        result = run(
            ["py", "-3.12", "-c", "import sys; print(sys.executable)"],
            env=python_child_environment(),
            timeout=30,
        )
        if result.returncode == 0 and result.stdout:
            return result.stdout.strip()
    for name in ("python3.12", "python"):
        executable = which(name)
        if not executable:
            continue
        result = run(
            [executable, "-I", "-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"],
            env=python_child_environment(),
            timeout=30,
        )
        expected = ".".join(str(item) for item in REQUIRED_PYTHON_VERSION)
        if result.returncode == 0 and (result.stdout or "").strip() == expected:
            return executable
    return None


def install_python312_windows() -> bool:
    if not sys.platform.startswith("win") or not which("winget"):
        return False
    print("[*] Python 3.12 was not found; installing with winget...")
    result = run(
        [
            "winget",
            "install",
            "--id",
            "Python.Python.3.12",
            "-e",
            "--accept-source-agreements",
            "--accept-package-agreements",
        ],
        capture=False,
    )
    return result.returncode == 0


def environment_bin(root: Path, name: str) -> Path:
    if sys.platform.startswith("win"):
        suffix = "" if Path(name).suffix else ".exe"
        return root / "Scripts" / f"{name}{suffix}"
    return root / "bin" / name


def venv_bin(name: str) -> Path:
    return environment_bin(VENV, name)


def mcpo_venv_bin(name: str) -> Path:
    return environment_bin(MCPO_VENV, name)


def weknora_venv_bin(name: str) -> Path:
    return environment_bin(WEKNORA_VENV, name)


class BrokenVirtualEnvironmentError(RuntimeError):
    """Raised when the venv interpreter itself cannot start reliably."""


def python_child_environment(*, ignore_pip_config: bool = False) -> Dict[str, str]:
    """Return an environment isolated from an active Conda/base Python.

    Proxy, certificate and package-index variables are intentionally preserved,
    because they may be required on corporate networks. Variables that can
    redirect Python or pip outside the dedicated venv are removed.
    """
    environment = os.environ.copy()
    for name in (
        "PYTHONHOME",
        "PYTHONPATH",
        "VIRTUAL_ENV",
        "PIP_TARGET",
        "PIP_PREFIX",
        "PIP_USER",
        "PIP_REQUIRE_VIRTUALENV",
        "CONDA_PREFIX",
        "CONDA_DEFAULT_ENV",
        "CONDA_PROMPT_MODIFIER",
        "CONDA_PYTHON_EXE",
        "_CE_CONDA",
        "_CE_M",
        "__PYVENV_LAUNCHER__",
    ):
        environment.pop(name, None)
    environment["PYTHONUTF8"] = "1"
    environment["PYTHONIOENCODING"] = "utf-8"
    environment["PYTHONNOUSERSITE"] = "1"
    environment["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    environment["PIP_NO_INPUT"] = "1"
    environment["PIP_PROGRESS_BAR"] = "off"
    if ignore_pip_config:
        environment["PIP_CONFIG_FILE"] = os.devnull
    return environment


def run_streamed_logged(
    command: List[str],
    *,
    log_path: Path,
    env: Optional[Dict[str, str]] = None,
    cwd: Optional[Path] = None,
) -> subprocess.CompletedProcess:
    """Run a command, mirror output to the console and keep a full log.

    Only the last 160 lines are retained in memory for a concise exception;
    the complete output is written to ``log_path``.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    tail: deque[str] = deque(maxlen=160)
    with log_path.open("a", encoding="utf-8", errors="replace") as handle:
        handle.write(f"\n=== {now_iso()} ===\n")
        handle.write(f"COMMAND: {format_command(command)}\n")
        handle.flush()
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                env=env or os.environ.copy(),
                cwd=str(cwd) if cwd else None,
            )
        except OSError as exc:
            message = f"Could not start command: {exc}\n"
            handle.write(message)
            handle.write("EXIT: 127\n")
            raise RuntimeError(message.strip()) from exc

        assert process.stdout is not None
        for line in process.stdout:
            print(line, end="")
            handle.write(line)
            handle.flush()
            tail.append(line)
        returncode = int(process.wait())
        handle.write(f"EXIT: {returncode}\n")
        handle.flush()
    return subprocess.CompletedProcess(command, returncode, "".join(tail), None)


def read_pyvenv_config() -> Dict[str, str]:
    config_path = VENV / "pyvenv.cfg"
    if not config_path.is_file():
        return {}
    result: Dict[str, str] = {}
    try:
        for raw_line in config_path.read_text(encoding="utf-8", errors="replace").splitlines():
            if "=" not in raw_line:
                continue
            key, value = raw_line.split("=", 1)
            result[key.strip().lower()] = value.strip().strip('"')
    except OSError:
        return {}
    return result


def venv_health() -> Tuple[bool, Dict[str, Any]]:
    """Validate the whole venv, not only ``Scripts\\python.exe``.

    Windows exit code 106 is commonly emitted when the redirector executable
    exists but ``pyvenv.cfg`` is absent or no longer points at a valid base
    interpreter. This check catches that state before pip is invoked.
    """
    python = venv_bin("python")
    config_path = VENV / "pyvenv.cfg"
    details: Dict[str, Any] = {
        "venv": str(VENV),
        "python": str(python),
        "config": str(config_path),
    }
    if not VENV.is_dir():
        details["reason"] = "virtual environment directory is missing"
        return False, details
    if not config_path.is_file():
        details["reason"] = "pyvenv.cfg is missing"
        return False, details
    if not python.is_file():
        details["reason"] = "virtual environment Python executable is missing"
        return False, details

    config = read_pyvenv_config()
    details["pyvenv"] = config
    home = config.get("home")
    if not home:
        details["reason"] = "pyvenv.cfg has no home entry"
        return False, details
    if not Path(home).expanduser().exists():
        details["reason"] = f"base Python directory from pyvenv.cfg does not exist: {home}"
        return False, details

    probe_code = (
        "import json, os, sys; "
        "print(json.dumps({"
        "'version':[sys.version_info.major,sys.version_info.minor],"
        "'prefix':os.path.abspath(sys.prefix),"
        "'base_prefix':os.path.abspath(sys.base_prefix),"
        "'executable':os.path.abspath(sys.executable)}))"
    )
    result = run(
        [str(python), "-I", "-c", probe_code],
        env=python_child_environment(),
        timeout=30,
    )
    details["returncode"] = result.returncode
    details["probe_output"] = (result.stdout or "").strip()
    if result.returncode != 0:
        details["reason"] = (
            f"venv interpreter returned exit code {result.returncode}: "
            f"{(result.stdout or '').strip() or 'no diagnostic output'}"
        )
        return False, details
    try:
        payload = json.loads((result.stdout or "").strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        details["reason"] = "venv interpreter health probe returned invalid output"
        return False, details
    details["probe"] = payload
    if payload.get("version") != list(REQUIRED_PYTHON_VERSION):
        expected_version = ".".join(str(item) for item in REQUIRED_PYTHON_VERSION)
        details["reason"] = f"venv uses Python {payload.get('version')}, expected {expected_version}"
        return False, details
    expected_prefix = os.path.normcase(os.path.abspath(str(VENV)))
    actual_prefix = os.path.normcase(os.path.abspath(str(payload.get("prefix", ""))))
    if actual_prefix != expected_prefix:
        details["reason"] = f"venv prefix mismatch: {actual_prefix} != {expected_prefix}"
        return False, details
    details["reason"] = "healthy"
    return True, details


def pip_health() -> Tuple[bool, Dict[str, Any]]:
    python = venv_bin("python")
    result = run(
        [str(python), "-I", "-m", "pip", "--version"],
        env=python_child_environment(),
        timeout=30,
    )
    details = {
        "returncode": result.returncode,
        "output": (result.stdout or "").strip(),
    }
    return result.returncode == 0 and "pip " in (result.stdout or "").lower(), details


def locate_base_python312() -> Optional[str]:
    candidates: List[str] = []
    located = locate_python312()
    if located:
        candidates.append(located)
    base_executable = getattr(sys, "_base_executable", None)
    if base_executable:
        candidates.append(str(base_executable))
    config_home = read_pyvenv_config().get("home")
    if config_home:
        home_path = Path(config_home)
        if sys.platform.startswith("win"):
            candidates.append(str(home_path / "python.exe"))
        else:
            candidates.extend([str(home_path / "python3.12"), str(home_path / "python")])

    seen: set[str] = set()
    for raw in candidates:
        if not raw:
            continue
        executable = Path(raw).expanduser()
        key = os.path.normcase(os.path.abspath(str(executable)))
        if key in seen:
            continue
        seen.add(key)
        if not executable.is_file() or path_is_within(executable, VENV):
            continue
        result = run(
            [str(executable), "-I", "-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"],
            env=python_child_environment(),
            timeout=30,
        )
        expected = ".".join(str(item) for item in REQUIRED_PYTHON_VERSION)
        if result.returncode == 0 and (result.stdout or "").strip() == expected:
            return str(executable)
    return None


def invalidate_venv_dependent_checkpoint(checkpoint: Optional[Dict[str, Any]]) -> None:
    if checkpoint is None:
        return
    dependent_exact = {
        "venv",
        "deploy-self",
        "mcpo",
        "configuration",
        "launchers",
        "autostart",
        "start",
    }
    steps = checkpoint.setdefault("steps", {})
    for name in list(steps):
        if (
            name in dependent_exact
            or name.startswith("server:")
            or name.startswith("matlab-runtime-health-")
            or name.startswith("matlab-mcp-tool-health-")
            or name.startswith("weknora-runtime-health-")
            or name.startswith("weknora-mcp-tool-health-")
        ):
            steps.pop(name, None)
    checkpoint["installed"] = {}
    checkpoint.pop("matlab_runtime", None)
    checkpoint.pop("weknora_runtime", None)
    checkpoint.pop("package_failures", None)
    checkpoint.pop("verification_failed", None)
    checkpoint["complete"] = False
    checkpoint["venv_rebuilt_at"] = now_iso()
    save_checkpoint(checkpoint)


def rename_with_retries(source: Path, destination: Path, attempts: int = 10) -> None:
    last_error: Optional[BaseException] = None
    for attempt in range(1, attempts + 1):
        try:
            source.rename(destination)
            return
        except OSError as exc:
            last_error = exc
            time.sleep(min(0.25 * attempt, 2.0))
    raise RuntimeError(f"Could not move stale venv to {destination}: {last_error}")


def remove_tree_with_retries(path: Path, attempts: int = 8) -> bool:
    if not path.exists():
        return True
    for attempt in range(1, attempts + 1):
        try:
            shutil.rmtree(path)
            return True
        except OSError:
            time.sleep(min(0.25 * attempt, 2.0))
    return not path.exists()


def auxiliary_venv_health(root: Path) -> Tuple[bool, Dict[str, Any]]:
    python = environment_bin(root, "python")
    config = root / "pyvenv.cfg"
    details: Dict[str, Any] = {
        "root": str(root),
        "python": str(python),
        "config": str(config),
    }
    if not root.is_dir() or not config.is_file() or not python.is_file():
        details["reason"] = "auxiliary virtual environment is incomplete"
        return False, details
    probe = (
        "import json, os, sys; "
        "print(json.dumps({'version':[sys.version_info.major,sys.version_info.minor],"
        "'prefix':os.path.abspath(sys.prefix),'executable':os.path.abspath(sys.executable)}))"
    )
    result = run(
        [str(python), "-I", "-c", probe],
        env=python_child_environment(),
        timeout=30,
    )
    details["returncode"] = result.returncode
    details["output"] = (result.stdout or "").strip()
    if result.returncode != 0:
        details["reason"] = f"auxiliary Python returned {result.returncode}"
        return False, details
    try:
        payload = json.loads((result.stdout or "").strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        details["reason"] = "auxiliary Python returned invalid probe output"
        return False, details
    details["probe"] = payload
    if payload.get("version") != list(REQUIRED_PYTHON_VERSION):
        details["reason"] = f"auxiliary Python version mismatch: {payload.get('version')}"
        return False, details
    if os.path.normcase(os.path.abspath(str(payload.get("prefix") or ""))) != os.path.normcase(
        os.path.abspath(str(root))
    ):
        details["reason"] = "auxiliary virtual environment prefix mismatch"
        return False, details
    details["reason"] = "healthy"
    return True, details


def auxiliary_package_version(root: Path, package: str) -> Optional[str]:
    python = environment_bin(root, "python")
    if not python.is_file():
        return None
    code = (
        "import importlib.metadata as m, sys\n"
        "try:\n"
        "    print(m.version(sys.argv[1]))\n"
        "except m.PackageNotFoundError:\n"
        "    pass\n"
    )
    result = run(
        [str(python), "-I", "-c", code, package],
        env=python_child_environment(),
        timeout=30,
    )
    value = (result.stdout or "").strip()
    return value if result.returncode == 0 and value else None


def auxiliary_pip_install(root: Path, specs: Iterable[str], log_path: Path) -> None:
    python = environment_bin(root, "python")
    command = [
        str(python),
        "-I",
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--no-input",
        "--progress-bar",
        "off",
        "--retries",
        "5",
        "--timeout",
        "60",
        "--upgrade",
        *[str(spec) for spec in specs],
    ]
    result = run_streamed_logged(
        command,
        log_path=log_path,
        env=python_child_environment(),
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Auxiliary package installation failed ({result.returncode}); see {log_path}.\n"
            f"{result.stdout or ''}"
        )


def recreate_auxiliary_venv(root: Path, label: str) -> Dict[str, Any]:
    base_python = locate_base_python312()
    if not base_python and venv_bin("python").is_file():
        base_python = str(venv_bin("python"))
    if not base_python:
        raise RuntimeError(f"Python 3.12 is required to create the isolated {label} environment")
    if root.exists() and not remove_tree_with_retries(root):
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = root.with_name(f"{root.name}.invalid-{stamp}-{uuid.uuid4().hex[:8]}")
        rename_with_retries(root, backup)
    root.parent.mkdir(parents=True, exist_ok=True)
    result = run_streamed_logged(
        [base_python, "-I", "-m", "venv", "--copies", str(root)],
        log_path=AUXILIARY_VENV_REPAIR_LOG,
        env=python_child_environment(),
    )
    if result.returncode != 0:
        raise RuntimeError(f"Could not create isolated {label} environment; see {AUXILIARY_VENV_REPAIR_LOG}")
    python = environment_bin(root, "python")
    ensurepip = run_streamed_logged(
        [str(python), "-I", "-m", "ensurepip", "--upgrade", "--default-pip"],
        log_path=AUXILIARY_VENV_REPAIR_LOG,
        env=python_child_environment(),
    )
    if ensurepip.returncode != 0:
        raise RuntimeError(f"Could not bootstrap pip in isolated {label} environment")
    healthy, details = auxiliary_venv_health(root)
    if not healthy:
        raise RuntimeError(f"Isolated {label} environment failed its probe: {details.get('reason')}")
    return details


def ensure_auxiliary_environment(
    root: Path,
    label: str,
    specs: Iterable[str],
    required_versions: Dict[str, str],
    required_commands: Iterable[str],
    log_path: Path,
) -> Dict[str, Any]:
    healthy, health = auxiliary_venv_health(root)
    if not healthy:
        print(f"[*] Rebuilding isolated {label} environment: {health.get('reason')}")
        health = recreate_auxiliary_venv(root, label)
    versions = {package: auxiliary_package_version(root, package) for package in required_versions}
    commands_ok = all(environment_bin(root, command).is_file() for command in required_commands)
    if any(versions.get(package) != version for package, version in required_versions.items()) or not commands_ok:
        print(f"[*] Installing isolated {label} packages...")
        auxiliary_pip_install(root, specs, log_path)
        versions = {package: auxiliary_package_version(root, package) for package in required_versions}
        commands_ok = all(environment_bin(root, command).is_file() for command in required_commands)
    mismatches = {
        package: {"expected": expected, "actual": versions.get(package)}
        for package, expected in required_versions.items()
        if versions.get(package) != expected
    }
    if mismatches or not commands_ok:
        raise RuntimeError(
            f"Isolated {label} environment is incomplete: version mismatches={mismatches}, "
            f"commands_ok={commands_ok}. See {log_path}"
        )
    return {
        "root": str(root),
        "health": health,
        "versions": versions,
        "commands": {command: str(environment_bin(root, command)) for command in required_commands},
    }


def ensure_mcpo_environment() -> Dict[str, Any]:
    return ensure_auxiliary_environment(
        MCPO_VENV,
        "MCPO gateway",
        [f"mcp[cli]=={REQUIRED_MCPO_MCP_VERSION}", f"mcpo=={REQUIRED_MCPO_VERSION}"],
        {"mcp": REQUIRED_MCPO_MCP_VERSION, "mcpo": REQUIRED_MCPO_VERSION},
        ["mcpo"],
        MCPO_PIP_LOG_FILE,
    )


def ensure_weknora_mcp_environment() -> Dict[str, Any]:
    report = ensure_auxiliary_environment(
        WEKNORA_VENV,
        "WeKnora MCP",
        [WEKNORA_PACKAGE_SPEC],
        {WEKNORA_PACKAGE: WEKNORA_PACKAGE_VERSION},
        [WEKNORA_COMMAND],
        WEKNORA_PIP_LOG_FILE,
    )
    command = weknora_venv_bin(WEKNORA_COMMAND)
    if not command_supports_option(command, "--transport"):
        raise RuntimeError(
            f"Isolated WeKnora MCP command does not support --transport: {command}"
        )
    return report


def bootstrap_pip_offline() -> Dict[str, Any]:
    """Repair/bootstrap pip from the wheel bundled with CPython.

    ``ensurepip`` is intentionally used instead of upgrading pip from PyPI, so
    this recovery step does not depend on network access and does not replace a
    running pip installation in-place.
    """
    global _PIP_PREPARED
    python = str(venv_bin("python"))
    last_result: Optional[subprocess.CompletedProcess] = None
    for attempt in range(1, 3):
        print(f"[*] Bootstrapping pip from CPython ensurepip (attempt {attempt}/2)...")
        result = run_streamed_logged(
            [python, "-I", "-m", "ensurepip", "--upgrade", "--default-pip"],
            log_path=VENV_REPAIR_LOG,
            env=python_child_environment(),
        )
        last_result = result
        if result.returncode == 0:
            healthy, details = pip_health()
            if healthy:
                _PIP_PREPARED = True
                return {"action": "ensurepip", "pip": details}
        if result.returncode == 106 or "pyvenv.cfg" in (result.stdout or "").lower():
            raise BrokenVirtualEnvironmentError(
                "The venv interpreter cannot locate pyvenv.cfg (Windows exit code 106)."
            )
        time.sleep(1.0 * attempt)
    raise RuntimeError(
        "CPython ensurepip could not repair pip. "
        f"See {VENV_REPAIR_LOG}. Last output:\n{(last_result.stdout if last_result else '')}"
    )


def create_fresh_venv(
    checkpoint: Optional[Dict[str, Any]],
    *,
    reason: str,
) -> Dict[str, Any]:
    global _PIP_PREPARED
    ensure_dirs()
    _PIP_PREPARED = False
    base_python = locate_base_python312()
    installed_python = False
    if not base_python and install_python312_windows():
        installed_python = True
        base_python = locate_base_python312()
    if not base_python:
        raise RuntimeError("A working base Python 3.12 is required to rebuild the MCP environment.")
    if path_is_within(Path(sys.executable), VENV):
        raise RuntimeError(
            "The bootstrapper is currently running from the damaged EngineeringMCP venv, "
            "so Windows cannot replace it in-place. Run the current release copy of "
            "install-engineering-mcp-unified-v2.9.18.ps1 -Resume; it will use the base Python 3.12 interpreter."
        )

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = APP_HOME / f".venv.invalid-{timestamp}-{uuid.uuid4().hex[:8]}"
    had_existing = VENV.exists()
    print(f"[!] Rebuilding Engineering MCP Python environment: {reason}")
    if had_existing:
        rename_with_retries(VENV, backup)
        print(f"    Stale environment moved to: {backup}")

    try:
        command = [base_python, "-I", "-m", "venv", "--copies", "--without-pip", str(VENV)]
        result = run_streamed_logged(
            command,
            log_path=VENV_REPAIR_LOG,
            env=python_child_environment(),
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Python venv creation failed ({result.returncode}). See {VENV_REPAIR_LOG}.\n"
                f"{result.stdout or ''}"
            )
        healthy, details = venv_health()
        if not healthy:
            raise RuntimeError(f"Fresh venv failed its interpreter probe: {details.get('reason')}")
        pip_details = bootstrap_pip_offline()
        invalidate_venv_dependent_checkpoint(checkpoint)
        if checkpoint is not None and installed_python:
            checkpoint["python_installed_by_bootstrapper"] = True
            save_checkpoint(checkpoint)
        if had_existing and backup.exists() and not remove_tree_with_retries(backup):
            print(f"[!] The obsolete venv backup could not be removed yet: {backup}")
        return {
            "action": "rebuilt",
            "reason": reason,
            "base_python": base_python,
            "health": details,
            "pip": pip_details,
        }
    except Exception:
        remove_tree_with_retries(VENV)
        if had_existing and backup.exists() and not VENV.exists():
            try:
                backup.rename(VENV)
            except OSError:
                pass
        raise


def ensure_venv(checkpoint: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    ensure_dirs()
    healthy, details = venv_health()
    if not healthy:
        return create_fresh_venv(checkpoint, reason=str(details.get("reason") or "invalid venv"))

    try:
        pip_details = prepare_pip()
        print(f"[*] Python 3.12 environment is healthy: {VENV}")
        return {"action": "reused", "health": details, "pip": pip_details}
    except Exception as exc:
        # A valid interpreter with an irreparable/missing pip is cheaper and
        # safer to replace than to keep a partially modified package manager.
        return create_fresh_venv(checkpoint, reason=f"pip health check failed: {exc}")


def prepare_pip() -> Dict[str, Any]:
    global _PIP_PREPARED
    if _PIP_PREPARED:
        healthy, details = pip_health()
        if healthy:
            return {"action": "already-prepared", "pip": details}
        _PIP_PREPARED = False

    healthy, details = pip_health()
    if healthy:
        _PIP_PREPARED = True
        print(f"[*] Using bundled venv pip: {details.get('output')}")
        return {"action": "existing", "pip": details}

    print(f"[!] pip health check failed; attempting offline ensurepip repair: {details}")
    return bootstrap_pip_offline()


def pip_install(spec: str) -> None:
    prepare_pip()
    python = str(venv_bin("python"))
    command = [
        python,
        "-I",
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--no-input",
        "--progress-bar",
        "off",
        "--retries",
        "5",
        "--timeout",
        "60",
        "--upgrade",
        spec,
    ]
    last_result: Optional[subprocess.CompletedProcess] = None
    for attempt in range(1, 4):
        ignore_config = False
        if attempt == 3 and last_result:
            lowered = (last_result.stdout or "").lower()
            ignore_config = any(
                token in lowered
                for token in (
                    "configuration file",
                    "error in configuration",
                    "could not load configuration",
                    "invalid value for",
                )
            )
        if attempt > 1:
            print(f"[*] Retrying package installation ({attempt}/3): {spec}")
        result = run_streamed_logged(
            command,
            log_path=PIP_LOG_FILE,
            env=python_child_environment(ignore_pip_config=ignore_config),
        )
        last_result = result
        if result.returncode == 0:
            return
        lowered = (result.stdout or "").lower()
        if result.returncode == 106 or "failed to locate pyvenv.cfg" in lowered:
            healthy, health_details = venv_health()
            raise BrokenVirtualEnvironmentError(
                "Python returned Windows exit code 106 while running pip. "
                f"Venv health: {health_details.get('reason') if not healthy else 'interpreter probe passed'}. "
                f"Full log: {PIP_LOG_FILE}"
            )
        time.sleep(float(attempt * 2))

    tail = (last_result.stdout if last_result else "") or "no diagnostic output"
    raise RuntimeError(
        f"Package installation failed after 3 attempts: {spec}\n"
        f"Full pip log: {PIP_LOG_FILE}\n"
        f"Last output:\n{tail}"
    )


def command_installed(command: str) -> bool:
    return venv_bin(command).exists()


def installed_package_version(package: str) -> Optional[str]:
    python = venv_bin("python")
    if not python.exists():
        return None
    code = (
        "import importlib.metadata as m, sys\n"
        "try:\n"
        "    print(m.version(sys.argv[1]))\n"
        "except m.PackageNotFoundError:\n"
        "    pass\n"
    )
    result = run(
        [str(python), "-I", "-c", code, package],
        env=python_child_environment(),
        timeout=30,
    )
    value = (result.stdout or "").strip()
    return value if result.returncode == 0 and value else None


def get_matlab_root(scan_data: Dict[str, Any]) -> Optional[str]:
    matlab_info = scan_data.get("applications", {}).get("matlab", {})
    selected = matlab_info.get("selected_root")
    if selected and Path(selected).exists():
        return str(Path(selected))
    for raw in list(matlab_info.get("roots", [])) + list(matlab_info.get("paths", [])):
        root = matlab_root_from_candidate(raw)
        if root and root.exists():
            return str(root)
    return None


def download_matlab_server(existing: Optional[str] = None) -> Optional[Path]:
    if not detect_matlab().get("found"):
        return None

    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "windows":
        suffix = "windows-arm64.exe" if "arm" in machine else "windows-x64.exe"
    elif system == "darwin":
        suffix = "macos-arm64" if "arm" in machine else "macos-x64"
    elif system == "linux":
        suffix = "linux-arm64" if "arm" in machine else "linux-x64"
    else:
        return None

    api_url = "https://api.github.com/repos/matlab/matlab-mcp-server/releases/latest"
    request = urllib.request.Request(
        api_url,
        headers={"User-Agent": f"engineering-mcp-bootstrapper/{BOOTSTRAPPER_VERSION}"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        release = json.load(response)
    asset = next((item for item in release.get("assets", []) if item.get("name", "").endswith(suffix)), None)
    if not asset:
        raise RuntimeError(f"No MATLAB MCP release asset matching {suffix}")

    destination = BIN_DIR / asset["name"]
    expected_size = int(asset.get("size") or 0)
    existing_path = Path(existing) if existing else None
    if destination.exists() and destination.stat().st_size > 0:
        if not expected_size or destination.stat().st_size == expected_size:
            return destination
    if existing_path and existing_path.exists() and existing_path != destination:
        print(f"[*] Replacing obsolete MATLAB MCP binary: {existing_path.name}")

    partial = destination.with_suffix(destination.suffix + ".part")
    partial.unlink(missing_ok=True)
    print(
        f"[*] Downloading official MATLAB MCP server {release.get('tag_name', 'latest')}: "
        f"{asset['name']}"
    )
    urllib.request.urlretrieve(asset["browser_download_url"], partial)
    if expected_size and partial.stat().st_size != expected_size:
        actual_size = partial.stat().st_size
        partial.unlink(missing_ok=True)
        raise RuntimeError(
            f"Downloaded MATLAB MCP binary has unexpected size: {actual_size} != {expected_size}"
        )
    os.replace(partial, destination)
    if not sys.platform.startswith("win"):
        destination.chmod(0o755)
    return destination


# ---------------------------------------------------------------------------
# MATLAB licensing / MathWorks Service Host health and repair
# ---------------------------------------------------------------------------

def matlab_mcp_supports_option(binary: Path, option: str) -> bool:
    try:
        result = run([str(binary), "--help"], timeout=30)
    except Exception:
        return False
    return option in (result.stdout or "")


def matlab_service_host_paths() -> List[Path]:
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "MathWorks"
        return [base / "ServiceHost", base / "MATLABConnector"]
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / "MathWorks"
        return [base / "ServiceHost", base / "MATLABConnector"]
    return [Path.home() / ".MathWorks" / "ServiceHost", Path.home() / ".MATLABConnector"]


def windows_process_ids(image_name: str) -> List[int]:
    if not sys.platform.startswith("win"):
        return []
    result = run(["tasklist", "/FI", f"IMAGENAME eq {image_name}", "/FO", "CSV", "/NH"])
    if result.returncode != 0:
        return []
    pids: List[int] = []
    for row in csv.reader((result.stdout or "").splitlines()):
        if len(row) < 2 or row[0].lower() != image_name.lower():
            continue
        try:
            pids.append(int(row[1]))
        except ValueError:
            pass
    return pids


def copy_recent_mathworks_logs(destination: Path) -> List[str]:
    copied: List[str] = []
    destination.mkdir(parents=True, exist_ok=True)
    for base in matlab_service_host_paths():
        candidates = [base / "logs", base]
        source = next((item for item in candidates if item.exists()), None)
        if not source:
            continue
        target = destination / base.name
        try:
            if source.is_dir():
                shutil.copytree(source, target, dirs_exist_ok=True)
            else:
                shutil.copy2(source, target)
            copied.append(str(target))
        except OSError:
            pass
    return copied


def recent_mathworks_log_text(max_files: int = 12, max_bytes_per_file: int = 256_000) -> str:
    files: List[Path] = []
    for base in matlab_service_host_paths():
        if not base.exists():
            continue
        try:
            files.extend(item for item in base.rglob("*") if item.is_file())
        except OSError:
            continue
    files.sort(key=lambda item: item.stat().st_mtime if item.exists() else 0, reverse=True)
    chunks: List[str] = []
    for item in files[:max_files]:
        try:
            chunks.append(item.read_bytes()[-max_bytes_per_file:].decode("utf-8", errors="replace"))
        except OSError:
            pass
    return "\n".join(chunks)


def matlab_error_5201(text: str) -> bool:
    normalized = text.lower()
    return any(
        marker in normalized
        for marker in (
            "error 5201",
            "5201",
            "unable to access services required to run matlab",
            "unable to communicate with required mathworks services",
            "unable to communicate with the required mathworks services",
        )
    )


def terminate_spawned_process(process: subprocess.Popen[Any]) -> None:
    if process.poll() is not None:
        return
    if sys.platform.startswith("win"):
        run(["taskkill", "/PID", str(process.pid), "/T", "/F"])
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except OSError:
            try:
                process.terminate()
            except OSError:
                pass


def run_matlab_preflight(
    scan_data: Dict[str, Any],
    *,
    timeout: float = DEFAULT_MATLAB_HEALTH_TIMEOUT,
    label: str = "preflight",
) -> Dict[str, Any]:
    root = get_matlab_root(scan_data)
    executable = matlab_executable_from_root(root) if root else None
    result: Dict[str, Any] = {
        "checked_at": now_iso(),
        "root": root,
        "executable": str(executable) if executable else None,
        "healthy": False,
        "error_5201": False,
        "timed_out": False,
        "returncode": None,
    }
    if not root or not executable:
        result["error"] = "MATLAB executable could not be resolved"
        return result

    MATLAB_REPAIR_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_path = MATLAB_REPAIR_DIR / f"matlab-{label}-{stamp}.log"
    matlab_code = (
        "tf=license('test','MATLAB');"
        "if ~tf,error('EngineeringMCP:LicenseUnavailable',"
        "'MATLAB license test returned false.');end;"
        f"fprintf(1,'{MATLAB_PREFLIGHT_MARKER}\\n');"
    )
    command = [str(executable)]
    if sys.platform.startswith("win"):
        command.append("-wait")
    command.extend(["-nosplash", "-nodesktop", "-logfile", str(log_path), "-batch", matlab_code])
    result["command"] = format_command(command)
    result["log"] = str(log_path)

    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform.startswith("win") else 0
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(root),
            env=os.environ.copy(),
            creationflags=creationflags,
            start_new_session=not sys.platform.startswith("win"),
        )
        try:
            output, _ = process.communicate(timeout=max(30.0, float(timeout)))
        except subprocess.TimeoutExpired:
            result["timed_out"] = True
            terminate_spawned_process(process)
            try:
                output, _ = process.communicate(timeout=15)
            except subprocess.TimeoutExpired:
                output = ""
        result["returncode"] = process.returncode
    except OSError as exc:
        result["error"] = str(exc)
        output = ""

    try:
        logfile_text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
    except OSError:
        logfile_text = ""
    service_text = recent_mathworks_log_text()
    combined = "\n".join((output or "", logfile_text, service_text))
    result["healthy"] = (
        not result["timed_out"]
        and result.get("returncode") == 0
        and MATLAB_PREFLIGHT_MARKER in combined
    )
    result["error_5201"] = matlab_error_5201(combined) and not result["healthy"]
    result["output_tail"] = combined[-12_000:]
    if not result["healthy"] and not result.get("error"):
        result["error"] = (
            "MathWorks licensing/Service Host error 5201"
            if result["error_5201"]
            else "MATLAB did not complete the licensing preflight"
        )
    return result


def stop_mathworks_service_host() -> None:
    if sys.platform.startswith("win"):
        for image in ("MathWorksServiceHost.exe", "MATLABConnector.exe"):
            run(["taskkill", "/IM", image, "/T", "/F"])
    elif sys.platform == "darwin":
        run(["killall", "MathWorksServiceHost"])
    else:
        run(["killall", "MathWorksServiceHost"])


def remove_mathworks_service_host_directories() -> List[str]:
    removed: List[str] = []
    for path in matlab_service_host_paths():
        if not path.exists():
            continue
        last_error: Optional[Exception] = None
        for attempt in range(6):
            try:
                shutil.rmtree(path)
                removed.append(str(path))
                last_error = None
                break
            except OSError as exc:
                last_error = exc
                stop_mathworks_service_host()
                time.sleep(1.0 + attempt * 0.5)
        if last_error is not None and path.exists():
            raise RuntimeError(f"Could not remove {path}: {last_error}")
    return removed


def resolve_service_host_reinstaller_url() -> str:
    try:
        request = urllib.request.Request(
            MATHWORKS_SERVICE_HOST_SUPPORT_URL,
            headers={"User-Agent": f"engineering-mcp-bootstrapper/{BOOTSTRAPPER_VERSION}"},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            page = response.read().decode("utf-8", errors="replace")
        decoded = html_module.unescape(page)
        matches = re.findall(
            r"https://ssd\\.mathworks\\.com/[^\"'<>\\s]+/reinstallers/win64/"
            r"ReinstallMathWorksServiceHost\\.exe",
            decoded,
            flags=re.IGNORECASE,
        )
        if matches:
            return matches[0]
    except (OSError, urllib.error.URLError):
        pass
    return MATHWORKS_SERVICE_HOST_REINSTALLER_FALLBACK


def verify_mathworks_authenticode(path: Path) -> Dict[str, Any]:
    if not sys.platform.startswith("win"):
        return {"valid": False, "reason": "Authenticode applies only to Windows"}
    powershell = which("powershell.exe") or which("powershell") or which("pwsh")
    if not powershell:
        return {"valid": False, "reason": "PowerShell not available for Authenticode verification"}
    environment = os.environ.copy()
    environment["ENGINEERING_MCP_SIGNATURE_FILE"] = str(path)
    script = (
        "$s=Get-AuthenticodeSignature -LiteralPath $env:ENGINEERING_MCP_SIGNATURE_FILE;"
        "$subject=if($null -ne $s.SignerCertificate){$s.SignerCertificate.Subject}else{''};"
        "[pscustomobject]@{Status=$s.Status.ToString();Subject=$subject}|ConvertTo-Json -Compress"
    )
    result = run(
        [powershell, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
        env=environment,
        timeout=60,
    )
    try:
        payload = json.loads((result.stdout or "").strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        return {"valid": False, "reason": (result.stdout or "Authenticode check failed").strip()}
    status = str(payload.get("Status", ""))
    subject = str(payload.get("Subject", ""))
    return {
        "valid": status.lower() == "valid" and "mathworks" in subject.lower(),
        "status": status,
        "subject": subject,
    }


def download_service_host_reinstaller() -> Tuple[Optional[Path], Dict[str, Any]]:
    info: Dict[str, Any] = {"url": None, "downloaded": False, "signature": None}
    if not sys.platform.startswith("win"):
        info["error"] = "Official executable reinstaller is Windows-only"
        return None, info
    url = resolve_service_host_reinstaller_url()
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "ssd.mathworks.com" or not parsed.path.endswith(
        "/ReinstallMathWorksServiceHost.exe"
    ):
        info["error"] = f"Refusing unexpected reinstaller URL: {url}"
        return None, info
    info["url"] = url
    destination = BIN_DIR / "ReinstallMathWorksServiceHost.exe"
    partial = destination.with_suffix(".exe.part")
    partial.unlink(missing_ok=True)
    try:
        request = urllib.request.Request(
            url,
            headers={"User-Agent": f"engineering-mcp-bootstrapper/{BOOTSTRAPPER_VERSION}"},
        )
        with urllib.request.urlopen(request, timeout=120) as response, partial.open("wb") as stream:
            shutil.copyfileobj(response, stream)
        if partial.stat().st_size < 1_000_000:
            raise RuntimeError(f"Reinstaller download is unexpectedly small ({partial.stat().st_size} bytes)")
        os.replace(partial, destination)
        info["downloaded"] = True
        info["size"] = destination.stat().st_size
        info["sha256"] = hashlib.sha256(destination.read_bytes()).hexdigest()
        signature = verify_mathworks_authenticode(destination)
        info["signature"] = signature
        if not signature.get("valid"):
            destination.unlink(missing_ok=True)
            raise RuntimeError(
                "Downloaded Service Host reinstaller does not have a valid MathWorks signature: "
                f"{signature}"
            )
        return destination, info
    except Exception as exc:
        partial.unlink(missing_ok=True)
        info["error"] = str(exc)
        return None, info


def run_service_host_reinstaller(path: Path) -> Dict[str, Any]:
    result: Dict[str, Any] = {"path": str(path), "started": False, "returncode": None}
    try:
        process = subprocess.Popen([str(path)], cwd=str(path.parent))
        result["started"] = True
        try:
            result["returncode"] = process.wait(timeout=MATLAB_REPAIR_TIMEOUT)
        except subprocess.TimeoutExpired:
            terminate_spawned_process(process)
            result["timed_out"] = True
            result["error"] = f"Service Host reinstaller exceeded {int(MATLAB_REPAIR_TIMEOUT)} seconds"
    except OSError as exc:
        result["error"] = str(exc)
    return result


def setup_matlab_mcp_toolbox(binary: Path, scan_data: Dict[str, Any]) -> Dict[str, Any]:
    root = get_matlab_root(scan_data)
    release = matlab_release_tuple(root)
    result: Dict[str, Any] = {
        "attempted": False,
        "installed": False,
        "root": root,
        "supported_release": bool(release and release >= (2023, 0)),
    }
    if not root or not result["supported_release"]:
        result["reason"] = "Existing-session toolbox requires MATLAB R2023a or newer"
        return result
    if not matlab_mcp_supports_option(binary, "--setup-matlab"):
        result["reason"] = "Downloaded MATLAB MCP binary does not expose --setup-matlab"
        return result
    MATLAB_MCP_LOG_DIR.mkdir(parents=True, exist_ok=True)
    command = [str(binary), "--setup-matlab", f"--matlab-root={root}"]
    result["attempted"] = True
    result["command"] = format_command(command)
    try:
        completed = run(command, timeout=MATLAB_REPAIR_TIMEOUT)
        result["returncode"] = completed.returncode
        result["output_tail"] = (completed.stdout or "")[-12_000:]
        result["installed"] = completed.returncode == 0
    except Exception as exc:
        result["error"] = str(exc)
    return result


def repair_matlab_service_host(
    scan_data: Dict[str, Any],
    *,
    force_matlab_close: bool = False,
    health_timeout: float = DEFAULT_MATLAB_HEALTH_TIMEOUT,
) -> Dict[str, Any]:
    """Perform the supported per-user Service Host reset and verify MATLAB."""
    ensure_dirs()
    result: Dict[str, Any] = {
        "started_at": now_iso(),
        "platform": platform.system(),
        "force_matlab_close": force_matlab_close,
        "success": False,
        "attempts": [],
    }
    existing_matlab = windows_process_ids("MATLAB.exe") if sys.platform.startswith("win") else []
    result["existing_matlab_pids"] = existing_matlab
    if existing_matlab and not force_matlab_close:
        result["error"] = (
            "MATLAB is already running. Save work and close all MATLAB windows, then run "
            "install-engineering-mcp-unified-v2.9.18.ps1 -Resume. Use -ForceCloseMatlab only if discarding unsaved work is acceptable."
        )
        atomic_write_json(MATLAB_REPAIR_REPORT, result, private=True)
        return result
    if existing_matlab and force_matlab_close:
        print("[!] Force-closing MATLAB processes as explicitly requested; unsaved work can be lost.")
        run(["taskkill", "/IM", "MATLAB.exe", "/T", "/F"])
        time.sleep(2)

    snapshot = MATLAB_REPAIR_DIR / datetime.now().strftime("before-%Y%m%d-%H%M%S")
    result["copied_logs"] = copy_recent_mathworks_logs(snapshot)

    try:
        stop_mathworks_service_host()
        result["removed"] = remove_mathworks_service_host_directories()
        manual_probe = run_matlab_preflight(
            scan_data,
            timeout=max(float(health_timeout), 240.0),
            label="after-manual-service-host-reset",
        )
        result["attempts"].append({"type": "manual-reset", "probe": manual_probe})
        if manual_probe.get("healthy"):
            result["success"] = True
            result["completed_at"] = now_iso()
            atomic_write_json(MATLAB_REPAIR_REPORT, result, private=True)
            return result
    except Exception as exc:
        result["attempts"].append({"type": "manual-reset", "error": str(exc)})

    reinstaller, download_info = download_service_host_reinstaller()
    reinstaller_attempt: Dict[str, Any] = {"type": "official-reinstaller", "download": download_info}
    if reinstaller:
        reinstaller_attempt["execution"] = run_service_host_reinstaller(reinstaller)
        final_probe = run_matlab_preflight(
            scan_data,
            timeout=max(float(health_timeout), 240.0),
            label="after-official-service-host-reinstaller",
        )
        reinstaller_attempt["probe"] = final_probe
        result["attempts"].append(reinstaller_attempt)
        result["success"] = bool(final_probe.get("healthy"))
    else:
        result["attempts"].append(reinstaller_attempt)

    if not result["success"]:
        last_probe = next(
            (
                item.get("probe")
                for item in reversed(result["attempts"])
                if isinstance(item, dict) and isinstance(item.get("probe"), dict)
            ),
            {},
        )
        if last_probe.get("error_5201"):
            result["requires_user_signin_or_network_action"] = True
            result["error"] = (
                "MathWorks Service Host was reinstalled, but MATLAB still reports error 5201. "
                "The remaining cause is account activation, proxy/VPN/security software, or a managed "
                "license policy; the installer cannot bypass credentials or an external license server."
            )
        else:
            result["error"] = "MATLAB still does not pass the licensing preflight after Service Host repair."
    result["completed_at"] = now_iso()
    atomic_write_json(MATLAB_REPAIR_REPORT, result, private=True)
    return result


def prepare_matlab_runtime(
    binary: Path,
    scan_data: Dict[str, Any],
    *,
    auto_repair: bool,
    force_matlab_close: bool,
    health_timeout: float,
) -> Dict[str, Any]:
    print("[*] Running MATLAB licensing/Service Host preflight...")
    preflight = run_matlab_preflight(scan_data, timeout=health_timeout, label="initial")
    runtime: Dict[str, Any] = {
        "checked_at": now_iso(),
        "preflight": preflight,
        "healthy": bool(preflight.get("healthy")),
        "auto_repair": auto_repair,
        "service_host_repair": None,
        "toolbox": None,
        "session_mode": "new",
    }
    if runtime["healthy"]:
        print("[+] MATLAB startup and licensing preflight passed.")
    elif auto_repair:
        if preflight.get("error_5201"):
            print("[!] MATLAB error 5201 detected; repairing MathWorks Service Host automatically.")
        else:
            print("[!] MATLAB startup preflight failed; attempting the supported Service Host repair.")
        repair = repair_matlab_service_host(
            scan_data,
            force_matlab_close=force_matlab_close,
            health_timeout=health_timeout,
        )
        runtime["service_host_repair"] = repair
        runtime["healthy"] = bool(repair.get("success"))
        if runtime["healthy"]:
            print("[+] MathWorks Service Host repair succeeded; MATLAB now starts correctly.")
        else:
            print(f"[!] MATLAB repair did not complete successfully: {repair.get('error', 'unknown error')}")
            print(f"    Repair report: {MATLAB_REPAIR_REPORT}")
    else:
        print("[!] MATLAB preflight failed and automatic Service Host repair was disabled.")

    if runtime["healthy"]:
        toolbox = setup_matlab_mcp_toolbox(binary, scan_data)
        runtime["toolbox"] = toolbox
        if toolbox.get("installed"):
            runtime["session_mode"] = "auto"
            print("[+] MATLAB MCP Server Toolbox is ready; session mode set to auto.")
        elif toolbox.get("supported_release"):
            print("[!] MATLAB MCP Toolbox setup failed; the server will fall back to a new session.")
    return runtime


# ---------------------------------------------------------------------------
# WeKnora runtime, credentials and knowledge-base catalogue
# ---------------------------------------------------------------------------

def _deep_value(value: Any, dotted_path: str) -> Any:
    current = value
    for part in dotted_path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _first_deep_value(value: Any, paths: Iterable[str]) -> Any:
    for path in paths:
        candidate = _deep_value(value, path)
        if candidate not in (None, ""):
            return candidate
    return None


def _weknora_request(
    method: str,
    url: str,
    *,
    payload: Optional[Dict[str, Any]] = None,
    api_key: str = "",
    bearer_token: str = "",
    tenant_id: str = "",
    timeout: float = 45.0,
    ca_file: str = "",
    diagnostics: Optional[Dict[str, Any]] = None,
) -> Tuple[int, Any, str]:
    headers = {
        "Accept": "application/json",
        "User-Agent": f"engineering-mcp-weknora/{BOOTSTRAPPER_VERSION}",
    }
    body: Optional[bytes] = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    if api_key:
        headers["X-API-Key"] = api_key
    if bearer_token:
        headers["Authorization"] = f"Bearer {bearer_token}"
    if tenant_id:
        headers["X-Tenant-ID"] = str(tenant_id)
    request = urllib.request.Request(url, data=body, headers=headers, method=method.upper())
    scheme = urllib.parse.urlsplit(url).scheme.lower()
    context = _weknora_ssl_context(ca_file) if scheme == "https" else None

    def record(
        *,
        status: int,
        raw: str,
        parsed: Any,
        content_type: str = "",
        final_url: str = "",
        error: str = "",
    ) -> None:
        if diagnostics is None:
            return
        diagnostics.clear()
        diagnostics.update(
            {
                "method": method.upper(),
                "requested_url": url,
                "final_url": final_url or url,
                "http_status": status,
                "content_type": content_type,
                "json_type": type(parsed).__name__ if parsed is not None else None,
                "top_level_keys": sorted(str(key) for key in parsed)[:100]
                if isinstance(parsed, dict)
                else [],
                "raw_preview": raw[:2000],
                "error": error or None,
            }
        )

    try:
        with urllib.request.urlopen(
            request,
            timeout=timeout,
            context=context,
        ) as response:
            raw = response.read().decode("utf-8", errors="replace")
            content_type = str(response.headers.get("Content-Type") or "")
            try:
                parsed: Any = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                parsed = None
            record(
                status=int(response.status),
                raw=raw,
                parsed=parsed,
                content_type=content_type,
                final_url=str(response.geturl() or url),
            )
            return int(response.status), parsed, raw[:2000]
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        content_type = str(exc.headers.get("Content-Type") or "") if exc.headers else ""
        try:
            parsed = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            parsed = None
        record(
            status=int(exc.code),
            raw=raw,
            parsed=parsed,
            content_type=content_type,
            final_url=str(exc.geturl() or url),
            error=str(exc),
        )
        return int(exc.code), parsed, raw[:2000]
    except (urllib.error.URLError, TimeoutError, OSError, RuntimeError, ssl.SSLError) as exc:
        record(status=0, raw="", parsed=None, error=str(exc))
        return 0, None, str(exc)


def wait_for_weknora_backend(info: Dict[str, Any], timeout: float) -> Dict[str, Any]:
    result = dict(info)
    raw_candidates = info.get("base_url_candidates")
    candidates: List[Dict[str, Any]] = []
    if isinstance(raw_candidates, list):
        for raw in raw_candidates:
            if not isinstance(raw, dict):
                continue
            try:
                root_url, base_url = _normalise_weknora_urls(
                    str(raw.get("base_url") or raw.get("root_url") or "")
                )
            except RuntimeError:
                continue
            candidates.append({**raw, "root_url": root_url, "base_url": base_url})
    if not candidates:
        _append_unique_url_candidate(
            candidates,
            str(info.get("base_url") or info.get("api_url") or ""),
            "configured-api",
        )
    deadline = time.monotonic() + max(1.0, float(timeout))
    last_probes: List[Dict[str, Any]] = []
    while time.monotonic() < deadline:
        probes: List[Dict[str, Any]] = []
        for candidate in candidates:
            ca_file = (
                str(info.get("ca_certificate") or "")
                if candidate["root_url"].startswith("https://")
                else ""
            )
            status, detail = _probe_http_status(
                candidate["root_url"].rstrip("/") + "/health",
                timeout=5.0,
                ca_file=ca_file,
            )
            probes.append(
                {
                    **candidate,
                    "health_http_status": status,
                    "health_detail": detail[:500],
                    "healthy": status == 200,
                }
            )
        last_probes = probes
        selected = next((item for item in probes if item.get("healthy")), None)
        if selected:
            result.update(
                {
                    "running": True,
                    "healthy": True,
                    "api_url": selected["root_url"],
                    "health_http_status": selected["health_http_status"],
                    "health_detail": selected["health_detail"],
                    "base_url_candidates": probes,
                }
            )
            return result
        time.sleep(2.0)
    selected = last_probes[0] if last_probes else {}
    result.update(
        {
            "running": False,
            "healthy": False,
            "health_http_status": selected.get("health_http_status", 0),
            "health_detail": selected.get("health_detail", "not attempted"),
            "base_url_candidates": last_probes or candidates,
        }
    )
    return result


def _read_single_secret_file(path: Path) -> str:
    if not path.is_file():
        raise RuntimeError(f"WeKnora API key file does not exist: {path}")
    text = path.read_text(encoding="utf-8", errors="strict")
    values = [line.strip().rstrip("\r") for line in text.splitlines() if line.strip()]
    if len(values) != 1:
        raise RuntimeError("WeKnora API key file must contain exactly one non-empty line")
    key = values[0]
    if not re.fullmatch(r"[A-Za-z0-9._~+/=-]{8,4096}", key):
        raise RuntimeError("WeKnora API key file contains an invalid key format")
    return key


_WSL_READ_KV_CODE = r'''
import json
from pathlib import Path
import sys
values = {}
try:
    for raw in Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().rstrip("\r")
except OSError:
    pass
print(json.dumps(values))
'''


def _read_weknora_linux_kv(info: Dict[str, Any], path: str) -> Dict[str, str]:
    if not path:
        return {}
    distro = str(info.get("distro") or "").strip()
    if sys.platform.startswith("win"):
        wsl = which("wsl.exe") or which("wsl")
        if not wsl or not distro:
            return {}
        code, output = _run_bytes(
            [wsl, "-d", distro, "--", "python3", "-c", _WSL_READ_KV_CODE, path],
            timeout=30,
        )
        if code != 0:
            return {}
        try:
            parsed = json.loads(output.strip().splitlines()[-1])
            return {str(key): str(value) for key, value in parsed.items()} if isinstance(parsed, dict) else {}
        except (json.JSONDecodeError, IndexError, AttributeError):
            return {}
    return _read_key_value_file(Path(path).expanduser())


_WEKNORA_COLLECTION_KEYS: Tuple[str, ...] = (
    "data",
    "list",
    "items",
    "knowledge_bases",
    "knowledgeBases",
    "records",
    "rows",
    "results",
)


def _weknora_api_error(response: Any) -> str:
    if not isinstance(response, dict):
        return ""
    if response.get("success") is False:
        return str(
            _first_deep_value(
                response,
                ("message", "error.message", "error", "detail", "data.message"),
            )
            or "WeKnora returned success=false"
        )
    return ""


def _extract_weknora_collection(response: Any) -> Tuple[Optional[List[Any]], str, str]:
    """Return ``(items, shape, error)`` for supported WeKnora list envelopes."""
    api_error = _weknora_api_error(response)
    if api_error:
        return None, "error-envelope", api_error
    current = response
    shape: List[str] = []
    for _ in range(8):
        if isinstance(current, list):
            return current, ".".join(shape) or "list", ""
        if not isinstance(current, dict):
            return None, ".".join(shape) or type(current).__name__, (
                "catalog response is not a JSON list or supported object envelope"
            )
        selected = None
        for key in _WEKNORA_COLLECTION_KEYS:
            if key in current:
                selected = key
                break
        if selected is None:
            return None, ".".join(shape) or "object", (
                "catalog JSON has no supported collection key; top-level keys="
                + ",".join(sorted(str(key) for key in current)[:30])
            )
        shape.append(selected)
        current = current[selected]
    return None, ".".join(shape), "catalog JSON nesting is unexpectedly deep"


def _normalise_weknora_kb_entries(items: Any, *, shared: bool) -> List[Dict[str, Any]]:
    if not isinstance(items, list):
        return []
    values: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        candidate = item
        for key in ("knowledge_base", "knowledgeBase", "kb"):
            nested = item.get(key)
            if isinstance(nested, dict):
                candidate = nested
                break
        kb_id = str(candidate.get("id") or candidate.get("knowledge_base_id") or "").strip()
        if not kb_id:
            continue
        values.append(
            {
                "id": kb_id,
                "name": str(candidate.get("name") or candidate.get("title") or kb_id).strip(),
                "description": str(candidate.get("description") or "").strip(),
                "shared": shared,
            }
        )
    return values


def _safe_weknora_identity(response: Any) -> Dict[str, Any]:
    if not isinstance(response, dict):
        return {}
    return {
        "tenant_id": _first_deep_value(
            response,
            (
                "data.active_tenant.id",
                "active_tenant.id",
                "data.tenant.id",
                "tenant.id",
                "data.user.tenant_id",
                "user.tenant_id",
            ),
        ),
        "tenant_name": _first_deep_value(
            response,
            (
                "data.active_tenant.name",
                "active_tenant.name",
                "data.tenant.name",
                "tenant.name",
            ),
        ),
        "user_id": _first_deep_value(response, ("data.user.id", "user.id", "data.id", "id")),
        "user_email": _first_deep_value(
            response,
            ("data.user.email", "user.email", "data.email", "email"),
        ),
    }


def _normalise_weknora_workspace_entries(items: Any) -> List[Dict[str, Any]]:
    if not isinstance(items, list):
        return []
    values: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        candidate = item
        for key in ("tenant", "workspace", "active_tenant"):
            nested = item.get(key)
            if isinstance(nested, dict):
                candidate = nested
                break
        tenant_id = str(candidate.get("id") or candidate.get("tenant_id") or "").strip()
        if not re.fullmatch(r"[1-9][0-9]*", tenant_id) or tenant_id in seen:
            continue
        seen.add(tenant_id)
        values.append(
            {
                "id": tenant_id,
                "name": str(
                    candidate.get("name")
                    or candidate.get("tenant_name")
                    or candidate.get("title")
                    or f"workspace-{tenant_id}"
                ).strip(),
                "description": str(candidate.get("description") or "").strip(),
                "status": str(candidate.get("status") or "").strip(),
            }
        )
    return values


def validate_weknora_api_key(
    base_url: str,
    api_key: str,
    *,
    tenant_id: str = "",
    timeout: float = 45.0,
    ca_file: str = "",
) -> Dict[str, Any]:
    """Validate one API-key/workspace pair and return an auditable KB catalogue."""
    base_url = str(base_url).rstrip("/")
    tenant_id = str(tenant_id or "").strip()
    if tenant_id and not re.fullmatch(r"[1-9][0-9]*", tenant_id):
        return {
            "valid": False,
            "base_url": base_url,
            "tenant_id": tenant_id,
            "error": "target workspace id must be a positive integer",
        }

    owned_url = _weknora_catalog_url(base_url)
    owned_probe: Dict[str, Any] = {}
    status, owned_response, detail = _weknora_request(
        "GET",
        owned_url,
        api_key=api_key,
        tenant_id=tenant_id,
        timeout=timeout,
        ca_file=ca_file,
        diagnostics=owned_probe,
    )
    if status < 200 or status >= 300:
        return {
            "valid": False,
            "base_url": base_url,
            "tenant_id": tenant_id,
            "catalog_url": owned_url,
            "catalog_probe": owned_probe,
            "error": f"GET {owned_url} returned HTTP {status or 'unreachable'}: {detail}",
        }
    if owned_response is None:
        return {
            "valid": False,
            "base_url": base_url,
            "tenant_id": tenant_id,
            "catalog_url": owned_url,
            "catalog_probe": owned_probe,
            "error": (
                f"GET {owned_url} returned HTTP {status}, but the body is not JSON. "
                "This usually means the URL reached a frontend/SPA fallback instead of WeKnora REST API."
            ),
        }
    owned_items, owned_shape, owned_error = _extract_weknora_collection(owned_response)
    owned_probe["collection_shape"] = owned_shape
    if owned_error:
        owned_probe["collection_error"] = owned_error
        return {
            "valid": False,
            "base_url": base_url,
            "tenant_id": tenant_id,
            "catalog_url": owned_url,
            "catalog_probe": owned_probe,
            "error": f"GET {owned_url} returned unsupported JSON: {owned_error}",
        }
    owned = _normalise_weknora_kb_entries(owned_items, shared=False)

    shared_url = base_url + "/shared-knowledge-bases?" + urllib.parse.urlencode(
        {"page": 1, "page_size": WEKNORA_CATALOG_PAGE_SIZE}
    )
    shared_probe: Dict[str, Any] = {}
    shared_status, shared_response, shared_detail = _weknora_request(
        "GET",
        shared_url,
        api_key=api_key,
        tenant_id=tenant_id,
        timeout=timeout,
        ca_file=ca_file,
        diagnostics=shared_probe,
    )
    shared: List[Dict[str, Any]] = []
    if 200 <= shared_status < 300 and shared_response is not None:
        shared_items, shared_shape, shared_error = _extract_weknora_collection(shared_response)
        shared_probe["collection_shape"] = shared_shape
        if not shared_error:
            shared = _normalise_weknora_kb_entries(shared_items, shared=True)
        else:
            shared_probe["collection_error"] = shared_error

    entries: List[Dict[str, Any]] = []
    seen: set[str] = set()
    inaccessible: List[Dict[str, Any]] = []
    for entry in [*owned, *shared]:
        if entry["id"] in seen:
            continue
        seen.add(entry["id"])
        detail_url = base_url + "/knowledge-bases/" + urllib.parse.quote(entry["id"], safe="")
        detail_probe: Dict[str, Any] = {}
        detail_status, detail_response, detail_text = _weknora_request(
            "GET",
            detail_url,
            api_key=api_key,
            tenant_id=tenant_id,
            timeout=timeout,
            ca_file=ca_file,
            diagnostics=detail_probe,
        )
        verified = 200 <= detail_status < 300 and not _weknora_api_error(detail_response)
        enriched = dict(entry)
        enriched["detail_http_status"] = detail_status
        enriched["verified"] = verified
        enriched["tool_name"] = _weknora_alias_name(enriched)
        if isinstance(detail_response, dict):
            detail_kb = detail_response.get("data", detail_response)
            if isinstance(detail_kb, dict):
                enriched["name"] = str(detail_kb.get("name") or enriched["name"])
                enriched["description"] = str(
                    detail_kb.get("description") or enriched.get("description") or ""
                )
        if not verified:
            inaccessible.append(
                {
                    "id": entry["id"],
                    "name": entry["name"],
                    "url": detail_url,
                    "http_status": detail_status,
                    "detail": detail_text[:300],
                    "probe": detail_probe,
                }
            )
        entries.append(enriched)

    # Identity is useful even for a non-empty catalogue: it proves which
    # workspace a tenant-scoped key is bound to. Platform keys receive the
    # fixed X-Tenant-ID above, so auth/me reports the same target context.
    identity_probe: Dict[str, Any] = {}
    identity: Dict[str, Any] = {}
    identity_status, identity_response, _identity_detail = _weknora_request(
        "GET",
        base_url + "/auth/me",
        api_key=api_key,
        tenant_id=tenant_id,
        timeout=timeout,
        ca_file=ca_file,
        diagnostics=identity_probe,
    )
    if 200 <= identity_status < 300:
        identity = _safe_weknora_identity(identity_response)
    if tenant_id and not identity.get("tenant_id"):
        identity["tenant_id"] = tenant_id

    return {
        "valid": not inaccessible,
        "empty_catalog": not entries,
        "base_url": base_url,
        "tenant_id": str(identity.get("tenant_id") or tenant_id or ""),
        "tenant_name": str(identity.get("tenant_name") or ""),
        "catalog_url": owned_url,
        "knowledge_bases": entries,
        "owned_count": len(owned),
        "shared_count": len(shared),
        "owned_collection_shape": owned_shape,
        "shared_list_http_status": shared_status,
        "shared_list_detail": shared_detail[:300] if not (200 <= shared_status < 300) else None,
        "inaccessible": inaccessible,
        "identity": identity,
        "catalog_probe": {
            "base_url": base_url,
            "tenant_id": tenant_id or None,
            "owned": owned_probe,
            "shared": shared_probe,
            "identity": identity_probe,
        },
        "error": (
            "The API key could list knowledge bases but could not read every individual base"
            if inaccessible
            else None
        ),
    }


def list_weknora_workspaces(
    base_url: str,
    api_key: str,
    *,
    timeout: float = 30.0,
    ca_file: str = "",
) -> Dict[str, Any]:
    """List workspaces visible to a platform key without selecting a tenant."""
    base_url = str(base_url).rstrip("/")
    candidate_urls = [
        base_url + "/tenants/search?" + urllib.parse.urlencode(
            {"page": 1, "page_size": WEKNORA_CATALOG_PAGE_SIZE}
        ),
        base_url + "/tenants/all",
    ]
    attempts: List[Dict[str, Any]] = []
    for url in candidate_urls:
        diagnostics: Dict[str, Any] = {}
        status, response, detail = _weknora_request(
            "GET",
            url,
            api_key=api_key,
            timeout=timeout,
            ca_file=ca_file,
            diagnostics=diagnostics,
        )
        attempt: Dict[str, Any] = {
            "url": url,
            "http_status": status,
            "probe": diagnostics,
            "error": None,
        }
        attempts.append(attempt)
        if status < 200 or status >= 300:
            attempt["error"] = detail[:500]
            continue
        if response is None:
            attempt["error"] = "response is not JSON"
            continue
        items, shape, error = _extract_weknora_collection(response)
        attempt["collection_shape"] = shape
        if error:
            attempt["error"] = error
            continue
        workspaces = _normalise_weknora_workspace_entries(items)
        attempt["workspace_count"] = len(workspaces)
        return {
            "valid": True,
            "base_url": base_url,
            "url": url,
            "workspaces": workspaces,
            "attempts": attempts,
        }
    return {
        "valid": False,
        "base_url": base_url,
        "workspaces": [],
        "attempts": attempts,
        "error": "The API key could not list the WeKnora workspace catalogue",
    }


def _login_weknora_bootstrap_admin(
    info: Dict[str, Any],
    base_url: str,
    *,
    ca_file: str = "",
) -> Dict[str, Any]:
    credentials_path = str(info.get("bootstrap_credentials_file") or "")
    credentials = _read_weknora_linux_kv(info, credentials_path)
    email = str(credentials.get("WEKNORA_ADMIN_EMAIL") or "").strip()
    password = str(credentials.get("WEKNORA_ADMIN_PASSWORD") or "")
    if not email or not password:
        raise RuntimeError(
            "No usable bootstrap administrator credentials were found for this WeKnora target. "
            "Supply a key from the target workspace, or a platform key together with "
            "-WeKnoraTenantId/-WeKnoraTenantName."
        )
    login_status, login_response, login_detail = _weknora_request(
        "POST",
        base_url.rstrip("/") + "/auth/login",
        payload={"email": email, "password": password},
        timeout=45,
        ca_file=ca_file,
    )
    if login_status != 200:
        raise RuntimeError(
            f"WeKnora bootstrap administrator login failed (HTTP {login_status or 'unreachable'}): "
            f"{login_detail}"
        )
    access_token = str(
        _first_deep_value(
            login_response,
            ("token", "data.token", "access_token", "data.access_token"),
        )
        or ""
    )
    if not access_token:
        raise RuntimeError("WeKnora login succeeded but returned no access token")
    identity_status, identity_response, _identity_detail = _weknora_request(
        "GET",
        base_url.rstrip("/") + "/auth/me",
        bearer_token=access_token,
        timeout=30,
        ca_file=ca_file,
    )
    identity = _safe_weknora_identity(identity_response) if 200 <= identity_status < 300 else {}
    return {
        "access_token": access_token,
        "email": email,
        "identity": identity,
        "credentials_file": credentials_path,
    }


def _create_weknora_platform_api_key(
    base_url: str,
    bearer_token: str,
    capabilities: Iterable[str],
    *,
    name_suffix: str,
    ca_file: str = "",
) -> Dict[str, Any]:
    capability_list = [str(value) for value in capabilities if str(value).strip()]
    payload = {
        "name": f"engineering-mcp-{name_suffix}-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
        "capabilities": capability_list,
    }
    status, response, detail = _weknora_request(
        "POST",
        base_url.rstrip("/") + "/system/admin/api-keys",
        payload=payload,
        bearer_token=bearer_token,
        timeout=45,
        ca_file=ca_file,
    )
    if status not in (200, 201):
        raise RuntimeError(
            "The bootstrap account could not create a WeKnora platform API key "
            f"(HTTP {status or 'unreachable'}): {detail}. The account must be SystemAdmin."
        )
    token = str(
        _first_deep_value(
            response,
            ("data.token", "data.api_key", "token", "api_key"),
        )
        or ""
    )
    key_id = str(_first_deep_value(response, ("data.id", "id")) or "")
    if not re.fullmatch(r"[A-Za-z0-9._~+/=-]{8,4096}", token):
        raise RuntimeError("WeKnora created a platform key but returned no usable plaintext token")
    if not re.fullmatch(r"[1-9][0-9]*", key_id):
        raise RuntimeError("WeKnora created a platform key but returned no usable key id")
    return {
        "api_key": token,
        "key_id": key_id,
        "capabilities": capability_list,
        "scope_type": "platform",
        "name": payload["name"],
    }


def _revoke_weknora_platform_api_key(
    base_url: str,
    bearer_token: str,
    key_id: str,
    *,
    ca_file: str = "",
) -> Dict[str, Any]:
    if not re.fullmatch(r"[1-9][0-9]*", str(key_id or "")):
        return {"revoked": False, "error": "invalid platform key id"}
    status, _response, detail = _weknora_request(
        "DELETE",
        base_url.rstrip("/") + "/system/admin/api-keys/" + urllib.parse.quote(str(key_id), safe=""),
        bearer_token=bearer_token,
        timeout=30,
        ca_file=ca_file,
    )
    return {
        "revoked": 200 <= status < 300,
        "http_status": status,
        "error": None if 200 <= status < 300 else detail[:500],
    }


def discover_weknora_workspace(
    base_url: str,
    api_key: str,
    *,
    requested_tenant_id: str = "",
    requested_tenant_name: str = "",
    allow_empty_catalog: bool = False,
    timeout: float = 30.0,
    ca_file: str = "",
) -> Dict[str, Any]:
    """Select one workspace using a platform key and verify its KB catalogue."""
    requested_tenant_id = str(requested_tenant_id or "").strip()
    requested_tenant_name = str(requested_tenant_name or "").strip()
    listing = list_weknora_workspaces(
        base_url,
        api_key,
        timeout=timeout,
        ca_file=ca_file,
    )
    result: Dict[str, Any] = {
        "checked_at": now_iso(),
        "base_url": str(base_url).rstrip("/"),
        "requested_tenant_id": requested_tenant_id or None,
        "requested_tenant_name": requested_tenant_name or None,
        "workspace_listing": listing,
        "workspace_probes": [],
        "selected": None,
        "valid": False,
    }
    workspaces = list(listing.get("workspaces") or []) if listing.get("valid") else []

    if requested_tenant_id:
        candidates = [entry for entry in workspaces if str(entry.get("id")) == requested_tenant_id]
        if not candidates:
            candidates = [{"id": requested_tenant_id, "name": "", "description": "", "synthetic": True}]
    elif requested_tenant_name:
        matches = [
            entry
            for entry in workspaces
            if str(entry.get("name") or "").strip().casefold() == requested_tenant_name.casefold()
        ]
        if len(matches) != 1:
            result["error"] = (
                f"Workspace name {requested_tenant_name!r} matched {len(matches)} workspaces. "
                "Use -WeKnoraTenantId with one numeric id."
            )
            return result
        candidates = matches
    else:
        if not listing.get("valid"):
            result["error"] = str(listing.get("error") or "Workspace catalogue is unavailable")
            return result
        candidates = workspaces

    for workspace in candidates:
        tenant_id = str(workspace.get("id") or "").strip()
        validation = validate_weknora_api_key(
            base_url,
            api_key,
            tenant_id=tenant_id,
            timeout=max(5.0, min(float(timeout), 30.0)),
            ca_file=ca_file,
        )
        probe = {
            "id": tenant_id,
            "name": str(workspace.get("name") or validation.get("tenant_name") or ""),
            "valid": bool(validation.get("valid")),
            "empty_catalog": bool(validation.get("empty_catalog")),
            "knowledge_base_count": len(validation.get("knowledge_bases") or []),
            "owned_count": validation.get("owned_count", 0),
            "shared_count": validation.get("shared_count", 0),
            "error": validation.get("error"),
            "validation": validation,
        }
        result["workspace_probes"].append(probe)

    valid_probes = [entry for entry in result["workspace_probes"] if entry.get("valid")]
    nonempty = [entry for entry in valid_probes if not entry.get("empty_catalog")]
    requested = bool(requested_tenant_id or requested_tenant_name)
    selected: Optional[Dict[str, Any]] = None
    if requested:
        if len(valid_probes) == 1 and (not valid_probes[0].get("empty_catalog") or allow_empty_catalog):
            selected = valid_probes[0]
        elif len(valid_probes) == 1:
            result["error"] = (
                f"Selected workspace {valid_probes[0].get('name') or '?'} "
                f"(tenant_id={valid_probes[0].get('id')}) contains 0 visible knowledge bases."
            )
        else:
            result["error"] = "The selected workspace could not be accessed with this platform API key"
    elif len(nonempty) == 1:
        selected = nonempty[0]
    elif len(nonempty) > 1:
        summary = ", ".join(
            f"{entry.get('name') or '?'} (tenant_id={entry.get('id')}, KBs={entry.get('knowledge_base_count')})"
            for entry in nonempty[:20]
        )
        result["ambiguous"] = True
        result["error"] = (
            "More than one workspace contains knowledge bases: " + summary + ". "
            "Rerun with -WeKnoraTenantId or -WeKnoraTenantName."
        )
    elif allow_empty_catalog and len(valid_probes) == 1:
        selected = valid_probes[0]
    elif not valid_probes:
        result["error"] = "No workspace catalogue could be read with the platform API key"
    else:
        summary = ", ".join(
            f"{entry.get('name') or '?'} (tenant_id={entry.get('id')})" for entry in valid_probes[:20]
        )
        result["error"] = (
            "All visible workspaces have an empty knowledge-base catalogue: " + summary + ". "
            "Choose the intended workspace explicitly or use -WeKnoraAllowEmptyCatalog."
        )

    if selected is not None:
        result["valid"] = True
        result["selected"] = selected
    return result


def provision_weknora_workspace_key(
    info: Dict[str, Any],
    base_url: str,
    *,
    requested_tenant_id: str = "",
    requested_tenant_name: str = "",
    allow_empty_catalog: bool = False,
    ca_file: str = "",
) -> Tuple[str, Dict[str, Any], Dict[str, Any]]:
    """Create a least-privileged platform key fixed to one selected workspace."""
    login = _login_weknora_bootstrap_admin(info, base_url, ca_file=ca_file)
    bearer = str(login["access_token"])
    discovery_key: Optional[Dict[str, Any]] = None
    runtime_key: Optional[Dict[str, Any]] = None
    discovery: Dict[str, Any] = {}
    cleanup: Dict[str, Any] = {}
    try:
        discovery_key = _create_weknora_platform_api_key(
            base_url,
            bearer,
            WEKNORA_DISCOVERY_CAPABILITIES,
            name_suffix="workspace-discovery",
            ca_file=ca_file,
        )
        discovery = discover_weknora_workspace(
            base_url,
            str(discovery_key["api_key"]),
            requested_tenant_id=requested_tenant_id,
            requested_tenant_name=requested_tenant_name,
            allow_empty_catalog=allow_empty_catalog,
            timeout=30.0,
            ca_file=ca_file,
        )
        atomic_write_json(WEKNORA_WORKSPACE_PROBE_REPORT, discovery, private=True)
        if not discovery.get("valid") or not isinstance(discovery.get("selected"), dict):
            raise RuntimeError(str(discovery.get("error") or "No target workspace was selected"))
        selected = dict(discovery["selected"])
        tenant_id = str(selected.get("id") or "")
        tenant_name = str(selected.get("name") or "")
        runtime_key = _create_weknora_platform_api_key(
            base_url,
            bearer,
            WEKNORA_RUNTIME_CAPABILITIES,
            name_suffix=f"workspace-{tenant_id}",
            ca_file=ca_file,
        )
        validation = validate_weknora_api_key(
            base_url,
            str(runtime_key["api_key"]),
            tenant_id=tenant_id,
            timeout=45.0,
            ca_file=ca_file,
        )
        if not validation.get("valid"):
            raise RuntimeError(
                "The selected workspace was discovered, but the least-privileged runtime platform key "
                f"could not read it: {validation.get('error') or 'unknown error'}"
            )
        if validation.get("empty_catalog") and not allow_empty_catalog:
            raise RuntimeError(
                f"Selected workspace {tenant_name or '?'} (tenant_id={tenant_id}) contains 0 visible knowledge bases"
            )
        metadata = {
            "source": "bootstrap-system-admin-platform-key",
            "scope_type": "platform",
            "tenant_id": tenant_id,
            "tenant_name": tenant_name or validation.get("tenant_name") or "",
            "capabilities": list(WEKNORA_RUNTIME_CAPABILITIES),
            "knowledge_base_ids": [],
            "all_current_and_future_tenant_kbs_allowed": True,
            "full_access": False,
            "runtime_key_id": runtime_key.get("key_id"),
            "workspace_selection_source": (
                "explicit-tenant-id"
                if requested_tenant_id
                else "explicit-tenant-name"
                if requested_tenant_name
                else "unique-nonempty-workspace"
            ),
            "validation": validation,
        }
        return str(runtime_key["api_key"]), metadata, discovery
    except Exception:
        if runtime_key is not None:
            cleanup["runtime_key"] = _revoke_weknora_platform_api_key(
                base_url,
                bearer,
                str(runtime_key.get("key_id") or ""),
                ca_file=ca_file,
            )
        raise
    finally:
        if discovery_key is not None:
            cleanup["discovery_key"] = _revoke_weknora_platform_api_key(
                base_url,
                bearer,
                str(discovery_key.get("key_id") or ""),
                ca_file=ca_file,
            )
        if discovery:
            discovery["temporary_key_cleanup"] = cleanup


def prepare_weknora_runtime(
    info: Dict[str, Any],
    *,
    explicit_api_key_file: str = "",
    auto_provision: bool = True,
    health_timeout: float = DEFAULT_WEKNORA_HEALTH_TIMEOUT,
    allow_empty_catalog: bool = False,
    target_tenant_id: str = "",
    target_tenant_name: str = "",
) -> Dict[str, Any]:
    target_tenant_id = str(target_tenant_id or "").strip()
    target_tenant_name = str(target_tenant_name or "").strip()
    # Do not let a failed run reuse an older workspace-discovery report.  The
    # report is recreated below only from probes performed during this invocation.
    WEKNORA_WORKSPACE_PROBE_REPORT.unlink(missing_ok=True)
    report: Dict[str, Any] = {
        "checked_at": now_iso(),
        "found": bool(info.get("found")),
        "installation_source": info.get("installation_source"),
        "remote": bool(info.get("remote")),
        "distro": info.get("distro"),
        "install_dir": info.get("install_dir"),
        "service_url": info.get("service_url") or info.get("requested_url") or info.get("api_url"),
        "requested_api_url": info.get("requested_api_url"),
        "api_url": info.get("api_url"),
        "base_url": info.get("base_url"),
        "healthy": False,
        "configured": False,
        "allow_empty_catalog": bool(allow_empty_catalog),
        "requested_tenant_id": target_tenant_id or None,
        "requested_tenant_name": target_tenant_name or None,
    }
    if not info.get("found"):
        report["error"] = "No WeKnora installation or explicit backend URL was detected"
        atomic_write_json(WEKNORA_RUNTIME_REPORT, report, private=True)
        return report

    refreshed = wait_for_weknora_backend(info, health_timeout)
    report.update(
        {
            "healthy": bool(refreshed.get("healthy")),
            "health_http_status": refreshed.get("health_http_status"),
            "health_detail": refreshed.get("health_detail"),
            "base_url_candidates": refreshed.get("base_url_candidates", []),
        }
    )
    if not refreshed.get("healthy"):
        report["error"] = (
            "WeKnora is installed/configured, but none of the candidate backend health endpoints responds. "
            "MCP configuration was not generated."
        )
        atomic_write_json(WEKNORA_RUNTIME_REPORT, report, private=True)
        return report

    raw_candidates = refreshed.get("base_url_candidates")
    endpoint_candidates: List[Dict[str, Any]] = []
    if isinstance(raw_candidates, list):
        for raw in raw_candidates:
            if not isinstance(raw, dict):
                continue
            _append_unique_url_candidate(
                endpoint_candidates,
                str(raw.get("base_url") or raw.get("root_url") or ""),
                str(raw.get("source") or "discovered-api"),
            )
    if not endpoint_candidates:
        _append_unique_url_candidate(
            endpoint_candidates,
            str(refreshed.get("base_url") or refreshed.get("api_url") or ""),
            "configured-api",
        )
    if not endpoint_candidates:
        report["error"] = "No syntactically valid WeKnora REST API base was produced"
        atomic_write_json(WEKNORA_RUNTIME_REPORT, report, private=True)
        return report

    ca_source = str(refreshed.get("ca_certificate") or "").strip()
    if ca_source:
        source_path = Path(ca_source).expanduser()
        if not source_path.is_file():
            report["error"] = f"WeKnora CA certificate file does not exist: {source_path}"
            atomic_write_json(WEKNORA_RUNTIME_REPORT, report, private=True)
            return report
        WEKNORA_CA_FILE.parent.mkdir(parents=True, exist_ok=True)
        if source_path.resolve() != WEKNORA_CA_FILE.resolve():
            shutil.copy2(source_path, WEKNORA_CA_FILE)
        if not sys.platform.startswith("win"):
            WEKNORA_CA_FILE.chmod(0o600)
        ca_file = str(WEKNORA_CA_FILE)
    else:
        WEKNORA_CA_FILE.unlink(missing_ok=True)
        ca_file = ""

    previous_secret = read_json(WEKNORA_SECRET_FILE)
    credential_candidates: List[Dict[str, str]] = []
    if explicit_api_key_file:
        credential_candidates.append(
            {
                "source": "explicit-file",
                "api_key": _read_single_secret_file(Path(explicit_api_key_file).expanduser()),
                "tenant_id": "",
                "tenant_name": "",
                "scope_type": "unknown",
            }
        )
    environment_key = str(
        os.environ.get("ENGINEERING_MCP_WEKNORA_API_KEY")
        or os.environ.get("WEKNORA_API_KEY")
        or ""
    ).strip()
    if environment_key:
        credential_candidates.append(
            {
                "source": "environment",
                "api_key": environment_key,
                "tenant_id": "",
                "tenant_name": "",
                "scope_type": "unknown",
            }
        )
    known_bases = {str(item.get("base_url") or "").rstrip("/") for item in endpoint_candidates}
    if (
        previous_secret.get("api_key")
        and str(previous_secret.get("base_url") or "").rstrip("/") in known_bases
    ):
        credential_candidates.append(
            {
                "source": "existing-engineering-secret",
                "api_key": str(previous_secret["api_key"]),
                "tenant_id": str(previous_secret.get("tenant_id") or ""),
                "tenant_name": str(previous_secret.get("tenant_name") or ""),
                "scope_type": str(previous_secret.get("scope_type") or "unknown"),
            }
        )
    legacy_environment = _read_weknora_linux_kv(refreshed, str(refreshed.get("env_file") or ""))
    legacy_key = str(legacy_environment.get("WEKNORA_API_KEY") or "").strip()
    if legacy_key:
        credential_candidates.append(
            {
                "source": "legacy-wsl-env-migration",
                "api_key": legacy_key,
                "tenant_id": "",
                "tenant_name": "",
                "scope_type": "tenant",
            }
        )

    probe_report: Dict[str, Any] = {
        "checked_at": now_iso(),
        "service_url": report.get("service_url"),
        "requested_api_url": report.get("requested_api_url"),
        "requested_tenant_id": target_tenant_id or None,
        "requested_tenant_name": target_tenant_name or None,
        "candidate_endpoints": endpoint_candidates,
        "attempts": [],
        "selected_base_url": None,
    }
    workspace_report: Dict[str, Any] = {
        "checked_at": now_iso(),
        "requested_tenant_id": target_tenant_id or None,
        "requested_tenant_name": target_tenant_name or None,
        "attempts": [],
        "selected": None,
    }
    selected: Optional[Dict[str, Any]] = None
    empty_fallback: Optional[Dict[str, Any]] = None
    rejected_sources: List[str] = []

    def record_choice(
        *,
        candidate: Dict[str, str],
        endpoint: Dict[str, Any],
        validation: Dict[str, Any],
        key_scope: str,
        tenant_id: str,
        tenant_name: str,
        selection_source: str,
    ) -> Dict[str, Any]:
        return {
            "api_key": candidate["api_key"],
            "credential_source": candidate["source"],
            "endpoint": endpoint,
            "validation": validation,
            "scope_type": key_scope,
            "tenant_id": tenant_id,
            "tenant_name": tenant_name,
            "workspace_selection_source": selection_source,
        }

    def validate_candidate(candidate: Dict[str, str]) -> bool:
        nonlocal selected, empty_fallback
        source_had_valid_endpoint = False
        for endpoint in endpoint_candidates:
            base_url = str(endpoint["base_url"]).rstrip("/")
            scheme = urllib.parse.urlsplit(base_url).scheme.lower()
            endpoint_ca = ca_file if scheme == "https" else ""
            candidate_hint_id = str(candidate.get("tenant_id") or "").strip()
            candidate_hint_name = str(candidate.get("tenant_name") or "").strip()
            if target_tenant_id:
                effective_id = target_tenant_id
            elif target_tenant_name:
                # Reuse a previously verified fixed-workspace secret when its
                # saved name still matches.  If the operator changed the name,
                # omit the old id so a discovery-capable key can resolve the new
                # workspace instead of silently pinning the previous tenant.
                effective_id = (
                    candidate_hint_id
                    if candidate_hint_id
                    and candidate_hint_name
                    and candidate_hint_name.casefold() == target_tenant_name.casefold()
                    else ""
                )
            else:
                effective_id = candidate_hint_id

            if effective_id:
                validation = validate_weknora_api_key(
                    base_url,
                    candidate["api_key"],
                    tenant_id=effective_id,
                    ca_file=endpoint_ca,
                )
                attempt = {
                    "credential_source": candidate["source"],
                    "endpoint_source": endpoint.get("source"),
                    "base_url": base_url,
                    "tenant_id": effective_id,
                    "catalog_url": validation.get("catalog_url") or _weknora_catalog_url(base_url),
                    "valid": bool(validation.get("valid")),
                    "empty_catalog": bool(validation.get("empty_catalog")),
                    "owned_count": validation.get("owned_count", 0),
                    "shared_count": validation.get("shared_count", 0),
                    "identity": validation.get("identity", {}),
                    "error": validation.get("error"),
                    "catalog_probe": validation.get("catalog_probe"),
                }
                probe_report["attempts"].append(attempt)
                if not validation.get("valid"):
                    continue
                source_had_valid_endpoint = True
                actual_name = str(
                    validation.get("tenant_name")
                    or (validation.get("identity") or {}).get("tenant_name")
                    or candidate_hint_name
                    or ""
                )
                if target_tenant_name and actual_name and actual_name.casefold() != target_tenant_name.casefold():
                    attempt["valid"] = False
                    attempt["error"] = (
                        f"tenant_id={effective_id} resolves to workspace {actual_name!r}, "
                        f"not requested name {target_tenant_name!r}"
                    )
                    continue
                choice = record_choice(
                    candidate=candidate,
                    endpoint=endpoint,
                    validation=validation,
                    key_scope=str(candidate.get("scope_type") or "unknown"),
                    tenant_id=effective_id,
                    tenant_name=actual_name,
                    selection_source=(
                        "explicit-tenant-id"
                        if target_tenant_id
                        else "saved-workspace"
                    ),
                )
                if not validation.get("empty_catalog"):
                    selected = choice
                    return True
                if empty_fallback is None:
                    empty_fallback = choice
                continue

            direct = validate_weknora_api_key(
                base_url,
                candidate["api_key"],
                ca_file=endpoint_ca,
            )
            attempt = {
                "credential_source": candidate["source"],
                "endpoint_source": endpoint.get("source"),
                "base_url": base_url,
                "tenant_id": direct.get("tenant_id"),
                "catalog_url": direct.get("catalog_url") or _weknora_catalog_url(base_url),
                "valid": bool(direct.get("valid")),
                "empty_catalog": bool(direct.get("empty_catalog")),
                "owned_count": direct.get("owned_count", 0),
                "shared_count": direct.get("shared_count", 0),
                "identity": direct.get("identity", {}),
                "error": direct.get("error"),
                "catalog_probe": direct.get("catalog_probe"),
            }
            probe_report["attempts"].append(attempt)
            identity = direct.get("identity") or {}
            direct_id = str(identity.get("tenant_id") or direct.get("tenant_id") or "")
            direct_name = str(identity.get("tenant_name") or direct.get("tenant_name") or "")
            if direct.get("valid"):
                source_had_valid_endpoint = True
                name_matches = not target_tenant_name or direct_name.casefold() == target_tenant_name.casefold()
                if name_matches:
                    choice = record_choice(
                        candidate=candidate,
                        endpoint=endpoint,
                        validation=direct,
                        key_scope=str(candidate.get("scope_type") or "tenant"),
                        tenant_id=direct_id,
                        tenant_name=direct_name,
                        selection_source=(
                            "explicit-tenant-name-current-key"
                            if target_tenant_name
                            else "key-bound-workspace"
                        ),
                    )
                    if not direct.get("empty_catalog"):
                        selected = choice
                        return True
                    if empty_fallback is None:
                        empty_fallback = choice

            # A platform key without X-Tenant-ID cannot call tenant-scoped
            # routes, but it can enumerate workspaces when it has
            # system_tenants_read. Try that path after the direct probe.
            discovery = discover_weknora_workspace(
                base_url,
                candidate["api_key"],
                requested_tenant_name=target_tenant_name,
                allow_empty_catalog=allow_empty_catalog,
                timeout=30.0,
                ca_file=endpoint_ca,
            )
            workspace_report["attempts"].append(
                {
                    "credential_source": candidate["source"],
                    "endpoint_source": endpoint.get("source"),
                    "base_url": base_url,
                    "discovery": discovery,
                }
            )
            if discovery.get("valid") and isinstance(discovery.get("selected"), dict):
                selected_workspace = dict(discovery["selected"])
                validation = dict(selected_workspace.get("validation") or {})
                choice = record_choice(
                    candidate=candidate,
                    endpoint=endpoint,
                    validation=validation,
                    key_scope="platform",
                    tenant_id=str(selected_workspace.get("id") or ""),
                    tenant_name=str(selected_workspace.get("name") or ""),
                    selection_source=(
                        "explicit-tenant-name-platform-key"
                        if target_tenant_name
                        else "unique-nonempty-workspace-platform-key"
                    ),
                )
                selected = choice
                workspace_report["selected"] = {
                    "id": choice["tenant_id"],
                    "name": choice["tenant_name"],
                    "source": choice["workspace_selection_source"],
                }
                return True
        return source_had_valid_endpoint

    for candidate in credential_candidates:
        if validate_candidate(candidate):
            if selected is not None:
                break
        else:
            rejected_sources.append(candidate["source"])

    provision_metadata: Dict[str, Any] = {}
    auto_provision_errors: List[str] = []
    can_auto_provision = bool(str(refreshed.get("bootstrap_credentials_file") or "").strip())
    # An empty tenant-scoped key is not a reason to skip automatic repair: it
    # is exactly the situation where a SystemAdmin platform key is needed to
    # select the workspace containing the books.
    if selected is None and auto_provision and can_auto_provision:
        for endpoint in endpoint_candidates:
            base_url = str(endpoint["base_url"]).rstrip("/")
            endpoint_ca = ca_file if base_url.startswith("https://") else ""
            try:
                provisioned_key, provision_metadata, discovery = provision_weknora_workspace_key(
                    refreshed,
                    base_url,
                    requested_tenant_id=target_tenant_id,
                    requested_tenant_name=target_tenant_name,
                    allow_empty_catalog=allow_empty_catalog,
                    ca_file=endpoint_ca,
                )
                workspace_report["attempts"].append(
                    {
                        "credential_source": provision_metadata.get("source"),
                        "endpoint_source": endpoint.get("source"),
                        "base_url": base_url,
                        "discovery": discovery,
                    }
                )
                validation = dict(provision_metadata.pop("validation"))
                selected = {
                    "api_key": provisioned_key,
                    "credential_source": str(provision_metadata.get("source") or "auto-provision"),
                    "endpoint": endpoint,
                    "validation": validation,
                    "scope_type": "platform",
                    "tenant_id": str(provision_metadata.get("tenant_id") or ""),
                    "tenant_name": str(provision_metadata.get("tenant_name") or ""),
                    "workspace_selection_source": str(
                        provision_metadata.get("workspace_selection_source") or "auto-provision"
                    ),
                }
                workspace_report["selected"] = {
                    "id": selected["tenant_id"],
                    "name": selected["tenant_name"],
                    "source": selected["workspace_selection_source"],
                }
                break
            except Exception as exc:
                auto_provision_errors.append(f"{base_url}: {exc}")
                failed_discovery = read_json(WEKNORA_WORKSPACE_PROBE_REPORT)
                if failed_discovery:
                    workspace_report["attempts"].append(
                        {
                            "credential_source": "bootstrap-system-admin-platform-key",
                            "endpoint_source": endpoint.get("source"),
                            "base_url": base_url,
                            "discovery": failed_discovery,
                            "error": str(exc),
                        }
                    )

    atomic_write_json(WEKNORA_WORKSPACE_PROBE_REPORT, workspace_report, private=True)

    if selected is None and empty_fallback is not None:
        if allow_empty_catalog:
            selected = empty_fallback
        else:
            validation = empty_fallback["validation"]
            identity = validation.get("identity") or {}
            tenant_hint = ""
            if identity.get("tenant_id") or identity.get("tenant_name"):
                tenant_hint = (
                    f" API key identity reports workspace {identity.get('tenant_name') or '?'} "
                    f"(tenant_id={identity.get('tenant_id') or '?'})."
                )
            selected_url = str(empty_fallback["endpoint"]["base_url"])
            probe_report["selected_base_url"] = selected_url
            probe_report["result"] = "empty-catalog-rejected"
            atomic_write_json(WEKNORA_CATALOG_PROBE_REPORT, probe_report, private=True)
            report.update(
                {
                    "error": (
                        f"WeKnora REST catalog was reached at {_weknora_catalog_url(selected_url)} and returned "
                        "a supported JSON response, but the current tenant-scoped API key can see 0 knowledge bases."
                        + tenant_hint
                        + " Tenant-scoped keys cannot switch workspaces. Rerun with -WeKnoraTenantId or "
                        "-WeKnoraTenantName so the local SystemAdmin flow can create a fixed-workspace platform key, "
                        "or supply a key created directly in the workspace containing the books."
                    ),
                    "catalog_url": _weknora_catalog_url(selected_url),
                    "base_url": selected_url,
                    "empty_catalog": True,
                    "identity": identity,
                    "catalog_probe_report": str(WEKNORA_CATALOG_PROBE_REPORT),
                    "workspace_probe_report": str(WEKNORA_WORKSPACE_PROBE_REPORT),
                    "rejected_credential_sources": rejected_sources,
                    "auto_provision_errors": auto_provision_errors,
                }
            )
            atomic_write_json(WEKNORA_RUNTIME_REPORT, report, private=True)
            return report

    if selected is None:
        probe_report["result"] = "no-valid-credential-endpoint-workspace"
        atomic_write_json(WEKNORA_CATALOG_PROBE_REPORT, probe_report, private=True)
        endpoint_errors: List[str] = []
        for attempt in probe_report.get("attempts", []):
            if not isinstance(attempt, dict):
                continue
            base = str(attempt.get("base_url") or "").strip()
            error = str(attempt.get("error") or "").strip()
            if base and error:
                summary = f"{base}: {error}"
                if summary not in endpoint_errors:
                    endpoint_errors.append(summary)
        first_attempt = next(
            (item for item in probe_report.get("attempts", []) if isinstance(item, dict)),
            {},
        )
        if first_attempt:
            report["base_url"] = first_attempt.get("base_url")
            report["catalog_url"] = first_attempt.get("catalog_url")
        workspace_errors = [
            str((item.get("discovery") or {}).get("error") or "")
            for item in workspace_report.get("attempts", [])
            if isinstance(item, dict) and isinstance(item.get("discovery"), dict)
        ]
        workspace_errors = [value for value in workspace_errors if value]
        report["error"] = (
            "No valid WeKnora API key/REST endpoint/workspace combination was found. "
            + (" Tested endpoints: " + " | ".join(endpoint_errors[:8]) if endpoint_errors else "")
            + (" Workspace selection: " + " | ".join(workspace_errors[:4]) if workspace_errors else "")
            + " Supply a key from the target workspace, or a platform key plus -WeKnoraTenantId. "
            "For a local WSL installation keep auto-provision enabled and choose the workspace with "
            "-WeKnoraTenantId/-WeKnoraTenantName when more than one contains books."
        )
        report["endpoint_errors"] = endpoint_errors
        report["rejected_credential_sources"] = rejected_sources
        report["catalog_probe_report"] = str(WEKNORA_CATALOG_PROBE_REPORT)
        report["workspace_probe_report"] = str(WEKNORA_WORKSPACE_PROBE_REPORT)
        if auto_provision_errors:
            report["auto_provision_errors"] = auto_provision_errors
        atomic_write_json(WEKNORA_RUNTIME_REPORT, report, private=True)
        return report

    api_key = str(selected["api_key"])
    credential_source = str(selected["credential_source"])
    endpoint = dict(selected["endpoint"])
    validation = dict(selected["validation"])
    base_url = str(endpoint["base_url"]).rstrip("/")
    tenant_id = str(selected.get("tenant_id") or validation.get("tenant_id") or "").strip()
    tenant_name = str(selected.get("tenant_name") or validation.get("tenant_name") or "").strip()
    scope_type = str(selected.get("scope_type") or "unknown")
    selection_source = str(selected.get("workspace_selection_source") or "key-bound-workspace")
    transport_scheme = urllib.parse.urlsplit(base_url).scheme.lower()
    if transport_scheme == "http":
        report["transport_warning"] = (
            "Plain HTTP is enabled for this WeKnora target; the API key and retrieved content "
            "are not encrypted in transit."
        )

    probe_report["selected_base_url"] = base_url
    probe_report["selected_endpoint_source"] = endpoint.get("source")
    probe_report["selected_tenant_id"] = tenant_id or None
    probe_report["selected_tenant_name"] = tenant_name or None
    probe_report["result"] = "configured"
    atomic_write_json(WEKNORA_CATALOG_PROBE_REPORT, probe_report, private=True)

    secret = {
        "schema": 3,
        "created_at": now_iso(),
        "service_url": report.get("service_url"),
        "base_url": base_url,
        "api_key": api_key,
        "tenant_id": tenant_id,
        "tenant_name": tenant_name,
        "scope_type": scope_type,
        "workspace_selection_source": selection_source,
        "chat_timeout": 300,
        "verify_ssl": transport_scheme == "https",
        "transport_scheme": transport_scheme,
        "ca_file": ca_file if transport_scheme == "https" else "",
        "distro": refreshed.get("distro"),
        "install_dir": refreshed.get("install_dir"),
        "credential_source": credential_source,
        "endpoint_source": endpoint.get("source"),
    }
    atomic_write_json(WEKNORA_SECRET_FILE, secret, private=True)
    knowledge_bases = [
        {
            "id": str(entry.get("id")),
            "name": str(entry.get("name") or entry.get("id")),
            "description": str(entry.get("description") or ""),
            "shared": bool(entry.get("shared")),
            "verified": bool(entry.get("verified")),
            "detail_http_status": entry.get("detail_http_status"),
            "tool_name": str(entry.get("tool_name") or _weknora_alias_name(entry)),
        }
        for entry in validation.get("knowledge_bases", [])
        if isinstance(entry, dict) and entry.get("id")
    ]
    all_tenant_kbs_allowed: Optional[bool] = (
        True if provision_metadata.get("all_current_and_future_tenant_kbs_allowed") else None
    )
    catalog = {
        "schema": 3,
        "generated_at": now_iso(),
        "service_url": report.get("service_url"),
        "base_url": base_url,
        "catalog_url": validation.get("catalog_url") or _weknora_catalog_url(base_url),
        "endpoint_source": endpoint.get("source"),
        "api_url": endpoint.get("root_url"),
        "installation_source": refreshed.get("installation_source"),
        "distro": refreshed.get("distro"),
        "tenant_id": tenant_id,
        "tenant_name": tenant_name,
        "scope_type": scope_type,
        "workspace_selection_source": selection_source,
        "all_current_and_future_tenant_kbs_allowed": all_tenant_kbs_allowed,
        "knowledge_bases": knowledge_bases,
    }
    atomic_write_json(WEKNORA_KB_CATALOG, catalog, private=True)
    report.update(
        {
            "healthy": True,
            "configured": True,
            "service_url": report.get("service_url"),
            "api_url": endpoint.get("root_url"),
            "base_url": base_url,
            "catalog_url": catalog["catalog_url"],
            "endpoint_source": endpoint.get("source"),
            "endpoint_fallback_used": base_url != str(endpoint_candidates[0]["base_url"]).rstrip("/"),
            "transport_scheme": transport_scheme,
            "transport_encrypted": transport_scheme == "https",
            "ca_file": ca_file if transport_scheme == "https" else "",
            "credential_source": credential_source,
            "scope_type": scope_type,
            "tenant_id": tenant_id,
            "tenant_name": tenant_name,
            "workspace_selection_source": selection_source,
            "secret_file": str(WEKNORA_SECRET_FILE),
            "catalog_file": str(WEKNORA_KB_CATALOG),
            "catalog_probe_report": str(WEKNORA_CATALOG_PROBE_REPORT),
            "workspace_probe_report": str(WEKNORA_WORKSPACE_PROBE_REPORT),
            "knowledge_base_count": len(knowledge_bases),
            "owned_knowledge_base_count": validation.get("owned_count", 0),
            "shared_knowledge_base_count": validation.get("shared_count", 0),
            "knowledge_bases": knowledge_bases,
            "empty_catalog": not knowledge_bases,
            "identity": validation.get("identity") or {},
            "scope": provision_metadata
            or {
                "scope_type": scope_type,
                "tenant_id": tenant_id,
                "knowledge_base_ids": [entry["id"] for entry in knowledge_bases],
                "all_current_and_future_tenant_kbs_allowed": None,
                "note": "Exact key scope is unknown; all currently listable bases were verified.",
            },
            "rejected_credential_sources": rejected_sources,
        }
    )
    atomic_write_json(WEKNORA_RUNTIME_REPORT, report, private=True)
    return report


# ---------------------------------------------------------------------------
# Integrated PhysicsNeMo / NeMo Agent Toolkit runtime (WSL2)
# ---------------------------------------------------------------------------


def _legacy_physnemo_state() -> Dict[str, Any]:
    component = physnemo_component()
    try:
        return component.read_json(component.STATE_FILE)
    except Exception:
        return {}


def detect_physnemo(
    *,
    preferred_distro: str = "",
    explicit_install_dir: str = "",
) -> Dict[str, Any]:
    """Report whether PhysicsNeMo can be installed into a managed WSL2 runtime."""
    if not sys.platform.startswith("win"):
        return {
            "found": False,
            "installable": False,
            "installed": False,
            "reason": "The managed NeMo Agent Toolkit runtime is supported from Windows through WSL2",
            "paths": [],
        }
    component = physnemo_component()
    try:
        distros = component.list_wsl_distros()
    except Exception as exc:
        return {
            "found": False,
            "installable": False,
            "installed": False,
            "reason": str(exc),
            "paths": [],
            "distros": [],
        }
    names = [str(item.get("name") or "") for item in distros if isinstance(item, dict)]
    names = [value for value in names if value]
    requested = str(preferred_distro or "").strip()
    selected = requested if requested in names else ""
    if requested and not selected:
        return {
            "found": False,
            "installable": False,
            "installed": False,
            "reason": f"Requested WSL distribution was not found: {requested}",
            "paths": [],
            "distros": names,
        }
    legacy = _legacy_physnemo_state()
    if not selected and str(legacy.get("distro") or "") in names:
        selected = str(legacy["distro"])
    if not selected and names:
        preferred = ["Ubuntu-24.04", "Ubuntu-22.04", "Ubuntu"]
        selected = next((name for name in preferred if name in names), names[0])
    if not selected:
        return {
            "found": False,
            "installable": False,
            "installed": False,
            "reason": "No usable WSL2 distribution is installed",
            "paths": [],
            "distros": names,
        }
    try:
        install_dir = component.resolve_linux_install_dir(
            selected,
            str(explicit_install_dir or legacy.get("linux_install_dir") or ""),
        )
    except Exception as exc:
        return {
            "found": False,
            "installable": False,
            "installed": False,
            "reason": str(exc),
            "paths": [],
            "distros": names,
            "distro": selected,
        }
    probe_script = f'''set -u
root={component.shell_path(install_dir)}
marker="$root/.engineering-mcp-physnemo-managed"
installed=0
[[ -f "$marker" ]] && grep -q '^managed_by=engineering-mcp-physnemo$' "$marker" && installed=1 || true
printf '%s\\n' "$installed"
'''
    installed = False
    try:
        result = component.wsl_run(selected, probe_script, check=True, timeout=30)
        installed = (result.stdout or "").strip().splitlines()[-1:] == ["1"]
    except Exception:
        installed = False
    return {
        "found": True,
        "installable": True,
        "installed": installed,
        "distro": selected,
        "distros": names,
        "install_dir": install_dir,
        "paths": [install_dir] if installed else [],
        "nat_port": int(legacy.get("nat_port") or DEFAULT_PHYSNEMO_NAT_PORT),
        "installation_source": "integrated-wsl2-runtime",
    }


def _physnemo_nat_tool_filter_args() -> str:
    """Render exact repeated NAT 1.9 --tool_names flags.

    PhysicsNeMo exposes five public top-level NAT functions while the task-planning and workspace tools remain internal. Their instance
    names are the public ``physnemo__*`` identifiers.  Passing those exact
    names keep MCP filtering and SessionManager entry-workflow lookup aligned.
    """
    invalid = [
        name for name in PHYSNEMO_EXPECTED_TOOLS
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", name)
    ]
    if invalid:
        raise RuntimeError(f"Unsafe PhysicsNeMo MCP tool names: {invalid}")
    return " ".join(f"--tool_names {name}" for name in PHYSNEMO_EXPECTED_TOOLS)


def _render_integrated_physnemo_run_script(root: str, nat_port: int) -> str:
    component = physnemo_component()
    tool_filter_args = _physnemo_nat_tool_filter_args()
    return f'''#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
ROOT={component.shell_path(root)}
NAT="$ROOT/.venv-nat/bin/nat"
CONFIG="$ROOT/config/physnemo.yml"
ENV_FILE="$ROOT/config/runtime.env"
LOG_DIR="$ROOT/logs"
RUN_DIR="$ROOT/run"
mkdir -p "$LOG_DIR" "$RUN_DIR"
[[ -x "$NAT" ]] || {{ echo "Missing NAT command: $NAT" >&2; exit 78; }}
[[ -r "$CONFIG" ]] || {{ echo "Missing NAT config: $CONFIG" >&2; exit 78; }}
[[ -r "$ENV_FILE" ]] || {{ echo "Missing NAT private environment: $ENV_FILE" >&2; exit 78; }}
# shellcheck disable=SC1090
source "$ENV_FILE"
for key in PHYSNEMO_AGENT_API_KEY PHYSNEMO_AGENT_BASE_URL PHYSNEMO_AGENT_MODEL PHYSNEMO_OPENWEBUI_BRIDGE_URL PHYSNEMO_OPENWEBUI_BRIDGE_SECRET PHYSNEMO_AGENT_TRANSPORT PHYSNEMO_GATEWAY_PORT PHYSNEMO_GATEWAY_ROUTE; do
  b64_key="${{key}}_B64"
  printf -v "$key" '%s' "$(printf '%s' "${{!b64_key:-}}" | base64 -d)"
  export "$key"
done
if [[ "$PHYSNEMO_AGENT_TRANSPORT" == "openwebui-chat-api" ]]; then
  windows_host="$(ip route show default 2>/dev/null | awk 'NR==1 {{print $3}}')"
  if [[ -z "$windows_host" ]]; then
    windows_host="$(awk '/^nameserver[[:space:]]+/ {{print $2; exit}}' /etc/resolv.conf 2>/dev/null || true)"
  fi
  [[ -n "$windows_host" ]] || {{ echo "Unable to resolve the Windows host address for the Open WebUI agent bridge" >&2; exit 78; }}
  if [[ "$windows_host" == *:* && "${{windows_host:0:1}}" != "[" ]]; then windows_host="[$windows_host]"; fi
  bridge_origin="http://${{windows_host}}:${{PHYSNEMO_GATEWAY_PORT}}/${{PHYSNEMO_GATEWAY_ROUTE}}"
  PHYSNEMO_AGENT_BASE_URL="$bridge_origin/openwebui-api"
  PHYSNEMO_OPENWEBUI_BRIDGE_URL="$bridge_origin"
  export PHYSNEMO_AGENT_BASE_URL PHYSNEMO_OPENWEBUI_BRIDGE_URL
fi
printf '%s\\n' "$$" > "$RUN_DIR/nat.pid"
export PYTHONUTF8=1 PYTHONIOENCODING=utf-8 PYTHONUNBUFFERED=1 NAT_TELEMETRY_ENABLED=false
export PHYSNEMO_SOURCE_ROOT="$ROOT/physicsnemo-source"
exec "$NAT" mcp serve \\
  --config_file "$CONFIG" \\
  --host 127.0.0.1 \\
  --port {int(nat_port)} \\
  --transport streamable-http \\
  --name "Engineering MCP - PhysicsNeMo" \\
  {tool_filter_args} \\
  >>"$LOG_DIR/nat-mcp.log" 2>&1
'''


def _render_integrated_physnemo_stop_script(root: str) -> str:
    component = physnemo_component()
    return f'''#!/usr/bin/env bash
set -u
ROOT={component.shell_path(root)}
file="$ROOT/run/nat.pid"
if [[ -f "$file" ]]; then
  pid="$(cat "$file" 2>/dev/null || true)"
  if [[ "$pid" =~ ^[0-9]+$ ]]; then
    kill "$pid" 2>/dev/null || true
    for _ in $(seq 1 40); do kill -0 "$pid" 2>/dev/null || break; sleep 0.2; done
    kill -9 "$pid" 2>/dev/null || true
  fi
fi
rm -f "$file"
'''



def _read_first_secret_line(path_value: str) -> str:
    path_value = str(path_value or "").strip()
    if not path_value:
        return ""
    path = Path(path_value).expanduser().resolve()
    if not path.is_file():
        raise RuntimeError(f"Secret file was not found: {path}")
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    value = next((line.strip() for line in lines if line.strip()), "")
    if not value:
        raise RuntimeError(f"Secret file is empty: {path}")
    return value


def _valid_http_base_url(value: str, label: str) -> str:
    value = str(value or "").strip().rstrip("/")
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise RuntimeError(f"{label} must be an absolute http:// or https:// URL")
    if parsed.username or parsed.password or parsed.fragment:
        raise RuntimeError(f"{label} must not contain credentials or a fragment")
    return value


def _looks_like_placeholder_api_key(value: str) -> bool:
    normalized = str(value or "").strip().casefold()
    if not normalized:
        return True
    return any(token in normalized for token in ("fake", "change-me", "sem-vlozte", "placeholder"))


def _decode_sqlite_json(value: Any, default: Any = None) -> Any:
    if value is None:
        return default
    if isinstance(value, (dict, list, bool, int, float)):
        return value
    if isinstance(value, bytes):
        try:
            value = value.decode("utf-8")
        except UnicodeDecodeError:
            return default
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return default


def _openwebui_process_inventory() -> List[Dict[str, Any]]:
    """Return native Open WebUI Python processes without exposing their environment."""
    if not sys.platform.startswith("win"):
        return []
    powershell = which("powershell.exe") or which("powershell") or which("pwsh.exe") or which("pwsh")
    if not powershell:
        return []
    script = r'''$ErrorActionPreference = "Stop"
$rows = Get-CimInstance Win32_Process | Where-Object {
  ($_.Name -match '^(python|pythonw)\.exe$') -and
  (($_.CommandLine -match '(?i)open[-_]webui\s+serve|open_webui') -or
   ($_.ExecutablePath -match '(?i)\\web-ui\\python\\python(w)?\.exe$'))
} | Select-Object ProcessId, ParentProcessId, ExecutablePath, CommandLine
@($rows) | ConvertTo-Json -Compress -Depth 4
'''
    result = run(
        [powershell, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
        timeout=30,
    )
    if result.returncode != 0 or not (result.stdout or "").strip():
        return []
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []
    rows = value if isinstance(value, list) else [value]
    output: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        executable = str(row.get("ExecutablePath") or "").strip()
        command_line = str(row.get("CommandLine") or "").strip()
        try:
            pid = int(row.get("ProcessId") or 0)
        except (TypeError, ValueError):
            pid = 0
        if executable and pid > 0:
            output.append(
                {
                    "pid": pid,
                    "parent_pid": int(row.get("ParentProcessId") or 0),
                    "executable": executable,
                    "command_match": bool(command_line),
                }
            )
    return output


def _openwebui_data_dir_from_python(executable: str) -> Dict[str, Any]:
    executable = str(executable or "").strip()
    if not executable or not Path(executable).is_file():
        return {}
    code = (
        "import os;os.environ['FROM_INIT_PY']='true';"
        "from open_webui.env import DATA_DIR,DATABASE_URL;"
        "print('ENGINEERING_MCP_OPENWEBUI_DATA_V1\\t'+str(DATA_DIR)+'\\t'+str(DATABASE_URL))"
    )
    result = run([executable, "-c", code], timeout=90)
    marker = "ENGINEERING_MCP_OPENWEBUI_DATA_V1\t"
    for line in reversed((result.stdout or "").splitlines()):
        if line.startswith(marker):
            parts = line.split("\t", 2)
            return {
                "executable": executable,
                "data_dir": parts[1] if len(parts) > 1 else "",
                "database_url": parts[2] if len(parts) > 2 else "",
                "returncode": result.returncode,
            }
    return {
        "executable": executable,
        "returncode": result.returncode,
        "error": (result.stdout or "")[-1000:],
    }


def _validate_openwebui_sqlite(path: Path) -> Dict[str, Any]:
    result: Dict[str, Any] = {"path": str(path), "valid": False}
    try:
        if not path.is_file():
            result["error"] = "not a file"
            return result
        connection = sqlite3.connect(f"file:{path}?mode=rw", uri=True, timeout=10)
        try:
            tables = {
                str(row[0])
                for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            }
            result["tables"] = sorted(tables)
            required = {"config", "user", "api_key"}
            missing = sorted(required - tables)
            if missing:
                result["error"] = "missing tables: " + ", ".join(missing)
                return result
            result["journal_mode"] = str(connection.execute("PRAGMA journal_mode").fetchone()[0])
            result["valid"] = True
            return result
        finally:
            connection.close()
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        return result


def _openwebui_database_candidates(explicit_path: str = "") -> Tuple[List[Path], List[Dict[str, Any]]]:
    candidates: List[Path] = []
    probes: List[Dict[str, Any]] = []
    if explicit_path:
        candidates.append(Path(explicit_path).expanduser())
    for variable in ("OPENWEBUI_DATABASE", "OPENWEBUI_DB_PATH"):
        value = str(os.environ.get(variable) or "").strip()
        if value:
            candidates.append(Path(value).expanduser())

    processes = _openwebui_process_inventory()
    for process in processes:
        executable = Path(str(process.get("executable") or ""))
        probe = _openwebui_data_dir_from_python(str(executable))
        if probe:
            probes.append(probe)
        data_dir = str(probe.get("data_dir") or "").strip()
        if data_dir:
            candidates.append(Path(data_dir) / "webui.db")
        database_url = str(probe.get("database_url") or "").strip()
        if database_url.startswith("sqlite:///"):
            candidates.append(Path(database_url.removeprefix("sqlite:///")))
        install_root = executable.parent.parent if executable.parent.name.casefold() == "python" else executable.parent
        candidates.extend(
            [
                install_root / "data" / "webui.db",
                install_root / "backend" / "data" / "webui.db",
                executable.parent / "Lib" / "site-packages" / "open_webui" / "data" / "webui.db",
                executable.parent / "Lib" / "site-packages" / "open_webui" / "backend" / "data" / "webui.db",
            ]
        )
        try:
            for found in install_root.rglob("webui.db"):
                try:
                    if len(found.relative_to(install_root).parts) <= 7:
                        candidates.append(found)
                except ValueError:
                    continue
        except OSError:
            pass

    local = Path(os.environ.get("LOCALAPPDATA", Path.home()))
    candidates.extend(
        [
            local / "open-webui" / "data" / "webui.db",
            local / "Open WebUI" / "data" / "webui.db",
            Path.home() / ".open-webui" / "webui.db",
        ]
    )
    unique: List[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        try:
            normalized = os.path.normcase(os.path.abspath(str(candidate)))
        except OSError:
            normalized = str(candidate)
        if normalized in seen:
            continue
        seen.add(normalized)
        unique.append(candidate)
    return unique, [{"processes": processes, "python_probes": probes}]


def _discover_openwebui_sqlite(explicit_path: str = "") -> Dict[str, Any]:
    candidates, context = _openwebui_database_candidates(explicit_path)
    attempts: List[Dict[str, Any]] = []
    for candidate in candidates:
        validation = _validate_openwebui_sqlite(candidate)
        attempts.append(validation)
        if validation.get("valid"):
            return {
                "found": True,
                "path": str(candidate),
                "validation": validation,
                "attempts": attempts,
                "context": context,
            }
    return {"found": False, "path": "", "attempts": attempts, "context": context}


def _sqlite_config_get(connection: sqlite3.Connection, key: str, default: Any = None) -> Any:
    row = connection.execute("SELECT value FROM config WHERE key = ?", (key,)).fetchone()
    return _decode_sqlite_json(row[0], default) if row else default


def _sqlite_config_upsert(connection: sqlite3.Connection, key: str, value: Any) -> None:
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    now = int(time.time())
    connection.execute(
        "INSERT INTO config(key, value, updated_at) VALUES(?,?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
        (key, encoded, now),
    )


def _backup_openwebui_database(path: Path, purpose: str) -> Path:
    OPENWEBUI_DB_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    destination = OPENWEBUI_DB_BACKUP_DIR / (
        f"webui-{purpose}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}.db"
    )
    source = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=10)
    target = sqlite3.connect(destination)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()
    restrict_private_file(destination)
    return destination


def _extract_model_ids_from_chat_payload(payload: Any) -> List[str]:
    values: List[str] = []
    if not isinstance(payload, dict):
        return values
    for key in ("models", "model"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            values.append(value.strip())
        elif isinstance(value, list):
            values.extend(str(item).strip() for item in value if str(item).strip())
    params = payload.get("params")
    if isinstance(params, dict):
        value = params.get("model")
        if isinstance(value, str) and value.strip():
            values.append(value.strip())
    history = payload.get("history")
    if isinstance(history, dict):
        messages = history.get("messages")
        iterable = messages.values() if isinstance(messages, dict) else messages if isinstance(messages, list) else []
        for message in reversed(list(iterable)):
            if isinstance(message, dict):
                value = message.get("model")
                if isinstance(value, str) and value.strip():
                    values.append(value.strip())
    return list(dict.fromkeys(values))


def _openwebui_database_model_hint(connection: sqlite3.Connection, admin_user_id: str) -> Dict[str, Any]:
    default_models = _sqlite_config_get(connection, "ui.default_models", None)
    candidates: List[str] = []
    source = ""
    if isinstance(default_models, str):
        candidates.extend(item.strip() for item in re.split(r"[,;]", default_models) if item.strip())
    elif isinstance(default_models, list):
        candidates.extend(str(item).strip() for item in default_models if str(item).strip())
    if candidates:
        source = "ui.default_models"
    tables = {
        row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    if not candidates and "chat" in tables:
        queries = (
            ("SELECT chat FROM chat WHERE user_id = ? ORDER BY updated_at DESC LIMIT 20", (admin_user_id,), "latest-admin-chat"),
            ("SELECT chat FROM chat ORDER BY updated_at DESC LIMIT 40", (), "latest-local-chat"),
        )
        for sql, params, candidate_source in queries:
            for (raw_chat,) in connection.execute(sql, params).fetchall():
                payload = _decode_sqlite_json(raw_chat, {})
                candidates.extend(_extract_model_ids_from_chat_payload(payload))
                if candidates:
                    source = candidate_source
                    break
            if candidates:
                break
    candidates = list(dict.fromkeys(candidates))
    return {"model": candidates[0] if candidates else "", "source": source, "candidates": candidates[:20]}


def _ensure_openwebui_managed_api_key(
    database_path: str,
    *,
    enable_dlp_repair: bool = True,
) -> Dict[str, Any]:
    """Create/reuse a managed admin API key and repair the required global DLP filter."""
    path = Path(database_path)
    backup = _backup_openwebui_database(path, "engineering-mcp-sync")
    report: Dict[str, Any] = {
        "contract": OPENWEBUI_MANAGED_API_KEY_CONTRACT,
        "database": str(path),
        "backup": str(backup),
        "api_key_created": False,
        "api_key_reused": False,
        "api_key_present": False,
        "dlp": {},
    }
    connection = sqlite3.connect(path, timeout=30)
    connection.execute("PRAGMA busy_timeout=30000")
    try:
        admin = connection.execute(
            "SELECT id, email FROM user WHERE role = 'admin' ORDER BY created_at ASC LIMIT 1"
        ).fetchone()
        if not admin:
            raise RuntimeError("Open WebUI database contains no administrator user")
        admin_id, admin_email = str(admin[0]), str(admin[1] or "")
        report["admin_user_id"] = admin_id
        report["admin_email"] = admin_email

        managed_row = None
        for row in connection.execute(
            "SELECT id, key, data FROM api_key WHERE user_id = ? ORDER BY created_at DESC",
            (admin_id,),
        ).fetchall():
            metadata = _decode_sqlite_json(row[2], {})
            if (
                isinstance(metadata, dict)
                and metadata.get("managed_by") == "engineering-mcp-unified"
                and metadata.get("purpose") == "physnemo-openwebui"
            ):
                managed_row = row
                break
        now = int(time.time())
        if managed_row:
            key_id, api_key = str(managed_row[0]), str(managed_row[1])
            if not re.fullmatch(r"sk-[A-Za-z0-9._~-]{16,256}", api_key):
                api_key = "sk-" + uuid.uuid4().hex
                connection.execute(
                    "UPDATE api_key SET key = ?, updated_at = ? WHERE id = ?",
                    (api_key, now, key_id),
                )
                report["api_key_rotated"] = True
            else:
                report["api_key_reused"] = True
        else:
            key_id = str(uuid.uuid4())
            api_key = "sk-" + uuid.uuid4().hex
            metadata = json.dumps(
                {
                    "name": "Engineering MCP PhysicsNeMo",
                    "managed_by": "engineering-mcp-unified",
                    "purpose": "physnemo-openwebui",
                    "schema": 1,
                },
                separators=(",", ":"),
            )
            connection.execute(
                "INSERT INTO api_key(id,user_id,key,data,expires_at,last_used_at,created_at,updated_at) "
                "VALUES(?,?,?,?,NULL,NULL,?,?)",
                (key_id, admin_id, api_key, metadata, now, now),
            )
            report["api_key_created"] = True
        report["api_key_id"] = key_id
        report["api_key_present"] = bool(api_key)

        api_keys_enabled = bool(_sqlite_config_get(connection, "auth.enable_api_keys", False))
        if not api_keys_enabled:
            _sqlite_config_upsert(connection, "auth.enable_api_keys", True)
            report["api_keys_enabled_by_installer"] = True
        else:
            report["api_keys_enabled_by_installer"] = False

        if bool(_sqlite_config_get(connection, "auth.api_key.endpoint_restrictions", False)):
            raw_allowed = _sqlite_config_get(connection, "auth.api_key.allowed_endpoints", "")
            if isinstance(raw_allowed, list):
                allowed = [str(item).strip() for item in raw_allowed if str(item).strip()]
            else:
                allowed = [item.strip() for item in str(raw_allowed or "").split(",") if item.strip()]
            required_paths = (
                "/api/models",
                "/api/chat/completions",
                "/api/v1/files",
                "/api/v1/configs/tool_servers",
                "/api/v1/functions",
            )
            changed = False
            for item in required_paths:
                if item not in allowed:
                    allowed.append(item)
                    changed = True
            if changed:
                _sqlite_config_upsert(connection, "auth.api_key.allowed_endpoints", ",".join(allowed))
            report["endpoint_restrictions_extended"] = changed
            report["allowed_endpoint_count"] = len(allowed)

        dlp: Dict[str, Any] = {
            "contract": OPENWEBUI_DLP_PREFLIGHT_CONTRACT,
            "tool_present": False,
            "filter_present": False,
            "active": None,
            "global": None,
            "repaired": False,
            "blocking": False,
        }
        tables = {
            row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        if "tool" in tables:
            dlp["tool_present"] = bool(
                connection.execute("SELECT 1 FROM tool WHERE id = 'anonymizovat' LIMIT 1").fetchone()
            )
        if "function" in tables:
            row = connection.execute(
                "SELECT type,is_active,is_global FROM function WHERE id = 'pseudo_anonymization' LIMIT 1"
            ).fetchone()
            if row:
                dlp.update(
                    {
                        "filter_present": True,
                        "type": str(row[0] or ""),
                        "active": bool(row[1]),
                        "global": bool(row[2]),
                    }
                )
                if dlp["tool_present"] and (not dlp["active"] or not dlp["global"]):
                    if enable_dlp_repair and dlp["type"] == "filter":
                        connection.execute(
                            "UPDATE function SET is_active = 1, is_global = 1, updated_at = ? "
                            "WHERE id = 'pseudo_anonymization'",
                            (now,),
                        )
                        dlp.update({"active": True, "global": True, "repaired": True})
                    else:
                        dlp["blocking"] = True
            elif dlp["tool_present"]:
                dlp["blocking"] = True
                dlp["error"] = "tool_anonymizovat is installed but pseudo_anonymization filter is missing"
        report["dlp"] = dlp
        report["model_hint"] = _openwebui_database_model_hint(connection, admin_id)
        connection.commit()
        return {**report, "api_key": api_key}
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _safe_native_openwebui_summary(value: Dict[str, Any]) -> Dict[str, Any]:
    return {key: item for key, item in value.items() if key != "api_key"}


def _scheduled_task_runtime_candidates() -> List[Path]:
    """Discover e-INFRA Open WebUI runtime.json from its scheduled task without reading secrets."""
    if not sys.platform.startswith("win"):
        return []
    executable = which("schtasks.exe") or which("schtasks")
    if not executable:
        return []
    result = run(
        [executable, "/Query", "/TN", "e-INFRA Open WebUI Backend", "/XML"],
        timeout=20,
    )
    if result.returncode != 0 or not (result.stdout or "").strip():
        return []
    try:
        root = ET.fromstring(result.stdout)
    except ET.ParseError:
        return []
    values: Dict[str, List[str]] = {"Arguments": [], "WorkingDirectory": []}
    for node in root.iter():
        local_name = node.tag.rsplit("}", 1)[-1]
        if local_name in values and node.text:
            values[local_name].append(node.text.strip())
    candidates: List[Path] = []
    file_pattern = re.compile(r"(?i)(?:^|\s)-File\s+(?:\"([^\"]+)\"|'([^']+)'|(\S+))")
    for arguments in values["Arguments"]:
        match = file_pattern.search(arguments)
        if not match:
            continue
        script_path = next((part for part in match.groups() if part), "")
        if script_path:
            candidates.append(Path(script_path).expanduser().parent / "runtime.json")
    for working_directory in values["WorkingDirectory"]:
        if working_directory:
            candidates.append(Path(working_directory).expanduser() / "config" / "runtime.json")
    return candidates


def _physnemo_runtime_candidates() -> List[Path]:
    candidates: List[Path] = []
    for variable in ("EINFRA_OPENWEBUI_RUNTIME", "PHYSNEMO_OPENWEBUI_RUNTIME"):
        value = str(os.environ.get(variable) or "").strip()
        if value:
            candidates.append(Path(value).expanduser())
    candidates.append(PHYSNEMO_OPENWEBUI_RUNTIME_DEFAULT)
    candidates.extend(_scheduled_task_runtime_candidates())
    program_data = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData"))
    try:
        for child in program_data.iterdir():
            if child.is_dir() and "openwebui" in child.name.casefold():
                candidates.append(child / "config" / "runtime.json")
    except OSError:
        pass
    unique: List[Path] = []
    seen: set[str] = set()
    for path in candidates:
        try:
            key = os.path.normcase(os.path.abspath(str(path)))
        except OSError:
            key = str(path)
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


def _runtime_environment_value(environment: Dict[str, Any], *names: str) -> str:
    for name in names:
        value = environment.get(name)
        if isinstance(value, list):
            value = next((item for item in value if str(item).strip()), "")
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _first_delimited_value(value: str) -> str:
    return next((item.strip() for item in re.split(r"[,;]", str(value or "")) if item.strip()), "")


def _detect_einfra_openwebui_runtime() -> Dict[str, Any]:
    attempts: List[Dict[str, Any]] = []
    selected: Dict[str, Any] = {}
    for path in _physnemo_runtime_candidates():
        attempt: Dict[str, Any] = {"path": str(path), "exists": False, "readable": False}
        attempts.append(attempt)
        try:
            attempt["exists"] = path.is_file()
        except OSError as exc:
            attempt["error"] = f"{type(exc).__name__}: {exc}"
            continue
        if not attempt["exists"]:
            continue
        try:
            raw = path.read_text(encoding="utf-8-sig")
            value = json.loads(raw)
            attempt["readable"] = True
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            attempt["error"] = f"{type(exc).__name__}: {exc}"
            continue
        environment = value.get("Environment") if isinstance(value, dict) else None
        if not isinstance(environment, dict):
            attempt["error"] = "runtime.json has no Environment object"
            continue
        default_models = _runtime_environment_value(environment, "DEFAULT_MODELS", "DEFAULT_MODEL")
        model = _first_delimited_value(default_models)
        provider_base = _first_delimited_value(
            _runtime_environment_value(environment, "OPENAI_API_BASE_URL", "OPENAI_API_BASE_URLS")
        )
        provider_key = _first_delimited_value(
            _runtime_environment_value(environment, "OPENAI_API_KEY", "OPENAI_API_KEYS")
        )
        backend_port = value.get("BackendPort")
        openwebui_base = ""
        try:
            port = int(backend_port)
            if 1 <= port <= 65535:
                openwebui_base = f"http://127.0.0.1:{port}"
        except (TypeError, ValueError):
            pass
        primary_url = str(value.get("PrimaryUrl") or environment.get("WEBUI_URL") or "").strip()
        attempt.update(
            {
                "provider_base_url": provider_base,
                "provider_model": model,
                "provider_api_key_present": bool(provider_key),
                "provider_api_key_placeholder": _looks_like_placeholder_api_key(provider_key),
                "openwebui_base_url": openwebui_base,
                "primary_url": primary_url,
            }
        )
        candidate = {
            "path": str(path),
            "agent_base_url": provider_base,
            "agent_api_key": "" if _looks_like_placeholder_api_key(provider_key) else provider_key,
            "agent_model": model,
            "openwebui_base_url": openwebui_base or primary_url,
            "primary_url": primary_url,
        }
        if not selected:
            selected = candidate
        if candidate["agent_base_url"] and candidate["agent_api_key"] and candidate["agent_model"]:
            selected = candidate
            break
    return {**selected, "attempts": attempts}


def _probe_openwebui_root(value: str) -> Dict[str, Any]:
    root = str(value or "").strip().rstrip("/")
    if not root:
        return {"base_url": "", "healthy": False, "error": "empty URL"}
    try:
        root = _valid_http_base_url(root, "Open WebUI base URL")
    except RuntimeError as exc:
        return {"base_url": root, "healthy": False, "error": str(exc)}
    urls = [root + "/_app/version.json", root + "/health"]
    for url in urls:
        request = urllib.request.Request(url, headers={"Accept": "application/json,text/plain,*/*"})
        try:
            with urllib.request.urlopen(request, timeout=3) as response:
                status = int(getattr(response, "status", 200))
                if 200 <= status < 500:
                    return {"base_url": root, "healthy": True, "url": url, "http_status": status}
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
    return {"base_url": root, "healthy": False, "error": locals().get("last_error", "unreachable")}


def _discover_local_openwebui_base_url(*preferred: str) -> Tuple[str, List[Dict[str, Any]]]:
    candidates: List[str] = []
    candidates.extend(str(item or "").strip() for item in preferred if str(item or "").strip())
    candidates.extend(
        [
            "http://127.0.0.1:8080",
            "http://127.0.0.1:18080",
            "http://127.0.0.1:3000",
        ]
    )
    attempts: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for candidate in candidates:
        root = candidate.rstrip("/")
        if root in seen:
            continue
        seen.add(root)
        result = _probe_openwebui_root(root)
        attempts.append(result)
        if result.get("healthy"):
            return root, attempts
    return "", attempts


def _openwebui_agent_base_url(openwebui_root: str) -> str:
    root = _valid_http_base_url(openwebui_root, "Open WebUI base URL")
    parsed = urllib.parse.urlparse(root)
    path = parsed.path.rstrip("/")
    if path.endswith("/api/v1"):
        path = path[:-3]
    elif not path.endswith("/api"):
        path = path + "/api"
    return urllib.parse.urlunparse(parsed._replace(path=path, params="", query="", fragment=""))


def _openwebui_model_catalog(openwebui_root: str, api_key: str) -> Tuple[List[str], List[Dict[str, Any]]]:
    attempts: List[Dict[str, Any]] = []
    models: List[str] = []
    headers = {"Accept": "application/json", "Authorization": f"Bearer {api_key}"}
    for suffix in ("/api/models", "/api/v1/models"):
        url = openwebui_root.rstrip("/") + suffix
        attempt: Dict[str, Any] = {"url": url}
        attempts.append(attempt)
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                attempt["http_status"] = int(getattr(response, "status", 200))
                payload = json.loads(response.read(4 * 1024 * 1024).decode("utf-8"))
        except urllib.error.HTTPError as exc:
            attempt["http_status"] = int(exc.code)
            attempt["error"] = str(exc.reason)
            continue
        except (urllib.error.URLError, TimeoutError, OSError, UnicodeError, json.JSONDecodeError) as exc:
            attempt["error"] = f"{type(exc).__name__}: {exc}"
            continue
        rows = payload.get("data") if isinstance(payload, dict) else payload
        if not isinstance(rows, list):
            attempt["error"] = "model response is not a list or {data:[...]}"
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            model_id = str(row.get("id") or row.get("model") or "").strip()
            if model_id and model_id not in models:
                models.append(model_id)
        attempt["model_count"] = len(models)
        if models:
            break
    return models, attempts


def _resolve_physnemo_agent_secret(options: Dict[str, Any]) -> Dict[str, Any]:
    existing = read_json(PHYSNEMO_AGENT_SECRET_FILE)
    auto_detect = options.get("physnemo_agent_auto_detect") is not False
    detected = _detect_einfra_openwebui_runtime() if auto_detect else {"attempts": []}
    native_database = (
        _discover_openwebui_sqlite(str(options.get("openwebui_database") or ""))
        if auto_detect and options.get("openwebui_native_sync") is not False
        else {"found": False, "attempts": []}
    )
    native_access: Dict[str, Any] = {}
    if native_database.get("found"):
        try:
            native_access = _ensure_openwebui_managed_api_key(
                str(native_database["path"]),
                enable_dlp_repair=bool(options.get("openwebui_dlp_repair", True)),
            )
        except Exception as exc:
            native_access = {
                "error": f"{type(exc).__name__}: {exc}",
                "database": str(native_database.get("path") or ""),
            }

    explicit_agent_key = _read_first_secret_line(str(options.get("physnemo_agent_api_key_file") or ""))
    explicit_openwebui_key = _read_first_secret_line(
        str(options.get("physnemo_openwebui_api_key_file") or "")
    )
    openwebui_api_key = (
        explicit_openwebui_key
        or str(os.environ.get("PHYSNEMO_OPENWEBUI_API_KEY") or "").strip()
        or str(existing.get("openwebui_api_key") or "").strip()
        or str(native_access.get("api_key") or "").strip()
    )
    preferred_openwebui = (
        str(options.get("physnemo_openwebui_url") or "").strip()
        or str(os.environ.get("PHYSNEMO_OPENWEBUI_URL") or "").strip()
        or str(existing.get("openwebui_base_url") or "").strip()
        or str(detected.get("openwebui_base_url") or "").strip()
        or str(detected.get("primary_url") or "").strip()
        or ("http://127.0.0.1:8080" if native_database.get("found") else "")
    )
    openwebui_base_url, openwebui_probe_attempts = _discover_local_openwebui_base_url(
        preferred_openwebui
    )
    if not openwebui_base_url and preferred_openwebui:
        # Preserve a remote/public URL even when the local health probe cannot reach it.
        try:
            openwebui_base_url = _valid_http_base_url(preferred_openwebui, "Open WebUI base URL")
        except RuntimeError:
            openwebui_base_url = ""

    explicit_model = (
        str(options.get("physnemo_agent_model") or "").strip()
        or str(os.environ.get("PHYSNEMO_AGENT_MODEL") or "").strip()
    )
    saved_model = str(existing.get("agent_model") or "").strip()
    detected_model = str(detected.get("agent_model") or "").strip()
    native_model_hint = native_access.get("model_hint") if isinstance(native_access.get("model_hint"), dict) else {}
    native_model = str(native_model_hint.get("model") or "").strip()
    native_model_candidates = [
        str(item).strip()
        for item in (native_model_hint.get("candidates") or [])
        if str(item).strip()
    ]

    direct_base_url = (
        str(options.get("physnemo_agent_base_url") or "").strip()
        or str(os.environ.get("PHYSNEMO_AGENT_BASE_URL") or "").strip()
        or (
            str(existing.get("agent_base_url") or "").strip()
            if str(existing.get("agent_transport") or "direct-provider") == "direct-provider"
            else ""
        )
        or str(detected.get("agent_base_url") or "").strip()
    )
    direct_api_key = (
        explicit_agent_key
        or str(os.environ.get("PHYSNEMO_AGENT_API_KEY") or "").strip()
        or (
            str(existing.get("agent_api_key") or "").strip()
            if str(existing.get("agent_transport") or "direct-provider") == "direct-provider"
            else ""
        )
        or str(detected.get("agent_api_key") or "").strip()
    )
    direct_model = explicit_model or saved_model or detected_model or native_model

    configured = False
    transport = "unconfigured"
    source = "none"
    base_url = ""
    model = ""
    api_key = ""
    configuration_error = ""
    openwebui_models: List[str] = []
    model_attempts: List[Dict[str, Any]] = []

    if direct_base_url and direct_model and direct_api_key and not _looks_like_placeholder_api_key(direct_api_key):
        base_url = _valid_http_base_url(direct_base_url, "PhysicsNeMo agent base URL")
        model = direct_model
        api_key = direct_api_key
        configured = True
        transport = "direct-provider"
        source = (
            "explicit-provider"
            if options.get("physnemo_agent_base_url") or options.get("physnemo_agent_api_key_file")
            else "saved-provider"
            if existing.get("agent_base_url")
            else "einfra-runtime-provider"
        )
    elif openwebui_base_url and openwebui_api_key:
        openwebui_models, model_attempts = _openwebui_model_catalog(
            openwebui_base_url, openwebui_api_key
        )
        model_hint = explicit_model or saved_model or detected_model or native_model
        if model_hint and (not openwebui_models or model_hint in openwebui_models):
            model = model_hint
        elif not explicit_model:
            model = next(
                (candidate for candidate in native_model_candidates if candidate in openwebui_models),
                "",
            )
        if not model and len(openwebui_models) == 1:
            model = openwebui_models[0]
        if model:
            base_url = _openwebui_agent_base_url(openwebui_base_url)
            api_key = openwebui_api_key
            configured = True
            transport = "openwebui-chat-api"
            source = "openwebui-api-key"
        else:
            configuration_error = (
                "Open WebUI is reachable and its API key was supplied, but no unique agent model could be "
                "selected. Rerun with -PhysNeMoAgentModel. Accessible models: "
                + (", ".join(openwebui_models[:20]) if openwebui_models else "none returned")
            )
    else:
        missing: List[str] = []
        if not (direct_base_url and direct_api_key):
            missing.append("direct provider credentials")
        if not openwebui_api_key:
            missing.append("Open WebUI user API key")
        if not (explicit_model or saved_model or detected_model or native_model):
            missing.append("agent model")
        configuration_error = (
            "PhysicsNeMo and the artifact bridge were installed, but the internal NeMo Agent Toolkit LLM is "
            "not configured (missing " + ", ".join(missing or ["usable LLM settings"]) + "). "
            "Create an Open WebUI user API key and rerun with -PhysNeMoOpenWebUIUrl, "
            "-PhysNeMoOpenWebUIApiKeyFile and -PhysNeMoAgentModel, or provide a direct OpenAI-compatible "
            "provider with -PhysNeMoAgentBaseUrl, -PhysNeMoAgentApiKeyFile and -PhysNeMoAgentModel."
        )

    if not configured and not configuration_error:
        configuration_error = "PhysicsNeMo agent LLM configuration is incomplete"

    bridge_secret = str(existing.get("bridge_secret") or secrets.token_urlsafe(48))
    value = {
        "schema": 2,
        "configured": configured,
        "configuration_error": configuration_error,
        "agent_transport": transport,
        "credential_source": source,
        "agent_base_url": base_url,
        "agent_model": model,
        "agent_api_key": api_key,
        "openwebui_base_url": openwebui_base_url,
        "openwebui_api_key": openwebui_api_key,
        "bridge_secret": bridge_secret,
        "detected_runtime": str(detected.get("path") or ""),
        "openwebui_database": str(native_database.get("path") or ""),
        "managed_openwebui_api_key_id": str(native_access.get("api_key_id") or ""),
        "updated_at": now_iso(),
    }
    atomic_write_json(PHYSNEMO_AGENT_SECRET_FILE, value, private=True)
    detection_report = {
        "checked_at": now_iso(),
        "configured": configured,
        "credential_source": source,
        "agent_transport": transport,
        "agent_base_url": base_url,
        "agent_model": model,
        "configuration_error": configuration_error,
        "runtime_attempts": detected.get("attempts") or [],
        "openwebui_probe_attempts": openwebui_probe_attempts,
        "openwebui_base_url": openwebui_base_url,
        "openwebui_api_key_present": bool(openwebui_api_key),
        "openwebui_model_ids": openwebui_models,
        "openwebui_model_attempts": model_attempts,
        "native_openwebui": {
            "database_discovery": native_database,
            "managed_access": _safe_native_openwebui_summary(native_access),
            "model_candidates": native_model_candidates,
        },
        "direct_provider": {
            "base_url": direct_base_url,
            "model": direct_model,
            "api_key_present": bool(direct_api_key),
            "api_key_placeholder": _looks_like_placeholder_api_key(direct_api_key),
        },
    }
    atomic_write_json(PHYSNEMO_AGENT_DETECTION_REPORT, detection_report, private=True)
    return value



def _wsl_windows_host_ip(distro: str) -> str:
    component = physnemo_component()
    script = r'''set -Eeuo pipefail
value="$(ip route show default 2>/dev/null | awk 'NR==1 {print $3}')"
if [[ -z "$value" ]]; then
  value="$(awk '/^nameserver[[:space:]]+/ {print $2; exit}' /etc/resolv.conf 2>/dev/null || true)"
fi
printf '%s\n' "${value:-127.0.0.1}"
'''
    try:
        result = component.wsl_run(distro, script, check=True, timeout=30, stage="resolve-windows-host-ip")
        value = (result.stdout or "").strip().splitlines()[-1]
        if re.fullmatch(r"[0-9A-Fa-f:.]+", value):
            return value
    except Exception:
        pass
    return "127.0.0.1"


def _url_for_wsl(value: str, windows_host_ip: str) -> str:
    """Translate a Windows-loopback HTTP(S) endpoint into a WSL-reachable URL."""
    value = _valid_http_base_url(value, "PhysicsNeMo agent base URL")
    parsed = urllib.parse.urlparse(value)
    if (parsed.hostname or "").lower() not in {"127.0.0.1", "localhost", "::1"}:
        return value
    host = windows_host_ip
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    netloc = host + (f":{parsed.port}" if parsed.port else "")
    return urllib.parse.urlunparse(parsed._replace(netloc=netloc))


def _physnemo_agent_secret_safe_summary(secret: Dict[str, Any]) -> Dict[str, Any]:
    api_key = str(secret.get("agent_api_key") or "")
    return {
        "configured": bool(secret.get("configured")),
        "transport": str(secret.get("agent_transport") or "unconfigured"),
        "credential_source": str(secret.get("credential_source") or "none"),
        "base_url": secret.get("agent_base_url") or None,
        "model": secret.get("agent_model") or None,
        "configuration_error": secret.get("configuration_error") or None,
        "api_key_sha256_prefix": hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:12] if api_key else None,
        "detected_runtime": secret.get("detected_runtime") or None,
        "detection_report": str(PHYSNEMO_AGENT_DETECTION_REPORT),
        "openwebui_file_bridge": bool(secret.get("openwebui_base_url") and secret.get("openwebui_api_key")),
        "openwebui_base_url": secret.get("openwebui_base_url") or None,
    }

def _write_integrated_physnemo_assets(runtime: Dict[str, Any]) -> None:
    component = physnemo_component()
    distro = str(runtime["distro"])
    root = str(runtime["linux_install_dir"])
    plugin = f"{root}/plugin"
    secret = read_json(PHYSNEMO_AGENT_SECRET_FILE)
    agent_configured = bool(secret.get("configured"))
    bridge_enabled = bool(secret.get("openwebui_base_url") and secret.get("openwebui_api_key"))
    bridge_url = str(runtime.get("openwebui_bridge_url") or "") if bridge_enabled else ""
    bridge_secret = str(secret.get("bridge_secret") or "") if bridge_enabled else ""
    # NAT validates referenced environment variables while parsing YAML.  In
    # unconfigured mode the LLM section is omitted, nevertheless use harmless
    # non-secret placeholders in runtime.env so the managed service remains
    # deterministic and can be reconfigured later with -Resume.
    effective_agent_base_url = str(
        runtime.get("agent_base_url_for_wsl")
        or secret.get("agent_base_url")
        or "http://127.0.0.1:9/api"
    )
    effective_agent_model = str(secret.get("agent_model") or "engineering-mcp-unconfigured")
    agent_transport = str(secret.get("agent_transport") or "unconfigured")
    effective_agent_key = (
        bridge_secret
        if agent_transport == "openwebui-chat-api" and bridge_enabled and bridge_secret
        else str(secret.get("agent_api_key") or "EMPTY")
    )
    private_env = component.render_agent_env(
        {
            "PHYSNEMO_AGENT_API_KEY": effective_agent_key,
            "PHYSNEMO_AGENT_BASE_URL": effective_agent_base_url,
            "PHYSNEMO_AGENT_MODEL": effective_agent_model,
            "PHYSNEMO_OPENWEBUI_BRIDGE_URL": bridge_url,
            "PHYSNEMO_OPENWEBUI_BRIDGE_SECRET": bridge_secret,
        }
    )
    for key, value in {
        "PHYSNEMO_AGENT_TRANSPORT": agent_transport,
        "PHYSNEMO_GATEWAY_PORT": str(urllib.parse.urlparse(bridge_url).port or DEFAULT_MCPO_PORT),
        "PHYSNEMO_GATEWAY_ROUTE": PHYSNEMO_ROUTE,
    }.items():
        encoded = base64.b64encode(str(value).encode("utf-8")).decode("ascii")
        private_env += f"{key}_B64={encoded}\n"
    files = {
        f"{plugin}/pyproject.toml": (component.PLUGIN_PYPROJECT, "644"),
        f"{plugin}/src/engineering_physnemo_nat/__init__.py": (component.PLUGIN_INIT, "644"),
        f"{plugin}/src/engineering_physnemo_nat/register.py": (component.PLUGIN_REGISTER, "644"),
        f"{root}/config/physnemo.yml": (
            component.render_nat_config(
                f"{root}/physicsnemo-source",
                str(runtime["source_ref"]),
                str(runtime["artifact_root"]),
                str(runtime["artifact_base_url"]),
                str(runtime["artifact_secret"]),
                agent_model=effective_agent_model,
                agent_base_url=effective_agent_base_url,
                openwebui_bridge_url=bridge_url,
                openwebui_bridge_secret=bridge_secret,
                agent_configured=agent_configured,
                agent_configuration_error=str(
                    secret.get("configuration_error")
                    or "PhysicsNeMo agent LLM is not configured"
                ),
            ),
            "600",
        ),
        f"{root}/config/runtime.env": (private_env, "600"),
        f"{root}/bin/run-nat.sh": (
            _render_integrated_physnemo_run_script(root, int(runtime["nat_port"])),
            "700",
        ),
        f"{root}/bin/stop-nat.sh": (_render_integrated_physnemo_stop_script(root), "700"),
        f"{root}/.engineering-mcp-physnemo-managed": (
            f"managed_by=engineering-mcp-physnemo\\nversion={BOOTSTRAPPER_VERSION}\\n",
            "600",
        ),
    }
    for path, (content, mode) in files.items():
        component.wsl_write_file(distro, path, content, mode)


def _physnemo_runtime_defaults(options: Dict[str, Any]) -> Dict[str, Any]:
    component = physnemo_component()
    agent_secret = _resolve_physnemo_agent_secret(options)
    previous = load_state().get("physnemo_runtime", {})
    legacy = _legacy_physnemo_state()
    distro = component.choose_wsl_distro(
        str(options.get("physnemo_distro") or previous.get("distro") or legacy.get("distro") or "")
    )
    install_dir = component.resolve_linux_install_dir(
        distro,
        str(
            options.get("physnemo_install_dir")
            or previous.get("linux_install_dir")
            or legacy.get("linux_install_dir")
            or ""
        ),
    )
    nat_port = int(
        options.get("physnemo_nat_port")
        or previous.get("nat_port")
        or legacy.get("nat_port")
        or DEFAULT_PHYSNEMO_NAT_PORT
    )
    if not 1 <= nat_port <= 65535:
        raise RuntimeError("PhysicsNeMo NAT port must be between 1 and 65535")
    nat_version = component.validate_version(
        str(options.get("physnemo_nat_version") or DEFAULT_PHYSNEMO_NAT_VERSION),
        "NeMo Agent Toolkit version",
    )
    physics_version = component.validate_version(
        str(options.get("physicsnemo_version") or DEFAULT_PHYSNEMO_VERSION),
        "PhysicsNeMo version",
    )
    source_ref = component.validate_source_ref(
        str(options.get("physicsnemo_source_ref") or DEFAULT_PHYSNEMO_SOURCE_REF)
    )
    profile = str(options.get("physicsnemo_profile") or "base").lower()
    component.physicsnemo_package_spec(physics_version, profile)
    windows_host_ip = _wsl_windows_host_ip(distro)
    shared_port = int(options.get("port") or DEFAULT_MCPO_PORT)
    bridge_enabled = bool(agent_secret.get("openwebui_base_url") and agent_secret.get("openwebui_api_key"))
    bridge_origin = (
        f"http://{windows_host_ip}:{shared_port}/{PHYSNEMO_ROUTE}"
        if bridge_enabled else ""
    )
    if agent_secret.get("configured") and agent_secret.get("agent_base_url"):
        if str(agent_secret.get("agent_transport") or "") == "openwebui-chat-api" and bridge_origin:
            # Open WebUI Desktop deliberately listens only on Windows loopback.  WSL cannot
            # reach that listener through the Windows host IP in NAT mode, so route the
            # OpenAI-compatible call through the authenticated Engineering MCP gateway.
            effective_agent_base_url = bridge_origin + "/openwebui-api"
        else:
            effective_agent_base_url = _url_for_wsl(
                str(agent_secret.get("agent_base_url")), windows_host_ip
            )
    else:
        effective_agent_base_url = "http://127.0.0.1:9/api"
    return {
        "configured": False,
        "enabled": True,
        "distro": distro,
        "linux_install_dir": install_dir,
        "nat_port": nat_port,
        "mcp_url": f"http://127.0.0.1:{nat_port}/mcp",
        "health_url": f"http://127.0.0.1:{nat_port}/health",
        "nat_version": nat_version,
        "physicsnemo_version": physics_version,
        "physicsnemo_profile": profile,
        "source_ref": source_ref,
        "install_prerequisites": bool(options.get("physnemo_install_prerequisites", True)),
        "artifact_root": f"{install_dir}/artifacts",
        "artifact_secret": str(previous.get("artifact_secret") or secrets.token_urlsafe(48)),
        "artifact_base_url": (
            str(options.get("physnemo_artifact_base_url") or "").rstrip("/")
            or f"http://127.0.0.1:{shared_port}/{PHYSNEMO_ROUTE}/artifacts"
        ),
        "agent": {
            **_physnemo_agent_secret_safe_summary(agent_secret),
            "wsl_base_url": effective_agent_base_url,
        },
        "agent_base_url_for_wsl": effective_agent_base_url,
        "agent_configured": bool(agent_secret.get("configured")),
        "agent_configuration_error": str(agent_secret.get("configuration_error") or ""),
        "agent_detection_report": str(PHYSNEMO_AGENT_DETECTION_REPORT),
        "openwebui_bridge_enabled": bridge_enabled,
        "openwebui_bridge_url": bridge_origin,
        "agent_via_windows_bridge": bool(
            bridge_origin and str(agent_secret.get("agent_transport") or "") == "openwebui-chat-api"
        ),
    }


def stop_legacy_physnemo_service() -> Dict[str, Any]:
    """Disable the former standalone task without deleting its reusable WSL runtime."""
    component = physnemo_component()
    report: Dict[str, Any] = {"present": False, "stopped": False, "task_removed": False}
    try:
        legacy_state = component.read_json(component.STATE_FILE)
        report["present"] = bool(legacy_state) or bool(component.task_exists())
        if legacy_state or component.task_exists():
            component.stop_background(legacy_state or None)
            report["stopped"] = True
            component.delete_task()
            report["task_removed"] = True
    except Exception as exc:
        report["error"] = str(exc)
    return report


def _read_text_tail(path: Path, maximum_chars: int = 24000) -> str:
    try:
        value = path.read_text(encoding="utf-8", errors="replace")
        return value[-maximum_chars:]
    except OSError:
        return ""


def _physnemo_runtime_report_for_log(report: Dict[str, Any]) -> Dict[str, Any]:
    """Keep the signing key in private runtime state, not the shareable health JSON."""
    safe = {key: value for key, value in report.items() if key != "artifact_secret"}
    if "artifact_secret" in report:
        safe["artifact_secret_present"] = bool(report["artifact_secret"])
    return safe


def prepare_physnemo_runtime(options: Dict[str, Any], *, force: bool = False) -> Dict[str, Any]:
    """Install/repair NAT + PhysicsNeMo and return one shared-gateway route.

    Every WSL operation records a named stage. A partial venv or dedicated WSL
    root left by an older interrupted Engineering MCP run is validated and can
    be adopted only through the strict managed-layout contract.
    """
    previous_runtime_report = read_json(PHYSNEMO_RUNTIME_REPORT)
    report: Dict[str, Any] = {
        "checked_at": now_iso(),
        "configured": False,
        "enabled": bool(options.get("physnemo", True)),
        "stage": "initializing",
        "wsl_command_log": str(PHYSNEMO_WSL_INSTALL_LOG),
        "failed_script_directory": str(PHYSNEMO_FAILED_SCRIPT_DIR),
    }

    def stage(name: str, **details: Any) -> None:
        report["stage"] = name
        report["stage_updated_at"] = now_iso()
        if details:
            report.setdefault("stage_details", {}).update(details)
        atomic_write_json(PHYSNEMO_RUNTIME_REPORT, _physnemo_runtime_report_for_log(report), private=True)

    if not report["enabled"]:
        report["skipped"] = True
        report["reason"] = "PhysicsNeMo integration disabled by option"
        atomic_write_json(PHYSNEMO_RUNTIME_REPORT, _physnemo_runtime_report_for_log(report), private=True)
        return report
    if not sys.platform.startswith("win"):
        report["skipped"] = True
        report["reason"] = "Integrated PhysicsNeMo installation requires Windows with WSL2"
        atomic_write_json(PHYSNEMO_RUNTIME_REPORT, _physnemo_runtime_report_for_log(report), private=True)
        return report

    component = physnemo_component()
    runtime = _physnemo_runtime_defaults(options)
    report.update(runtime)
    report["agent"] = dict(runtime.get("agent") or {})
    report["embedded_component_version"] = str(component.BOOTSTRAPPER_VERSION)
    report["embedded_component_sha256"] = PHYSNEMO_COMPONENT_SOURCE_SHA256
    report["nat_function_contract"] = str(component.NAT_FUNCTION_CONTRACT)
    report["nat_runtime_compatibility_packages"] = list(component.NAT_RUNTIME_COMPATIBILITY_PACKAGES)
    if runtime.get("agent_configured"):
        print(
            "[+] PhysicsNeMo general NAT agent LLM is configured: "
            f"transport={runtime.get('agent', {}).get('transport') or 'unknown'}, "
            f"model={runtime.get('agent', {}).get('model') or 'unknown'}"
        )
    else:
        print("[!] PhysicsNeMo will be installed in LLM-unconfigured mode.")
        print(
            "    The MCP route, environment/status tools and artifact/file bridge remain available; "
            "physnemo__solve will return configuration_required until an LLM is configured."
        )
        print(f"    Cause: {runtime.get('agent_configuration_error') or 'missing usable LLM settings'}")
        print(f"    Detection report: {PHYSNEMO_AGENT_DETECTION_REPORT}")
    stage("stop-legacy-physnemo-service")
    report["legacy_migration"] = stop_legacy_physnemo_service()

    try:
        stage("validate-nat-port", nat_port=int(runtime["nat_port"]))
        if tcp_open("127.0.0.1", int(runtime["nat_port"]), timeout=0.5):
            raise RuntimeError(
                f"PhysicsNeMo NAT port {runtime['nat_port']} is already in use after stopping "
                "the managed Engineering MCP service. Select -PhysNeMoNatPort explicitly or "
                "stop the conflicting process."
            )

        stage("wsl-prerequisites")
        prerequisites = component.ensure_wsl_prerequisites(
            runtime["distro"], bool(runtime["install_prerequisites"])
        )
        report["prerequisites"] = prerequisites

        prior_root = str(previous_runtime_report.get("linux_install_dir") or "").rstrip("/")
        prior_distro = str(previous_runtime_report.get("distro") or "").casefold()
        current_root = str(runtime["linux_install_dir"]).rstrip("/")
        current_distro = str(runtime["distro"]).casefold()
        prior_claim_matches = bool(
            prior_root
            and prior_root == current_root
            and prior_distro == current_distro
            and (
                previous_runtime_report.get("embedded_component_version")
                or previous_runtime_report.get("stage")
                or previous_runtime_report.get("failed_stage")
            )
        )
        report["previous_runtime_claim_matches"] = prior_claim_matches
        stage(
            "validate-managed-install-root",
            partial_adoption_authorized=prior_claim_matches or bool(force),
        )
        managed_root = component.assert_managed_wsl_root(
            runtime["distro"],
            runtime["linux_install_dir"],
            allow_partial_adoption=prior_claim_matches or bool(force),
        )
        report["managed_root"] = managed_root
        if managed_root.get("adopted"):
            print(
                "[+] Safely adopted a recognizable partial PhysicsNeMo WSL directory: "
                f"{runtime['linux_install_dir']}"
            )
            if managed_root.get("entries"):
                print("    Existing managed entries: " + ", ".join(managed_root["entries"]))
            if managed_root.get("evidence"):
                print("    Ownership evidence: " + ", ".join(managed_root["evidence"]))

        stage("write-managed-plugin-and-runtime-assets")
        _write_integrated_physnemo_assets(runtime)

        stage("physicsnemo-source-checkout", source_ref=runtime["source_ref"])
        source = component.ensure_physicsnemo_source(
            runtime["distro"],
            f"{runtime['linux_install_dir']}/physicsnemo-source",
            runtime["source_ref"],
            bool(force),
        )
        report["source"] = source

        nat_venv = f"{runtime['linux_install_dir']}/.venv-nat"
        python_command = str(prerequisites.get("python_command") or "")
        stage("create-or-repair-nat-venv", venv=nat_venv, base_python=python_command)
        component.ensure_python_venv(runtime["distro"], nat_venv, python_command)
        nat_python = f"{nat_venv}/bin/python"

        stage("install-nat-and-physicsnemo-packages")
        component.pip_install_wsl(
            runtime["distro"],
            nat_python,
            [
                f"nvidia-nat[langchain]=={runtime['nat_version']}",
                f"nvidia-nat-mcp=={runtime['nat_version']}",
                *component.NAT_RUNTIME_COMPATIBILITY_PACKAGES,
                component.physicsnemo_package_spec(
                    runtime["physicsnemo_version"], runtime["physicsnemo_profile"]
                ),
            ],
            f"{runtime['linux_install_dir']}/logs/pip-nat-physicsnemo.log",
            timeout=7200,
        )

        stage("install-engineering-physnemo-nat-plugin", nat_function_contract=PHYSNEMO_NAT_FUNCTION_CONTRACT)
        component.pip_install_wsl(
            runtime["distro"],
            nat_python,
            ["--no-deps", "-e", f"{runtime['linux_install_dir']}/plugin"],
            f"{runtime['linux_install_dir']}/logs/pip-plugin.log",
            timeout=1200,
        )

        stage("verify-installed-packages-and-plugin")
        verify_script = f'''set -Eeuo pipefail
{component.shell_path(nat_python)} - <<'PYVERIFY'
import importlib.metadata as m, json
import engineering_physnemo_nat.register
import physicsnemo
import torch
from physicsnemo.models.mlp import FullyConnected
entry_points = m.entry_points()
if hasattr(entry_points, "select"):
    plugin_names = sorted(ep.name for ep in entry_points.select(group="nat.plugins"))
else:
    plugin_names = sorted(ep.name for ep in entry_points.get("nat.plugins", []))
if "engineering_physnemo_nat" not in plugin_names:
    raise RuntimeError(f"Engineering PhysicsNeMo plugin is not registered in nat.plugins: {{plugin_names}}")
from engineering_physnemo_nat import register as phys_register
for required_name in (
    "PhysNeMoInternalConfig", "PhysNeMoSolveConfig", "PhysNeMoPublicConfig",
    "SolveInput", "JobInput", "GetArtifactInput",
):
    if not hasattr(phys_register, required_name):
        raise RuntimeError(f"PhysicsNeMo plugin is missing {{required_name}}")
for forbidden_name in ("PhysNeMoToolsConfig",):
    if hasattr(phys_register, forbidden_name):
        raise RuntimeError(f"PhysicsNeMo plugin unexpectedly contains obsolete {{forbidden_name}}")
old_threads = torch.get_num_threads()
try:
    torch.set_num_threads(min(old_threads, 2))
    torch.manual_seed(17)
    model = FullyConnected(in_features=4, layer_size=8, out_features=2, num_layers=2).cpu().eval()
    sample = torch.tensor([[0.0, 0.25, 0.5, 1.0], [1.0, 0.5, 0.25, 0.0]], dtype=torch.float32)
    with torch.no_grad():
        output = model(sample)
    if tuple(output.shape) != (2, 2) or not bool(torch.isfinite(output).all().item()):
        raise RuntimeError(f"Unexpected PhysicsNeMo smoke-test output: {{tuple(output.shape)}}")
    print(json.dumps({{
      "nvidia_nat": m.version("nvidia-nat"),
      "nvidia_nat_mcp": m.version("nvidia-nat-mcp"),
      "nvidia_physicsnemo": m.version("nvidia-physicsnemo"),
      "langchain_core": m.version("langchain-core"),
      "nvidia_nat_langchain": m.version("nvidia-nat-langchain"),
      "plugin": m.version("engineering-physnemo-nat"),
      "plugin_entry_point": "nat.plugins:engineering_physnemo_nat",
      "physicsnemo_import": getattr(physicsnemo, "__version__", None),
      "torch": torch.__version__,
      "smoke_output_shape": list(output.shape),
      "smoke_finite": True,
    }}))
finally:
    torch.set_num_threads(old_threads)
PYVERIFY
{component.shell_path(nat_python)} -m pip check
NAT_TELEMETRY_ENABLED=false {component.shell_path(nat_venv + '/bin/nat')} --version
NAT_TELEMETRY_ENABLED=false {component.shell_path(nat_venv + '/bin/nat')} mcp serve --help >/dev/null
'''
        verification = component.wsl_run(
            runtime["distro"],
            verify_script,
            check=True,
            timeout=900,
            stage="verify-installed-packages-and-plugin",
        )
        package_line = next(
            (line for line in (verification.stdout or "").splitlines() if line.strip().startswith("{")),
            "{}",
        )
        packages = json.loads(package_line)
        if not packages:
            raise RuntimeError("PhysicsNeMo package verification returned no metadata JSON")
        report["packages"] = packages

        stage("nat-mcp-configuration-preflight")
        preflight_log = f"{runtime['linux_install_dir']}/logs/nat-install-preflight.log"
        preflight_json = f"{runtime['linux_install_dir']}/run/nat-install-preflight-tools.json"
        expected_json = json.dumps(list(PHYSNEMO_EXPECTED_TOOLS))
        tool_filter_args = _physnemo_nat_tool_filter_args()
        preflight_script = f'''set -Eeuo pipefail
root={component.shell_path(runtime['linux_install_dir'])}
nat={component.shell_path(nat_venv + '/bin/nat')}
python={component.shell_path(nat_python)}
config="$root/config/physnemo.yml"
log={component.shell_path(preflight_log)}
tools={component.shell_path(preflight_json)}
port={int(runtime['nat_port'])}
mkdir -p "$root/logs" "$root/run"
rm -f "$tools"
env_file="$root/config/runtime.env"
[[ -r "$env_file" ]] || {{ echo "Missing $env_file" >&2; exit 78; }}
# shellcheck disable=SC1090
source "$env_file"
for key in PHYSNEMO_AGENT_API_KEY PHYSNEMO_AGENT_BASE_URL PHYSNEMO_AGENT_MODEL PHYSNEMO_OPENWEBUI_BRIDGE_URL PHYSNEMO_OPENWEBUI_BRIDGE_SECRET PHYSNEMO_AGENT_TRANSPORT PHYSNEMO_GATEWAY_PORT PHYSNEMO_GATEWAY_ROUTE; do
  b64_key="${{key}}_B64"
  printf -v "$key" '%s' "$(printf '%s' "${{!b64_key:-}}" | base64 -d)"
  export "$key"
done
if [[ "$PHYSNEMO_AGENT_TRANSPORT" == "openwebui-chat-api" ]]; then
  windows_host="$(ip route show default 2>/dev/null | awk 'NR==1 {{print $3}}')"
  if [[ -z "$windows_host" ]]; then
    windows_host="$(awk '/^nameserver[[:space:]]+/ {{print $2; exit}}' /etc/resolv.conf 2>/dev/null || true)"
  fi
  [[ -n "$windows_host" ]] || {{ echo "Unable to resolve the Windows host address for the Open WebUI agent bridge" >&2; exit 78; }}
  if [[ "$windows_host" == *:* && "${{windows_host:0:1}}" != "[" ]]; then windows_host="[$windows_host]"; fi
  bridge_origin="http://${{windows_host}}:${{PHYSNEMO_GATEWAY_PORT}}/${{PHYSNEMO_GATEWAY_ROUTE}}"
  PHYSNEMO_AGENT_BASE_URL="$bridge_origin/openwebui-api"
  PHYSNEMO_OPENWEBUI_BRIDGE_URL="$bridge_origin"
  export PHYSNEMO_AGENT_BASE_URL PHYSNEMO_OPENWEBUI_BRIDGE_URL
fi
export PYTHONUTF8=1 PYTHONIOENCODING=utf-8 PYTHONUNBUFFERED=1 NAT_TELEMETRY_ENABLED=false
export PHYSNEMO_SOURCE_ROOT="$root/physicsnemo-source"
"$nat" mcp serve --config_file "$config" --host 127.0.0.1 --port "$port" \
  --transport streamable-http --name "Engineering MCP - PhysicsNeMo" {tool_filter_args} \
  >"$log" 2>&1 &
pid=$!
cleanup() {{ kill "$pid" 2>/dev/null || true; wait "$pid" 2>/dev/null || true; }}
trap cleanup EXIT INT TERM
ready=0
for _ in $(seq 1 180); do
  if ! kill -0 "$pid" 2>/dev/null; then
    echo "NAT MCP exited during installation preflight" >&2
    tail -n 160 "$log" >&2 || true
    exit 1
  fi
  if curl -fsS --connect-timeout 2 --max-time 8 "http://127.0.0.1:$port/debug/tools/list" -o "$tools"; then
    ready=1
    break
  fi
  sleep 1
done
if [[ "$ready" != 1 ]]; then
  echo "NAT MCP did not expose /debug/tools/list within the timeout" >&2
  tail -n 160 "$log" >&2 || true
  exit 1
fi
"$python" - "$tools" <<'PYCHECK'
import json, pathlib, sys
expected = set({expected_json})
payload = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
tools = payload.get("tools", []) if isinstance(payload, dict) else []
names = {{str(item.get("name")) for item in tools if isinstance(item, dict)}}
missing = sorted(expected - names)
if missing:
    raise SystemExit("Missing PhysicsNeMo MCP tools: " + ", ".join(missing))
print(json.dumps({{"tool_count": len(names), "tools": sorted(names), "server_name": payload.get("server_name")}}))
PYCHECK
'''
        preflight = component.wsl_run(
            runtime["distro"],
            preflight_script,
            check=True,
            timeout=360,
            stage="nat-mcp-configuration-preflight",
        )
        preflight_line = next(
            (line for line in reversed((preflight.stdout or "").splitlines()) if line.strip().startswith("{")),
            "{}",
        )
        nat_preflight = json.loads(preflight_line)
        if not nat_preflight or not set(PHYSNEMO_EXPECTED_TOOLS).issubset(set(nat_preflight.get("tools", []))):
            raise RuntimeError("NAT MCP configuration preflight did not confirm all PhysicsNeMo tools")

        report.update(
            {
                "configured": True,
                "healthy": False,
                "stage": "configured",
                "nat_preflight": nat_preflight,
                "nat_preflight_log": preflight_log,
                "nat_log": f"{runtime['linux_install_dir']}/logs/nat-mcp.log",
                "managed_by": "engineering-mcp-unified",
            }
        )
        try:
            legacy_home = Path(component.APP_HOME)
            if legacy_home.exists() and legacy_home.resolve() != APP_HOME.resolve():
                shutil.rmtree(legacy_home, ignore_errors=True)
        except Exception:
            pass
    except Exception as exc:
        report["error"] = str(exc)
        report["error_type"] = type(exc).__name__
        report["failed_stage"] = report.get("stage")
        report["traceback"] = traceback.format_exc()
        report["wsl_command_log_tail"] = _read_text_tail(PHYSNEMO_WSL_INSTALL_LOG)
        try:
            report["failed_scripts"] = [
                str(path)
                for path in sorted(
                    PHYSNEMO_FAILED_SCRIPT_DIR.glob("*.sh"),
                    key=lambda item: item.stat().st_mtime,
                )[-8:]
            ]
        except OSError:
            report["failed_scripts"] = []
    atomic_write_json(PHYSNEMO_RUNTIME_REPORT, _physnemo_runtime_report_for_log(report), private=True)
    return report


def _physnemo_runtime_from_state(state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    value = (state or load_state()).get("physnemo_runtime", {})
    return value if isinstance(value, dict) else {}


def stop_physnemo_nat(state: Optional[Dict[str, Any]] = None) -> None:
    runtime = _physnemo_runtime_from_state(state)
    if runtime.get("distro") and runtime.get("linux_install_dir"):
        component = physnemo_component()
        root = str(runtime["linux_install_dir"])
        script = f'''set -u
stop={component.shell_path(root + '/bin/stop-nat.sh')}
[[ -x "$stop" ]] && "$stop" || true
'''
        try:
            component.wsl_run(str(runtime["distro"]), script, check=False, timeout=60)
        except Exception:
            pass
    pid = read_pid(PHYSNEMO_WSL_PROXY_PID_FILE)
    if pid:
        terminate_pid_tree(pid, force=True)
    PHYSNEMO_WSL_PROXY_PID_FILE.unlink(missing_ok=True)


def start_physnemo_nat_process(
    state: Dict[str, Any],
) -> Tuple[Optional[subprocess.Popen], Optional[Any]]:
    runtime = _physnemo_runtime_from_state(state)
    if PHYSNEMO_ROUTE not in configured_routes() or not runtime.get("configured"):
        return None, None
    stop_physnemo_nat(state)
    component = physnemo_component()
    command = [
        *component._wsl_exec_prefix(str(runtime["distro"])),
        "/bin/bash",
        "--noprofile",
        "--norc",
        f"{runtime['linux_install_dir']}/bin/run-nat.sh",
    ]
    PHYSNEMO_WSL_PROXY_LOG.parent.mkdir(parents=True, exist_ok=True)
    handle = PHYSNEMO_WSL_PROXY_LOG.open("a", encoding="utf-8", errors="replace")
    handle.write(f"\n=== {now_iso()} ===\nCOMMAND: {format_command(command)}\n")
    handle.flush()
    process = subprocess.Popen(
        command,
        stdout=handle,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        cwd=str(APP_HOME),
    )
    write_pid(PHYSNEMO_WSL_PROXY_PID_FILE, process.pid)
    return process, handle


def wait_for_physnemo_nat(
    state: Dict[str, Any],
    process: Optional[subprocess.Popen] = None,
    timeout: float = 180.0,
) -> bool:
    runtime = _physnemo_runtime_from_state(state)
    if not runtime.get("configured"):
        return False
    url = str(runtime.get("health_url") or "")
    deadline = time.monotonic() + max(5.0, float(timeout))
    while time.monotonic() < deadline:
        if process is not None and process.poll() is not None:
            return False
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    runtime["healthy"] = True
                    return True
        except (urllib.error.URLError, TimeoutError, OSError):
            pass
        time.sleep(1.0)
    return False


def run_mcp_http_probe(arguments: List[str]) -> int:
    """Internal MCP streamable-HTTP probe, executed with the isolated MCPO Python."""
    import asyncio
    parser = argparse.ArgumentParser(prog="engineering-mcp --mcp-http-probe")
    parser.add_argument("--url", required=True)
    parser.add_argument("--route", default=PHYSNEMO_ROUTE)
    parsed = parser.parse_args(arguments)

    async def perform() -> Dict[str, Any]:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client
        async with streamablehttp_client(url=parsed.url) as connection:
            reader, writer, *_ = connection
            async with ClientSession(reader, writer) as session:
                initialized = await session.initialize()
                listed = await session.list_tools()
                names = sorted(
                    str(getattr(tool, "name", ""))
                    for tool in getattr(listed, "tools", [])
                    if str(getattr(tool, "name", ""))
                )
                server_info = getattr(initialized, "serverInfo", None) or getattr(
                    initialized, "server_info", None
                )
                native_contract = None
                if parsed.route == PHYSNEMO_ROUTE:
                    env_result = await session.call_tool("physnemo__environment_info", {"detail": False})
                    if getattr(env_result, "isError", False):
                        raise RuntimeError("PHYSNEMO_NATIVE_RUNTIME_PROBE_FAILED")
                    env_data = None
                    for block in getattr(env_result, "content", []):
                        text = getattr(block, "text", None)
                        if isinstance(text, str):
                            try:
                                candidate = json.loads(text)
                            except json.JSONDecodeError:
                                continue
                            if isinstance(candidate, dict) and "native_tool_contract" in candidate:
                                env_data = candidate
                                break
                    native_contract = (env_data or {}).get("native_tool_contract")
                    if native_contract != "PHYSNEMO_NATIVE_TOOL_DISPATCH_V5":
                        raise RuntimeError("PHYSNEMO_NATIVE_RUNNING_PLUGIN_STALE")
                return {
                    "success": True,
                    "native_tool_contract": native_contract,
                    "route": parsed.route,
                    "server_name": str(getattr(server_info, "name", "") or ""),
                    "tool_count": len(names),
                    "tool_names": names,
                }

    try:
        print(json.dumps(asyncio.run(perform()), ensure_ascii=True, separators=(",", ":")))
        return 0
    except Exception as exc:
        print(
            json.dumps(
                {
                    "success": False,
                    "route": parsed.route,
                    "error": f"{type(exc).__name__}: {exc}",
                },
                ensure_ascii=True,
                separators=(",", ":"),
            )
        )
        return 1


PHYSNEMO_AGENT_BRIDGE_CHECK_SOURCE = '#!/usr/bin/env python3\n"""Engineering MCP 2.9.18: verify models, JSON, SSE and the installed LangChain.\n\nSends two small model requests, or five with --langchain. Does not submit a\nPhysicsNeMo job or call tools. Credentials and model response text are not printed.\nUse --runtime-env with the WSL <linux_install_dir>/config/runtime.env file,\nor specify --base-url and --model (key from PHYSNEMO_AGENT_API_KEY or a hidden prompt).\n"""\nfrom __future__ import annotations\n\nimport argparse\nimport asyncio\nimport base64\nimport getpass\nimport math\nimport importlib.metadata\nimport ipaddress\nimport json\nimport os\nfrom pathlib import Path\nimport re\nimport shlex\nimport subprocess\nimport sys\nimport urllib.error\nimport urllib.parse\nimport urllib.request\n\nPROBE = "Reply with exactly ENGINEERING_MCP_BRIDGE_OK. Do not call any tools."\nKEYS = {"PHYSNEMO_AGENT_API_KEY", "PHYSNEMO_AGENT_MODEL", "PHYSNEMO_AGENT_BASE_URL",\n        "PHYSNEMO_AGENT_TRANSPORT", "PHYSNEMO_GATEWAY_PORT", "PHYSNEMO_GATEWAY_ROUTE"}\nLIMIT = 32 * 1024 * 1024\nPROTOCOL = "buffered-sse-v1"\n\n\nclass ProbeError(Exception):\n    """A diagnostic message constructed locally, never a provider response."""\n\n\n\ndef read_runtime_env(path: Path) -> dict[str, str]:\n    """Read only the known Base64 variables, never source/execute the file."""\n    values: dict[str, str] = {}\n    for line in path.read_text(encoding="utf-8-sig").splitlines():\n        match = re.fullmatch(r"\\s*(?:export\\s+)?([A-Z0-9_]+)_B64=(.*?)\\s*", line)\n        if not match or match[1] not in KEYS:\n            continue\n        parts = shlex.split(match[2], comments=True)\n        if len(parts) > 1:\n            raise ProbeError("Malformed private runtime.env assignment")\n        encoded = parts[0] if parts else ""\n        values[match[1]] = base64.b64decode(encoded, validate=True).decode("utf-8")\n    return values\n\n\ndef windows_host() -> str:\n    if os.name == "nt":\n        return "127.0.0.1"\n    try:\n        result = subprocess.run(["ip", "route", "show", "default"], capture_output=True,\n                                text=True, check=True, timeout=5)\n        match = re.search(r"\\bvia\\s+(\\S+)", result.stdout)\n        if match:\n            return str(ipaddress.ip_address(match[1]))\n    except (OSError, subprocess.SubprocessError, ValueError):\n        pass\n    try:\n        for line in Path("/etc/resolv.conf").read_text().splitlines():\n            if line.strip().startswith("nameserver "):\n                return str(ipaddress.ip_address(line.split()[1]))\n    except (OSError, ValueError, IndexError):\n        pass\n    raise ProbeError("Cannot resolve the Windows host; provide --base-url explicitly")\n\n\ndef resolve_config(args) -> tuple[str, str, str]:\n    values = {key: os.environ.get(key, "") for key in KEYS}\n    if args.runtime_env:\n        values.update(read_runtime_env(args.runtime_env))\n    base = args.base_url\n    if not base and values.get("PHYSNEMO_AGENT_TRANSPORT") == "openwebui-chat-api":\n        port = int(values.get("PHYSNEMO_GATEWAY_PORT") or "8200")\n        route = values.get("PHYSNEMO_GATEWAY_ROUTE") or "physnemo"\n        if not 1 <= port <= 65535 or not re.fullmatch(r"[A-Za-z0-9_-]+", route):\n            raise ProbeError("Invalid bridge port or route in runtime.env")\n        host = windows_host()\n        host = f"[{host}]" if ":" in host else host\n        base = f"http://{host}:{port}/{route}/openwebui-api"\n    base = (base or values.get("PHYSNEMO_AGENT_BASE_URL") or "").rstrip("/")\n    parsed = urllib.parse.urlsplit(base)\n    if (parsed.scheme not in {"http", "https"} or not parsed.hostname\n            or parsed.username or parsed.password or parsed.query or parsed.fragment\n            or not parsed.path.endswith("/openwebui-api")):\n        raise ProbeError("Use the bridge base URL ending in /physnemo/openwebui-api (or your configured route)")\n    model = args.model or values.get("PHYSNEMO_AGENT_MODEL")\n    if not model:\n        raise ProbeError("Model is missing; provide --model or --runtime-env")\n    key = values.get("PHYSNEMO_AGENT_API_KEY")\n    if not key and not args.non_interactive:\n        key = getpass.getpass("Bridge secret (hidden): ")\n    if not key or "\\r" in key or "\\n" in key:\n        raise ProbeError("Missing or invalid bridge credential")\n    return base, model, key\n\n\ndef parse_sse(content: bytes) -> list[dict]:\n    text = content.decode("utf-8-sig").replace("\\r\\n", "\\n").replace("\\r", "\\n")\n    frames: list[dict] = []\n    done = False\n    for block in text.split("\\n\\n"):\n        fields = []\n        for line in block.split("\\n"):\n            if line.startswith("data:"):\n                fields.append(line[5:].removeprefix(" "))\n        if not fields:\n            continue\n        data = "\\n".join(fields)\n        if data.strip() == "[DONE]":\n            done = True\n            break\n        payload = json.loads(data)\n        if not isinstance(payload, dict) or payload.get("error"):\n            raise ProbeError("SSE contains an error or malformed event")\n        if payload.get("object") != "chat.completion.chunk":\n            raise ProbeError("SSE event is not a chat.completion.chunk")\n        if not isinstance(payload.get("choices"), list):\n            raise ProbeError("SSE event has no choices list")\n        frames.append(payload)\n    if not done or not frames:\n        raise ProbeError("Expected completion SSE events followed by data: [DONE]")\n    return frames\n\n\ndef check_http(base: str, model: str, key: str, stream: bool, timeout: float) -> dict:\n    payload = {"model": model, "messages": [{"role": "user", "content": PROBE}], "stream": stream}\n    if stream:\n        payload["stream_options"] = {"include_usage": True}\n    req = urllib.request.Request(\n        base + "/chat/completions",\n        data=json.dumps(payload).encode("utf-8"), method="POST",\n        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json",\n                 "Accept": "text/event-stream" if stream else "application/json"},\n    )\n    with urllib.request.urlopen(req, timeout=timeout) as response:\n        content = response.read(LIMIT + 1)\n        status = response.status\n        media = response.headers.get_content_type()\n        marker = response.headers.get("X-Engineering-MCP-Bridge-Protocol")\n    if len(content) > LIMIT:\n        raise ProbeError("Response exceeds diagnostic size limit")\n    if status != 200 or marker != PROTOCOL:\n        raise ProbeError("Expected bridge protocol header is absent: verify that the 2.9.18 gateway is active")\n    if stream:\n        if media != "text/event-stream":\n            raise ProbeError("stream=true did not return text/event-stream")\n        frames = parse_sse(content)\n        usable = False\n        finished = False\n        for frame in frames:\n            for choice in frame["choices"]:\n                if not isinstance(choice, dict):\n                    raise ProbeError("SSE choice is not an object")\n                delta = choice.get("delta") or {}\n                if not isinstance(delta, dict):\n                    raise ProbeError("SSE delta is not an object")\n                usable |= bool(delta.get("content") or delta.get("tool_calls") or delta.get("refusal")\n                               or delta.get("function_call"))\n                finished |= bool(choice.get("finish_reason"))\n        if not usable or not finished:\n            raise ProbeError("SSE lacks a usable message or finish_reason")\n        return {"mode": "stream=true", "success": True, "http": status, "content_type": media,\n                "events": len(frames), "done": True, "protocol": marker}\n    if media != "application/json":\n        raise ProbeError("stream=false did not return application/json")\n    data = json.loads(content)\n    choices = data.get("choices") if isinstance(data, dict) else None\n    if not isinstance(choices, list) or not choices:\n        raise ProbeError("JSON response contains no choices")\n    if not isinstance(choices[0], dict):\n        raise ProbeError("JSON choice is not an object")\n    message = choices[0].get("message") or {}\n    if not isinstance(message, dict) or not choices[0].get("finish_reason"):\n        raise ProbeError("JSON choice lacks a message or finish_reason")\n    if not (message.get("content") or message.get("tool_calls") or message.get("refusal") or message.get("function_call")):\n        raise ProbeError("JSON response contains no usable message")\n    return {"mode": "stream=false", "success": True, "http": status, "content_type": media,\n            "choices": len(choices), "protocol": marker}\n\n\ndef check_models(base: str, model: str, key: str, timeout: float) -> dict:\n    request = urllib.request.Request(base + "/models", headers={\n        "Authorization": "Bearer " + key, "Accept": "application/json",\n    })\n    with urllib.request.urlopen(request, timeout=timeout) as response:\n        raw = response.read(LIMIT + 1)\n        if response.status != 200 or len(raw) > LIMIT:\n            raise ProbeError("Invalid model catalogue response or size")\n    data = json.loads(raw)\n    items = data.get("data", data.get("models", [])) if isinstance(data, dict) else []\n    ids = {str(item.get("id") or item.get("name")) for item in items\n           if isinstance(item, dict) and (item.get("id") or item.get("name"))} if isinstance(items, list) else set()\n    if model not in ids:\n        raise ProbeError("Configured agent model is absent from the bridge model catalogue")\n    return {"model_count": len(ids), "configured_model_present": True}\n\n\ndef usable_message(message) -> bool:\n    return bool(message.content or message.tool_calls or message.additional_kwargs.get("refusal"))\n\n\nasync def check_langchain(base: str, model: str, key: str, timeout: float) -> dict:\n    from langchain_openai import ChatOpenAI\n    versions = {}\n    for name in ("langchain-core", "langchain-openai", "openai", "nvidia-nat", "nvidia-nat-langchain"):\n        try:\n            versions[name] = importlib.metadata.version(name)\n        except importlib.metadata.PackageNotFoundError:\n            pass\n    llm = ChatOpenAI(model=model, api_key=key, base_url=base, timeout=timeout,\n                     max_retries=0, streaming=True, stream_usage=True)\n    try:\n        result = await llm.ainvoke(PROBE)\n        if not usable_message(result):\n            raise ProbeError("LangChain ainvoke returned no usable message")\n        count = 0\n        usable = False\n        async for chunk in llm.astream(PROBE):\n            count += 1\n            usable |= usable_message(chunk)\n        if not count or not usable:\n            raise ProbeError("LangChain astream returned no usable generation chunks")\n        event_count = 0\n        event_usable = False\n        async for event in llm.astream_events(PROBE, version="v2"):\n            if event.get("event") == "on_chat_model_stream":\n                event_count += 1\n                chunk = event.get("data", {}).get("chunk")\n                event_usable |= bool(chunk is not None and usable_message(chunk))\n        if not event_count or not event_usable:\n            raise ProbeError("LangChain astream_events returned no usable model stream events")\n        return {"success": True, "ainvoke_streaming": True, "astream_chunks": count,\n                "model_stream_events": event_count, "installed_versions": versions}\n    finally:\n        # Clients are constructed exclusively for this diagnostic.\n        try:\n            await llm.root_async_client.close()\n            llm.root_client.close()\n        except (AttributeError, RuntimeError):\n            pass\n\n\ndef main() -> int:\n    parser = argparse.ArgumentParser(description=__doc__)\n    parser.add_argument("--runtime-env", type=Path)\n    parser.add_argument("--base-url")\n    parser.add_argument("--model")\n    parser.add_argument("--timeout", type=float, default=180.0)\n    parser.add_argument("--langchain", action="store_true",\n                        help="Also test the installed LangChain client (three additional requests)")\n    parser.add_argument("--non-interactive", action="store_true",\n                        help="Fail rather than prompt if the existing bridge credential is missing")\n    args = parser.parse_args()\n    report = {"success": False, "release": "2.9.18", "protocol": PROTOCOL}\n    stage = "configuration"\n    try:\n        if not math.isfinite(args.timeout) or args.timeout <= 0:\n            raise ProbeError("timeout must be a positive finite number")\n        base, model, key = resolve_config(args)\n        report.update({"model": model, "models_url": base + "/models", "chat_url": base + "/chat/completions"})\n        stage = "models"\n        report.update(check_models(base, model, key, args.timeout))\n        stage = "json"\n        report["json"] = check_http(base, model, key, False, args.timeout)\n        report["chat_choice_count"] = report["json"]["choices"]\n        stage = "sse"\n        report["sse"] = check_http(base, model, key, True, args.timeout)\n        report.update({"sse_event_count": report["sse"]["events"], "sse_done": report["sse"]["done"]})\n        if args.langchain:\n            stage = "langchain"\n            async def checked():\n                return await asyncio.wait_for(check_langchain(base, model, key, args.timeout),\n                                              timeout=args.timeout * 3 + 15)\n            report["langchain"] = asyncio.run(checked())\n        report["success"] = True\n    except urllib.error.HTTPError as exc:\n        report.update({"error": "HTTPError", "http_status": exc.code,\n                       "note": "Inspect bridge/Open WebUI logs; response bodies are not printed."})\n        try:\n            data = json.loads(exc.read(65536))\n            code = data.get("error", {}).get("code") if isinstance(data, dict) else None\n            if isinstance(code, str) and re.fullmatch(r"openwebui_[a-z0-9_]{1,80}", code):\n                report["bridge_error_code"] = code\n        except Exception:\n            pass\n        finally:\n            exc.close()\n    except ProbeError as exc:\n        report.update({"error": "BridgePreflightError", "message": str(exc)})\n    except Exception as exc:\n        # Do not echo exception text: third-party clients may include credentials or response bodies.\n        report.update({"error": type(exc).__name__,\n                       "note": "Check connectivity and installed client versions; no provider bodies or credentials printed."})\n    if not report["success"]:\n        report["failed_stage"] = stage\n    print(json.dumps(report, ensure_ascii=True))\n    return 0 if report["success"] else 2\n\n\nif __name__ == "__main__":\n    raise SystemExit(main())\n'


def probe_physnemo_agent_bridge(state: Dict[str, Any], timeout: float = 90.0) -> Dict[str, Any]:
    """Verify the real WSL -> gateway -> Open WebUI path, including SSE and LangChain.

    The embedded diagnostic reads runtime.env without executing it. No dependency
    download or separate hotfix is needed. It sends five small chat requests (two
    wire-protocol checks and three installed-client checks), but submits no job.
    """
    runtime = _physnemo_runtime_from_state(state)
    secret = read_json(PHYSNEMO_AGENT_SECRET_FILE)
    report: Dict[str, Any] = {
        "checked_at": now_iso(),
        "contract": PHYSNEMO_OPENWEBUI_AGENT_BRIDGE_CONTRACT,
        "chat_protocol_contract": PHYSNEMO_OPENWEBUI_CHAT_PROTOCOL,
        "attempted": False,
        "success": False,
        "transport": str(secret.get("agent_transport") or "unconfigured"),
        "model": str(secret.get("agent_model") or ""),
    }
    if report["transport"] != "openwebui-chat-api":
        report.update({"success": True, "skipped": True, "reason": "direct provider or unconfigured agent"})
        atomic_write_json(PHYSNEMO_AGENT_BRIDGE_PREFLIGHT_REPORT, report, private=True)
        return report
    if not runtime.get("configured") or not runtime.get("distro") or not runtime.get("linux_install_dir"):
        report["error"] = "PhysicsNeMo runtime is not configured"
        atomic_write_json(PHYSNEMO_AGENT_BRIDGE_PREFLIGHT_REPORT, report, private=True)
        return report
    report["attempted"] = True
    component = physnemo_component()
    root = str(runtime["linux_install_dir"])
    env_file = f"{root}/config/runtime.env"
    request_timeout = max(30, int(timeout))
    script = f"""set -Eeuo pipefail
root={component.shell_path(root)}
env_file={component.shell_path(env_file)}
[[ -r "$env_file" ]] || {{ echo "Missing PhysicsNeMo runtime.env" >&2; exit 78; }}
[[ -x "$root/.venv-nat/bin/python" ]] || {{ echo "Missing NAT Python interpreter" >&2; exit 78; }}
"$root/.venv-nat/bin/python" - --runtime-env "$env_file" --timeout {request_timeout} --langchain --non-interactive <<'PY_AGENT_BRIDGE_CHECK_2912'
{PHYSNEMO_AGENT_BRIDGE_CHECK_SOURCE}
PY_AGENT_BRIDGE_CHECK_2912
"""
    try:
        result = component.wsl_run(
            str(runtime["distro"]), script, check=True,
            timeout=request_timeout * 6.0 + 30.0,
            stage="openwebui-agent-bridge-preflight",
        )
        line = next(
            (item for item in reversed((result.stdout or "").splitlines()) if item.strip().startswith("{")),
            "{}",
        )
        payload = json.loads(line)
        report.update(payload if isinstance(payload, dict) else {})
        report["success"] = bool(
            report.get("success") is True
            and report.get("protocol") == "buffered-sse-v1"
            and report.get("configured_model_present") is True
            and report.get("chat_choice_count", 0) > 0
            and report.get("sse_event_count", 0) > 0
            and report.get("sse_done") is True
            and isinstance(report.get("langchain"), dict)
            and report["langchain"].get("success") is True
        )
        if not report["success"]:
            report.setdefault("error", "Agent bridge JSON/SSE/LangChain preflight did not pass all checks")
    except Exception as exc:
        report["success"] = False
        report["error"] = f"{type(exc).__name__}: {exc}"
    atomic_write_json(PHYSNEMO_AGENT_BRIDGE_PREFLIGHT_REPORT, report, private=True)
    return report


PHYSNEMO_NATIVE_TOOLS_CHECK_SOURCE = '#!/usr/bin/env python3\n"""Run in the installed NAT venv. No shell sourcing, dependency installation or secret output."""\nfrom __future__ import annotations\nimport argparse\nimport asyncio\nimport base64\nimport ipaddress\nimport importlib.metadata\nimport json\nimport math\nimport os\nfrom pathlib import Path\nimport re\nimport shlex\nimport sys\nimport subprocess\nimport urllib.parse\n\nCONTRACT = "PHYSNEMO_NATIVE_TOOL_DISPATCH_V5"\nPREFLIGHT_CONTRACT = "PHYSNEMO_NATIVE_TOOL_PREFLIGHT_V5"\n\nDEFAULT_REQUEST_TIMEOUT_SECONDS = 300.0\nDEFAULT_TOTAL_TIMEOUT_SECONDS = 1800.0\n\nKEYS = {"PHYSNEMO_AGENT_BASE_URL", "PHYSNEMO_AGENT_API_KEY", "PHYSNEMO_AGENT_MODEL",\n        "PHYSNEMO_AGENT_TRANSPORT", "PHYSNEMO_GATEWAY_PORT", "PHYSNEMO_GATEWAY_ROUTE"}\n\ndef read_env(path: Path) -> dict[str, str]:\n    """Decode the installer\'s private *_B64 format without sourcing/executing it."""\n    values = {}\n    for line in path.read_text(encoding="utf-8-sig").splitlines():\n        m = re.fullmatch(r"\\s*(?:export\\s+)?([A-Z0-9_]+)_B64=(.*?)\\s*", line)\n        if not m or m[1] not in KEYS:\n            continue\n        parts = shlex.split(m[2], comments=True)\n        if len(parts) > 1:\n            raise RuntimeError("PHYSNEMO_NATIVE_RUNTIME_ENV_INVALID")\n        values[m[1]] = base64.b64decode(parts[0] if parts else "", validate=True).decode("utf-8")\n    return values\n\ndef windows_host() -> str:\n    if os.name == "nt":\n        return "127.0.0.1"\n    try:\n        cp = subprocess.run(["ip", "route", "show", "default"], capture_output=True,\n                            text=True, check=True, timeout=5)\n        m = re.search(r"\\bvia\\s+(\\S+)", cp.stdout)\n        if m:\n            return str(ipaddress.ip_address(m[1]))\n    except (OSError, subprocess.SubprocessError, ValueError):\n        pass\n    try:\n        for line in Path("/etc/resolv.conf").read_text().splitlines():\n            if line.strip().startswith("nameserver "):\n                return str(ipaddress.ip_address(line.split()[1]))\n    except (OSError, ValueError, IndexError):\n        pass\n    raise RuntimeError("PHYSNEMO_NATIVE_WINDOWS_HOST_UNAVAILABLE")\n\ndef resolve_env(values: dict[str, str]) -> dict[str, str]:\n    env = dict(values)\n    if env.get("PHYSNEMO_AGENT_TRANSPORT") == "openwebui-chat-api":\n        port = int(env.get("PHYSNEMO_GATEWAY_PORT") or "8200")\n        route = env.get("PHYSNEMO_GATEWAY_ROUTE") or "physnemo"\n        if not 1 <= port <= 65535 or not re.fullmatch(r"[A-Za-z0-9_-]+", route):\n            raise RuntimeError("PHYSNEMO_NATIVE_BRIDGE_CONFIG_INVALID")\n        host = windows_host()\n        host = f"[{host}]" if ":" in host else host\n        env["PHYSNEMO_AGENT_BASE_URL"] = f"http://{host}:{port}/{route}/openwebui-api"\n    for key in ("PHYSNEMO_AGENT_BASE_URL", "PHYSNEMO_AGENT_API_KEY", "PHYSNEMO_AGENT_MODEL"):\n        if not env.get(key) or any(c in env[key] for c in ("\\r", "\\n")):\n            raise RuntimeError("PHYSNEMO_NATIVE_AGENT_NOT_CONFIGURED")\n    url = urllib.parse.urlsplit(env["PHYSNEMO_AGENT_BASE_URL"])\n    if (url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password\n            or url.query or url.fragment):\n        raise RuntimeError("PHYSNEMO_NATIVE_BASE_URL_INVALID")\n    env["PHYSNEMO_AGENT_BASE_URL"] = env["PHYSNEMO_AGENT_BASE_URL"].rstrip("/")\n    return env\n\ndef validate_timeouts(request_timeout: float, total_timeout: float) -> None:\n    if (isinstance(request_timeout, bool) or isinstance(total_timeout, bool)\n            or not isinstance(request_timeout, (int, float)) or not isinstance(total_timeout, (int, float))\n            or not math.isfinite(request_timeout) or not math.isfinite(total_timeout)\n            or not 1 <= request_timeout <= 900 or not request_timeout <= total_timeout <= 7200):\n        raise RuntimeError("PHYSNEMO_MODEL_TIMEOUT_CONFIG_INVALID")\n\n\ndef progress(event: dict) -> None:\n    # The plugin callback supplies only host-authored metadata; no response bodies.\n    print("PHYSNEMO_PREFLIGHT_PROGRESS " + json.dumps(event, ensure_ascii=True), file=sys.stderr, flush=True)\n\n\nasync def check(root: Path, env: dict[str, str], tool_transport: str = "auto",\n                request_timeout: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,\n                total_timeout: float = DEFAULT_TOTAL_TIMEOUT_SECONDS) -> dict:\n    validate_timeouts(request_timeout, total_timeout)\n    from langchain_openai import ChatOpenAI\n    from engineering_physnemo_nat.register import NATIVE_TOOL_CONTRACT, NATIVE_PREFLIGHT_CONTRACT, native_tool_preflight\n    if NATIVE_TOOL_CONTRACT != CONTRACT or NATIVE_PREFLIGHT_CONTRACT != PREFLIGHT_CONTRACT:\n        raise RuntimeError("PHYSNEMO_NATIVE_PLUGIN_STALE")\n    env = resolve_env(env)\n    llm = ChatOpenAI(base_url=env["PHYSNEMO_AGENT_BASE_URL"], api_key=env["PHYSNEMO_AGENT_API_KEY"],\n                    model=env["PHYSNEMO_AGENT_MODEL"], temperature=0.1, max_tokens=8192,\n                    timeout=float(request_timeout), max_retries=0)\n    result = await native_tool_preflight(llm, root / "physicsnemo-source", root / "run/native-tool-probes", tool_transport=tool_transport,\n        request_timeout_seconds=request_timeout, total_timeout_seconds=total_timeout, progress_callback=progress)\n    result["client_policy"] = {"request_timeout_seconds": float(request_timeout), "sdk_max_retries": 0,\n                               "configured_by": "installed_preflight_checker"}\n    result["versions"] = {name: importlib.metadata.version(name) for name in\n        ("nvidia-nat", "nvidia-nat-langchain", "langchain-core", "langchain-openai", "engineering-physnemo-nat")}\n    return result\n\ndef main() -> int:\n    p = argparse.ArgumentParser(description=__doc__)\n    p.add_argument("--root", required=True)\n    p.add_argument("--runtime-env", required=True)\n    p.add_argument("--tool-transport", choices=("auto", "native", "json_actions_v1"), default="auto")\n    p.add_argument("--request-timeout", type=float, default=DEFAULT_REQUEST_TIMEOUT_SECONDS,\n                   help="SDK request timeout in seconds (1..900; default 300). No automatic retry.")\n    p.add_argument("--total-timeout", type=float, default=DEFAULT_TOTAL_TIMEOUT_SECONDS,\n                   help="Whole model phase deadline in seconds (request timeout..7200; default 1800).")\n    a = p.parse_args()\n    result = {"success": False, "contract": CONTRACT, "preflight_contract": PREFLIGHT_CONTRACT}\n    try:\n        result.update(asyncio.run(check(Path(a.root).resolve(), read_env(Path(a.runtime_env)), a.tool_transport, a.request_timeout, a.total_timeout)))\n    except Exception as exc:\n        # Third-party exception text may contain credentials or private model content.\n        safe = str(exc) if re.fullmatch(r"PHYSNEMO_[A-Z_]+", str(exc)) else "PHYSNEMO_NATIVE_PREFLIGHT_FAILED"\n        result.update(error=safe, exception_type=type(exc).__name__,\n                      failed_stage="load_runtime_or_client", note="No provider bodies or credentials printed. Inspect both model-events.jsonl and tool-events.jsonl in the reported probe directory.")\n    print(json.dumps(result, ensure_ascii=True))\n    return 0 if result.get("success") else 2\n\nif __name__ == "__main__":\n    raise SystemExit(main())\n'

def _physnemo_model_execution_verified(report: Dict[str, Any]) -> bool:
    """Registration, native API support and verified JSON action execution differ."""
    if (not isinstance(report, dict) or report.get("success") is not True
            or report.get("contract") != "PHYSNEMO_NATIVE_TOOL_DISPATCH_V5"
            or report.get("preflight_contract") != "PHYSNEMO_NATIVE_TOOL_PREFLIGHT_V5"
            or report.get("model_tool_execution_verified") is not True
            or report.get("selected_tool_transport") not in {"native", "json_actions_v1"}
            or report.get("missing_tools") != [] or report.get("exact_content_roundtrip") is not True
            or report.get("script_exact") is not True):
        return False
    for phase in (report.get("local_probe"), report.get("model_probe"), report):
        if not isinstance(phase, dict):
            return False
        execution = phase.get("execution_summary") or {}
        tools = phase.get("tool_summary") or {}
        if (phase.get("success") is not True or phase.get("missing_tools") != []
                or phase.get("exact_content_roundtrip") is not True or phase.get("script_exact") is not True
                or not isinstance(execution, dict) or not isinstance(tools, dict)):
            return False
        if (type(execution.get("succeeded")) is not int or execution["succeeded"] < 1
                or type(tools.get("succeeded")) is not int or tools["succeeded"] < 7):
            return False
    summary = report.get("model_summary") or {}
    if not isinstance(summary, dict):
        return False
    native_calls = summary.get("tool_calls", 0)
    json_actions = summary.get("json_actions", 0)
    if type(native_calls) is not int or type(json_actions) is not int or min(native_calls, json_actions) < 0:
        return False
    if native_calls + json_actions < 7:
        return False
    if report["selected_tool_transport"] == "native":
        return native_calls >= 7 and json_actions == 0 and report.get("native_tool_calls_verified") is True
    return json_actions > 0 and report.get("native_tool_calls_verified") is False


def _physnemo_model_probe_timeouts() -> tuple[float, float]:
    """Local preflight budgets only; do not put these settings into model prompts or secrets."""
    import math
    try:
        request = float(os.environ.get("ENGINEERING_MCP_PHYSNEMO_REQUEST_TIMEOUT_SECONDS", "300"))
        total = float(os.environ.get("ENGINEERING_MCP_PHYSNEMO_PREFLIGHT_TIMEOUT_SECONDS", "1800"))
    except (ValueError, TypeError):
        raise ValueError("PHYSNEMO_MODEL_TIMEOUT_CONFIG_INVALID") from None
    if not (math.isfinite(request) and math.isfinite(total) and 1 <= request <= 900 and request <= total <= 7200):
        raise ValueError("PHYSNEMO_MODEL_TIMEOUT_CONFIG_INVALID")
    return request, total


def probe_physnemo_native_tools(state: Dict[str, Any]) -> Dict[str, Any]:
    """Verify real model-generated structured args, file IO and a fixed subprocess in WSL."""
    runtime = _physnemo_runtime_from_state(state)
    secret = read_json(PHYSNEMO_AGENT_SECRET_FILE)
    report: Dict[str, Any] = {"success": False, "contract": "PHYSNEMO_NATIVE_TOOL_DISPATCH_V5",
                             "attempted": False, "checked_at": now_iso()}
    path = PHYSNEMO_AGENT_BRIDGE_PREFLIGHT_REPORT.with_name("physnemo-native-tools-preflight.json")
    if not secret.get("agent_model"):
        report.update(skipped=True, reason="agent is not configured; execution readiness NOT verified")
    elif not runtime.get("configured") or not runtime.get("distro") or not runtime.get("linux_install_dir"):
        report["error"] = "PHYSNEMO_RUNTIME_UNAVAILABLE"
    else:
        try:
            request_timeout, total_timeout = _physnemo_model_probe_timeouts()
        except ValueError:
            report.update(error="PHYSNEMO_MODEL_TIMEOUT_CONFIG_INVALID", failed_stage="load_timeout_policy")
            atomic_write_json(path, report, private=True)
            return report
        report["launcher_timeout_seconds"] = total_timeout + 120.0
        component = physnemo_component()
        root = str(runtime["linux_install_dir"])
        script = f'''set -Eeuo pipefail
root={component.shell_path(root)}
"$root/.venv-nat/bin/python" - --root "$root" --runtime-env "$root/config/runtime.env" --request-timeout {request_timeout:g} --total-timeout {total_timeout:g} <<'PY_NATIVE_TOOL_CHECK_2918'
{PHYSNEMO_NATIVE_TOOLS_CHECK_SOURCE}
PY_NATIVE_TOOL_CHECK_2918
'''
        report["attempted"] = True
        try:
            result = component.wsl_run(str(runtime["distro"]), script, check=False, capture=False, timeout=total_timeout + 120.0,
                                       stage="physnemo-native-tools-preflight")
            line = next((line for line in reversed((result.stdout or "").splitlines()) if line.strip().startswith("{")), "{}")
            data = json.loads(line)
            if not isinstance(data, dict):
                raise ValueError("Invalid native probe report shape")
            report.update(data)
            report["returncode"] = result.returncode
            report["success"] = bool(result.returncode == 0 and _physnemo_model_execution_verified(data))
            if not report["success"]:
                report.setdefault("error", "PHYSNEMO_NATIVE_PREFLIGHT_FAILED")
        except Exception as exc:
            report.update(success=False, error="PHYSNEMO_NATIVE_PREFLIGHT_FAILED", exception_type=type(exc).__name__)
    atomic_write_json(path, report, private=True)
    return report


def probe_physnemo_mcp(state: Optional[Dict[str, Any]] = None, timeout: float = 90.0) -> Dict[str, Any]:
    runtime = _physnemo_runtime_from_state(state)
    url = str(runtime.get("mcp_url") or "")
    report: Dict[str, Any] = {
        "checked_at": now_iso(),
        "success": False,
        "url": url,
        "expected_tools": list(PHYSNEMO_EXPECTED_TOOLS),
    }
    if not url:
        report["error"] = "PhysicsNeMo MCP URL is unavailable"
        atomic_write_json(PHYSNEMO_MCP_PREFLIGHT_REPORT, report, private=True)
        return report
    command = [
        str(mcpo_venv_bin("python")),
        str(INSTALLED_SCRIPT),
        "--mcp-http-probe",
        "--url",
        url,
        "--route",
        PHYSNEMO_ROUTE,
    ]
    try:
        completed = run(command, timeout=timeout)
        report["returncode"] = completed.returncode
        report["output_tail"] = (completed.stdout or "")[-12000:]
        payload = next(
            (
                json.loads(line)
                for line in reversed((completed.stdout or "").splitlines())
                if line.strip().startswith("{")
            ),
            {},
        )
        if isinstance(payload, dict):
            report.update(payload)
        names = {str(value) for value in report.get("tool_names", [])}
        missing = sorted(set(PHYSNEMO_EXPECTED_TOOLS) - names)
        report["missing_tools"] = missing
        report["success"] = bool(
            completed.returncode == 0 and report.get("success") and not missing
        )
        if missing:
            report["error"] = f"PhysicsNeMo MCP is missing expected tools: {missing}"
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
    atomic_write_json(PHYSNEMO_MCP_PREFLIGHT_REPORT, report, private=True)
    return report


def uninstall_physnemo_runtime(state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    runtime = _physnemo_runtime_from_state(state)
    report: Dict[str, Any] = {"removed": False}
    stop_physnemo_nat(state)
    if not runtime.get("distro") or not runtime.get("linux_install_dir"):
        report["skipped"] = True
        return report
    component = physnemo_component()
    root = str(runtime["linux_install_dir"])
    script = f'''set -Eeuo pipefail
root={component.shell_path(root)}
marker="$root/.engineering-mcp-physnemo-managed"
if [[ ! -f "$marker" ]] || ! grep -q '^managed_by=engineering-mcp-physnemo$' "$marker"; then
  echo "Refusing to remove unmarked PhysicsNeMo directory: $root" >&2
  exit 70
fi
[[ ! -x "$root/bin/stop-nat.sh" ]] || "$root/bin/stop-nat.sh" || true
rm -rf --one-file-system "$root"
'''
    try:
        component.wsl_run(str(runtime["distro"]), script, check=True, timeout=900)
        report["removed"] = True
        report["distro"] = runtime["distro"]
        report["linux_install_dir"] = root
    except Exception as exc:
        report["error"] = str(exc)
    return report


# ---------------------------------------------------------------------------
# State and resumable installation checkpoint
# ---------------------------------------------------------------------------

def load_state() -> Dict[str, Any]:
    return read_json(STATE_FILE)


def save_state(state: Dict[str, Any]) -> None:
    state["updated_at"] = now_iso()
    atomic_write_json(STATE_FILE, state, private=True)


def load_checkpoint() -> Dict[str, Any]:
    return read_json(CHECKPOINT_FILE)


def save_checkpoint(checkpoint: Dict[str, Any]) -> None:
    checkpoint["updated_at"] = now_iso()
    atomic_write_json(CHECKPOINT_FILE, checkpoint, private=True)


def set_checkpoint_step(
    checkpoint: Dict[str, Any],
    name: str,
    status: str,
    *,
    error: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    entry: Dict[str, Any] = {"status": status, "updated_at": now_iso()}
    if error:
        entry["error"] = error
    if details:
        entry["details"] = details
    checkpoint.setdefault("steps", {})[name] = entry
    if error:
        checkpoint["last_error"] = error
    save_checkpoint(checkpoint)


def step_done(checkpoint: Dict[str, Any], name: str) -> bool:
    return checkpoint.get("steps", {}).get(name, {}).get("status") == "done"


def create_checkpoint(options: Dict[str, Any], previous_state: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "schema": 2,
        "bootstrapper_version": BOOTSTRAPPER_VERSION,
        "operation": "install",
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "complete": False,
        "options": options,
        "api_key": previous_state.get("api_key") or secrets.token_urlsafe(32),
        "installed": dict(previous_state.get("installed", {})),
        "matlab_binary": previous_state.get("matlab_binary"),
        "weknora_runtime": previous_state.get("weknora_runtime", {}),
        "steps": {},
    }


def archive_interrupted_checkpoint(checkpoint: Dict[str, Any]) -> Optional[Path]:
    """Archive a stale checkpoint when the user explicitly chooses a fresh install.

    `--resume` remains the only mode that continues an interrupted operation.  An
    explicit `--install` must be able to start cleanly after an uninstall or a
    failed older release instead of being trapped by the previous checkpoint.
    """
    if not checkpoint:
        return None
    archive_dir = LOG_DIR / "checkpoint-archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    archive_path = archive_dir / f"install-checkpoint-{timestamp}-{uuid.uuid4().hex[:8]}.json"
    atomic_write_json(archive_path, checkpoint, private=True)
    CHECKPOINT_FILE.unlink(missing_ok=True)
    return archive_path


def resolve_install_context(args: argparse.Namespace, resume: bool) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    previous_state = load_state()
    existing_checkpoint = load_checkpoint()
    legacy_physnemo = _legacy_physnemo_state()

    if resume and existing_checkpoint:
        checkpoint = existing_checkpoint
    elif resume:
        saved_options = previous_state.get("options", {})
        checkpoint = create_checkpoint(saved_options, previous_state)
    else:
        # The three public modes have deliberately distinct semantics:
        #   install   -> start a fresh installation/upgrade transaction
        #   resume    -> continue the previous interrupted transaction
        #   uninstall -> remove the managed environment
        # Therefore an explicit fresh install archives, rather than blocks on,
        # an incomplete checkpoint left by an older or interrupted uninstall.
        if existing_checkpoint and not existing_checkpoint.get("complete"):
            archived = archive_interrupted_checkpoint(existing_checkpoint)
            print(
                "[!] A previous incomplete checkpoint was archived before the "
                f"fresh install: {archived}"
            )
        checkpoint = create_checkpoint({}, previous_state)

    saved_options = checkpoint.get("options", {})
    options = {
        "port": args.port if args.port is not None else int(saved_options.get("port", previous_state.get("mcpo_port", DEFAULT_MCPO_PORT))),
        "community": args.community if args.community is not None else bool(saved_options.get("community", previous_state.get("community_enabled", False))),
        "physnemo": (
            args.physnemo
            if args.physnemo is not None
            else bool(saved_options.get("physnemo", True))
        ),
        "physnemo_distro": (
            str(args.physnemo_distro or "").strip()
            or str(saved_options.get("physnemo_distro") or "").strip()
            or str((previous_state.get("physnemo_runtime") or {}).get("distro") or "").strip()
            or str(legacy_physnemo.get("distro") or "").strip()
        ),
        "physnemo_install_dir": (
            str(args.physnemo_install_dir or "").strip()
            or str(saved_options.get("physnemo_install_dir") or "").strip()
            or str((previous_state.get("physnemo_runtime") or {}).get("linux_install_dir") or "").strip()
            or str(legacy_physnemo.get("linux_install_dir") or "").strip()
        ),
        "physnemo_nat_port": int(
            args.physnemo_nat_port
            if args.physnemo_nat_port is not None
            else saved_options.get(
                "physnemo_nat_port",
                (previous_state.get("physnemo_runtime") or {}).get(
                    "nat_port", legacy_physnemo.get("nat_port", DEFAULT_PHYSNEMO_NAT_PORT)
                ),
            )
        ),
        "physnemo_nat_version": (
            str(args.physnemo_nat_version or "").strip()
            or str(saved_options.get("physnemo_nat_version") or DEFAULT_PHYSNEMO_NAT_VERSION)
        ),
        "physicsnemo_version": (
            str(args.physicsnemo_version or "").strip()
            or str(saved_options.get("physicsnemo_version") or DEFAULT_PHYSNEMO_VERSION)
        ),
        "physicsnemo_profile": (
            str(args.physicsnemo_profile or "").strip()
            or str(saved_options.get("physicsnemo_profile") or "base")
        ),
        "physicsnemo_source_ref": (
            str(args.physicsnemo_source_ref or "").strip()
            or str(saved_options.get("physicsnemo_source_ref") or DEFAULT_PHYSNEMO_SOURCE_REF)
        ),
        "physnemo_install_prerequisites": (
            args.physnemo_install_prerequisites
            if args.physnemo_install_prerequisites is not None
            else bool(saved_options.get("physnemo_install_prerequisites", True))
        ),
        "physnemo_agent_base_url": (
            str(args.physnemo_agent_base_url or "").strip()
            or str(saved_options.get("physnemo_agent_base_url") or "").strip()
        ),
        "physnemo_agent_model": (
            str(args.physnemo_agent_model or "").strip()
            or str(saved_options.get("physnemo_agent_model") or "").strip()
        ),
        "physnemo_agent_api_key_file": str(args.physnemo_agent_api_key_file or "").strip(),
        "physnemo_agent_auto_detect": (
            args.physnemo_agent_auto_detect
            if args.physnemo_agent_auto_detect is not None
            else bool(saved_options.get("physnemo_agent_auto_detect", True))
        ),
        "physnemo_openwebui_url": (
            str(args.physnemo_openwebui_url or "").strip()
            or str(saved_options.get("physnemo_openwebui_url") or "").strip()
        ),
        "physnemo_openwebui_api_key_file": str(args.physnemo_openwebui_api_key_file or "").strip(),
        "physnemo_artifact_base_url": (
            str(args.physnemo_artifact_base_url or "").strip()
            or str(saved_options.get("physnemo_artifact_base_url") or "").strip()
        ),
        "openwebui_database": (
            str(args.openwebui_database or "").strip()
            or str(saved_options.get("openwebui_database") or "").strip()
            or str(os.environ.get("OPENWEBUI_DATABASE") or "").strip()
        ),
        "openwebui_native_sync": (
            args.openwebui_native_sync
            if args.openwebui_native_sync is not None
            else bool(saved_options.get("openwebui_native_sync", True))
        ),
        "openwebui_dlp_repair": (
            args.openwebui_dlp_repair
            if args.openwebui_dlp_repair is not None
            else bool(saved_options.get("openwebui_dlp_repair", True))
        ),
        "physnemo_allow_unconfigured_agent": (
            args.physnemo_allow_unconfigured_agent
            if args.physnemo_allow_unconfigured_agent is not None
            else bool(saved_options.get("physnemo_allow_unconfigured_agent", False))
        ),
        "weknora": (
            args.weknora
            if args.weknora is not None
            else bool(saved_options.get("weknora", True))
        ),
        "weknora_url": (
            str(args.weknora_url or "").strip()
            or str(saved_options.get("weknora_url") or "").strip()
            or str(os.environ.get("ENGINEERING_MCP_WEKNORA_URL") or "").strip()
        ),
        "weknora_api_url": (
            str(args.weknora_api_url or "").strip()
            or str(saved_options.get("weknora_api_url") or "").strip()
            or str(os.environ.get("ENGINEERING_MCP_WEKNORA_API_URL") or "").strip()
        ),
        "weknora_api_key_file": (
            str(args.weknora_api_key_file or "").strip()
            or str(os.environ.get("ENGINEERING_MCP_WEKNORA_API_KEY_FILE") or "").strip()
        ),
        "weknora_tenant_id": (
            str(args.weknora_tenant_id or "").strip()
            or str(saved_options.get("weknora_tenant_id") or "").strip()
            or str(os.environ.get("ENGINEERING_MCP_WEKNORA_TENANT_ID") or "").strip()
        ),
        "weknora_tenant_name": (
            str(args.weknora_tenant_name or "").strip()
            or str(saved_options.get("weknora_tenant_name") or "").strip()
            or str(os.environ.get("ENGINEERING_MCP_WEKNORA_TENANT_NAME") or "").strip()
        ),
        "weknora_ca_certificate": (
            str(args.weknora_ca_certificate or "").strip()
            or str(saved_options.get("weknora_ca_certificate") or "").strip()
            or str(os.environ.get("ENGINEERING_MCP_WEKNORA_CA_CERTIFICATE") or "").strip()
        ),
        "weknora_distro": (
            str(args.weknora_distro or "").strip()
            or str(saved_options.get("weknora_distro") or "").strip()
        ),
        "weknora_install_dir": (
            str(args.weknora_install_dir or "").strip()
            or str(saved_options.get("weknora_install_dir") or "").strip()
        ),
        "weknora_auto_provision": (
            args.weknora_auto_provision
            if args.weknora_auto_provision is not None
            else bool(saved_options.get("weknora_auto_provision", True))
        ),
        "weknora_allow_empty_catalog": (
            args.weknora_allow_empty_catalog
            if args.weknora_allow_empty_catalog is not None
            else bool(saved_options.get("weknora_allow_empty_catalog", False))
        ),
        "weknora_health_timeout": (
            float(args.weknora_health_timeout)
            if args.weknora_health_timeout is not None
            else float(
                saved_options.get(
                    "weknora_health_timeout",
                    previous_state.get("weknora_health_timeout", DEFAULT_WEKNORA_HEALTH_TIMEOUT),
                )
            )
        ),
        "autostart": args.autostart if args.autostart is not None else bool(saved_options.get("autostart", True)),
        "start": args.start if args.start is not None else bool(saved_options.get("start", True)),
        "startup_timeout": (
            float(args.startup_timeout)
            if args.startup_timeout is not None
            else float(
                saved_options.get(
                    "startup_timeout",
                    previous_state.get("startup_timeout", DEFAULT_STARTUP_TIMEOUT),
                )
            )
        ),
        "matlab_repair": (
            args.matlab_repair
            if args.matlab_repair is not None
            else bool(saved_options.get("matlab_repair", True))
        ),
        # Safety-sensitive: never persist permission to kill MATLAB.
        "matlab_force_close": bool(args.matlab_force_close),
        "matlab_health_timeout": (
            float(args.matlab_health_timeout)
            if args.matlab_health_timeout is not None
            else float(saved_options.get("matlab_health_timeout", DEFAULT_MATLAB_HEALTH_TIMEOUT))
        ),
    }
    if not 1 <= int(options["physnemo_nat_port"]) <= 65535:
        raise RuntimeError("PhysicsNeMo NAT port must be between 1 and 65535")
    if int(options["physnemo_nat_port"]) == int(options["port"]):
        raise RuntimeError("PhysicsNeMo NAT port and the shared MCPO gateway port must be different")
    component = physnemo_component()
    options["physnemo_nat_version"] = component.validate_version(
        options["physnemo_nat_version"], "NeMo Agent Toolkit version"
    )
    options["physicsnemo_version"] = component.validate_version(
        options["physicsnemo_version"], "PhysicsNeMo version"
    )
    options["physicsnemo_source_ref"] = component.validate_source_ref(
        options["physicsnemo_source_ref"]
    )
    component.physicsnemo_package_spec(
        options["physicsnemo_version"], options["physicsnemo_profile"]
    )
    if options.get("physnemo_artifact_base_url"):
        options["physnemo_artifact_base_url"] = _valid_http_base_url(
            options["physnemo_artifact_base_url"], "PhysicsNeMo artifact base URL"
        )
    if options["startup_timeout"] < 10 or options["startup_timeout"] > 1800:
        raise RuntimeError("Startup timeout must be between 10 and 1800 seconds")
    if options["matlab_health_timeout"] < 30 or options["matlab_health_timeout"] > 1800:
        raise RuntimeError("MATLAB health timeout must be between 30 and 1800 seconds")
    if options["weknora_health_timeout"] < 10 or options["weknora_health_timeout"] > 1800:
        raise RuntimeError("WeKnora health timeout must be between 10 and 1800 seconds")
    if options["weknora_tenant_id"] and not re.fullmatch(r"[1-9][0-9]*", options["weknora_tenant_id"]):
        raise RuntimeError("WeKnora tenant id must be a positive integer")
    if options["weknora_tenant_id"] and options["weknora_tenant_name"]:
        raise RuntimeError("Use only one of --weknora-tenant-id and --weknora-tenant-name")
    if options["weknora_tenant_name"]:
        tenant_name = str(options["weknora_tenant_name"]).strip()
        if len(tenant_name) > 255 or "\r" in tenant_name or "\n" in tenant_name:
            raise RuntimeError("WeKnora tenant name must be one line and at most 255 characters")
        options["weknora_tenant_name"] = tenant_name
    if options["weknora_url"]:
        root_url, _base_url = _normalise_weknora_urls(options["weknora_url"])
        options["weknora_url"] = root_url
    if options["weknora_api_url"]:
        api_root, api_base = _normalise_weknora_urls(options["weknora_api_url"])
        # Preserve the explicit REST contract rather than reducing it to the
        # service root. This lets operators point at a separate backend port.
        options["weknora_api_url"] = api_base
    effective_transport_url = options["weknora_api_url"] or options["weknora_url"]
    if effective_transport_url:
        scheme = urllib.parse.urlsplit(effective_transport_url).scheme.lower()
        explicit_ca = bool(
            str(args.weknora_ca_certificate or "").strip()
            or str(os.environ.get("ENGINEERING_MCP_WEKNORA_CA_CERTIFICATE") or "").strip()
        )
        if scheme == "http":
            if explicit_ca:
                raise RuntimeError("A WeKnora CA certificate can be used only with an https:// API URL")
            options["weknora_ca_certificate"] = ""
    if options["weknora_ca_certificate"]:
        ca_path = Path(options["weknora_ca_certificate"]).expanduser()
        if not ca_path.is_file():
            raise RuntimeError(f"WeKnora CA certificate file does not exist: {ca_path}")
        options["weknora_ca_certificate"] = str(ca_path.resolve())
    checkpoint["options"] = options
    checkpoint["complete"] = False
    checkpoint["bootstrapper_version"] = BOOTSTRAPPER_VERSION
    checkpoint.pop("last_error", None)
    save_checkpoint(checkpoint)
    return checkpoint, options


# ---------------------------------------------------------------------------
# MCPO configuration and Open WebUI endpoint descriptions
# ---------------------------------------------------------------------------

def detected_for_server(route: str, metadata: Dict[str, Any], scan_data: Dict[str, Any]) -> bool:
    application = scan_data.get("applications", {}).get(metadata["detection"], {})
    if metadata.get("requires_healthy_application"):
        return bool(application.get("found") and application.get("healthy"))
    product = metadata.get("product")
    if product:
        return bool(application.get("products", {}).get(product))
    return bool(application.get("found"))


def command_supports_option(command: Path, option: str, timeout: float = 30.0) -> bool:
    """Return whether an installed MCP command advertises a required CLI option."""
    try:
        result = run([str(command), "--help"], timeout=timeout)
    except Exception:
        return False
    return result.returncode == 0 and option in (result.stdout or "")


def server_command_path(route: str, metadata: Dict[str, Any]) -> Path:
    if route == "weknora":
        return weknora_venv_bin(str(metadata["command"]))
    return venv_bin(str(metadata["command"]))


def server_command_installed(route: str, metadata: Dict[str, Any]) -> bool:
    return server_command_path(route, metadata).is_file()


def server_package_version(route: str, package: str) -> Optional[str]:
    if route == "weknora":
        return auxiliary_package_version(WEKNORA_VENV, package)
    return installed_package_version(package)


def server_launch_args(route: str, metadata: Dict[str, Any]) -> List[str]:
    """Build validated server arguments; fail before writing a deficient OpenAPI route."""
    command = server_command_path(route, metadata)
    args = [str(value) for value in metadata.get("args", [])]
    for option in metadata.get("required_cli_options", []):
        if not command_supports_option(command, str(option)):
            package = str(metadata.get("package") or metadata.get("command") or route)
            version = server_package_version(route, package) if not package.startswith("git+") else None
            purpose = (
                "without static tool exposure Open WebUI cannot reliably discover the modeling and solver tools"
                if route == "ansys-mechanical"
                else "the integration cannot be started with its validated transport/runtime contract"
            )
            raise RuntimeError(
                f"{server_label(route)} MCP command does not support required option {option}. "
                f"Installed package version: {version or 'unknown'}. Upgrade the MCP package; {purpose}."
            )
    return args


def missing_required_tool_groups(route: str, tool_names: Iterable[str]) -> Dict[str, List[str]]:
    """Return required capability groups absent from one generated OpenAPI schema."""
    metadata = OFFICIAL_SERVERS.get(route, {})
    required = (
        PHYSNEMO_REQUIRED_TOOL_GROUPS
        if route == PHYSNEMO_ROUTE
        else metadata.get("required_tool_groups", {})
    )
    available = {str(value).strip().strip("/") for value in tool_names if str(value).strip()}
    missing: Dict[str, List[str]] = {}
    for group, alternatives in required.items():
        candidates = [str(value) for value in alternatives]
        if candidates and not any(candidate in available for candidate in candidates):
            missing[str(group)] = candidates
    return missing


def generate_mcpo_config(
    installed: Dict[str, bool],
    scan_data: Dict[str, Any],
    matlab_binary: Optional[Path],
    physnemo_runtime: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    servers: Dict[str, Any] = {}
    for route, metadata in OFFICIAL_SERVERS.items():
        if installed.get(route) and server_command_installed(route, metadata):
            if route == "weknora" and (
                not WEKNORA_SECRET_FILE.is_file() or not WEKNORA_KB_CATALOG.is_file()
            ):
                raise RuntimeError(
                    "WeKnora was marked installed, but its validated credential/catalog files are missing"
                )
            servers[route] = named_stdio_server(
                route,
                str(server_command_path(route, metadata)),
                server_launch_args(route, metadata),
            )
    if installed.get(PHYSNEMO_ROUTE):
        runtime = dict(physnemo_runtime or {})
        if not runtime.get("configured") or not runtime.get("mcp_url"):
            raise RuntimeError(
                "PhysicsNeMo was marked installed but its managed NAT MCP runtime is incomplete"
            )
        servers[PHYSNEMO_ROUTE] = {
            "type": "streamable-http",
            "url": str(runtime["mcp_url"]),
        }
    if installed.get("matlab") and matlab_binary and matlab_binary.exists():
        args: List[str] = []
        matlab_root = get_matlab_root(scan_data)
        if matlab_root and matlab_mcp_supports_option(matlab_binary, "--matlab-root"):
            args.append(f"--matlab-root={matlab_root}")
        release = matlab_release_tuple(matlab_root)
        supports_existing = release is None or release >= (2023, 0)
        if matlab_mcp_supports_option(matlab_binary, "--matlab-session-mode"):
            args.append(
                "--matlab-session-mode=auto"
                if supports_existing
                else "--matlab-session-mode=new"
            )
        MATLAB_MCP_LOG_DIR.mkdir(parents=True, exist_ok=True)
        if matlab_mcp_supports_option(matlab_binary, "--log-folder"):
            args.append(f"--log-folder={MATLAB_MCP_LOG_DIR}")
        if matlab_mcp_supports_option(matlab_binary, "--log-level"):
            args.append("--log-level=info")
        servers["matlab"] = named_stdio_server("matlab", str(matlab_binary), args)
    for route, metadata in COMMUNITY_SERVERS.items():
        if installed.get(route) and command_installed(metadata["command"]):
            servers[route] = named_stdio_server(route, str(venv_bin(metadata["command"])))
    config = {"mcpServers": servers}
    atomic_write_json(MCPO_CONFIG, config, private=True)
    return config


def configured_routes() -> List[str]:
    config = read_json(MCPO_CONFIG, {"mcpServers": {}})
    return list(config.get("mcpServers", {}).keys())


def run_mcp_stdio_probe(arguments: List[str]) -> int:
    """Internal MCP-client probe; execute this mode with the isolated MCPO Python."""
    import asyncio
    parser = argparse.ArgumentParser(prog="engineering-mcp --mcp-stdio-probe")
    parser.add_argument("--config", required=True)
    parser.add_argument("--route", required=True)
    parsed = parser.parse_args(arguments)

    async def perform() -> Dict[str, Any]:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        config = read_json(Path(parsed.config), {"mcpServers": {}})
        entry = config.get("mcpServers", {}).get(parsed.route)
        if not isinstance(entry, dict) or not entry.get("command"):
            raise RuntimeError(f"No stdio configuration exists for route {parsed.route!r}")
        parameters = StdioServerParameters(
            command=str(entry["command"]),
            args=[str(value) for value in entry.get("args", [])],
            env={**os.environ, **{str(k): str(v) for k, v in entry.get("env", {}).items()}},
        )
        async with stdio_client(parameters) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                initialized = await session.initialize()
                listed = await session.list_tools()
                names = sorted(
                    str(getattr(tool, "name", ""))
                    for tool in getattr(listed, "tools", [])
                    if str(getattr(tool, "name", ""))
                )
                server_info = getattr(initialized, "serverInfo", None) or getattr(initialized, "server_info", None)
                return {
                    "success": True,
                    "route": parsed.route,
                    "server_name": str(getattr(server_info, "name", "") or ""),
                    "tool_count": len(names),
                    "tool_names": names,
                }

    try:
        payload = asyncio.run(perform())
        print(json.dumps(payload, ensure_ascii=True, separators=(",", ":")))
        return 0
    except Exception as exc:
        payload = {
            "success": False,
            "route": parsed.route,
            "error": f"{type(exc).__name__}: {exc}",
        }
        print(json.dumps(payload, ensure_ascii=True, separators=(",", ":")))
        return 3


def probe_configured_stdio_route(route: str, timeout: float = 45.0) -> Dict[str, Any]:
    python = mcpo_venv_bin("python")
    if not python.is_file():
        return {
            "success": False,
            "route": route,
            "error": f"isolated MCPO Python is missing: {python}",
        }
    command = [
        str(python),
        str(INSTALLED_SCRIPT),
        "--mcp-stdio-probe",
        "--config",
        str(MCPO_CONFIG),
        "--route",
        route,
    ]
    try:
        result = run(command, timeout=max(10.0, float(timeout)))
    except Exception as exc:
        return {"success": False, "route": route, "error": f"probe launch failed: {exc}"}
    output = (result.stdout or "").strip()
    payload: Optional[Dict[str, Any]] = None
    for raw_line in reversed(output.splitlines()):
        try:
            candidate = json.loads(raw_line.strip())
        except json.JSONDecodeError:
            continue
        if isinstance(candidate, dict) and candidate.get("route") == route:
            payload = candidate
            break
    if payload is None:
        payload = {
            "success": False,
            "route": route,
            "error": f"probe returned no JSON result (exit={result.returncode})",
        }
    payload["returncode"] = result.returncode
    payload["output_tail"] = output[-12000:]
    if result.returncode != 0:
        payload["success"] = False
    if route == "weknora" and payload.get("success"):
        names = {str(value) for value in payload.get("tool_names", [])}
        missing = missing_required_tool_groups(route, names)
        expected_aliases = {
            str(entry.get("tool_name"))
            for entry in read_json(WEKNORA_KB_CATALOG, {"knowledge_bases": []}).get("knowledge_bases", [])
            if isinstance(entry, dict) and str(entry.get("tool_name") or "")
        }
        missing_aliases = sorted(expected_aliases - names)
        payload["missing_required_tool_groups"] = missing
        payload["missing_kb_aliases"] = missing_aliases
        if missing or missing_aliases:
            payload["success"] = False
            payload["error"] = (
                f"stdio tools/list is incomplete: missing_groups={missing}, "
                f"missing_kb_aliases={missing_aliases}"
            )
    return payload


def connection_hosts(state: Dict[str, Any]) -> Dict[str, str]:
    dockerized = state.get("scan", {}).get("docker", {}).get("openwebui_container", False)
    hosts = {"user_or_desktop": "127.0.0.1"}
    if dockerized:
        hosts["admin_global"] = "host.docker.internal"
    else:
        hosts["admin_global"] = "127.0.0.1"
    return hosts


def build_connection_records(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    routes = configured_routes()
    port = int(state.get("mcpo_port", DEFAULT_MCPO_PORT))
    hosts = connection_hosts(state)
    records: List[Dict[str, Any]] = []
    for route in routes:
        label = server_label(route)
        user_base = f"http://{hosts['user_or_desktop']}:{port}/{route}"
        admin_base = f"http://{hosts['admin_global']}:{port}/{route}"
        docs_path = documentation_path(route)
        schema_path = openapi_schema_path(route)
        record = {
            "id": route.replace("-", "_"),
            "name": integration_title(route),
            "description": f"MCP/OpenAPI tools for {label}",
            "route": route,
            "type": "OpenAPI",
            "expected_openapi_title": integration_title(route),
            "user_or_desktop_url": user_base,
            "admin_global_url": admin_base,
            "spec_path": schema_path,
            "docs_path": docs_path,
            "openapi_schema": f"{user_base}/{schema_path}",
            "admin_openapi_schema": f"{admin_base}/{schema_path}",
            "documentation": f"{user_base}/{docs_path}",
            "admin_documentation": f"{admin_base}/{docs_path}",
            "documentation_note": (
                "Use the product-specific *-docs address only in a browser. "
                "Open WebUI connects to the base URL and the product-specific spec path."
            ),
        }
        if route == "matlab":
            record["visualization_tool"] = MATLAB_VISUALIZATION_TOOL
            record["visualization_note"] = (
                "Use evaluate_matlab_code_with_figures for plots. It returns MCP ImageContent; "
                "do not ask MATLAB to print a base64 variable. Open WebUI/model function calling must be Native."
            )
        if route == PHYSNEMO_ROUTE:
            runtime = state.get("physnemo_runtime", {})
            record["physnemo_mcp_url"] = runtime.get("mcp_url")
            record["physnemo_distro"] = runtime.get("distro")
            record["physnemo_install_dir"] = runtime.get("linux_install_dir")
            record["physnemo_nat_version"] = runtime.get("nat_version")
            record["physicsnemo_version"] = runtime.get("physicsnemo_version")
            record["physicsnemo_profile"] = runtime.get("physicsnemo_profile")
            record["physnemo_note"] = (
                "PhysicsNeMo tools run through NVIDIA NeMo Agent Toolkit in the managed WSL2 runtime. "
                "After physnemo__solve, physnemo__render_artifacts returns an inline Open WebUI gallery "
                "for images, SVG, code, JSON, tables, PDF and working signed downloads."
            )
        if route == "weknora":
            catalog = read_json(WEKNORA_KB_CATALOG, {"knowledge_bases": []})
            knowledge_bases = catalog.get("knowledge_bases", [])
            if not isinstance(knowledge_bases, list):
                knowledge_bases = []
            record["knowledge_base_catalog"] = str(WEKNORA_KB_CATALOG)
            record["weknora_service_url"] = catalog.get("service_url")
            record["weknora_rest_base_url"] = catalog.get("base_url")
            record["weknora_catalog_url"] = catalog.get("catalog_url")
            record["weknora_endpoint_source"] = catalog.get("endpoint_source")
            record["weknora_tenant_id"] = catalog.get("tenant_id")
            record["weknora_tenant_name"] = catalog.get("tenant_name")
            record["weknora_key_scope"] = catalog.get("scope_type")
            record["weknora_workspace_selection_source"] = catalog.get("workspace_selection_source")
            record["knowledge_base_count"] = len(knowledge_bases)
            record["knowledge_bases"] = [
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "shared": bool(item.get("shared")),
                    "search_tool": item.get("tool_name"),
                }
                for item in knowledge_bases
                if isinstance(item, dict)
            ]
            record["knowledge_base_note"] = (
                "The official WeKnora MCP tools remain available. Engineering MCP additionally exposes "
                "one read-only search operation per verified knowledge base so models need not guess a KB ID."
            )
        records.append(record)
    return records


def build_openwebui_import(state: Dict[str, Any], *, docker_backend: bool) -> List[Dict[str, Any]]:
    """Build an Open WebUI import payload with explicit unique ids/spec paths."""
    payload: List[Dict[str, Any]] = []
    for record in build_connection_records(state):
        base_url = record["admin_global_url"] if docker_backend else record["user_or_desktop_url"]
        payload.append(
            {
                "type": "openapi",
                "url": base_url,
                "spec_type": "url",
                "spec": "",
                "path": record["spec_path"],
                "auth_type": "bearer",
                "key": state.get("api_key", ""),
                "config": {"enable": True},
                "info": {
                    "id": record["id"],
                    "name": record["name"],
                    "description": record["description"],
                },
            }
        )
    return payload


def write_openwebui_connections(state: Dict[str, Any]) -> None:
    records = build_connection_records(state)
    data = {
        "generated_at": now_iso(),
        "bootstrapper_version": BOOTSTRAPPER_VERSION,
        "authentication": {"type": "bearer", "token": state.get("api_key")},
        "servers": records,
        "import_files": {
            "desktop_or_browser": str(OPENWEBUI_IMPORT_DESKTOP),
            "docker_backend": str(OPENWEBUI_IMPORT_DOCKER),
        },
    }
    atomic_write_json(OPENWEBUI_CONNECTIONS, data, private=True)
    atomic_write_json(
        OPENWEBUI_IMPORT_DESKTOP,
        build_openwebui_import(state, docker_backend=False),
        private=True,
    )
    atomic_write_json(
        OPENWEBUI_IMPORT_DOCKER,
        build_openwebui_import(state, docker_backend=True),
        private=True,
    )



def _openwebui_config_request(
    base_url: str,
    api_key: str,
    path: str,
    *,
    method: str = "GET",
    payload: Optional[Dict[str, Any]] = None,
    timeout: float = 45.0,
) -> Tuple[int, Any, str]:
    url = base_url.rstrip("/") + path
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": f"EngineeringMCP/{BOOTSTRAPPER_VERSION}",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(4 * 1024 * 1024)
            text = raw.decode("utf-8", errors="replace")
            try:
                value = json.loads(text) if text else {}
            except json.JSONDecodeError:
                value = None
            return int(response.status), value, text[:2000]
    except urllib.error.HTTPError as exc:
        raw = exc.read(256 * 1024)
        text = raw.decode("utf-8", errors="replace")
        try:
            value = json.loads(text) if text else None
        except json.JSONDecodeError:
            value = None
        return int(exc.code), value, text[:2000]
    except Exception as exc:
        return 0, None, f"{type(exc).__name__}: {exc}"


def _restart_openwebui_docker_for_schema_refresh(state: Dict[str, Any], base_url: str = "") -> Dict[str, Any]:
    result: Dict[str, Any] = {"attempted": False, "restarted": [], "healthy": False}
    docker = which("docker")
    rows = state.get("scan", {}).get("docker", {}).get("containers", [])
    if not docker or not isinstance(rows, list):
        result["reason"] = "Docker Open WebUI was not detected"
        return result
    names: List[str] = []
    for row in rows:
        parts = str(row).split("|", 1)
        name = parts[0].strip()
        image = parts[1].strip() if len(parts) > 1 else ""
        combined = f"{name} {image}".casefold()
        if name and ("open-webui" in combined or "openwebui" in combined):
            names.append(name)
    if not names:
        result["reason"] = "No running Open WebUI container name was found"
        return result
    result["attempted"] = True
    for name in dict.fromkeys(names):
        completed = run([docker, "restart", name], timeout=120)
        if completed.returncode == 0:
            result["restarted"].append(name)
        else:
            result.setdefault("errors", []).append(
                {"container": name, "detail": (completed.stdout or "")[-1000:]}
            )
    if not result["restarted"]:
        result["reason"] = "Open WebUI container restart failed"
        return result
    roots = [base_url, "http://127.0.0.1:8080", "http://127.0.0.1:3000"]
    deadline = time.time() + 90
    while time.time() < deadline:
        for root in roots:
            if not str(root or "").strip():
                continue
            probe = _probe_openwebui_root(str(root))
            if probe.get("healthy"):
                result["healthy"] = True
                result["health_probe"] = probe
                result["reason"] = (
                    "Open WebUI was restarted so it reloads the saved tool-server connections and their schemas"
                )
                return result
        time.sleep(2)
    result["reason"] = "Open WebUI container restarted but did not become healthy before timeout"
    return result



def _engineering_tool_router_self_test(source: str) -> Dict[str, Any]:
    """Compile and execute the managed filter without requiring bootstrapper Pydantic.

    The filter itself is loaded by Open WebUI, whose Python environment provides
    Pydantic.  The Engineering MCP bootstrapper intentionally uses a smaller,
    isolated environment where Pydantic is optional.  A tiny in-memory shim is
    therefore installed only for this local behavioral self-test when the real
    package is absent, and is removed again before the function returns.
    """
    import sys as _sys
    import types as _types

    previous_pydantic = _sys.modules.get("pydantic")
    installed_shim = False
    dependency_mode = "installed-pydantic"
    try:
        try:
            __import__("pydantic")
        except ModuleNotFoundError:
            dependency_mode = "stdlib-self-test-shim"
            shim = _types.ModuleType("pydantic")

            class _EngineeringRouterSelfTestBaseModel:
                def __init__(self, **values: Any):
                    annotations: Dict[str, Any] = {}
                    for base in reversed(type(self).__mro__):
                        annotations.update(getattr(base, "__annotations__", {}) or {})
                    for name in annotations:
                        if name in values:
                            value = values[name]
                        elif hasattr(type(self), name):
                            value = getattr(type(self), name)
                        else:
                            value = None
                        setattr(self, name, value)
                    for name, value in values.items():
                        if name not in annotations:
                            setattr(self, name, value)

            def _engineering_router_self_test_field(
                default: Any = None,
                *,
                default_factory: Any = None,
                **_kwargs: Any,
            ) -> Any:
                if default_factory is not None:
                    return default_factory()
                return default

            shim.BaseModel = _EngineeringRouterSelfTestBaseModel
            shim.Field = _engineering_router_self_test_field
            _sys.modules["pydantic"] = shim
            installed_shim = True

        namespace: Dict[str, Any] = {"__name__": "engineering_mcp_tool_router_self_test"}
        exec(compile(source, "<engineering-mcp-tool-router>", "exec"), namespace, namespace)
        filter_type = namespace.get("Filter")
        if filter_type is None:
            raise RuntimeError("Engineering MCP tool router source does not define Filter")
        instance = filter_type()
        inlet = getattr(instance, "inlet", None)
        if inlet is None:
            raise RuntimeError("Engineering MCP tool router source does not define inlet")

        async def exercise() -> Dict[str, Any]:
            request = {
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"{OPENWEBUI_ENGINEERING_TOOL_ROUTER_PROBE} Use MCP tool physnemo and send this request: "
                            "Create simulation of Karman vortex street by PINN, train it and visualize artifacts."
                        ),
                    }
                ],
            }
            metadata = {"chat_id": "engineering-mcp-router-self-test", "params": {"function_calling": "legacy"}}
            routed = await inlet(request, metadata, {"role": "admin"})
            internal = {
                "messages": [{"role": "user", "content": "PhysicsNeMo internal agent PINN task"}],
            }
            internal_metadata: Dict[str, Any] = {}
            untouched = await inlet(internal, internal_metadata, {"role": "admin"})
            return {
                "routed": routed,
                "metadata": metadata,
                "internal": untouched,
                "internal_metadata": internal_metadata,
            }

        import asyncio as _asyncio

        result = _asyncio.run(exercise())
        routed = result["routed"]
        tool_ids = routed.get("tool_ids") if isinstance(routed, dict) else None
        tool_choice = routed.get("tool_choice") if isinstance(routed, dict) else None
        forced_name = (
            tool_choice.get("function", {}).get("name")
            if isinstance(tool_choice, dict) and isinstance(tool_choice.get("function"), dict)
            else None
        )
        metadata = result["metadata"]
        internal = result["internal"]
        internal_metadata = result["internal_metadata"]
        checks = {
            "lifecycle_request_hook_present": callable(getattr(instance, "request", None)),
            "automatic_progress_enabled": bool(getattr(instance.valves, "automatic_progress", False)),
            "automatic_result_display_enabled": bool(getattr(instance.valves, "automatic_result_display", False)),
            "physnemo_tool_id_injected": isinstance(tool_ids, list) and "server:physnemo" in tool_ids,
            "native_mode_forced": metadata.get("params", {}).get("function_calling") == "native",
            "solve_forced": forced_name == "physnemo__solve",
            "internal_headless_call_not_routed": not bool(internal.get("tool_ids")),
            "internal_metadata_not_modified": not bool(internal_metadata),
            "no_late_body_params_shadow": "params" not in routed,
            "instruction_injected": any(
                isinstance(item, dict)
                and "[ENGINEERING_MCP_TOOL_ROUTER_V1]" in str(item.get("content") or "")
                for item in routed.get("messages", [])
            ),
        }
        if not all(checks.values()):
            raise RuntimeError(f"Engineering MCP tool router self-test failed: {checks}")
        return {
            "ok": True,
            "checks": checks,
            "tool_ids": tool_ids,
            "forced_function": forced_name,
            "dependency_mode": dependency_mode,
        }
    finally:
        if installed_shim:
            if previous_pydantic is None:
                _sys.modules.pop("pydantic", None)
            else:
                _sys.modules["pydantic"] = previous_pydantic


def _sync_openwebui_engineering_tool_router(
    base_url: str,
    api_key: str,
    route_ids: Iterable[str],
) -> Dict[str, Any]:
    """Install an active global inlet filter that restores missing server:* tool_ids.

    Open WebUI 0.11.x can display a global OpenAPI Tool Server while omitting its
    tool id from the chat payload.  In that case the model receives no function
    schemas and may print pseudo tool-call markup.  The managed filter runs before
    tool resolution and only attaches routes explicitly named by the user's saved
    chat request.  Headless API calls (including the nested PhysicsNeMo agent) are
    intentionally left untouched to prevent recursion.
    """
    source = OPENWEBUI_ENGINEERING_TOOL_ROUTER_SOURCE
    source_hash = hashlib.sha256(source.encode("utf-8")).hexdigest()
    report: Dict[str, Any] = {
        "contract": OPENWEBUI_ENGINEERING_TOOL_ROUTER_CONTRACT,
        "filter_contract": OPENWEBUI_ENGINEERING_TOOL_ROUTER_FILTER_CONTRACT,
        "id": OPENWEBUI_ENGINEERING_TOOL_ROUTER_ID,
        "source_sha256": source_hash,
        "route_ids": sorted({str(value) for value in route_ids if str(value)}),
        "created": False,
        "updated": False,
        "activated": False,
        "globalized": False,
        "ready": False,
    }
    try:
        report["self_test"] = _engineering_tool_router_self_test(source)
    except Exception as exc:
        report["error"] = f"local self-test failed: {type(exc).__name__}: {exc}"
        atomic_write_json(OPENWEBUI_ENGINEERING_TOOL_ROUTER_REPORT, report, private=True)
        return report

    function_id = urllib.parse.quote(OPENWEBUI_ENGINEERING_TOOL_ROUTER_ID, safe="")
    get_path = f"/api/v1/functions/id/{function_id}"
    status, existing, detail = _openwebui_config_request(base_url, api_key, get_path, timeout=45)
    report["initial_http_status"] = status
    payload = {
        "id": OPENWEBUI_ENGINEERING_TOOL_ROUTER_ID,
        "name": "Engineering MCP Tool Router",
        "content": source,
        "meta": {
            "description": (
                "Managed global filter: attaches server:* Engineering MCP tool ids to explicit requests "
                "before Open WebUI native tool resolution."
            ),
            "manifest": {
                "managed_by": "engineering-mcp-unified",
                "bootstrapper_version": BOOTSTRAPPER_VERSION,
                "contract": OPENWEBUI_ENGINEERING_TOOL_ROUTER_CONTRACT,
                "source_sha256": source_hash,
            },
        },
    }
    if status == 200 and isinstance(existing, dict):
        write_path = f"/api/v1/functions/id/{function_id}/update"
        write_status, written, write_detail = _openwebui_config_request(
            base_url, api_key, write_path, method="POST", payload=payload, timeout=90
        )
        report["updated"] = 200 <= write_status < 300
    elif status in {400, 401, 404}:
        write_status, written, write_detail = _openwebui_config_request(
            base_url, api_key, "/api/v1/functions/create", method="POST", payload=payload, timeout=90
        )
        report["created"] = 200 <= write_status < 300
    else:
        report["error"] = f"cannot read existing filter (HTTP {status}): {detail}"
        atomic_write_json(OPENWEBUI_ENGINEERING_TOOL_ROUTER_REPORT, report, private=True)
        return report
    report["write_http_status"] = write_status
    if not (200 <= write_status < 300):
        report["error"] = f"filter create/update failed (HTTP {write_status}): {write_detail}"
        atomic_write_json(OPENWEBUI_ENGINEERING_TOOL_ROUTER_REPORT, report, private=True)
        return report

    status, current, detail = _openwebui_config_request(base_url, api_key, get_path, timeout=45)
    if status != 200 or not isinstance(current, dict):
        report["error"] = f"filter could not be read after write (HTTP {status}): {detail}"
        atomic_write_json(OPENWEBUI_ENGINEERING_TOOL_ROUTER_REPORT, report, private=True)
        return report

    if not bool(current.get("is_active")):
        toggle_status, _, toggle_detail = _openwebui_config_request(
            base_url,
            api_key,
            f"/api/v1/functions/id/{function_id}/toggle",
            method="POST",
            payload={},
            timeout=45,
        )
        report["activate_http_status"] = toggle_status
        if not (200 <= toggle_status < 300):
            report["error"] = f"filter activation failed (HTTP {toggle_status}): {toggle_detail}"
            atomic_write_json(OPENWEBUI_ENGINEERING_TOOL_ROUTER_REPORT, report, private=True)
            return report
        report["activated"] = True

    status, current, detail = _openwebui_config_request(base_url, api_key, get_path, timeout=45)
    if status != 200 or not isinstance(current, dict):
        report["error"] = f"filter could not be read after activation (HTTP {status}): {detail}"
        atomic_write_json(OPENWEBUI_ENGINEERING_TOOL_ROUTER_REPORT, report, private=True)
        return report
    if not bool(current.get("is_global")):
        global_status, _, global_detail = _openwebui_config_request(
            base_url,
            api_key,
            f"/api/v1/functions/id/{function_id}/toggle/global",
            method="POST",
            payload={},
            timeout=45,
        )
        report["global_http_status"] = global_status
        if not (200 <= global_status < 300):
            report["error"] = f"filter global activation failed (HTTP {global_status}): {global_detail}"
            atomic_write_json(OPENWEBUI_ENGINEERING_TOOL_ROUTER_REPORT, report, private=True)
            return report
        report["globalized"] = True

    status, current, detail = _openwebui_config_request(base_url, api_key, get_path, timeout=45)
    report["final_http_status"] = status
    if status == 200 and isinstance(current, dict):
        report["type"] = current.get("type")
        report["active"] = bool(current.get("is_active"))
        report["global"] = bool(current.get("is_global"))
        content_hash = hashlib.sha256(str(current.get("content") or "").encode("utf-8")).hexdigest()
        report["installed_source_sha256"] = content_hash
        report["source_matches"] = hmac.compare_digest(content_hash, source_hash)
        report["ready"] = bool(
            current.get("type") == "filter"
            and report["active"]
            and report["global"]
            and report["source_matches"]
        )
    else:
        report["error"] = f"filter final verification failed (HTTP {status}): {detail}"
    atomic_write_json(OPENWEBUI_ENGINEERING_TOOL_ROUTER_REPORT, report, private=True)
    return report

def sync_physnemo_openwebui_tool_server(state: Dict[str, Any], options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Persist and live-load all Engineering MCP OpenAPI servers in native Open WebUI."""
    options = options or state.get("options", {}) or {}
    report: Dict[str, Any] = {
        "checked_at": now_iso(),
        "contract": PHYSNEMO_OPENWEBUI_SCHEMA_SYNC_CONTRACT,
        "native_contract": OPENWEBUI_NATIVE_DATABASE_SYNC_CONTRACT,
        "readiness_contract": OPENWEBUI_PHYSNEMO_READINESS_CONTRACT,
        "attempted": False,
        "updated": False,
        "verified": False,
        "all_engineering_routes_loaded": False,
    }
    secret = read_json(PHYSNEMO_AGENT_SECRET_FILE)
    base_url = str(secret.get("openwebui_base_url") or "").rstrip("/")
    api_key = str(secret.get("openwebui_api_key") or "")
    native_database = str(secret.get("openwebui_database") or options.get("openwebui_database") or "")

    if (not api_key or not native_database) and options.get("openwebui_native_sync") is not False:
        discovered = _discover_openwebui_sqlite(native_database)
        report["database_discovery"] = discovered
        if discovered.get("found"):
            native_database = str(discovered["path"])
            try:
                access = _ensure_openwebui_managed_api_key(
                    native_database,
                    enable_dlp_repair=bool(options.get("openwebui_dlp_repair", True)),
                )
                report["native_access"] = _safe_native_openwebui_summary(access)
                api_key = str(access.get("api_key") or api_key)
                if not base_url:
                    base_url, _ = _discover_local_openwebui_base_url("http://127.0.0.1:8080")
                secret.update(
                    {
                        "openwebui_base_url": base_url,
                        "openwebui_api_key": api_key,
                        "openwebui_database": native_database,
                        "managed_openwebui_api_key_id": str(access.get("api_key_id") or ""),
                    }
                )
                atomic_write_json(PHYSNEMO_AGENT_SECRET_FILE, secret, private=True)
            except Exception as exc:
                report["native_access_error"] = f"{type(exc).__name__}: {exc}"

    if not base_url:
        base_url, attempts = _discover_local_openwebui_base_url("http://127.0.0.1:8080")
        report["openwebui_probe_attempts"] = attempts
    if not base_url or not api_key:
        report.update(
            {
                "reason": (
                    "Open WebUI is reachable but no managed/admin API key could be provisioned. "
                    "The PhysicsNeMo schema was not loaded into the live chat backend."
                ),
                "database": native_database or None,
                "import_file": str(OPENWEBUI_IMPORT_DESKTOP),
            }
        )
        atomic_write_json(PHYSNEMO_OPENWEBUI_SYNC_REPORT, report, private=True)
        return report

    report["attempted"] = True
    report["base_url"] = base_url
    report["database"] = native_database or None
    status, response, detail = _openwebui_config_request(
        base_url, api_key, "/api/v1/configs/tool_servers"
    )
    report["get_http_status"] = status
    if status != 200 or not isinstance(response, dict):
        report["reason"] = "Open WebUI did not allow reading the global tool-server configuration."
        report["detail"] = detail
        atomic_write_json(PHYSNEMO_OPENWEBUI_SYNC_REPORT, report, private=True)
        return report

    current = response.get("TOOL_SERVER_CONNECTIONS")
    if not isinstance(current, list):
        current = []
    # A discovered local SQLite database proves that this is the native/Desktop
    # backend even when an unrelated or stale Open WebUI Docker container also
    # exists on the machine.  Use loopback URLs for that backend.
    docker_backend = bool(
        state.get("scan", {}).get("docker", {}).get("openwebui_container")
    ) and not bool(native_database)
    desired = build_openwebui_import(state, docker_backend=docker_backend)
    report["docker_backend"] = docker_backend
    desired_by_id = {
        str((item.get("info") or {}).get("id") or ""): json.loads(json.dumps(item))
        for item in desired
        if isinstance(item, dict) and str((item.get("info") or {}).get("id") or "")
    }
    for connection_id, item in desired_by_id.items():
        item.setdefault("info", {})["description"] = (
            f"Engineering MCP route {connection_id}; schema revision {BOOTSTRAPPER_VERSION}"
        )

    merged: List[Dict[str, Any]] = []
    replaced_ids: List[str] = []
    for connection in current:
        if not isinstance(connection, dict):
            continue
        info = connection.get("info") if isinstance(connection.get("info"), dict) else {}
        connection_id = str(info.get("id") or "")
        connection_url = str(connection.get("url") or "").rstrip("/")
        matched_id = connection_id if connection_id in desired_by_id else ""
        if not matched_id:
            for candidate_id in desired_by_id:
                if connection_url.endswith(f"/{candidate_id}"):
                    matched_id = candidate_id
                    break
        if matched_id:
            if matched_id not in replaced_ids:
                merged.append(desired_by_id[matched_id])
                replaced_ids.append(matched_id)
            continue
        merged.append(connection)
    for connection_id, item in desired_by_id.items():
        if connection_id not in replaced_ids:
            merged.append(item)

    post_status, post_response, post_detail = _openwebui_config_request(
        base_url,
        api_key,
        "/api/v1/configs/tool_servers",
        method="POST",
        payload={"TOOL_SERVER_CONNECTIONS": merged},
        timeout=120,
    )
    report.update(
        {
            "post_http_status": post_status,
            "connection_count_before": len(current),
            "connection_count_after": len(merged),
            "engineering_connection_ids": sorted(desired_by_id),
            "connections_replaced": sorted(replaced_ids),
        }
    )
    if post_status != 200:
        report["reason"] = "Open WebUI refused the live tool-server refresh request."
        report["detail"] = post_detail
        atomic_write_json(PHYSNEMO_OPENWEBUI_SYNC_REPORT, report, private=True)
        return report
    report["updated"] = True

    verification_rows: List[Dict[str, Any]] = []
    for connection_id, item in desired_by_id.items():
        verify_status, verify_response, verify_detail = _openwebui_config_request(
            base_url,
            api_key,
            "/api/v1/configs/tool_servers/verify",
            method="POST",
            payload=item,
            timeout=90,
        )
        verification_rows.append(
            {
                "id": connection_id,
                "http_status": verify_status,
                "ok": 200 <= verify_status < 300,
                "detail": None if 200 <= verify_status < 300 else verify_detail,
                "response_type": type(verify_response).__name__ if verify_response is not None else None,
            }
        )
    report["connection_verification"] = verification_rows
    physnemo_row = next((row for row in verification_rows if row["id"] == PHYSNEMO_ROUTE), None)
    report["verified"] = bool(physnemo_row and physnemo_row.get("ok"))
    report["all_engineering_routes_loaded"] = bool(verification_rows) and all(
        row.get("ok") for row in verification_rows
    )
    report["tool_router"] = _sync_openwebui_engineering_tool_router(
        base_url,
        api_key,
        desired_by_id.keys(),
    )

    if native_database:
        try:
            connection = sqlite3.connect(native_database, timeout=15)
            try:
                row = connection.execute(
                    "SELECT type,is_active,is_global FROM function WHERE id='pseudo_anonymization' LIMIT 1"
                ).fetchone()
                tool_present = bool(
                    connection.execute("SELECT 1 FROM tool WHERE id='anonymizovat' LIMIT 1").fetchone()
                )
                dlp = {
                    "contract": OPENWEBUI_DLP_PREFLIGHT_CONTRACT,
                    "tool_present": tool_present,
                    "filter_present": bool(row),
                    "type": str(row[0]) if row else None,
                    "active": bool(row[1]) if row else None,
                    "global": bool(row[2]) if row else None,
                }
                dlp["ready"] = (not tool_present) or bool(
                    row and str(row[0]) == "filter" and row[1] and row[2]
                )
                report["dlp"] = dlp
                atomic_write_json(OPENWEBUI_DLP_PREFLIGHT_REPORT, dlp, private=True)
            finally:
                connection.close()
        except Exception as exc:
            report["dlp"] = {"ready": False, "error": f"{type(exc).__name__}: {exc}"}

    report["chat_tool_registration_ready"] = bool(
        report.get("verified")
        and report.get("all_engineering_routes_loaded")
        and report.get("tool_router", {}).get("ready")
        and report.get("dlp", {}).get("ready", True)
    )
    native = state.get("physnemo_native_tools_preflight") or {}
    report["physnemo_model_tools_verified"] = _physnemo_model_execution_verified(native)
    report["physnemo_native_tools_verified"] = bool(
        report["physnemo_model_tools_verified"] and native.get("native_tool_calls_verified") is True)
    report["physnemo_selected_tool_transport"] = native.get("selected_tool_transport")
    report["chat_tool_execution_ready"] = bool(
        report["chat_tool_registration_ready"] and report["physnemo_model_tools_verified"])
    report["readiness_scope"] = "Registration, native API support and model-mediated JSON action execution are separate; scientific correctness is not checked."
    if not report["chat_tool_execution_ready"]:
        if not report.get("verified") or not report.get("all_engineering_routes_loaded"):
            report["reason"] = "Open WebUI did not finish loading one or more live Engineering MCP tool schemas."
        elif not report.get("tool_router", {}).get("ready"):
            router_error = str(report.get("tool_router", {}).get("error") or "unknown router error")
            report["reason"] = f"The managed Engineering MCP tool-id router is not ready: {router_error}"
        elif not report.get("dlp", {}).get("ready", True):
            report["reason"] = "A required Open WebUI DLP filter is not active and global."
        elif not report["physnemo_model_tools_verified"]:
            report["reason"] = "Open WebUI tools are registered, but PhysicsNeMo model-mediated execution is NOT verified. See physnemo-native-tools-preflight.json."
        else:
            report["reason"] = "Open WebUI chat tool execution readiness could not be established."
    atomic_write_json(PHYSNEMO_OPENWEBUI_SYNC_REPORT, report, private=True)
    atomic_write_json(OPENWEBUI_NATIVE_SYNC_REPORT, report, private=True)
    return report

def print_webui_config(state: Optional[Dict[str, Any]] = None) -> None:
    state = state or load_state()
    if not state:
        print("No installed state. Run --install or --resume first.")
        return
    records = build_connection_records(state)
    print("\n=== Open WebUI configuration ===")
    if records:
        print("Add every product as a separate OpenAPI server.")
        print("Each entry has a unique Open WebUI id and a unique *-openapi.json spec path.")
        print(f"Authentication: Bearer {state.get('api_key')}")
        dockerized = state.get("scan", {}).get("docker", {}).get("openwebui_container", False)
        for index, record in enumerate(records, start=1):
            print(f"\n[{index}] ID: {record['id']}")
            print(f"    Name: {record['name']}")
            print("    Type: OpenAPI")
            print(f"    Base URL (User/Desktop): {record['user_or_desktop_url']}")
            if dockerized:
                print(f"    Base URL (Admin/Global from Docker): {record['admin_global_url']}")
            print(f"    OpenAPI spec path: {record['spec_path']}")
            print(f"    Unique schema URL: {record['openapi_schema']}")
            print(f"    Unique browser docs: {record['documentation']}")
            print("    Generic /docs and /openapi.json endpoints are disabled by design.")
        if any(record.get("route") == "matlab" for record in records):
            print("\nMATLAB visualization:")
            print(f"    Preferred tool: {MATLAB_VISUALIZATION_TOOL}")
            print("    It exports open MATLAB figures and returns real MCP image content.")
            print("    Do not manually base64-encode PNG files in MATLAB.")
            print("    Open WebUI model setting: Advanced Params > Function Calling = Native.")
            print("    If chat displays raw <|start|>...<|call|> text, the model provider did not return")
            print("    a structured tool_calls object; no request reached this gateway.")
        physnemo_record = next((record for record in records if record.get("route") == PHYSNEMO_ROUTE), None)
        if physnemo_record:
            print("\nPhysicsNeMo / NeMo Agent Toolkit:")
            print(f"    MCP route: {physnemo_record.get('physnemo_mcp_url') or '(not recorded)'}")
            print(f"    WSL2 distro: {physnemo_record.get('physnemo_distro') or '?'}")
            print(f"    Managed path: {physnemo_record.get('physnemo_install_dir') or '?'}")
            print(
                f"    Versions: nvidia-nat={physnemo_record.get('physnemo_nat_version') or '?'}, "
                f"PhysicsNeMo={physnemo_record.get('physicsnemo_version') or '?'} "
                f"({physnemo_record.get('physicsnemo_profile') or '?'})"
            )
        weknora_record = next((record for record in records if record.get("route") == "weknora"), None)
        if weknora_record:
            print("\nWeKnora knowledge bases:")
            print(f"    Service/public target: {weknora_record.get('weknora_service_url') or '(not recorded)'}")
            print(f"    REST API base used: {weknora_record.get('weknora_rest_base_url') or '(not recorded)'}")
            print(f"    Catalog request: {weknora_record.get('weknora_catalog_url') or '(not recorded)'}")
            print(f"    Endpoint source: {weknora_record.get('weknora_endpoint_source') or '(not recorded)'}")
            print(
                "    Workspace: "
                f"{weknora_record.get('weknora_tenant_name') or '?'} "
                f"(tenant_id={weknora_record.get('weknora_tenant_id') or '?'}, "
                f"key_scope={weknora_record.get('weknora_key_scope') or 'unknown'})"
            )
            print(
                f"    Verified bases: {weknora_record.get('knowledge_base_count', 0)} "
                f"(catalog: {WEKNORA_KB_CATALOG})"
            )
            for item in weknora_record.get("knowledge_bases", [])[:50]:
                scope = "shared" if item.get("shared") else "owned"
                print(
                    f"    - {item.get('name')} [{item.get('id')}] ({scope}) -> "
                    f"{item.get('search_tool')}"
                )
            if len(weknora_record.get("knowledge_bases", [])) > 50:
                print("    - ... additional bases are recorded in the generated catalog JSON")
        print("\nReady-to-import Open WebUI JSON:")
        print(f"    Desktop/browser: {OPENWEBUI_IMPORT_DESKTOP}")
        print(f"    Docker backend : {OPENWEBUI_IMPORT_DOCKER}")
    else:
        print("No MCPO-backed server is configured. The background proxy is therefore not required.")

    fusion = state.get("scan", {}).get("applications", {}).get("fusion", {})
    if fusion.get("found"):
        print("\n[Direct MCP] ID: autodesk_fusion")
        print("    Name: Engineering MCP - Autodesk Fusion")
        print("    Type: MCP (Streamable HTTP)")
        print("    URL: http://127.0.0.1:27182")
        print("    Enable Fusion > Preferences > General > API > Fusion MCP Server.")

    print(f"\nGenerated connection inventory: {OPENWEBUI_CONNECTIONS}")
    print(f"State/key file: {STATE_FILE}")


def http_json(url: str, api_key: Optional[str], timeout: float = 4.0) -> Tuple[int, Optional[Dict[str, Any]], str]:
    headers = {"Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(body)
            except json.JSONDecodeError:
                parsed = None
            return response.status, parsed, body[:300]
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return exc.code, None, body[:300]
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return 0, None, str(exc)


def http_post_json(
    url: str,
    api_key: Optional[str],
    payload: Dict[str, Any],
    timeout: float = 300.0,
) -> Tuple[int, Any, str]:
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            try:
                parsed: Any = json.loads(raw)
            except json.JSONDecodeError:
                parsed = None
            return response.status, parsed, raw[:1000]
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = None
        return exc.code, parsed, raw[:1000]
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return 0, None, str(exc)


def weknora_mcp_runtime_test(
    state: Optional[Dict[str, Any]] = None,
    *,
    timeout: float = DEFAULT_WEKNORA_HEALTH_TIMEOUT,
    quiet: bool = False,
) -> Dict[str, Any]:
    """Verify the real MCPO route and every KB discovered during provisioning."""
    state = state or load_state()
    report: Dict[str, Any] = {
        "checked_at": now_iso(),
        "success": False,
        "list_http_status": 0,
        "knowledge_bases": [],
    }
    if not state:
        report["error"] = "No installed state"
        return report
    if "weknora" not in configured_routes():
        report["skipped"] = True
        report["error"] = "WeKnora route is not configured"
        return report
    if not wait_for_gateway(state, timeout=max(10.0, float(timeout)), quiet=quiet):
        report["error"] = "MCPO gateway did not become ready"
        return report

    port = int(state.get("mcpo_port", DEFAULT_MCPO_PORT))
    base = f"http://127.0.0.1:{port}/weknora"
    if not quiet:
        print("\n=== WeKnora MCP runtime verification ===")
        print(f"POST {base}/list_knowledge_bases")
    status, response, detail = http_post_json(
        f"{base}/list_knowledge_bases",
        state.get("api_key"),
        {},
        timeout=max(30.0, float(timeout)),
    )
    report["list_http_status"] = status
    report["list_response_preview"] = detail
    if status != 200:
        report["error"] = (
            f"WeKnora MCP list_knowledge_bases failed (HTTP {status or 'unreachable'}): {detail}"
        )
        return report

    entries = _weknora_catalog_entries(WEKNORA_KB_CATALOG)
    failures: List[Dict[str, Any]] = []
    checked: List[Dict[str, Any]] = []
    for index, entry in enumerate(entries, start=1):
        if not quiet:
            print(
                f"[*] Verifying WeKnora KB {index}/{len(entries)}: "
                f"{entry.get('name')} [{entry.get('id')}]"
            )
        detail_status, detail_response, detail_preview = http_post_json(
            f"{base}/get_knowledge_base",
            state.get("api_key"),
            {"kb_id": entry["id"]},
            timeout=max(30.0, float(timeout)),
        )
        try:
            response_text = json.dumps(detail_response, ensure_ascii=False)
        except (TypeError, ValueError):
            response_text = repr(detail_response)
        valid = detail_status == 200 and str(entry["id"]) in response_text
        result = {
            "id": entry["id"],
            "name": entry["name"],
            "shared": bool(entry.get("shared")),
            "search_tool": entry["tool_name"],
            "http_status": detail_status,
            "verified": valid,
        }
        checked.append(result)
        if not valid:
            failures.append({**result, "detail": detail_preview[:500]})

    report["knowledge_bases"] = checked
    report["knowledge_base_count"] = len(entries)
    report["failures"] = failures
    report["success"] = not failures
    if failures:
        report["error"] = (
            f"{len(failures)} individual WeKnora knowledge base(s) were not readable through MCP"
        )
    elif not quiet:
        print(
            f"[+] WeKnora MCP runtime test passed; {len(entries)} individual knowledge base(s) "
            "are available, including fixed-KB search operations."
        )
    atomic_write_json(WEKNORA_RUNTIME_REPORT, report, private=True)
    return report


def _collect_data_image_uris(value: Any) -> List[str]:
    found: List[str] = []
    if isinstance(value, str):
        if value.startswith("data:image/") and ";base64," in value:
            found.append(value)
    elif isinstance(value, list):
        for item in value:
            found.extend(_collect_data_image_uris(item))
    elif isinstance(value, dict):
        for item in value.values():
            found.extend(_collect_data_image_uris(item))
    return found


def matlab_mcp_tool_runtime_test(
    state: Optional[Dict[str, Any]] = None,
    *,
    timeout: float = DEFAULT_MATLAB_HEALTH_TIMEOUT,
    quiet: bool = False,
) -> Dict[str, Any]:
    """Exercise evaluate_matlab_code through the real MCPO route.

    The direct MATLAB batch preflight validates the local installation and
    license.  This second probe validates the exact path used by Open WebUI:
    MCPO -> stdio bridge -> official MATLAB MCP Server -> MATLAB.  Error 5201
    can otherwise remain hidden until the first user tool call.
    """
    state = state or load_state()
    result: Dict[str, Any] = {
        "checked_at": now_iso(),
        "healthy": False,
        "error_5201": False,
        "http_status": 0,
        "url": None,
        "matlab_pids_before": [],
        "matlab_pids_after": [],
    }
    if not state:
        result["error"] = "No installed state"
        return result
    if "matlab" not in configured_routes():
        result["skipped"] = True
        result["error"] = "MATLAB route is not configured"
        return result
    if not wait_for_gateway(state, timeout=max(10.0, float(timeout)), quiet=quiet):
        result["error"] = "MCPO gateway did not become ready"
        result["gateway_diagnostics"] = gateway_diagnostics(state)
        return result

    before = windows_process_ids("MATLAB.exe") if sys.platform.startswith("win") else []
    result["matlab_pids_before"] = before
    port = int(state.get("mcpo_port", DEFAULT_MCPO_PORT))
    url = f"http://127.0.0.1:{port}/matlab/{MATLAB_EVALUATE_TOOL}"
    result["url"] = url
    code = f"fprintf(1,'{MATLAB_TOOL_PREFLIGHT_MARKER}\\n');"
    if not quiet:
        print("\n=== MATLAB MCP runtime verification ===")
        print(f"POST {url}")
        print("Testing the same MATLAB tool route that Open WebUI will call...")

    started = time.monotonic()
    status, response, detail = http_post_json(
        url,
        state.get("api_key"),
        {"code": code},
        timeout=max(60.0, float(timeout)),
    )
    result["elapsed_seconds"] = round(time.monotonic() - started, 3)
    result["http_status"] = status
    result["response_preview"] = detail
    try:
        response_text = json.dumps(response, ensure_ascii=True) if response is not None else ""
    except (TypeError, ValueError):
        response_text = repr(response)
    diagnostic_text = "\n".join(
        (
            response_text,
            detail or "",
            _tail_log(MATLAB_MCP_LOG_DIR / "matlab-mcp-server.log", line_count=120),
            _tail_log(LOG_DIR / "mcpo.log", line_count=120),
            recent_mathworks_log_text(max_files=8, max_bytes_per_file=128_000),
        )
    )
    result["healthy"] = status == 200 and MATLAB_TOOL_PREFLIGHT_MARKER in diagnostic_text
    result["error_5201"] = (not result["healthy"]) and matlab_error_5201(diagnostic_text)
    result["diagnostic_tail"] = diagnostic_text[-20_000:]
    result["matlab_pids_after"] = (
        windows_process_ids("MATLAB.exe") if sys.platform.startswith("win") else []
    )
    if result["healthy"]:
        if not quiet:
            print("[+] MATLAB MCP tool runtime test passed.")
    else:
        if status == 0:
            result["error"] = f"MATLAB MCP endpoint is unreachable: {detail}"
        elif result["error_5201"]:
            result["error"] = "MATLAB MCP tool call reported MathWorks licensing error 5201"
        else:
            result["error"] = (
                f"MATLAB MCP tool call did not return the expected marker (HTTP {status})"
            )
        if not quiet:
            print(f"[!] {result['error']}")
    return result


def terminate_matlab_processes_created_by_probe(probe: Dict[str, Any]) -> List[int]:
    """Terminate only MATLAB processes that appeared during our health probe."""
    if not sys.platform.startswith("win"):
        return []
    before = {int(pid) for pid in probe.get("matlab_pids_before", [])}
    after = {int(pid) for pid in windows_process_ids("MATLAB.exe")}
    created = sorted(after - before)
    stopped: List[int] = []
    for pid in created:
        completed = run(["taskkill", "/PID", str(pid), "/T", "/F"])
        if completed.returncode == 0:
            stopped.append(pid)
    if stopped:
        time.sleep(2)
    return stopped


def ensure_matlab_mcp_tool_runtime(
    state: Dict[str, Any],
    scan_data: Dict[str, Any],
    matlab_binary: Path,
    *,
    auto_repair: bool,
    force_matlab_close: bool,
    health_timeout: float,
) -> Tuple[Dict[str, Any], bool, Dict[str, Any]]:
    """Verify and, for error 5201, repair the real MCP execution path.

    Returns (report, gateway_started, latest_endpoint_verification).
    """
    report: Dict[str, Any] = {
        "started_at": now_iso(),
        "auto_repair": auto_repair,
        "initial_probe": None,
        "repair": None,
        "retry_probe": None,
        "gateway_restart": None,
        "success": False,
    }
    initial = matlab_mcp_tool_runtime_test(state, timeout=health_timeout, quiet=False)
    report["initial_probe"] = initial
    report["success"] = bool(initial.get("healthy"))
    verification: Dict[str, Any] = {}
    gateway_started = True

    if report["success"]:
        report["completed_at"] = now_iso()
        atomic_write_json(MATLAB_MCP_RUNTIME_REPORT, report, private=True)
        return report, gateway_started, verification

    if not initial.get("error_5201") or not auto_repair:
        report["error"] = initial.get("error") or "MATLAB MCP runtime probe failed"
        report["completed_at"] = now_iso()
        atomic_write_json(MATLAB_MCP_RUNTIME_REPORT, report, private=True)
        return report, gateway_started, verification

    print("[!] Error 5201 occurred on the actual MCP tool route; starting automatic repair and retry.")
    # Stop MCPO first. This normally tears down the MCP-managed MATLAB child.
    # Any residual MATLAB process created only by our probe is safe to remove;
    # pre-existing user sessions are never touched unless -ForceCloseMatlab was
    # explicitly supplied.
    stop_background()
    report["probe_created_matlab_pids_stopped"] = terminate_matlab_processes_created_by_probe(initial)
    repair = repair_matlab_service_host(
        scan_data,
        force_matlab_close=force_matlab_close,
        health_timeout=health_timeout,
    )
    report["repair"] = repair
    if not repair.get("success"):
        report["error"] = repair.get("error") or "MathWorks Service Host repair failed"
        report["completed_at"] = now_iso()
        atomic_write_json(MATLAB_MCP_RUNTIME_REPORT, report, private=True)
        return report, False, verification

    # The supported Service Host reset removes MATLABConnector. Re-run the
    # official MCP toolbox setup so auto/existing session support remains valid.
    report["toolbox_after_repair"] = setup_matlab_mcp_toolbox(matlab_binary, scan_data)
    gateway_started = start_background(state)
    report["gateway_restart"] = gateway_started
    if not gateway_started:
        report["error"] = "MATLAB repair passed, but MCPO did not restart"
        report["completed_at"] = now_iso()
        atomic_write_json(MATLAB_MCP_RUNTIME_REPORT, report, private=True)
        return report, False, verification

    verification = check_endpoints(state, quiet=False, wait_timeout=0.0)
    retry = matlab_mcp_tool_runtime_test(state, timeout=health_timeout, quiet=False)
    report["retry_probe"] = retry
    report["success"] = bool(retry.get("healthy"))
    if not report["success"]:
        report["error"] = retry.get("error") or "MATLAB MCP runtime retry failed"
    report["completed_at"] = now_iso()
    atomic_write_json(MATLAB_MCP_RUNTIME_REPORT, report, private=True)
    return report, gateway_started, verification


def matlab_image_smoke_test(
    state: Optional[Dict[str, Any]] = None,
    *,
    startup_timeout: float = DEFAULT_STARTUP_TIMEOUT,
) -> bool:
    """Call the MATLAB image endpoint directly, bypassing the LLM/tool parser."""
    state = state or load_state()
    if not state:
        print("[FAIL] No installed state. Run -Install or -Resume first.")
        return False
    if "matlab" not in configured_routes():
        print("[FAIL] MATLAB is not configured in MCPO.")
        return False
    if not wait_for_gateway(state, timeout=startup_timeout, quiet=False):
        print("[FAIL] Gateway did not become ready.")
        print_gateway_diagnostics(state)
        return False

    port = int(state.get("mcpo_port", DEFAULT_MCPO_PORT))
    url = f"http://127.0.0.1:{port}/matlab/{MATLAB_VISUALIZATION_TOOL}"
    code = """x = linspace(0, 2*pi, 300);
f = figure('Color', 'w', 'Name', 'Engineering MCP visualization test', 'NumberTitle', 'off');
plot(x, sin(x), 'LineWidth', 2);
grid on;
xlabel('x'); ylabel('sin(x)');
title('Engineering MCP MATLAB image test');
"""
    print("\n=== MATLAB image smoke test ===")
    print(f"POST {url}")
    print("This bypasses the language model and tests MATLAB -> MCP ImageContent -> MCPO directly.")
    status, response, detail = http_post_json(
        url,
        state.get("api_key"),
        {"code": code, "max_figures": 1, "resolution": 120},
        timeout=max(60.0, float(startup_timeout)),
    )
    if status != 200:
        print(f"[FAIL] HTTP {status or 'unreachable'}: {detail}")
        print_gateway_diagnostics(state)
        return False

    image_uris = _collect_data_image_uris(response)
    if not image_uris:
        print("[FAIL] Endpoint responded, but no data:image/...;base64 payload was returned.")
        print(f"Response preview: {detail}")
        return False

    uri = image_uris[0]
    header, encoded = uri.split(",", 1)
    extension = ".png" if "image/png" in header else ".img"
    try:
        data = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        print(f"[FAIL] Returned image data is not valid base64: {exc}")
        return False
    smoke_dir = MATLAB_ARTIFACT_DIR / "smoke-tests"
    smoke_dir.mkdir(parents=True, exist_ok=True)
    destination = smoke_dir / f"matlab-image-test-{datetime.now().strftime('%Y%m%d-%H%M%S')}{extension}"
    destination.write_bytes(data)
    print(f"[OK] MATLAB image payload received ({len(data)} bytes).")
    print(f"Saved diagnostic image: {destination}")
    print(
        "If Open WebUI still prints raw <|start|>...<|call|> text, the remaining problem is the "
        "model/provider function-call parser, not MATLAB or MCPO."
    )
    return True


def _tail_log(path: Path, line_count: int = 50, byte_limit: int = 131072) -> str:
    if not path.exists():
        return ""
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - byte_limit), os.SEEK_SET)
            text = handle.read().decode("utf-8", errors="replace")
        return "\n".join(text.splitlines()[-line_count:])
    except OSError as exc:
        return f"<could not read {path}: {exc}>"


def _redact_diagnostics(text: str, state: Dict[str, Any]) -> str:
    value = text
    api_key = str(state.get("api_key") or "")
    if api_key:
        value = value.replace(api_key, "<redacted-api-key>")
    weknora_api_key = str(read_json(WEKNORA_SECRET_FILE).get("api_key") or "")
    if weknora_api_key:
        value = value.replace(weknora_api_key, "<redacted-weknora-api-key>")
    value = re.sub(r"(--api-key\s+)([^\s\"]+|\"[^\"]*\")", r"\1<redacted-api-key>", value)
    return value


def gateway_diagnostics(state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    state = state or load_state()
    supervisor_pid = read_pid(SUPERVISOR_PID_FILE)
    mcpo_pid = read_pid(MCPO_PID_FILE)
    return {
        "supervisor_pid": supervisor_pid,
        "supervisor_alive": bool(supervisor_pid and process_alive(supervisor_pid)),
        "mcpo_pid": mcpo_pid,
        "mcpo_alive": bool(mcpo_pid and process_alive(mcpo_pid)),
        "supervisor_log": _redact_diagnostics(_tail_log(LOG_DIR / "supervisor.log"), state),
        "mcpo_log": _redact_diagnostics(_tail_log(LOG_DIR / "mcpo.log"), state),
        "physnemo_log": _redact_diagnostics(_tail_log(PHYSNEMO_WSL_PROXY_LOG), state),
        "supervisor_log_path": str(LOG_DIR / "supervisor.log"),
        "mcpo_log_path": str(LOG_DIR / "mcpo.log"),
        "physnemo_log_path": str(PHYSNEMO_WSL_PROXY_LOG),
    }


def print_gateway_diagnostics(state: Optional[Dict[str, Any]] = None) -> None:
    details = gateway_diagnostics(state)
    print("\n=== Gateway diagnostics ===")
    print(
        "Supervisor: "
        + (
            f"PID {details['supervisor_pid']} running"
            if details["supervisor_alive"]
            else "not running"
        )
    )
    print(
        "MCPO: "
        + (f"PID {details['mcpo_pid']} running" if details["mcpo_alive"] else "not running")
    )
    if details["mcpo_log"]:
        print(f"\nLast MCPO log lines ({details['mcpo_log_path']}):")
        print(details["mcpo_log"])
    if details.get("physnemo_log"):
        print(f"\nLast PhysicsNeMo/NAT log lines ({details['physnemo_log_path']}):")
        print(details["physnemo_log"])
    if not details["mcpo_log"] and details["supervisor_log"]:
        print(f"\nLast supervisor log lines ({details['supervisor_log_path']}):")
        print(details["supervisor_log"])
    else:
        print(f"No gateway log was written. Expected logs under: {LOG_DIR}")


def wait_for_gateway(
    state: Dict[str, Any],
    timeout: Optional[float] = None,
    *,
    quiet: bool = False,
) -> bool:
    """Wait until MCPO accepts TCP connections.

    Config-file MCPO starts every mounted MCP server during application startup.
    Engineering adapters can therefore make HTTP readiness substantially slower
    than process creation.  Readiness must be based on the socket, not a fixed
    sleep or successful Task Scheduler launch.
    """
    port = int(state.get("mcpo_port", DEFAULT_MCPO_PORT))
    effective_timeout = float(
        timeout if timeout is not None else state.get("startup_timeout", DEFAULT_STARTUP_TIMEOUT)
    )
    deadline = time.monotonic() + max(1.0, effective_timeout)
    next_notice = time.monotonic() + 10.0

    while time.monotonic() < deadline:
        if tcp_open("127.0.0.1", port):
            return True
        now = time.monotonic()
        if not quiet and now >= next_notice:
            supervisor_pid = read_pid(SUPERVISOR_PID_FILE)
            mcpo_pid = read_pid(MCPO_PID_FILE)
            supervisor_state = "running" if supervisor_pid and process_alive(supervisor_pid) else "not running"
            mcpo_state = "running/initializing" if mcpo_pid and process_alive(mcpo_pid) else "not running"
            print(
                "[*] Gateway startup is still in progress; "
                f"supervisor={supervisor_state}, mcpo={mcpo_state}."
            )
            next_notice = now + 10.0
        time.sleep(0.5)
    return tcp_open("127.0.0.1", port)


def _http_json_with_retry(
    url: str,
    api_key: Optional[str],
    timeout: float = DEFAULT_ENDPOINT_RETRY_TIMEOUT,
) -> Tuple[int, Optional[Dict[str, Any]], str]:
    deadline = time.monotonic() + max(0.1, timeout)
    last_result: Tuple[int, Optional[Dict[str, Any]], str] = (0, None, "not attempted")
    while True:
        last_result = http_json(url, api_key)
        status = last_result[0]
        if status == 200:
            return last_result
        # A route can briefly be absent while MCPO completes startup/hot reload.
        # Authentication/client errors are deterministic and should be returned.
        if status not in (0, 404, 502, 503, 504) or time.monotonic() >= deadline:
            return last_result
        time.sleep(0.75)


_OPENAPI_HTTP_METHODS = frozenset({"get", "post", "put", "patch", "delete", "options", "head", "trace"})


def _openapi_tool_inventory(
    paths: Any,
    *,
    excluded_paths: Iterable[str] = (),
) -> Tuple[List[str], set[str], set[str], Dict[str, List[str]]]:
    """Return path names and OpenAPI operation ids for exposed tools.

    MCPO 0.0.20 creates tool URLs whose last path segment is the original MCP
    tool name, while FastAPI may auto-generate an unrelated operationId such as
    ``tool_physnemo__solve_post``.  Gateway-native operations do the opposite:
    ``/render-artifacts`` is intentionally readable, while its explicit
    ``operationId`` is the stable Open WebUI tool name
    ``physnemo__render_artifacts``.  Verification therefore keeps both
    namespaces and checks capabilities against their union.
    """
    if not isinstance(paths, dict):
        return [], set(), set(), {}

    excluded = {str(value) for value in excluded_paths}
    tool_paths: List[str] = []
    path_tool_names: set[str] = set()
    operation_ids: set[str] = set()
    operations_by_path: Dict[str, List[str]] = {}

    for raw_path, raw_item in paths.items():
        path = str(raw_path)
        if path in excluded or not isinstance(raw_item, dict):
            continue

        operations: List[str] = []
        has_http_operation = False
        for raw_method, raw_operation in raw_item.items():
            method = str(raw_method).casefold()
            if method not in _OPENAPI_HTTP_METHODS or not isinstance(raw_operation, dict):
                continue
            has_http_operation = True
            operation_id = str(raw_operation.get("operationId") or "").strip()
            if operation_id and operation_id not in operations:
                operations.append(operation_id)
                operation_ids.add(operation_id)

        if not has_http_operation:
            continue

        tool_paths.append(path)
        path_name = path.strip("/").split("/")[-1]
        if path_name:
            path_tool_names.add(path_name)
        operations_by_path[path] = operations

    return tool_paths, path_tool_names, operation_ids, operations_by_path


def _physnemo_lifecycle_schema_report(schema: Any) -> Dict[str, Any]:
    """Reject old cached runtime schemas before declaring automatic progress ready."""
    def resolve(value: Any, depth: int = 0) -> Dict[str, Any]:
        if depth > 16 or not isinstance(value, dict):
            return {}
        ref = value.get("$ref")
        if isinstance(ref, str):
            if not ref.startswith("#/"):
                return {}
            node = schema
            for part in ref[2:].split("/"):
                if not isinstance(node, dict):
                    return {}
                node = node.get(part.replace("~1", "/").replace("~0", "~"))
            return resolve(node, depth + 1)
        merged = dict(value)
        for part in value.get("allOf") or []:
            merged["properties"] = {**merged.get("properties", {}), **resolve(part, depth + 1).get("properties", {})}
        return merged
    found: Dict[str, List[str]] = {}
    if isinstance(schema, dict):
        for path, entry in (schema.get("paths") or {}).items():
            if not isinstance(entry, dict):
                continue
            for method, op in entry.items():
                if method not in _OPENAPI_HTTP_METHODS or not isinstance(op, dict):
                    continue
                names = {path.rstrip("/").split("/")[-1], op.get("operationId")}
                for tool in ("physnemo__solve", "physnemo__job_status"):
                    if tool in names:
                        body = resolve(op.get("requestBody"))
                        request_schema = resolve((body.get("content", {}).get("application/json") or {}).get("schema"))
                        found[tool] = sorted(request_schema.get("properties") or {})
    missing = [name for name in ("physnemo__solve", "physnemo__job_status")
               if "client_request_id" not in found.get(name, [])]
    return {"contract": PHYSNEMO_LIFECYCLE_CONTRACT, "ready": not missing,
            "request_fields": found, "missing_correlation_tools": missing}


def check_endpoints(
    state: Optional[Dict[str, Any]] = None,
    *,
    quiet: bool = False,
    wait_timeout: float = 0.0,
) -> Dict[str, Any]:
    state = state or load_state()
    if not state:
        return {"ok": False, "error": "No state"}
    port = int(state.get("mcpo_port", DEFAULT_MCPO_PORT))
    routes = configured_routes()

    if not tcp_open("127.0.0.1", port) and wait_timeout > 0:
        wait_for_gateway(state, timeout=wait_timeout, quiet=quiet)

    port_open = tcp_open("127.0.0.1", port)
    result: Dict[str, Any] = {
        "timestamp": now_iso(),
        "port_open": port_open,
        "servers": {},
    }
    if not quiet:
        print("\n=== MCPO/OpenAPI verification ===")
        print(f"Gateway port 127.0.0.1:{port}: {'OPEN' if port_open else 'CLOSED'}")

    if not port_open:
        result["ok"] = False
        result["error"] = "Gateway HTTP port is not ready"
        for route in routes:
            expected_name = integration_title(route)
            result["servers"][route] = {
                "id": route.replace("-", "_"),
                "name": expected_name,
                "ready": False,
                "not_checked": True,
                "detail": "Gateway port is closed; route verification was skipped",
            }
        if not quiet:
            print("[FAIL] Gateway is not reachable; product route checks were skipped.")
            print_gateway_diagnostics(state)
        atomic_write_json(OPENAPI_VERIFICATION_REPORT, result, private=True)
        return result

    for route in routes:
        expected_name = integration_title(route)
        base_url = f"http://127.0.0.1:{port}/{route}"
        schema_url = f"{base_url}/{openapi_schema_path(route)}"
        docs_url = f"{base_url}/{documentation_path(route)}"
        status, schema, detail = _http_json_with_retry(schema_url, state.get("api_key"))
        docs_status, _, docs_detail = _http_json_with_retry(docs_url, state.get("api_key"))
        paths = schema.get("paths", {}) if isinstance(schema, dict) else {}
        tool_paths, path_tool_names, openapi_operation_ids, operation_ids_by_path = _openapi_tool_inventory(
            paths,
            excluded_paths=(
                f"/{documentation_path(route)}",
                f"/{openapi_schema_path(route)}",
            ),
        )
        available_tool_names = path_tool_names | openapi_operation_ids
        actual_title = (
            schema.get("info", {}).get("title")
            if isinstance(schema, dict) and isinstance(schema.get("info"), dict)
            else None
        )
        title_ok = actual_title == expected_name
        matlab_visualization_ok = route != "matlab" or MATLAB_VISUALIZATION_TOOL in available_tool_names
        missing_groups = missing_required_tool_groups(route, available_tool_names)
        required_tools_ok = not missing_groups
        lifecycle_schema = _physnemo_lifecycle_schema_report(schema) if route == "physnemo" else None
        lifecycle_schema_ok = lifecycle_schema is None or lifecycle_schema["ready"]
        expected_weknora_aliases: set[str] = set()
        if route == "weknora":
            expected_weknora_aliases = {
                str(entry.get("tool_name"))
                for entry in read_json(WEKNORA_KB_CATALOG, {"knowledge_bases": []}).get(
                    "knowledge_bases", []
                )
                if isinstance(entry, dict) and str(entry.get("tool_name") or "")
            }
        missing_weknora_aliases = sorted(expected_weknora_aliases - available_tool_names)
        weknora_aliases_ok = route != "weknora" or not missing_weknora_aliases
        failure_reasons: List[str] = []
        if status != 200:
            failure_reasons.append(f"schema HTTP {status or 'unreachable'}: {detail}")
        if docs_status != 200:
            failure_reasons.append(f"documentation HTTP {docs_status or 'unreachable'}: {docs_detail}")
        if status == 200 and not tool_paths:
            failure_reasons.append("OpenAPI schema contains no MCP tool paths")
        if not title_ok:
            failure_reasons.append(
                f"non-canonical OpenAPI title {actual_title!r}; accepted because the route/spec path is unique"
            )
        if not lifecycle_schema_ok:
            failure_reasons.append("PHYSNEMO_LIFECYCLE_SCHEMA_STALE: missing flat client_request_id in solve/job_status request schemas")
        if not required_tools_ok:
            failure_reasons.append(f"missing required tool groups: {missing_groups}")
        if not weknora_aliases_ok:
            failure_reasons.append(f"missing WeKnora KB aliases: {missing_weknora_aliases}")

        server_result = {
            "id": route.replace("-", "_"),
            "name": expected_name,
            "connection_url": base_url,
            "spec_path": openapi_schema_path(route),
            "docs_path": documentation_path(route),
            "schema_url": schema_url,
            "documentation_url": docs_url,
            "http_status": status,
            "documentation_http_status": docs_status,
            "expected_title": expected_name,
            "actual_title": actual_title,
            "title_ok": title_ok,
            "tool_count": len(tool_paths),
            "tool_names": sorted(path_tool_names),
            "openapi_operation_ids": sorted(openapi_operation_ids),
            "available_tool_names": sorted(available_tool_names),
            "tool_operation_ids_by_path": operation_ids_by_path,
            "tool_name_source": "path-segment-union-openapi.operationId",
            "matlab_visualization_tool": MATLAB_VISUALIZATION_TOOL if route == "matlab" else None,
            "matlab_visualization_available": matlab_visualization_ok if route == "matlab" else None,
            "required_tools_ok": required_tools_ok,
            "physnemo_lifecycle": lifecycle_schema,
            "missing_required_tool_groups": missing_groups,
            "weknora_kb_aliases_expected": sorted(expected_weknora_aliases),
            "weknora_kb_aliases_missing": missing_weknora_aliases,
            "weknora_kb_aliases_ok": weknora_aliases_ok,
            "ready": (
                status == 200
                and docs_status == 200
                and len(tool_paths) > 0
                and matlab_visualization_ok
                and required_tools_ok
                and lifecycle_schema_ok
                and weknora_aliases_ok
            ),
            "detail": detail if status != 200 else None,
            "documentation_detail": docs_detail if docs_status != 200 else None,
            "failure_reasons": failure_reasons,
        }
        if route == "weknora" and not server_result["ready"]:
            direct_probe = probe_configured_stdio_route(route, timeout=45.0)
            server_result["stdio_preflight"] = direct_probe
            if not direct_probe.get("success"):
                server_result["failure_reasons"].append(
                    "direct stdio tools/list failed: "
                    + str(direct_probe.get("error") or direct_probe.get("output_tail") or "unknown")
                )
            else:
                server_result["failure_reasons"].append(
                    "direct stdio tools/list passed; MCPO route/schema generation is stale or failed"
                )
        if route == PHYSNEMO_ROUTE and not server_result["ready"]:
            direct_probe = probe_physnemo_mcp(state, timeout=45.0)
            server_result["streamable_http_preflight"] = direct_probe
            if not direct_probe.get("success"):
                server_result["failure_reasons"].append(
                    "direct PhysicsNeMo streamable-http tools/list failed: "
                    + str(direct_probe.get("error") or direct_probe.get("output_tail") or "unknown")
                )
            else:
                server_result["failure_reasons"].append(
                    "direct PhysicsNeMo tools/list passed; MCPO route/schema generation is stale or failed"
                )
        result["servers"][route] = server_result
        if not quiet:
            if server_result["ready"]:
                suffix = (
                    f", {MATLAB_VISUALIZATION_TOOL} available"
                    if route == "matlab"
                    else ""
                )
                print(
                    f"[OK]   {expected_name}: {len(tool_paths)} tool endpoint(s), "
                    f"named schema and documentation respond{suffix}"
                )
            elif status == 200 and len(tool_paths) > 0 and not required_tools_ok:
                groups = "; ".join(
                    f"{group}: one of {', '.join(alternatives)}"
                    for group, alternatives in missing_groups.items()
                )
                remedy = (
                    f"Restart the Mechanical MCP server with {MECHANICAL_STATIC_TOOLS_OPTION}."
                    if route == "ansys-mechanical"
                    else "Reinstall or upgrade the matching MCP package."
                )
                print(
                    f"[FAIL] {expected_name}: OpenAPI schema is missing required tool groups ({groups}). "
                    + remedy
                )
            elif route == "weknora" and status == 200 and not weknora_aliases_ok:
                print(
                    f"[FAIL] {expected_name}: {len(missing_weknora_aliases)} verified knowledge-base "
                    "search operation(s) are missing from OpenAPI. Run the same uniquely named installer with -Resume to refresh "
                    "the catalogue and restart the gateway."
                )
            elif route == "matlab" and status == 200 and len(tool_paths) > 0 and not matlab_visualization_ok:
                print(
                    f"[WARN] {expected_name}: MATLAB tools loaded, but {MATLAB_VISUALIZATION_TOOL} "
                    "is missing; run --resume with bootstrapper 2.4.0 or newer"
                )
            elif status == 200 and len(tool_paths) > 0 and not title_ok:
                print(
                    f"[WARN] {expected_name}: tools loaded, but OpenAPI title is "
                    f"{actual_title!r}; run --resume to regenerate the ASCII-safe stdio wrapper"
                )
            elif status == 200 and docs_status != 200:
                print(f"[WARN] {expected_name}: schema works, documentation HTTP {docs_status or 'unreachable'}")
            elif status == 200:
                print(f"[WARN] {expected_name}: schema responds, but no MCP tools were loaded")
                for reason in server_result.get("failure_reasons", []):
                    print(f"       - {reason}")
                if route == "weknora":
                    print(f"       Diagnostic report: {WEKNORA_STDIO_PREFLIGHT_REPORT}")
            else:
                print(
                    f"[FAIL] {expected_name}: schema HTTP {status or 'unreachable'}"
                    + (f" ({detail})" if detail else "")
                )
            if route == "weknora" and not server_result["ready"]:
                print("       WeKnora route diagnostics:")
                for reason in server_result.get("failure_reasons", []):
                    print(f"       - {reason}")
                print(f"       Direct stdio report: {WEKNORA_STDIO_PREFLIGHT_REPORT}")
                print(f"       MCPO log: {LOG_DIR / 'mcpo.log'}")
    result["ready_count"] = sum(1 for item in result["servers"].values() if item["ready"])
    result["ok"] = not result["servers"] or result["ready_count"] == len(result["servers"])
    atomic_write_json(OPENAPI_VERIFICATION_REPORT, result, private=True)
    return result


# ---------------------------------------------------------------------------
# Persistent service registration
# ---------------------------------------------------------------------------

def deployed_python(background: bool = False) -> Path:
    if sys.platform.startswith("win") and background:
        pythonw = venv_bin("pythonw")
        if pythonw.exists():
            return pythonw
    return venv_bin("python")


def deploy_self() -> None:
    ensure_dirs()
    source = Path(__file__).resolve()
    destination = INSTALLED_SCRIPT.resolve() if INSTALLED_SCRIPT.exists() else INSTALLED_SCRIPT
    if source != destination:
        shutil.copy2(source, INSTALLED_SCRIPT)
    if not sys.platform.startswith("win"):
        INSTALLED_SCRIPT.chmod(0o755)
    # Remove stale bootstrap entry points that previously allowed a uniquely
    # named PowerShell installer to execute a different generic Python file.
    for stale_name in (
        "engineering_mcp_bootstrap.py",
        "engineering_mcp_bootstrap-weknora-v2.6.2-http-https.py",
        "engineering_mcp_bootstrap-weknora-v2.6.3-openapi-fix.py",
        "engineering_mcp_bootstrap-weknora-v2.6.4-kb-catalog-fix.py",
        "engineering_mcp_bootstrap-weknora-v2.6.5-workspace-selector.py",
        "engineering_mcp_unified-v2.8.0.py",
        "engineering_mcp_unified-v2.8.1.py",
        "engineering_mcp_unified-v2.8.2.py",
        "engineering_mcp_unified-v2.8.3.py",
        "engineering_mcp_unified-v2.8.4.py",
        "engineering_mcp_unified-v2.8.5.py",
        "engineering_mcp_unified-v2.8.6.py",
        "engineering_mcp_unified-v2.8.7.py",
        "engineering_mcp_unified-v2.8.8.py",
        "engineering_mcp_unified-v2.9.0.py",
        "engineering_mcp_unified-v2.9.1.py",
    ):
        stale = APP_HOME / stale_name
        if stale != INSTALLED_SCRIPT:
            stale.unlink(missing_ok=True)


def windows_current_sid() -> str:
    result = run(["whoami", "/user", "/fo", "csv", "/nh"], check=True)
    row = next(csv.reader([(result.stdout or "").strip()]))
    if len(row) < 2 or not row[-1].startswith("S-"):
        raise RuntimeError("Could not determine the current Windows user SID")
    return row[-1]


def windows_task_exists() -> bool:
    if not sys.platform.startswith("win"):
        return False
    result = run(["schtasks", "/Query", "/TN", WINDOWS_TASK_NAME])
    return result.returncode == 0


def create_windows_task_xml() -> None:
    sid = windows_current_sid()
    pythonw = xml_escape(str(deployed_python(background=True)))
    script = xml_escape(str(INSTALLED_SCRIPT))
    working_directory = xml_escape(str(APP_HOME))
    description = xml_escape("Persistent Engineering MCP/MCPO background gateway")
    xml = f'''<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>{description}</Description>
  </RegistrationInfo>
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
      <UserId>{sid}</UserId>
    </LogonTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>{sid}</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>true</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Priority>7</Priority>
    <RestartOnFailure>
      <Interval>PT1M</Interval>
      <Count>999</Count>
    </RestartOnFailure>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{pythonw}</Command>
      <Arguments>"{script}" --service</Arguments>
      <WorkingDirectory>{working_directory}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
'''
    WINDOWS_TASK_XML.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(WINDOWS_TASK_XML, xml, encoding="utf-16")


def register_windows_task() -> Dict[str, Any]:
    create_windows_task_xml()
    run(["schtasks", "/Create", "/TN", WINDOWS_TASK_NAME, "/XML", str(WINDOWS_TASK_XML), "/F"], check=True)
    return {
        "type": "windows-task",
        "name": WINDOWS_TASK_NAME,
        "trigger": "user-logon",
        "registered": True,
        "note": "Starts after this user logs in following a reboot.",
    }


def systemd_escape(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def register_systemd_user_service() -> Dict[str, Any]:
    SYSTEMD_USER_DIR.mkdir(parents=True, exist_ok=True)
    unit = f"""[Unit]
Description=Engineering MCP MCPO gateway
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory={systemd_escape(str(APP_HOME))}
Environment={systemd_escape(f'ENGINEERING_MCP_HOME={APP_HOME}')}
ExecStart={systemd_escape(str(deployed_python()))} {systemd_escape(str(INSTALLED_SCRIPT))} --service
Restart=always
RestartSec=5
KillMode=control-group
TimeoutStopSec=20

[Install]
WantedBy=default.target
"""
    atomic_write_text(SYSTEMD_UNIT_FILE, unit)
    run(["systemctl", "--user", "daemon-reload"], check=True)
    run(["systemctl", "--user", "enable", SYSTEMD_UNIT_NAME], check=True)
    linger = None
    if which("loginctl"):
        try:
            linger = run(["loginctl", "enable-linger", getpass.getuser()], timeout=10)
        except RuntimeError:
            linger = None
    return {
        "type": "systemd-user",
        "name": SYSTEMD_UNIT_NAME,
        "registered": True,
        "linger_enabled": bool(linger and linger.returncode == 0),
        "note": "Starts at boot when user lingering is available; otherwise at user login.",
    }


def register_xdg_autostart() -> Dict[str, Any]:
    XDG_AUTOSTART_FILE.parent.mkdir(parents=True, exist_ok=True)
    command = format_command([str(deployed_python()), str(INSTALLED_SCRIPT), "--service"])
    desktop = f"""[Desktop Entry]
Type=Application
Version=1.0
Name=Engineering MCP Gateway
Comment=Persistent Engineering MCP/MCPO background gateway
Exec={command}
Terminal=false
X-GNOME-Autostart-enabled=true
NoDisplay=true
"""
    atomic_write_text(XDG_AUTOSTART_FILE, desktop)
    return {
        "type": "xdg-autostart",
        "name": str(XDG_AUTOSTART_FILE),
        "registered": True,
        "trigger": "desktop-login",
    }


def register_launch_agent() -> Dict[str, Any]:
    LAUNCH_AGENT_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "Label": LAUNCHD_LABEL,
        "ProgramArguments": [str(deployed_python()), str(INSTALLED_SCRIPT), "--service"],
        "RunAtLoad": True,
        "KeepAlive": True,
        "ProcessType": "Background",
        "WorkingDirectory": str(APP_HOME),
        "StandardOutPath": str(LOG_DIR / "launchd.out.log"),
        "StandardErrorPath": str(LOG_DIR / "launchd.err.log"),
        "EnvironmentVariables": {"ENGINEERING_MCP_HOME": str(APP_HOME)},
    }
    with tempfile.NamedTemporaryFile("wb", delete=False, dir=str(LAUNCH_AGENT_FILE.parent)) as temp:
        plistlib.dump(payload, temp)
        temp_path = Path(temp.name)
    os.replace(temp_path, LAUNCH_AGENT_FILE)
    uid = str(os.getuid())
    run(["launchctl", "bootout", f"gui/{uid}", str(LAUNCH_AGENT_FILE)])
    result = run(["launchctl", "bootstrap", f"gui/{uid}", str(LAUNCH_AGENT_FILE)])
    if result.returncode != 0:
        run(["launchctl", "load", "-w", str(LAUNCH_AGENT_FILE)], check=True)
    return {
        "type": "launchagent",
        "name": LAUNCHD_LABEL,
        "registered": True,
        "trigger": "user-login",
    }


def register_autostart() -> Dict[str, Any]:
    deploy_self()
    if sys.platform.startswith("win"):
        return register_windows_task()
    if sys.platform == "darwin":
        return register_launch_agent()
    if which("systemctl"):
        probe = run(["systemctl", "--user", "show-environment"], timeout=8)
        if probe.returncode == 0:
            return register_systemd_user_service()
    return register_xdg_autostart()


def autostart_status() -> Dict[str, Any]:
    if sys.platform.startswith("win"):
        return {"type": "windows-task", "registered": windows_task_exists(), "name": WINDOWS_TASK_NAME}
    if sys.platform == "darwin":
        registered = LAUNCH_AGENT_FILE.exists()
        loaded = False
        if which("launchctl"):
            loaded = run(["launchctl", "print", f"gui/{os.getuid()}/{LAUNCHD_LABEL}"]).returncode == 0
        return {"type": "launchagent", "registered": registered, "loaded": loaded, "name": LAUNCHD_LABEL}
    if SYSTEMD_UNIT_FILE.exists() and which("systemctl"):
        enabled = run(["systemctl", "--user", "is-enabled", SYSTEMD_UNIT_NAME]).returncode == 0
        active = run(["systemctl", "--user", "is-active", SYSTEMD_UNIT_NAME]).returncode == 0
        return {"type": "systemd-user", "registered": enabled, "active": active, "name": SYSTEMD_UNIT_NAME}
    return {"type": "xdg-autostart", "registered": XDG_AUTOSTART_FILE.exists(), "name": str(XDG_AUTOSTART_FILE)}


def start_registered_service() -> bool:
    status = autostart_status()
    service_type = status.get("type")
    if service_type == "windows-task" and status.get("registered"):
        result = run(["schtasks", "/Run", "/TN", WINDOWS_TASK_NAME])
        return result.returncode == 0
    if service_type == "systemd-user" and status.get("registered"):
        return run(["systemctl", "--user", "start", SYSTEMD_UNIT_NAME]).returncode == 0
    if service_type == "launchagent" and status.get("registered"):
        uid = str(os.getuid())
        result = run(["launchctl", "kickstart", "-k", f"gui/{uid}/{LAUNCHD_LABEL}"])
        if result.returncode != 0:
            result = run(["launchctl", "bootstrap", f"gui/{uid}", str(LAUNCH_AGENT_FILE)])
        return result.returncode == 0
    return False


def stop_registered_service(*, maintenance: bool = False) -> None:
    status = autostart_status()
    service_type = status.get("type")
    if service_type == "windows-task" and status.get("registered"):
        run(["schtasks", "/End", "/TN", WINDOWS_TASK_NAME])
        if maintenance:
            # Prevent RestartOnFailure from relaunching pythonw.exe while the
            # venv is being moved/rebuilt. register_windows_task() recreates an
            # enabled task after a successful install/resume.
            run(["schtasks", "/Change", "/TN", WINDOWS_TASK_NAME, "/Disable"])
    elif service_type == "systemd-user" and status.get("registered"):
        run(["systemctl", "--user", "stop", SYSTEMD_UNIT_NAME])
    elif service_type == "launchagent" and status.get("registered"):
        run(["launchctl", "bootout", f"gui/{os.getuid()}", str(LAUNCH_AGENT_FILE)])


def unregister_autostart() -> None:
    if sys.platform.startswith("win"):
        run(["schtasks", "/End", "/TN", WINDOWS_TASK_NAME])
        run(["schtasks", "/Delete", "/TN", WINDOWS_TASK_NAME, "/F"])
        return
    if sys.platform == "darwin":
        run(["launchctl", "bootout", f"gui/{os.getuid()}", str(LAUNCH_AGENT_FILE)])
        LAUNCH_AGENT_FILE.unlink(missing_ok=True)
        return
    if SYSTEMD_UNIT_FILE.exists() and which("systemctl"):
        run(["systemctl", "--user", "disable", "--now", SYSTEMD_UNIT_NAME])
        SYSTEMD_UNIT_FILE.unlink(missing_ok=True)
        run(["systemctl", "--user", "daemon-reload"])
    XDG_AUTOSTART_FILE.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# MCPO supervisor and process control
# ---------------------------------------------------------------------------

def mcpo_command(state: Dict[str, Any]) -> List[str]:
    routes = configured_routes()
    if not routes:
        raise RuntimeError("MCPO has no configured MCP servers")
    bind_host = state.get("bind_host") or (
        "0.0.0.0" if state.get("scan", {}).get("docker", {}).get("openwebui_container") else "127.0.0.1"
    )
    return [
        str(mcpo_venv_bin("python")),
        str(INSTALLED_SCRIPT),
        "--named-mcpo",
        "--host",
        bind_host,
        "--port",
        str(state.get("mcpo_port", DEFAULT_MCPO_PORT)),
        "--api-key",
        state["api_key"],
        "--name",
        "Engineering MCP Gateway",
        "--description",
        "Engineering application MCP servers exposed as separate OpenAPI routes",
        "--version",
        BOOTSTRAPPER_VERSION,
        "--config",
        str(MCPO_CONFIG),
        "--hot-reload",
    ]


def run_supervisor() -> int:
    """Supervise the one Engineering MCP gateway and its WSL PhysicsNeMo backend.

    All routes are exposed by the same MCPO process and port.  PhysicsNeMo is
    the only integration that needs an additional long-running backend process:
    NeMo Agent Toolkit inside WSL2.  The supervisor therefore starts NAT first,
    waits for its loopback MCP endpoint, and only then starts the shared MCPO
    gateway.  If either process exits unexpectedly, the pair is restarted as
    one service generation so MCPO never keeps a stale remote MCP session.
    """
    ensure_dirs()
    state = load_state()
    if not state:
        log_supervisor("Cannot start: state.json does not exist")
        return 2
    if not configured_routes():
        log_supervisor("No MCPO routes configured; supervisor exits without starting a proxy")
        return 0

    STOP_FILE.unlink(missing_ok=True)
    write_pid(SUPERVISOR_PID_FILE, os.getpid())
    stopping = False

    def request_stop(signum: int, _frame: Any) -> None:
        nonlocal stopping
        stopping = True
        log_supervisor(f"Supervisor received signal {signum}")

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, request_stop)
        except (ValueError, OSError):
            pass

    backoff = 2
    phys_process: Optional[subprocess.Popen] = None
    phys_log_handle: Optional[Any] = None
    mcpo_process: Optional[subprocess.Popen] = None
    try:
        while not stopping and not STOP_FILE.exists():
            state = load_state() or state
            routes = configured_routes()
            phys_required = PHYSNEMO_ROUTE in routes
            try:
                command = mcpo_command(state)
            except Exception as exc:
                log_supervisor(f"Configuration error: {exc}")
                return 3

            generation_failed = False
            exit_reason = "unknown"
            generation_started_at = time.monotonic()
            phys_process = None
            phys_log_handle = None
            mcpo_process = None

            try:
                if phys_required:
                    log_supervisor("Starting integrated PhysicsNeMo/NAT backend in WSL2")
                    phys_process, phys_log_handle = start_physnemo_nat_process(state)
                    if phys_process is None:
                        generation_failed = True
                        exit_reason = "PhysicsNeMo route is configured but no NAT process could be created"
                    elif not wait_for_physnemo_nat(
                        state,
                        process=phys_process,
                        timeout=min(
                            float(state.get("startup_timeout", DEFAULT_STARTUP_TIMEOUT)),
                            300.0,
                        ),
                    ):
                        generation_failed = True
                        code = phys_process.poll()
                        exit_reason = (
                            "PhysicsNeMo/NAT did not become healthy"
                            + (f" (WSL proxy exit {code})" if code is not None else "")
                        )
                    else:
                        log_supervisor("PhysicsNeMo/NAT MCP endpoint is healthy")

                if not generation_failed:
                    environment = os.environ.copy()
                    environment.setdefault("LOG_LEVEL", "INFO")
                    environment.setdefault("PYTHONUTF8", "1")
                    environment.setdefault("PYTHONIOENCODING", "utf-8")
                    log_supervisor(f"Starting shared MCPO gateway: {format_command_redacted(command)}")
                    mcpo_log = (LOG_DIR / "mcpo.log").open(
                        "a", encoding="utf-8", errors="replace"
                    )
                    try:
                        mcpo_process = subprocess.Popen(
                            command,
                            stdout=mcpo_log,
                            stderr=subprocess.STDOUT,
                            stdin=subprocess.DEVNULL,
                            env=environment,
                            cwd=str(APP_HOME),
                        )
                        write_pid(MCPO_PID_FILE, mcpo_process.pid)
                        while not stopping and not STOP_FILE.exists():
                            mcpo_code = mcpo_process.poll()
                            phys_code = phys_process.poll() if phys_process is not None else None
                            if mcpo_code is not None:
                                generation_failed = True
                                exit_reason = f"shared MCPO exited with code {mcpo_code}"
                                break
                            if phys_required and phys_process is not None and phys_code is not None:
                                generation_failed = True
                                exit_reason = f"PhysicsNeMo WSL proxy exited with code {phys_code}"
                                break
                            time.sleep(0.5)
                    finally:
                        mcpo_log.close()

                if stopping or STOP_FILE.exists():
                    exit_reason = "stop requested"
            except Exception as exc:
                generation_failed = True
                exit_reason = f"service generation failed: {type(exc).__name__}: {exc}"
            finally:
                if mcpo_process is not None and mcpo_process.poll() is None:
                    terminate_pid_tree(mcpo_process.pid, force=False)
                    if mcpo_process.poll() is None:
                        terminate_pid_tree(mcpo_process.pid, force=True)
                MCPO_PID_FILE.unlink(missing_ok=True)

                if phys_process is not None and phys_process.poll() is None:
                    terminate_pid_tree(phys_process.pid, force=False)
                    if phys_process.poll() is None:
                        terminate_pid_tree(phys_process.pid, force=True)
                if phys_log_handle is not None:
                    try:
                        phys_log_handle.close()
                    except OSError:
                        pass
                stop_physnemo_nat(state)

            if stopping or STOP_FILE.exists():
                log_supervisor("Engineering MCP service generation stopped by request")
                break
            if not generation_failed:
                # Defensive fallback: the inner generation should only end on a
                # stop or process failure, but avoid a tight loop if that changes.
                exit_reason = "service generation ended unexpectedly"
            if time.monotonic() - generation_started_at >= 120:
                backoff = 2
            log_supervisor(f"{exit_reason}; restart in {backoff}s")
            deadline = time.monotonic() + backoff
            while time.monotonic() < deadline and not stopping and not STOP_FILE.exists():
                time.sleep(0.25)
            backoff = min(backoff * 2, 60)
    finally:
        if mcpo_process is not None and mcpo_process.poll() is None:
            terminate_pid_tree(mcpo_process.pid, force=True)
        if phys_process is not None and phys_process.poll() is None:
            terminate_pid_tree(phys_process.pid, force=True)
        if phys_log_handle is not None:
            try:
                phys_log_handle.close()
            except OSError:
                pass
        stop_physnemo_nat(state)
        SUPERVISOR_PID_FILE.unlink(missing_ok=True)
        MCPO_PID_FILE.unlink(missing_ok=True)
        PHYSNEMO_WSL_PROXY_PID_FILE.unlink(missing_ok=True)
        STOP_FILE.unlink(missing_ok=True)
    return 0


def spawn_detached_supervisor() -> bool:
    existing = read_pid(SUPERVISOR_PID_FILE)
    if existing and process_alive(existing):
        return True
    deploy_self()
    python = str(deployed_python(background=sys.platform.startswith("win")))
    command = [python, str(INSTALLED_SCRIPT), "--service"]
    creationflags = 0
    if sys.platform.startswith("win"):
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    process = subprocess.Popen(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        cwd=str(APP_HOME),
        creationflags=creationflags,
        start_new_session=not sys.platform.startswith("win"),
    )
    time.sleep(0.5)
    return process.poll() is None


def start_background(state: Optional[Dict[str, Any]] = None) -> bool:
    state = state or load_state()
    if not state:
        raise RuntimeError("Not installed. Run --install or --resume first.")
    if not configured_routes():
        print("[*] No MCPO-backed servers are configured; no gateway service needs to start.")
        return True

    timeout = float(state.get("startup_timeout", DEFAULT_STARTUP_TIMEOUT))
    existing = read_pid(SUPERVISOR_PID_FILE)
    if existing and process_alive(existing):
        print(f"[*] Engineering MCP supervisor is already running (PID {existing}); checking HTTP readiness.")
        if wait_for_gateway(state, timeout=timeout):
            print(f"[+] Engineering MCP gateway is running on port {state.get('mcpo_port')}.")
            return True
        print("[!] Supervisor is running, but the MCPO HTTP gateway did not become ready.")
        print_gateway_diagnostics(state)
        return False

    STOP_FILE.unlink(missing_ok=True)
    log_supervisor(f"--- start request, bootstrapper {BOOTSTRAPPER_VERSION} ---")
    started = start_registered_service()
    if not started:
        started = spawn_detached_supervisor()
    if started and wait_for_gateway(state, timeout=timeout):
        print(f"[+] Engineering MCP gateway is running on port {state.get('mcpo_port')}.")
        return True

    print("[!] Background service was launched, but the MCPO HTTP port is not ready.")
    print_gateway_diagnostics(state)
    return False


def stop_background(*, create_home: bool = True, maintenance: bool = False) -> None:
    # Normal service management may create the state directory.  Uninstall
    # passes create_home=False so removal can never look like a fresh install.
    if create_home:
        ensure_dirs()
    home_exists = APP_HOME.exists()
    state = load_state() if home_exists else {}
    if home_exists:
        STOP_FILE.touch()
    stop_registered_service(maintenance=maintenance)
    for pid_file in (MCPO_PID_FILE, PHYSNEMO_WSL_PROXY_PID_FILE, SUPERVISOR_PID_FILE):
        pid = read_pid(pid_file)
        if pid:
            terminate_pid_tree(pid, force=True)
        pid_file.unlink(missing_ok=True)
    stop_physnemo_nat(state)
    if home_exists:
        STOP_FILE.unlink(missing_ok=True)
    print("[+] Engineering MCP background processes stopped (shared MCPO and PhysicsNeMo/NAT).")


# ---------------------------------------------------------------------------
# Launchers, installation, resume, status and uninstall
# ---------------------------------------------------------------------------

def generate_launchers() -> None:
    deploy_self()
    python = str(deployed_python())
    if sys.platform.startswith("win"):
        launchers = {
            "start-engineering-mcp.cmd": f'@echo off\r\n"{python}" "{INSTALLED_SCRIPT}" --start\r\npause\r\n',
            "stop-engineering-mcp.cmd": f'@echo off\r\n"{python}" "{INSTALLED_SCRIPT}" --stop\r\npause\r\n',
            "status-engineering-mcp.cmd": f'@echo off\r\n"{python}" "{INSTALLED_SCRIPT}" --status\r\npause\r\n',
            "config-engineering-mcp.cmd": f'@echo off\r\n"{python}" "{INSTALLED_SCRIPT}" --config\r\npause\r\n',
        }
        for name, content in launchers.items():
            atomic_write_text(APP_HOME / name, content)
    else:
        launchers = {
            "start-engineering-mcp.sh": "--start",
            "stop-engineering-mcp.sh": "--stop",
            "status-engineering-mcp.sh": "--status",
            "config-engineering-mcp.sh": "--config",
        }
        for name, flag in launchers.items():
            path = APP_HOME / name
            atomic_write_text(path, f'#!/bin/sh\n"{python}" "{INSTALLED_SCRIPT}" {flag}\n')
            path.chmod(0o755)


def install_or_resume(args: argparse.Namespace, *, resume: bool) -> int:
    checkpoint, options = resolve_install_context(args, resume)
    print(f"\n=== Engineering MCP Unified Bootstrapper {BOOTSTRAPPER_VERSION} ===")
    print("Mode: resume/repair" if resume else "Mode: install/upgrade")

    try:
        data = scan(
            weknora_url=options["weknora_url"],
            weknora_api_url=options["weknora_api_url"],
            weknora_distro=options["weknora_distro"],
            weknora_install_dir=options["weknora_install_dir"],
            weknora_health_timeout=min(15.0, float(options["weknora_health_timeout"])),
            weknora_ca_certificate=options["weknora_ca_certificate"],
            physnemo_distro=options["physnemo_distro"],
            physnemo_install_dir=options["physnemo_install_dir"],
        )
        checkpoint["scan"] = data
        set_checkpoint_step(checkpoint, "scan", "done")
        print_scan(data)

        # Stop a service from a previous release before replacing its venv or
        # configuration. This also migrates the original detached mcpo.pid
        # process into the new supervised service without a port collision.
        set_checkpoint_step(checkpoint, "quiesce-existing-service", "running")
        stop_background(maintenance=True)
        set_checkpoint_step(checkpoint, "quiesce-existing-service", "done")

        # Validate pyvenv.cfg, base interpreter, sys.prefix and pip on every
        # install/resume. Checking only Scripts\python.exe allowed an interrupted
        # venv to survive and later fail with Windows exit code 106.
        set_checkpoint_step(checkpoint, "venv", "running")
        venv_details = ensure_venv(checkpoint)
        set_checkpoint_step(checkpoint, "venv", "done", details=venv_details)

        deploy_self()
        set_checkpoint_step(checkpoint, "deploy-self", "done")

        set_checkpoint_step(checkpoint, "mcpo-isolated-v265", "running")
        mcpo_environment = ensure_mcpo_environment()
        current_mcpo_version = auxiliary_package_version(MCPO_VENV, "mcpo")
        set_checkpoint_step(
            checkpoint,
            "mcpo-isolated-v265",
            "done",
            details=mcpo_environment,
        )
        print(
            f"[*] Isolated MCPO {current_mcpo_version} with MCP "
            f"{auxiliary_package_version(MCPO_VENV, 'mcp')} is ready: {MCPO_VENV}"
        )

        installed: Dict[str, bool] = dict(checkpoint.get("installed", {}))
        package_failures: List[str] = []

        for route, metadata in OFFICIAL_SERVERS.items():
            step_name = f"server:{route}"
            application = data.get("applications", {}).get(metadata["detection"], {})
            if route == "weknora" and not options["weknora"]:
                installed[route] = False
                set_checkpoint_step(
                    checkpoint,
                    step_name,
                    "skipped",
                    details={"reason": "WeKnora integration disabled by option"},
                )
                continue
            if route == "weknora" and application.get("found") and not application.get("healthy"):
                installed[route] = False
                error = (
                    "The selected WeKnora backend is not healthy at "
                    f"{application.get('api_url')}/health. MCP was not configured."
                )
                package_failures.append("weknora-runtime")
                set_checkpoint_step(checkpoint, step_name, "failed", error=error, details=application)
                print(f"[!] {error}")
                checkpoint["installed"] = installed
                save_checkpoint(checkpoint)
                continue
            target = detected_for_server(route, metadata, data)
            if not target:
                installed[route] = False
                set_checkpoint_step(checkpoint, step_name, "skipped", details={"reason": "application not detected"})
                continue
            if step_done(checkpoint, step_name) and server_command_installed(route, metadata):
                try:
                    server_launch_args(route, metadata)
                    installed[route] = True
                    print(f"[*] {metadata['label']} MCP already complete; skipping.")
                    continue
                except Exception as exc:
                    print(f"[!] {metadata['label']} MCP requires upgrade/repair: {exc}")
            print(f"[*] Installing {metadata['label']} MCP...")
            set_checkpoint_step(checkpoint, step_name, "running")
            try:
                environment_report: Dict[str, Any] = {}
                if route == "weknora":
                    environment_report = ensure_weknora_mcp_environment()
                else:
                    pip_install(str(metadata.get("package_spec") or metadata["package"]))
                if not server_command_installed(route, metadata):
                    raise RuntimeError(f"Expected command not found: {server_command_path(route, metadata)}")
                server_launch_args(route, metadata)
                installed[route] = True
                set_checkpoint_step(
                    checkpoint,
                    step_name,
                    "done",
                    details=environment_report or {"command": str(server_command_path(route, metadata))},
                )
            except Exception as exc:
                installed[route] = False
                package_failures.append(route)
                set_checkpoint_step(checkpoint, step_name, "failed", error=str(exc))
                print(f"[!] {metadata['label']}: {exc}")
            checkpoint["installed"] = installed
            save_checkpoint(checkpoint)

        matlab_binary: Optional[Path] = None
        matlab_step = "server:matlab"
        if data.get("applications", {}).get("matlab", {}).get("found"):
            existing_matlab = checkpoint.get("matlab_binary")
            if step_done(checkpoint, matlab_step) and existing_matlab and Path(existing_matlab).exists():
                matlab_binary = Path(existing_matlab)
                installed["matlab"] = True
                print("[*] MATLAB MCP binary already complete; skipping.")
            else:
                print("[*] Installing/updating official MATLAB MCP server...")
                set_checkpoint_step(checkpoint, matlab_step, "running")
                try:
                    matlab_binary = download_matlab_server(existing_matlab)
                    if not matlab_binary:
                        raise RuntimeError("MATLAB MCP binary could not be selected")
                    checkpoint["matlab_binary"] = str(matlab_binary)
                    installed["matlab"] = True
                    set_checkpoint_step(checkpoint, matlab_step, "done")
                except Exception as exc:
                    installed["matlab"] = False
                    package_failures.append("matlab")
                    set_checkpoint_step(checkpoint, matlab_step, "failed", error=str(exc))
                    print(f"[!] MATLAB MCP: {exc}")
        else:
            installed["matlab"] = False
            set_checkpoint_step(checkpoint, matlab_step, "skipped", details={"reason": "MATLAB not detected"})

        matlab_runtime: Dict[str, Any] = {}
        runtime_step = "matlab-runtime-health-v253"
        if installed.get("matlab") and matlab_binary:
            set_checkpoint_step(checkpoint, runtime_step, "running")
            matlab_runtime = prepare_matlab_runtime(
                matlab_binary,
                data,
                auto_repair=bool(options["matlab_repair"]),
                force_matlab_close=bool(options["matlab_force_close"]),
                health_timeout=float(options["matlab_health_timeout"]),
            )
            checkpoint["matlab_runtime"] = matlab_runtime
            if matlab_runtime.get("healthy"):
                set_checkpoint_step(checkpoint, runtime_step, "done", details=matlab_runtime)
            else:
                installed["matlab"] = False
                package_failures.append("matlab-runtime")
                repair = matlab_runtime.get("service_host_repair") or {}
                error = str(
                    repair.get("error")
                    or matlab_runtime.get("preflight", {}).get("error")
                    or "MATLAB licensing/runtime health failed"
                )
                set_checkpoint_step(checkpoint, runtime_step, "failed", error=error, details=matlab_runtime)
                print(f"[!] MATLAB integration was not exposed: {error}")
                print(f"    Detailed repair report: {MATLAB_REPAIR_REPORT}")
            checkpoint["installed"] = installed
            save_checkpoint(checkpoint)
        elif data.get("applications", {}).get("matlab", {}).get("found"):
            set_checkpoint_step(
                checkpoint, runtime_step, "skipped",
                details={"reason": "MATLAB MCP binary is unavailable"},
            )
        else:
            set_checkpoint_step(checkpoint, runtime_step, "skipped", details={"reason": "MATLAB not detected"})

        weknora_runtime: Dict[str, Any] = {}
        weknora_runtime_step = "weknora-runtime-health-v265"
        weknora_info = data.get("applications", {}).get("weknora", {})
        if options["weknora"] and installed.get("weknora") and weknora_info.get("found"):
            set_checkpoint_step(checkpoint, weknora_runtime_step, "running")
            try:
                weknora_runtime = prepare_weknora_runtime(
                    weknora_info,
                    explicit_api_key_file=options["weknora_api_key_file"],
                    auto_provision=bool(options["weknora_auto_provision"]),
                    health_timeout=float(options["weknora_health_timeout"]),
                    allow_empty_catalog=bool(options["weknora_allow_empty_catalog"]),
                    target_tenant_id=str(options["weknora_tenant_id"]),
                    target_tenant_name=str(options["weknora_tenant_name"]),
                )
                if not weknora_runtime.get("configured"):
                    raise RuntimeError(
                        str(weknora_runtime.get("error") or "WeKnora runtime validation failed")
                    )
                set_checkpoint_step(
                    checkpoint,
                    weknora_runtime_step,
                    "done",
                    details=weknora_runtime,
                )
                print(
                    "[+] WeKnora MCP runtime is ready: "
                    f"{weknora_runtime.get('knowledge_base_count', 0)} knowledge base(s) verified."
                )
                print(f"    Service/public target: {weknora_runtime.get('service_url') or '(not recorded)'}")
                print(f"    REST API base used: {weknora_runtime.get('base_url') or '(not recorded)'}")
                print(f"    Catalog request: {weknora_runtime.get('catalog_url') or '(not recorded)'}")
                print(f"    Endpoint source: {weknora_runtime.get('endpoint_source') or '(not recorded)'}")
                print(
                    "    Workspace: "
                    f"{weknora_runtime.get('tenant_name') or '?'} "
                    f"(tenant_id={weknora_runtime.get('tenant_id') or '?'}, "
                    f"key_scope={weknora_runtime.get('scope_type') or 'unknown'})"
                )
                print(f"    Workspace probe report: {WEKNORA_WORKSPACE_PROBE_REPORT}")
                if weknora_runtime.get("endpoint_fallback_used"):
                    print("    Note: a verified fallback API endpoint was selected instead of the web/proxy candidate.")
                print(f"    Catalog probe report: {WEKNORA_CATALOG_PROBE_REPORT}")
            except Exception as exc:
                installed["weknora"] = False
                if "weknora-runtime" not in package_failures:
                    package_failures.append("weknora-runtime")
                if not weknora_runtime:
                    weknora_runtime = {
                        "configured": False,
                        "healthy": bool(weknora_info.get("healthy")),
                        "error": str(exc),
                    }
                set_checkpoint_step(
                    checkpoint,
                    weknora_runtime_step,
                    "failed",
                    error=str(exc),
                    details=weknora_runtime,
                )
                print(f"[!] WeKnora integration was not exposed: {exc}")
                if weknora_runtime.get("base_url"):
                    print(f"    REST API base tested: {weknora_runtime.get('base_url')}")
                if weknora_runtime.get("catalog_url"):
                    print(f"    Catalog request tested: {weknora_runtime.get('catalog_url')}")
                print(f"    Catalog probe report: {weknora_runtime.get('catalog_probe_report') or WEKNORA_CATALOG_PROBE_REPORT}")
                print(f"    Workspace probe report: {weknora_runtime.get('workspace_probe_report') or WEKNORA_WORKSPACE_PROBE_REPORT}")
                print(f"    Runtime report: {WEKNORA_RUNTIME_REPORT}")
                print(
                    "    Select the workspace with -WeKnoraTenantId <id> or -WeKnoraTenantName <name>. "
                    "A tenant-scoped key cannot switch workspaces; for local WSL keep auto-provision enabled "
                    "so the installer can create a least-privileged fixed-workspace platform key."
                )
            checkpoint["weknora_runtime"] = weknora_runtime
            checkpoint["installed"] = installed
            save_checkpoint(checkpoint)
        elif options["weknora"] and weknora_info.get("found"):
            reason = "WeKnora MCP package or healthy backend is unavailable"
            set_checkpoint_step(
                checkpoint,
                weknora_runtime_step,
                "skipped",
                details={"reason": reason},
            )
        else:
            reason = "WeKnora integration disabled" if not options["weknora"] else "WeKnora not detected"
            set_checkpoint_step(
                checkpoint,
                weknora_runtime_step,
                "skipped",
                details={"reason": reason},
            )

        physnemo_runtime: Dict[str, Any] = {}
        physnemo_step = "physnemo-runtime-v294"
        physnemo_info = data.get("applications", {}).get(PHYSNEMO_ROUTE, {})
        if options["physnemo"] and physnemo_info.get("installable"):
            print("[*] Installing/repairing integrated PhysicsNeMo MCP runtime in WSL2...")
            set_checkpoint_step(checkpoint, physnemo_step, "running")
            physnemo_runtime = prepare_physnemo_runtime(options, force=bool(args.force))
            checkpoint["physnemo_runtime"] = physnemo_runtime
            if physnemo_runtime.get("configured"):
                installed[PHYSNEMO_ROUTE] = True
                set_checkpoint_step(checkpoint, physnemo_step, "done", details=physnemo_runtime)
                print(
                    "[+] PhysicsNeMo runtime is ready: "
                    f"NAT {physnemo_runtime.get('nat_version')}, "
                    f"PhysicsNeMo {physnemo_runtime.get('physicsnemo_version')} "
                    f"({physnemo_runtime.get('physicsnemo_profile')})."
                )
                print(f"    WSL2: {physnemo_runtime.get('distro')}:{physnemo_runtime.get('linux_install_dir')}")
                print(f"    MCP: {physnemo_runtime.get('mcp_url')}")
            else:
                installed[PHYSNEMO_ROUTE] = False
                error = str(physnemo_runtime.get("error") or "PhysicsNeMo runtime installation failed")
                package_failures.append("physnemo-runtime")
                set_checkpoint_step(checkpoint, physnemo_step, "failed", error=error, details=physnemo_runtime)
                print(f"[!] PhysicsNeMo integration was not exposed: {error}")
                print(f"    Failed stage: {physnemo_runtime.get('failed_stage') or physnemo_runtime.get('stage') or 'unknown'}")
                print(f"    WSL command log: {physnemo_runtime.get('wsl_command_log') or PHYSNEMO_WSL_INSTALL_LOG}")
                if physnemo_runtime.get("failed_scripts"):
                    print(f"    Failed WSL script: {physnemo_runtime['failed_scripts'][-1]}")
                print(f"    Runtime report: {PHYSNEMO_RUNTIME_REPORT}")
        else:
            installed[PHYSNEMO_ROUTE] = False
            reason = (
                "PhysicsNeMo integration disabled"
                if not options["physnemo"]
                else str(physnemo_info.get("reason") or "No installable WSL2 distribution was detected")
            )
            set_checkpoint_step(checkpoint, physnemo_step, "skipped", details={"reason": reason})
            if options["physnemo"]:
                print(f"[*] PhysicsNeMo skipped: {reason}")
        checkpoint["installed"] = installed
        save_checkpoint(checkpoint)

        for route, metadata in COMMUNITY_SERVERS.items():
            step_name = f"server:{route}"
            target = options["community"] and detected_for_server(route, metadata, data)
            if not target:
                installed[route] = False
                reason = "community integrations disabled" if not options["community"] else "application not detected"
                set_checkpoint_step(checkpoint, step_name, "skipped", details={"reason": reason})
                continue
            if step_done(checkpoint, step_name) and command_installed(metadata["command"]):
                installed[route] = True
                print(f"[*] {metadata['label']} community MCP already complete; skipping.")
                continue
            print(f"[*] Installing community integration for {metadata['label']}...")
            set_checkpoint_step(checkpoint, step_name, "running")
            try:
                pip_install(metadata["package"])
                if not command_installed(metadata["command"]):
                    raise RuntimeError(f"Expected command not found: {metadata['command']}")
                installed[route] = True
                set_checkpoint_step(checkpoint, step_name, "done")
            except Exception as exc:
                installed[route] = False
                package_failures.append(route)
                set_checkpoint_step(checkpoint, step_name, "failed", error=str(exc))
                print(f"[!] {metadata['label']}: {exc}")
            checkpoint["installed"] = installed
            save_checkpoint(checkpoint)

        checkpoint["installed"] = installed
        save_checkpoint(checkpoint)

        set_checkpoint_step(checkpoint, "configuration", "running")
        config = generate_mcpo_config(installed, data, matlab_binary, physnemo_runtime)
        routes = list(config.get("mcpServers", {}))
        weknora_stdio_preflight: Dict[str, Any] = {}
        if "weknora" in routes:
            print("[*] Running direct WeKnora stdio tools/list preflight before MCPO startup...")
            weknora_stdio_preflight = probe_configured_stdio_route(
                "weknora",
                timeout=min(90.0, float(options["weknora_health_timeout"])),
            )
            atomic_write_json(WEKNORA_STDIO_PREFLIGHT_REPORT, weknora_stdio_preflight, private=True)
            if not weknora_stdio_preflight.get("success"):
                raise RuntimeError(
                    "WeKnora REST API is healthy, but the isolated MCP stdio adapter failed its "
                    f"tools/list preflight: {weknora_stdio_preflight.get('error') or 'unknown error'}. "
                    f"Diagnostic report: {WEKNORA_STDIO_PREFLIGHT_REPORT}"
                )
            print(
                "[+] WeKnora stdio preflight passed: "
                f"{weknora_stdio_preflight.get('tool_count', 0)} tools."
            )
        physnemo_windows_bridge_required = bool(
            physnemo_runtime
            and physnemo_runtime.get("agent_via_windows_bridge")
            and PHYSNEMO_ROUTE in routes
        )
        bind_host = (
            "0.0.0.0"
            if data.get("docker", {}).get("openwebui_container") or physnemo_windows_bridge_required
            else "127.0.0.1"
        )
        previous_state = load_state()
        physnemo_mcp_preflight: Dict[str, Any] = {}
        state = {
            "schema": 2,
            "bootstrapper_version": BOOTSTRAPPER_VERSION,
            "installed_at": previous_state.get("installed_at") or now_iso(),
            "mcpo_port": options["port"],
            "startup_timeout": options["startup_timeout"],
            "bind_host": bind_host,
            "api_key": checkpoint["api_key"],
            "installed": installed,
            "matlab_binary": str(matlab_binary) if matlab_binary else checkpoint.get("matlab_binary"),
            "matlab_runtime": matlab_runtime or checkpoint.get("matlab_runtime", {}),
            "weknora_runtime": weknora_runtime or checkpoint.get("weknora_runtime", {}),
            "weknora_health_timeout": options["weknora_health_timeout"],
            "physnemo_runtime": physnemo_runtime or checkpoint.get("physnemo_runtime", {}),
            "community_enabled": options["community"],
            "options": options,
            "scan": data,
            "routes": routes,
            "proxy_required": bool(routes),
            "mcpo_version": current_mcpo_version,
            "mcpo_environment": mcpo_environment,
            "weknora_stdio_preflight": weknora_stdio_preflight,
            "physnemo_mcp_preflight": physnemo_mcp_preflight,
        }
        save_state(state)
        write_openwebui_connections(state)
        set_checkpoint_step(checkpoint, "configuration", "done", details={"routes": routes})

        generate_launchers()
        set_checkpoint_step(checkpoint, "launchers", "done")

        if routes and options["autostart"]:
            set_checkpoint_step(checkpoint, "autostart", "running")
            service_info = register_autostart()
            state["autostart"] = service_info
            save_state(state)
            set_checkpoint_step(checkpoint, "autostart", "done", details=service_info)
            print(f"[+] Persistent background startup registered: {service_info.get('type')}")
        elif not routes:
            unregister_autostart()
            state["autostart"] = {"registered": False, "reason": "no MCPO-backed routes"}
            save_state(state)
            set_checkpoint_step(checkpoint, "autostart", "skipped", details={"reason": "no MCPO-backed routes"})
        else:
            unregister_autostart()
            state["autostart"] = {"registered": False, "reason": "disabled by option"}
            save_state(state)
            set_checkpoint_step(checkpoint, "autostart", "skipped", details={"reason": "disabled by option"})

        gateway_started = True
        verification: Dict[str, Any] = {}
        if routes and options["start"]:
            set_checkpoint_step(checkpoint, "start", "running")
            gateway_started = start_background(state)
            set_checkpoint_step(
                checkpoint,
                "start",
                "done" if gateway_started else "failed",
                error=None if gateway_started else "Gateway did not become ready before the startup timeout",
            )
            if gateway_started:
                # start_background() has already waited for the socket.  Route
                # verification now runs only against a genuinely ready HTTP app.
                verification = check_endpoints(state, quiet=False, wait_timeout=0.0)
            else:
                # Avoid the former misleading cascade of one schema failure per
                # product while the single shared gateway port is still closed.
                verification = check_endpoints(state, quiet=True, wait_timeout=0.0)
        else:
            set_checkpoint_step(checkpoint, "start", "skipped", details={"reason": "disabled or no routes"})

        physnemo_preflight_step = "physnemo-mcp-tool-health-v280"
        if (
            PHYSNEMO_ROUTE in routes
            and options["start"]
            and gateway_started
            and verification.get("servers", {}).get(PHYSNEMO_ROUTE, {}).get("ready")
        ):
            set_checkpoint_step(checkpoint, physnemo_preflight_step, "running")
            physnemo_mcp_preflight = probe_physnemo_mcp(
                state, timeout=min(120.0, float(options["startup_timeout"]))
            )
            state.setdefault("physnemo_runtime", {})["mcp_preflight"] = physnemo_mcp_preflight
            state["physnemo_mcp_preflight"] = physnemo_mcp_preflight
            if physnemo_mcp_preflight.get("success"):
                set_checkpoint_step(
                    checkpoint, physnemo_preflight_step, "done", details=physnemo_mcp_preflight
                )
                print(
                    "[+] PhysicsNeMo MCP preflight passed: "
                    f"{physnemo_mcp_preflight.get('tool_count', 0)} tools."
                )
            else:
                set_checkpoint_step(
                    checkpoint,
                    physnemo_preflight_step,
                    "failed",
                    error=str(physnemo_mcp_preflight.get("error") or "PhysicsNeMo MCP preflight failed"),
                    details=physnemo_mcp_preflight,
                )
                package_failures.append("physnemo-mcp-runtime")
        elif PHYSNEMO_ROUTE in routes:
            reason = "gateway/schema verification unavailable" if options["start"] else "gateway start disabled"
            set_checkpoint_step(checkpoint, physnemo_preflight_step, "skipped", details={"reason": reason})

        physnemo_agent_bridge_preflight: Dict[str, Any] = {}
        if (
            PHYSNEMO_ROUTE in routes
            and options["start"]
            and gateway_started
            and physnemo_mcp_preflight.get("success")
            and state.get("physnemo_runtime", {}).get("agent_configured")
        ):
            bridge_step = "physnemo-openwebui-agent-bridge-v2918"
            set_checkpoint_step(checkpoint, bridge_step, "running")
            physnemo_agent_bridge_preflight = probe_physnemo_agent_bridge(
                state, timeout=min(120.0, float(options["startup_timeout"]))
            )
            state["physnemo_agent_bridge_preflight"] = physnemo_agent_bridge_preflight
            if physnemo_agent_bridge_preflight.get("success"):
                set_checkpoint_step(
                    checkpoint, bridge_step, "done", details=physnemo_agent_bridge_preflight
                )
                if not physnemo_agent_bridge_preflight.get("skipped"):
                    print("[+] PhysicsNeMo WSL/Open WebUI agent bridge preflight passed: JSON, SSE, LangChain.")
            else:
                set_checkpoint_step(
                    checkpoint,
                    bridge_step,
                    "failed",
                    error=str(
                        physnemo_agent_bridge_preflight.get("error")
                        or "PhysicsNeMo agent bridge preflight failed"
                    ),
                    details=physnemo_agent_bridge_preflight,
                )
                package_failures.append("physnemo-openwebui-agent-bridge")
                print(f"[!] PhysicsNeMo agent bridge report: {PHYSNEMO_AGENT_BRIDGE_PREFLIGHT_REPORT}")

        native_step = "physnemo-native-tools-roundtrip-v2918"
        # Readiness is scoped to this installation attempt, never a saved older success.
        state["physnemo_native_tools_preflight"] = {
            "success": False, "attempted": False, "checked_at": now_iso(),
            "contract": "PHYSNEMO_NATIVE_TOOL_DISPATCH_V5",
            "preflight_contract": "PHYSNEMO_NATIVE_TOOL_PREFLIGHT_V5",
            "reason": "Native execution has not been verified in this installation attempt."}
        if (PHYSNEMO_ROUTE in routes and options["start"] and gateway_started
            and physnemo_mcp_preflight.get("success")
            and state.get("physnemo_runtime", {}).get("agent_configured")
            and physnemo_agent_bridge_preflight.get("success")):
            set_checkpoint_step(checkpoint, native_step, "running")
            native_report = probe_physnemo_native_tools(state)
            state["physnemo_native_tools_preflight"] = native_report
            if native_report.get("success"):
                set_checkpoint_step(checkpoint, native_step, "done", details=native_report)
                print("[+] PhysicsNeMo model tools preflight passed: local IO + model-directed actions, exact text roundtrip, actual Python subprocess.")
                print(f"    Selected tool transport: {native_report.get('selected_tool_transport')}; native API verified: {native_report.get('native_tool_calls_verified', False)}")
            else:
                set_checkpoint_step(checkpoint, native_step, "failed", details=native_report,
                    error=str(native_report.get("error") or "PHYSNEMO_NATIVE_PREFLIGHT_FAILED"))
                package_failures.append("physnemo-native-tools-roundtrip")
                print("[!] PhysicsNeMo native tool execution is NOT ready. Inspect physnemo-native-tools-preflight.json.")
                print(f"    Stage: {native_report.get('failed_stage') or 'unknown'}; code: {native_report.get('error') or 'unknown'}")
                print(f"    Local tools: {(native_report.get('local_probe') or {}).get('success', False)}; model tools: {(native_report.get('model_probe') or {}).get('success', False)}")
                validation = native_report.get("validation_error") or {}
                if validation.get("reason"):
                    print(f"    JSON validation: {validation['reason']}; attempt {validation.get('attempt', '?')}/{validation.get('max_attempts', '?')}")
        elif PHYSNEMO_ROUTE in routes:
            set_checkpoint_step(checkpoint, native_step, "skipped", details={
                "reason": "Configured agent and running, verified transport required; native execution NOT verified."})

        weknora_mcp_runtime_report: Dict[str, Any] = {}
        weknora_mcp_runtime_step = "weknora-mcp-tool-health-v264"
        if (
            routes
            and options["start"]
            and gateway_started
            and verification.get("servers", {}).get("weknora", {}).get("ready")
            and "weknora" in routes
            and installed.get("weknora")
        ):
            set_checkpoint_step(checkpoint, weknora_mcp_runtime_step, "running")
            weknora_mcp_runtime_report = weknora_mcp_runtime_test(
                state,
                timeout=float(options["weknora_health_timeout"]),
                quiet=False,
            )
            state.setdefault("weknora_runtime", {})["mcp_tool_health"] = weknora_mcp_runtime_report
            if weknora_mcp_runtime_report.get("success"):
                set_checkpoint_step(
                    checkpoint,
                    weknora_mcp_runtime_step,
                    "done",
                    details=weknora_mcp_runtime_report,
                )
            else:
                set_checkpoint_step(
                    checkpoint,
                    weknora_mcp_runtime_step,
                    "failed",
                    error=str(
                        weknora_mcp_runtime_report.get("error")
                        or "WeKnora MCP runtime verification failed"
                    ),
                    details=weknora_mcp_runtime_report,
                )
                if "weknora-mcp-runtime" not in package_failures:
                    package_failures.append("weknora-mcp-runtime")
        elif "weknora" in routes:
            reason = "gateway/schema verification unavailable" if options["start"] else "gateway start disabled"
            set_checkpoint_step(
                checkpoint,
                weknora_mcp_runtime_step,
                "skipped",
                details={"reason": reason},
            )

        matlab_mcp_runtime_report: Dict[str, Any] = {}
        matlab_runtime_step = "matlab-mcp-tool-health-v253"
        if (
            routes
            and options["start"]
            and gateway_started
            and verification.get("ok", False)
            and "matlab" in routes
            and installed.get("matlab")
            and matlab_binary
        ):
            set_checkpoint_step(checkpoint, matlab_runtime_step, "running")
            matlab_mcp_runtime_report, gateway_started, post_repair_verification = ensure_matlab_mcp_tool_runtime(
                state,
                data,
                matlab_binary,
                auto_repair=bool(options["matlab_repair"]),
                force_matlab_close=bool(options["matlab_force_close"]),
                health_timeout=float(options["matlab_health_timeout"]),
            )
            if post_repair_verification:
                verification = post_repair_verification
            state.setdefault("matlab_runtime", {})["mcp_tool_health"] = matlab_mcp_runtime_report
            if matlab_mcp_runtime_report.get("success"):
                set_checkpoint_step(
                    checkpoint,
                    matlab_runtime_step,
                    "done",
                    details=matlab_mcp_runtime_report,
                )
            else:
                set_checkpoint_step(
                    checkpoint,
                    matlab_runtime_step,
                    "failed",
                    error=str(matlab_mcp_runtime_report.get("error") or "MATLAB MCP tool runtime failed"),
                    details=matlab_mcp_runtime_report,
                )
                if "matlab-mcp-runtime" not in package_failures:
                    package_failures.append("matlab-mcp-runtime")
                print(f"[!] MATLAB MCP runtime report: {MATLAB_MCP_RUNTIME_REPORT}")
        elif "matlab" in routes:
            reason = "gateway/schema verification unavailable" if options["start"] else "gateway start disabled"
            set_checkpoint_step(checkpoint, matlab_runtime_step, "skipped", details={"reason": reason})

        if (
            PHYSNEMO_ROUTE in routes
            and options["start"]
            and gateway_started
            and verification.get("servers", {}).get(PHYSNEMO_ROUTE, {}).get("ready")
        ):
            physnemo_openwebui_sync = sync_physnemo_openwebui_tool_server(state, options)
            state["physnemo_openwebui_sync"] = physnemo_openwebui_sync
            if physnemo_openwebui_sync.get("chat_tool_execution_ready"):
                print("[+] Open WebUI loaded all Engineering MCP tool servers live; PhysicsNeMo is chat-ready.")
                print("    The active global Engineering MCP tool router injects server:physnemo into explicit requests.")
                print("    physnemo__solve, artifact gallery and signed downloads are present in the live schema.")
                print("    PhysicsNeMo automatic lifecycle: correlated solve/status schema and request hook installed.")
            elif physnemo_openwebui_sync.get("verified"):
                print("[!] Open WebUI loaded the PhysicsNeMo schema, but chat execution readiness did not pass.")
                print(f"    {physnemo_openwebui_sync.get('reason') or 'Check DLP/tool-server readiness.'}")
                print(f"    Report: {PHYSNEMO_OPENWEBUI_SYNC_REPORT}")
            elif physnemo_openwebui_sync.get("updated"):
                print("[!] Open WebUI accepted the tool-server refresh, but verification did not pass.")
                print(f"    Report: {PHYSNEMO_OPENWEBUI_SYNC_REPORT}")
            else:
                print("[!] Open WebUI PhysicsNeMo schema was not refreshed automatically.")
                print(f"    {physnemo_openwebui_sync.get('reason') or 'Use the generated import file.'}")
                print(f"    Report: {PHYSNEMO_OPENWEBUI_SYNC_REPORT}")
            if not physnemo_openwebui_sync.get("chat_tool_registration_ready"):
                package_failures.append("physnemo-openwebui-live-tool-sync")

        if (
            PHYSNEMO_ROUTE in routes
            and state.get("physnemo_runtime", {}).get("configured")
            and not state.get("physnemo_runtime", {}).get("agent_configured")
            and not options.get("physnemo_allow_unconfigured_agent")
        ):
            print("[!] PhysicsNeMo backend is installed, but physnemo__solve has no configured LLM agent.")
            print("    Auto-detection/provisioning did not select a usable model; pass -PhysNeMoAgentModel.")
            package_failures.append("physnemo-agent-unconfigured")

        state["gateway_started"] = gateway_started if routes and options["start"] else None
        state["last_verification"] = verification
        state["autostart"] = autostart_status() if routes else state.get("autostart", {})
        save_state(state)

        verification_failed = bool(
            routes
            and options["start"]
            and (not gateway_started or not verification.get("ok", False))
        )
        checkpoint["complete"] = not package_failures and not verification_failed
        checkpoint["completed_at"] = now_iso() if checkpoint["complete"] else None
        checkpoint["package_failures"] = package_failures
        checkpoint["verification_failed"] = verification_failed
        save_checkpoint(checkpoint)

        print("\n[+] Installation/configuration phase finished.")
        print(f"    Home: {APP_HOME}")
        print(f"    Configured routes: {', '.join(routes) or '(none)'}")
        print(f"    Autostart: {state.get('autostart')}")
        print_webui_config(state)

        fusion = data.get("applications", {}).get("fusion", {})
        if fusion.get("found") and not fusion.get("mcp_port_open"):
            print("\n[!] Autodesk Fusion is installed, but its MCP port is closed.")
            print("    Enable Preferences > General > API > Fusion MCP Server in Fusion.")

        if package_failures:
            print("\n[!] Some MCP package steps failed: " + ", ".join(package_failures))
            print("    Correct the reported cause and run: install-engineering-mcp-unified-v2.9.18.ps1 -Resume")
            return 2
        if routes and options["start"] and not gateway_started:
            print(
                "\n[!] The MCP gateway did not become HTTP-ready within "
                f"{int(options['startup_timeout'])} seconds."
            )
            print("    The relevant MCPO log tail was printed above.")
            print("    After correcting the logged cause, run: install-engineering-mcp-unified-v2.9.18.ps1 -Resume")
            return 3
        if routes and options["start"] and not verification.get("ok", False):
            failed_routes = [
                route
                for route, item in verification.get("servers", {}).items()
                if not item.get("ready")
            ]
            print("\n[!] OpenAPI verification failed for: " + ", ".join(failed_routes))
            print(f"    Detailed OpenAPI report: {OPENAPI_VERIFICATION_REPORT}")
            if "weknora" in failed_routes:
                print(f"    WeKnora direct stdio report: {WEKNORA_STDIO_PREFLIGHT_REPORT}")
                print(f"    MCPO log: {LOG_DIR / 'mcpo.log'}")
            if PHYSNEMO_ROUTE in failed_routes:
                print(f"    PhysicsNeMo MCP report: {PHYSNEMO_MCP_PREFLIGHT_REPORT}")
                print(f"    PhysicsNeMo WSL proxy log: {PHYSNEMO_WSL_PROXY_LOG}")
                print(f"    PhysicsNeMo runtime report: {PHYSNEMO_RUNTIME_REPORT}")
                print(f"    PhysicsNeMo agent bridge report: {PHYSNEMO_AGENT_BRIDGE_PREFLIGHT_REPORT}")
            print("    Run the same uniquely named installer with -Resume after correcting the reported adapter issue.")
            return 4
        return 0

    except KeyboardInterrupt:
        checkpoint["interrupted_at"] = now_iso()
        checkpoint["complete"] = False
        save_checkpoint(checkpoint)
        print("\n[!] Installation interrupted. Run with --resume to continue.")
        return 130
    except BrokenVirtualEnvironmentError as exc:
        checkpoint["complete"] = False
        checkpoint["last_error"] = str(exc)
        checkpoint["failed_at"] = now_iso()
        save_checkpoint(checkpoint)
        print(f"\n[!] Virtual environment became invalid during package installation: {exc}")
        print(f"    Full diagnostics: {VENV_REPAIR_LOG} and {PIP_LOG_FILE}")
        print("    Run the same uniquely named installer with -Resume; the venv health phase will rebuild it automatically.")
        return 1
    except Exception as exc:
        checkpoint["complete"] = False
        checkpoint["last_error"] = str(exc)
        checkpoint["failed_at"] = now_iso()
        save_checkpoint(checkpoint)
        print(f"\n[!] Installation failed: {exc}")
        print(f"    Package/venv logs: {PIP_LOG_FILE} and {VENV_REPAIR_LOG}")
        print("    Run with --resume after correcting the cause.")
        return 1


def status() -> None:
    state = load_state()
    saved_options = state.get("options", {}) if state else {}
    data = scan(
        weknora_url=str(saved_options.get("weknora_url") or ""),
        weknora_api_url=str(saved_options.get("weknora_api_url") or ""),
        weknora_distro=str(saved_options.get("weknora_distro") or ""),
        weknora_install_dir=str(saved_options.get("weknora_install_dir") or ""),
        weknora_health_timeout=5.0,
        weknora_ca_certificate=str(saved_options.get("weknora_ca_certificate") or ""),
        physnemo_distro=str(saved_options.get("physnemo_distro") or ""),
        physnemo_install_dir=str(saved_options.get("physnemo_install_dir") or ""),
    )
    print_scan(data)
    print("\n=== Installation/service status ===")
    if not state:
        print("State: not installed")
        return
    print(f"Bootstrapper version: {state.get('bootstrapper_version')}")
    print(f"MCPO port: {state.get('mcpo_port')}")
    print(f"Configured routes: {', '.join(configured_routes()) or '(none)'}")
    supervisor_pid = read_pid(SUPERVISOR_PID_FILE)
    mcpo_pid = read_pid(MCPO_PID_FILE)
    print(f"Supervisor: {'running PID ' + str(supervisor_pid) if supervisor_pid and process_alive(supervisor_pid) else 'not running'}")
    print(f"MCPO: {'running PID ' + str(mcpo_pid) if mcpo_pid and process_alive(mcpo_pid) else 'not running'}")
    print(f"Autostart: {autostart_status()}")
    physnemo_runtime = state.get("physnemo_runtime", {})
    if physnemo_runtime:
        print(
            "PhysicsNeMo: "
            + (
                f"configured, WSL={physnemo_runtime.get('distro') or '?'}, "
                f"NAT={physnemo_runtime.get('nat_version') or '?'}, "
                f"PhysicsNeMo={physnemo_runtime.get('physicsnemo_version') or '?'}, "
                f"MCP={physnemo_runtime.get('mcp_url') or '?'}"
                if physnemo_runtime.get("configured")
                else f"not configured ({physnemo_runtime.get('error') or physnemo_runtime.get('reason') or 'unknown reason'})"
            )
        )
    weknora_runtime = state.get("weknora_runtime", {})
    if weknora_runtime:
        print(
            "WeKnora: "
            + (
                f"configured, {weknora_runtime.get('knowledge_base_count', 0)} verified KB(s), "
                f"workspace={weknora_runtime.get('tenant_name') or '?'} "
                f"(tenant_id={weknora_runtime.get('tenant_id') or '?'}), "
                f"target={weknora_runtime.get('api_url') or weknora_runtime.get('base_url') or 'unknown'}"
                if weknora_runtime.get("configured")
                else f"not configured ({weknora_runtime.get('error') or 'unknown reason'})"
            )
        )
    checkpoint = load_checkpoint()
    if checkpoint:
        print(f"Installation checkpoint complete: {checkpoint.get('complete', False)}")
        failures = checkpoint.get("package_failures", [])
        if failures:
            print(f"Pending retry: {', '.join(failures)}")
    if configured_routes():
        check_endpoints(state)


def uninstall() -> int:
    print("\n=== Engineering MCP uninstall ===")
    try:
        stop_background(create_home=False)
    except Exception as exc:
        print(f"[!] Stop warning: {exc}")
    try:
        unregister_autostart()
        print("[+] Persistent autostart registration removed.")
    except Exception as exc:
        print(f"[!] Autostart removal warning: {exc}")
    physnemo_removal = uninstall_physnemo_runtime(load_state())
    if physnemo_removal.get("removed"):
        print(
            "[+] Managed PhysicsNeMo/NAT WSL runtime removed: "
            f"{physnemo_removal.get('distro')}:{physnemo_removal.get('linux_install_dir')}"
        )
    elif physnemo_removal.get("error"):
        print(f"[!] PhysicsNeMo WSL cleanup warning: {physnemo_removal.get('error')}")

    if sys.platform.startswith("win"):
        # Never recursively remove APP_HOME from a Python process on Windows.
        # Native extension DLLs (for example bcrypt/_bcrypt.pyd), python.exe,
        # or a child MCP process can still hold image sections open until this
        # interpreter exits.  install-engineering-mcp-unified-v2.9.18.ps1 always performs the final, retried
        # process cleanup and directory removal *after* this process terminates.
        print(
            "[*] Windows runtime cleanup completed; final directory removal is "
            "delegated to install-engineering-mcp-unified-v2.9.18.ps1 after the Python process exits."
        )
    else:
        shutil.rmtree(APP_HOME, ignore_errors=False) if APP_HOME.exists() else None
        print(f"[+] Removed {APP_HOME}")
    print("Engineering applications and the system Python installation were left untouched.")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def normalize_legacy_argv(argv: List[str]) -> List[str]:
    # Backwards compatibility with the first release, which used subcommands.
    # In particular, `install --start` used --start as an install option; the
    # current CLI reserves --start for the standalone service operation.
    if argv and argv[0] in ("install", "resume"):
        converted: List[str] = []
        for item in argv[1:]:
            if item == "--start":
                converted.append("--run-after-install")
            elif item == "--no-start":
                converted.append("--no-run-after-install")
            else:
                converted.append(item)
        argv = [argv[0], *converted]
    mapping = {
        "scan": "--scan",
        "install": "--install",
        "resume": "--resume",
        "uninstall": "--uninstall",
        "start": "--start",
        "stop": "--stop",
        "status": "--status",
        "config": "--config",
        "check": "--check",
        "matlab-image-test": "--matlab-image-test",
        "service": "--service",
    }
    if argv and argv[0] in mapping:
        return [mapping[argv[0]], *argv[1:]]
    return argv


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Engineering MCP Unified Bootstrapper")
    operation = parser.add_mutually_exclusive_group(required=True)
    operation.add_argument("--install", action="store_true", help="Install or upgrade detected MCP integrations")
    operation.add_argument("--resume", action="store_true", help="Resume/repair an interrupted installation")
    operation.add_argument("--uninstall", action="store_true", help="Remove the MCP tools, service and generated configuration")
    operation.add_argument("--scan", action="store_true", help="Detect engineering applications")
    operation.add_argument("--start", dest="start_operation", action="store_true", help="Start the background gateway")
    operation.add_argument("--stop", action="store_true", help="Stop the background gateway without unregistering autostart")
    operation.add_argument("--status", action="store_true", help="Show detection, service and endpoint status")
    operation.add_argument("--config", action="store_true", help="Print the Open WebUI connection settings")
    operation.add_argument("--check", action="store_true", help="Verify every named OpenAPI schema endpoint")
    operation.add_argument(
        "--matlab-image-test",
        action="store_true",
        help="Call MATLAB visualization directly and save the returned PNG (bypasses the LLM)",
    )
    operation.add_argument("--service", action="store_true", help=argparse.SUPPRESS)

    parser.add_argument("--port", type=int, default=None, help=f"MCPO gateway port (default {DEFAULT_MCPO_PORT})")
    parser.add_argument(
        "--startup-timeout",
        type=float,
        default=None,
        help=f"Maximum gateway startup wait in seconds (default {int(DEFAULT_STARTUP_TIMEOUT)})",
    )
    parser.add_argument(
        "--matlab-health-timeout",
        type=float,
        default=None,
        help=f"Maximum MATLAB licensing health wait in seconds (default {int(DEFAULT_MATLAB_HEALTH_TIMEOUT)})",
    )
    parser.add_argument(
        "--matlab-repair",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Automatically repair MathWorks Service Host when MATLAB startup/licensing fails",
    )
    parser.add_argument(
        "--matlab-force-close",
        action="store_true",
        help="Force-close running MATLAB before repair (can discard unsaved work)",
    )
    parser.add_argument(
        "--physnemo",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Enable/disable the integrated PhysicsNeMo MCP route through NeMo Agent Toolkit in WSL2",
    )
    parser.add_argument("--physnemo-distro", default=None, help="WSL2 distribution for the managed NeMo Agent Toolkit runtime")
    parser.add_argument("--physnemo-install-dir", default=None, help="Managed Linux directory for PhysicsNeMo inside WSL2")
    parser.add_argument("--physnemo-nat-port", type=int, default=None, help=f"Loopback NAT MCP port (default {DEFAULT_PHYSNEMO_NAT_PORT})")
    parser.add_argument("--physnemo-nat-version", default=None, help=f"Pinned nvidia-nat/nvidia-nat-mcp version (default {DEFAULT_PHYSNEMO_NAT_VERSION})")
    parser.add_argument("--physicsnemo-version", default=None, help=f"Pinned nvidia-physicsnemo version (default {DEFAULT_PHYSNEMO_VERSION})")
    parser.add_argument("--physicsnemo-profile", choices=("base", "cu12", "cu13"), default=None, help="PhysicsNeMo dependency profile")
    parser.add_argument("--physicsnemo-source-ref", default=None, help=f"Pinned NVIDIA/physicsnemo git ref (default {DEFAULT_PHYSNEMO_SOURCE_REF})")
    parser.add_argument(
        "--physnemo-install-prerequisites",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Allow apt installation of Python venv, git, curl and CA certificates inside WSL2",
    )
    parser.add_argument("--physnemo-agent-base-url", default=None, help="OpenAI-compatible base URL used by the internal NeMo Agent Toolkit agent")
    parser.add_argument("--physnemo-agent-model", default=None, help="Model id used by the internal NeMo Agent Toolkit agent")
    parser.add_argument("--physnemo-agent-api-key-file", default=None, help="File containing the LLM provider API key for the internal NeMo agent")
    parser.add_argument(
        "--physnemo-agent-auto-detect",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Auto-detect the LLM provider from the e-INFRA Open WebUI runtime configuration",
    )
    parser.add_argument("--physnemo-openwebui-url", default=None, help="Open WebUI backend base URL for optional authenticated file-id import")
    parser.add_argument("--physnemo-openwebui-api-key-file", default=None, help="Open WebUI user API key file enabling direct import of attached file ids")
    parser.add_argument("--physnemo-artifact-base-url", default=None, help="Externally reachable base URL for signed PhysicsNeMo artifact downloads")
    parser.add_argument("--openwebui-database", default=None, help="Optional exact native Open WebUI SQLite webui.db path")
    parser.add_argument(
        "--openwebui-native-sync",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Synchronize Engineering MCP tool servers through the native Open WebUI database/admin API",
    )
    parser.add_argument(
        "--openwebui-dlp-repair",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Activate the installed pseudo_anonymization filter when tool_anonymizovat requires it",
    )
    parser.add_argument(
        "--physnemo-allow-unconfigured-agent",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Allow installation success when physnemo__solve has no usable LLM configuration",
    )
    parser.add_argument(
        "--weknora",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Enable/disable WeKnora discovery and MCP exposure",
    )
    parser.add_argument(
        "--weknora-url",
        default=None,
        help=(
            "WeKnora HTTP or HTTPS origin, for example http://192.168.1.50:8088, "
            "https://weknora.example:8088 or a URL ending in /api/v1. "
            "HTTPS is recommended for remote devices."
        ),
    )
    parser.add_argument(
        "--weknora-api-url",
        default=None,
        help=(
            "Optional exact WeKnora REST origin/base when the public web URL uses a different port, "
            "for example http://localhost:18080 or http://localhost:18080/api/v1."
        ),
    )
    parser.add_argument(
        "--weknora-api-key-file",
        default=None,
        help=(
            "File containing a WeKnora tenant-scoped or platform API key; copied into the protected "
            "Engineering MCP secret store"
        ),
    )
    parser.add_argument(
        "--weknora-tenant-id",
        default=None,
        help=(
            "Numeric workspace/tenant id containing the books. Required when a platform key is supplied "
            "without workspace-discovery capability or when several workspaces contain knowledge bases."
        ),
    )
    parser.add_argument(
        "--weknora-tenant-name",
        default=None,
        help=(
            "Exact workspace name containing the books. Mutually exclusive with --weknora-tenant-id; "
            "the installer resolves it through a platform discovery key."
        ),
    )
    parser.add_argument(
        "--weknora-ca-certificate",
        default=None,
        help=(
            "Optional PEM root/intermediate CA for a private WeKnora certificate. "
            "The local WSL2 installer descriptor supplies it automatically when Open WebUI uses LocalCA."
        ),
    )
    parser.add_argument(
        "--weknora-distro",
        default=None,
        help="Specific WSL2 distribution containing WeKnora (auto-detected by default)",
    )
    parser.add_argument(
        "--weknora-install-dir",
        default=None,
        help="Linux WeKnora install directory inside WSL2 (descriptor/default path is auto-detected)",
    )
    parser.add_argument(
        "--weknora-auto-provision",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Allow Engineering MCP to create a bounded WeKnora API key using WSL bootstrap admin credentials",
    )
    parser.add_argument(
        "--weknora-health-timeout",
        type=float,
        default=None,
        help=(
            "Maximum WeKnora backend and MCP verification wait in seconds "
            f"(default {int(DEFAULT_WEKNORA_HEALTH_TIMEOUT)})"
        ),
    )
    parser.add_argument(
        "--weknora-allow-empty-catalog",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "Allow configuring WeKnora even when the authenticated workspace contains zero knowledge bases; "
            "by default an empty catalog is rejected with endpoint/workspace diagnostics."
        ),
    )
    parser.add_argument(
        "--community",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Enable/disable community ParaView and FreeCAD integrations",
    )
    parser.add_argument(
        "--autostart",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Enable/disable persistent startup after reboot/login",
    )
    parser.add_argument(
        "--run-after-install",
        dest="start",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Start/skip the gateway after installation",
    )
    parser.add_argument("--force", action="store_true", help="Backward-compatible flag; fresh --install already archives an incomplete checkpoint")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    raw_arguments = list(sys.argv[1:] if argv is None else argv)
    if raw_arguments and raw_arguments[0] == "--weknora-mcp-launcher":
        return run_weknora_mcp_launcher(raw_arguments[1:])
    if raw_arguments and raw_arguments[0] == "--stdio-name-proxy":
        return run_stdio_name_proxy(raw_arguments[1:])
    if raw_arguments and raw_arguments[0] == "--named-mcpo":
        return run_named_mcpo(raw_arguments[1:])
    if raw_arguments and raw_arguments[0] == "--mcp-stdio-probe":
        return run_mcp_stdio_probe(raw_arguments[1:])
    if raw_arguments and raw_arguments[0] == "--mcp-http-probe":
        return run_mcp_http_probe(raw_arguments[1:])
    normalized = normalize_legacy_argv(raw_arguments)
    parser = build_parser()
    args = parser.parse_args(normalized)

    # Uninstall is intentionally handled before ensure_dirs().  It must never
    # recreate the installation directory or execute any installation step.
    if args.uninstall:
        print(f"Bootstrapper {BOOTSTRAPPER_VERSION}: mode=UNINSTALL")
        return uninstall()

    ensure_dirs()
    if args.scan:
        print_scan(
            scan(
                weknora_url=str(args.weknora_url or ""),
                weknora_api_url=str(args.weknora_api_url or ""),
                weknora_distro=str(args.weknora_distro or ""),
                weknora_install_dir=str(args.weknora_install_dir or ""),
                weknora_health_timeout=float(args.weknora_health_timeout or 5.0),
                weknora_ca_certificate=str(args.weknora_ca_certificate or ""),
                physnemo_distro=str(args.physnemo_distro or ""),
                physnemo_install_dir=str(args.physnemo_install_dir or ""),
            )
        )
        return 0
    if args.install:
        print(f"Bootstrapper {BOOTSTRAPPER_VERSION}: mode=INSTALL")
        return install_or_resume(args, resume=False)
    if args.resume:
        print(f"Bootstrapper {BOOTSTRAPPER_VERSION}: mode=RESUME")
        return install_or_resume(args, resume=True)
    if args.start_operation:
        return 0 if start_background() else 1
    if args.stop:
        stop_background()
        return 0
    if args.status:
        status()
        return 0
    if args.config:
        print_webui_config()
        return 0
    if args.check:
        state = load_state()
        timeout = float(
            args.startup_timeout
            if args.startup_timeout is not None
            else state.get("startup_timeout", DEFAULT_STARTUP_TIMEOUT)
        )
        result = check_endpoints(state, wait_timeout=timeout)
        return 0 if result.get("ok") else 1
    if args.matlab_image_test:
        state = load_state()
        timeout = float(
            args.startup_timeout
            if args.startup_timeout is not None
            else state.get("startup_timeout", DEFAULT_STARTUP_TIMEOUT)
        )
        return 0 if matlab_image_smoke_test(state, startup_timeout=timeout) else 1
    if args.service:
        return run_supervisor()
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import builtins
import hashlib
import importlib.util
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import tempfile
import threading

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "engineering_mcp_unified-v2.9.18.py"
TMP = tempfile.TemporaryDirectory(prefix="emcp2911-router-")
os.environ["ENGINEERING_MCP_HOME"] = TMP.name
spec = importlib.util.spec_from_file_location("emcp2911_router", SOURCE)
assert spec and spec.loader
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def load_filter():
    ns = {"__name__": "engineering_mcp_tool_router_test"}
    exec(compile(m.OPENWEBUI_ENGINEERING_TOOL_ROUTER_SOURCE, "<router>", "exec"), ns, ns)
    return ns["Filter"]()


async def route(filter_obj, text: str, *, metadata: dict | None, tool_ids=None):
    body = {"messages": [{"role": "user", "content": text}]}
    if tool_ids is not None:
        body["tool_ids"] = list(tool_ids)
    meta = metadata if metadata is not None else {}
    result = await filter_obj.inlet(body, meta, {"id": "admin", "role": "admin"})
    return result, meta


f = load_filter()
body, metadata = asyncio.run(
    route(
        f,
        "Use MCP tool physnemo and send this full request: Create simulation of Karman path by PINN approach, train it and visualize artifacts.",
        metadata={"chat_id": "chat-1", "params": {"function_calling": "legacy"}},
        tool_ids=["server:weknora"],
    )
)
assert body["tool_ids"] == ["server:weknora", "server:physnemo"], body
assert metadata["params"]["function_calling"] == "native", metadata
assert body["tool_choice"] == {"type": "function", "function": {"name": "physnemo__solve"}}
assert body["parallel_tool_calls"] is False
assert "params" not in body  # apply_params_to_form_data already ran before inlet filters
assert any("[ENGINEERING_MCP_TOOL_ROUTER_V1]" in str(x.get("content")) for x in body["messages"])

# Exact public operation requests are deterministic.
body2, meta2 = asyncio.run(
    route(f, "Call physnemo__environment_info now.", metadata={"chat_id": "chat-2", "params": {}})
)
assert body2["tool_choice"]["function"]["name"] == "physnemo__environment_info"
assert meta2["params"]["function_calling"] == "native"

# Ordinary text must not silently attach Engineering MCP tools.
body3, meta3 = asyncio.run(route(f, "Explain finite elements.", metadata={"chat_id": "chat-3"}))
assert not body3.get("tool_ids") and not body3.get("tool_choice")
assert "params" not in meta3

# Nested OpenWebUI chat-completion calls made by the internal NAT agent have no
# saved-chat context and must not recursively attach physnemo.
body4, meta4 = asyncio.run(route(f, "PhysicsNeMo internal agent PINN task", metadata={}))
assert not body4.get("tool_ids") and not body4.get("tool_choice")
assert not meta4

# The embedded bootstrap has a fail-closed local self-test for the same contract.
self_test = m._engineering_tool_router_self_test(m.OPENWEBUI_ENGINEERING_TOOL_ROUTER_SOURCE)
assert self_test["ok"] and all(self_test["checks"].values()), self_test

# Regression for v2.9.9: the bootstrapper's isolated Python intentionally does
# not require Pydantic.  The local test must therefore use its temporary shim
# instead of aborting before it can create the filter through Open WebUI's API.
_real_import = builtins.__import__
_saved_pydantic = sys.modules.pop("pydantic", None)
def _without_pydantic(name, *args, **kwargs):
    if name == "pydantic" and name not in sys.modules:
        raise ModuleNotFoundError("No module named 'pydantic'", name="pydantic")
    return _real_import(name, *args, **kwargs)
builtins.__import__ = _without_pydantic
try:
    shim_test = m._engineering_tool_router_self_test(m.OPENWEBUI_ENGINEERING_TOOL_ROUTER_SOURCE)
finally:
    builtins.__import__ = _real_import
    if _saved_pydantic is not None:
        sys.modules["pydantic"] = _saved_pydantic
assert shim_test["ok"] and all(shim_test["checks"].values()), shim_test
assert shim_test["dependency_mode"] == "stdlib-self-test-shim", shim_test
assert "pydantic" in sys.modules if _saved_pydantic is not None else "pydantic" not in sys.modules

state = {"function": None}
expected_key = "sk-router-test-key-1234567890"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        return

    def _auth(self) -> bool:
        return self.headers.get("Authorization") == f"Bearer {expected_key}"

    def _json(self, status: int, payload):
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if not self._auth():
            return self._json(401, {"detail": "bad key"})
        if self.path == "/api/v1/functions/id/engineering_mcp_tool_router":
            if state["function"] is None:
                # Open WebUI's function-id endpoint currently uses 401 for not found.
                return self._json(401, {"detail": "Function not found"})
            return self._json(200, state["function"])
        return self._json(404, {})

    def do_POST(self):
        if not self._auth():
            return self._json(401, {"detail": "bad key"})
        size = int(self.headers.get("Content-Length", "0") or 0)
        payload = json.loads(self.rfile.read(size) or b"{}")
        if self.path == "/api/v1/functions/create":
            state["function"] = {
                **payload,
                "type": "filter",
                "is_active": False,
                "is_global": False,
            }
            return self._json(200, state["function"])
        if self.path == "/api/v1/functions/id/engineering_mcp_tool_router/update":
            assert state["function"] is not None
            state["function"].update(payload)
            state["function"]["type"] = "filter"
            return self._json(200, state["function"])
        if self.path == "/api/v1/functions/id/engineering_mcp_tool_router/toggle":
            state["function"]["is_active"] = not bool(state["function"].get("is_active"))
            return self._json(200, state["function"])
        if self.path == "/api/v1/functions/id/engineering_mcp_tool_router/toggle/global":
            state["function"]["is_global"] = not bool(state["function"].get("is_global"))
            return self._json(200, state["function"])
        return self._json(404, {})


server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
base = f"http://127.0.0.1:{server.server_port}"
report = m._sync_openwebui_engineering_tool_router(base, expected_key, ["physnemo", "matlab", "weknora"])
assert report["ready"], report
assert report["created"] and report["activated"] and report["globalized"]
assert report["source_matches"]
assert report["installed_source_sha256"] == hashlib.sha256(
    m.OPENWEBUI_ENGINEERING_TOOL_ROUTER_SOURCE.encode("utf-8")
).hexdigest()
assert state["function"]["is_active"] and state["function"]["is_global"]
assert state["function"]["type"] == "filter"
assert state["function"]["id"] == "engineering_mcp_tool_router"

# Resume is idempotent: update the managed filter but do not toggle it off.
report2 = m._sync_openwebui_engineering_tool_router(base, expected_key, ["physnemo"])
assert report2["ready"] and report2["updated"], report2
assert not report2["activated"] and not report2["globalized"]
assert state["function"]["is_active"] and state["function"]["is_global"]

report_text = Path(m.OPENWEBUI_ENGINEERING_TOOL_ROUTER_REPORT).read_text(encoding="utf-8")
assert expected_key not in report_text

server.shutdown()
server.server_close()
TMP.cleanup()
print("OPENWEBUI_ENGINEERING_TOOL_ROUTER_V2912_OK")

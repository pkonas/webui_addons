#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

EVENT_ID = "study_tutor_gateway_bootstrap"
PIPE_ID = "study_tutor_pipe"
RUNTIME_VERSION = "1.26.5"
RUNTIME_MARKER = "VUT-AI-TUTOR-1.26.5-SERVER-DESKTOP-WINDOWS-MOCK-TRANSPORT-COMPLETE"


class State:
    def __init__(self, prefix: str = "") -> None:
        self.prefix = prefix.rstrip("/")
        self.functions: dict[str, dict[str, Any]] = {}
        self.valves: dict[str, dict[str, Any]] = {}
        self.token = "mock-admin-token"
        self.openwebui_version = "0.11.3"
        self.runtime_active = False
        self.force_health_failure = False
        self.lock = threading.RLock()
        self.operations: list[dict[str, Any]] = []

    def record(self, method: str, path: str, **extra: Any) -> None:
        with self.lock:
            self.operations.append({"method": method, "path": path, **extra})


def infer_type(source: str) -> str:
    if re.search(r"(?m)^class\s+Event\b", source):
        return "event"
    if re.search(r"(?m)^class\s+Pipe\b", source):
        return "pipe"
    return "filter"


class Handler(BaseHTTPRequestHandler):
    server_version = "MockOpenWebUI/2.3.4"
    protocol_version = "HTTP/1.1"

    @property
    def state(self) -> State:
        return self.server.state  # type: ignore[attr-defined]

    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def _path(self) -> str:
        path = self.path.split("?", 1)[0]
        prefix = self.state.prefix
        if prefix:
            if not path.startswith(prefix + "/") and path != prefix:
                return "__outside__"
            path = path[len(prefix) :] or "/"
        return path

    def _read_json(self) -> Any:
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length) if length else b""
        if not raw:
            return None
        return json.loads(raw.decode("utf-8"))

    def _send(self, status: int, body: bytes, content_type: str, headers: dict[str, str] | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if body:
            self.wfile.write(body)
            self.wfile.flush()
        self.close_connection = True

    def _json(self, status: int, value: Any, headers: dict[str, str] | None = None) -> None:
        self._send(status, json.dumps(value, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8", headers)

    def _authorized(self) -> bool:
        return self.headers.get("Authorization", "") == f"Bearer {self.state.token}"

    def _require_auth(self) -> bool:
        if self._authorized():
            return True
        self._json(401, {"detail": "Unauthorized"})
        return False

    def do_GET(self) -> None:
        path = self._path()
        self.state.record("GET", path)
        if path == "/api/version":
            self._json(200, {"version": self.state.openwebui_version, "deployment_id": "mock-v230"})
            return
        if path == "/api/v1/functions/":
            if not self._require_auth():
                return
            with self.state.lock:
                self._json(200, list(self.state.functions.values()))
            return
        match = re.fullmatch(r"/api/v1/functions/id/([^/]+)(/valves)?", path)
        if match:
            if not self._require_auth():
                return
            function_id = match.group(1)
            with self.state.lock:
                if function_id not in self.state.functions:
                    self._json(404, {"detail": "Not found"})
                elif match.group(2):
                    self._json(200, self.state.valves.get(function_id, {}))
                else:
                    self._json(200, self.state.functions[function_id])
            return
        if path == "/study-tutor/health":
            with self.state.lock:
                event = self.state.functions.get(EVENT_ID)
                healthy = bool(event and event.get("is_active") and self.state.runtime_active and not self.state.force_health_failure)
            if not healthy:
                self._send(200, b"<!doctype html><html><title>Open WebUI</title></html>", "text/html; charset=utf-8")
                return
            routes = {
                "registration_strategy": "asgi-prefix-gateway-v7",
                "registration_version": 7,
                "healthy": True,
                "gateway_active": True,
                "main_router_mutated": False,
                "before_spa": True,
                "required_complete": True,
                "missing_required": [],
                "duplicate_method_paths": [],
                "study_routes": 43,
                "runtime_id": "mock-runtime",
                "registered_runtime_id": "mock-runtime",
                "bound_to_current_runtime": True,
            }
            self._json(
                200,
                {
                    "ok": True,
                    "version": RUNTIME_VERSION,
                    "build_marker": RUNTIME_MARKER,
                    "function_id": EVENT_ID,
                    "route_registration_version": 7,
                    "routes": routes,
                },
            )
            return
        if path == "/study-tutor/canvas":
            with self.state.lock:
                healthy = self.state.runtime_active and not self.state.force_health_failure
            if healthy:
                self._send(200, b"<!doctype html><html><title>VUT AI Tutor</title><body>VUT AI Tutor Canvas</body></html>", "text/html; charset=utf-8")
            else:
                self._send(200, b"<!doctype html><html><title>Open WebUI</title></html>", "text/html; charset=utf-8")
            return
        self._json(404, {"detail": "Not found"})

    def do_OPTIONS(self) -> None:
        path = self._path()
        self.state.record("OPTIONS", path)
        if path == "/study-tutor/api/state":
            self._send(
                204,
                b"",
                "text/plain; charset=utf-8",
                {
                    "Access-Control-Allow-Origin": "null",
                    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
                    "Access-Control-Allow-Headers": "authorization,content-type",
                },
            )
            return
        self._send(204, b"", "text/plain; charset=utf-8")

    def do_POST(self) -> None:
        path = self._path()
        body = self._read_json()
        self.state.record("POST", path, body=body)
        if path == "/api/v1/auths/signin":
            if not isinstance(body, dict) or not body.get("email") or not body.get("password"):
                self._json(400, {"detail": "Missing credentials"})
            else:
                self._json(200, {"token": self.state.token})
            return
        if not self._require_auth():
            return
        if path == "/api/v1/functions/create":
            self._upsert(body, create=True)
            return
        match = re.fullmatch(r"/api/v1/functions/id/([^/]+)/(update|toggle|toggle/global|valves/update)", path)
        if not match:
            self._json(404, {"detail": "Not found"})
            return
        function_id, operation = match.groups()
        with self.state.lock:
            current = self.state.functions.get(function_id)
        if current is None:
            self._json(404, {"detail": "Not found"})
            return
        if operation == "update":
            self._upsert(body, create=False, function_id=function_id)
            return
        if operation == "valves/update":
            with self.state.lock:
                self.state.valves[function_id] = body if isinstance(body, dict) else {}
            self._json(200, self.state.valves[function_id])
            return
        with self.state.lock:
            if operation == "toggle":
                current["is_active"] = not bool(current.get("is_active"))
                if function_id == EVENT_ID:
                    self.state.runtime_active = bool(current["is_active"])
            elif operation == "toggle/global":
                current["is_global"] = not bool(current.get("is_global"))
            current["updated_at"] = int(time.time())
            result = dict(current)
        self._json(200, result)

    def _upsert(self, body: Any, *, create: bool, function_id: str | None = None) -> None:
        if not isinstance(body, dict):
            self._json(400, {"detail": "Invalid form"})
            return
        identifier = function_id or str(body.get("id") or "")
        source = str(body.get("content") or "")
        if not identifier or not source:
            self._json(400, {"detail": "Missing id or content"})
            return
        with self.state.lock:
            if create and identifier in self.state.functions:
                self._json(409, {"detail": "Already exists"})
                return
            previous = self.state.functions.get(identifier, {})
            record = {
                "id": identifier,
                "name": str(body.get("name") or identifier),
                "content": source,
                "type": infer_type(source),
                "is_active": bool(previous.get("is_active", False)),
                "is_global": bool(previous.get("is_global", False)),
                "meta": body.get("meta") if isinstance(body.get("meta"), dict) else {},
                "updated_at": int(time.time()),
            }
            self.state.functions[identifier] = record
        self._json(200, record)

    def do_DELETE(self) -> None:
        path = self._path()
        self.state.record("DELETE", path)
        if not self._require_auth():
            return
        match = re.fullmatch(r"/api/v1/functions/id/([^/]+)/delete", path)
        if not match:
            self._json(404, {"detail": "Not found"})
            return
        function_id = match.group(1)
        with self.state.lock:
            self.state.functions.pop(function_id, None)
            self.state.valves.pop(function_id, None)
            if function_id == EVENT_ID:
                self.state.runtime_active = False
        self._json(200, True)


def start_server(prefix: str = "") -> tuple[ThreadingHTTPServer, State, threading.Thread, str]:
    state = State(prefix)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.state = state  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    base = f"http://{host}:{port}{state.prefix}"
    return server, state, thread, base


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prefix", default="")
    args = parser.parse_args()
    server, _, _, base = start_server(args.prefix)
    print(base, flush=True)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import pathlib
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit


def load_module(path: pathlib.Path):
    spec = importlib.util.spec_from_file_location("vut_universal_engine_under_test", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load engine module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", required=True)
    parser.add_argument("--bootstrap", required=True)
    parser.add_argument("--pipe", required=True)
    args = parser.parse_args()

    engine_path = pathlib.Path(args.engine).resolve()
    bootstrap_path = pathlib.Path(args.bootstrap).resolve()
    pipe_path = pathlib.Path(args.pipe).resolve()
    module = load_module(engine_path)

    declared = module.runtime_declared_route_strategies(bootstrap_path.read_text(encoding="utf-8"))
    if declared != {"asgi-prefix-gateway-v7"}:
        raise AssertionError(f"Unexpected bootstrap strategy declarations: {sorted(declared)!r}")

    runtime_id = "route-contract-test-runtime"
    routes = {
        "registration_version": 7,
        "registration_strategy": "asgi-prefix-gateway-v7",
        "runtime_id": runtime_id,
        "registered_runtime_id": runtime_id,
        "bound_to_current_runtime": True,
        "study_routes": 43,
        "nested_legacy_route_nodes": 0,
        "inserted_at": 0,
        "spa_at": -1,
        "before_spa": True,
        "required_complete": True,
        "missing_required": [],
        "duplicate_method_paths": [],
        "main_router_style": "unmodified",
        "main_router_mutated": False,
        "gateway_active": True,
        "healthy": True,
    }
    contract = module.validate_runtime_route_contract(routes)
    if contract["registration_strategy"] != "asgi-prefix-gateway-v7":
        raise AssertionError(contract)
    if contract["architecture"] != "asgi-prefix-gateway-v7-no-main-router-mutation":
        raise AssertionError(contract)

    erroneous = dict(routes)
    erroneous["registration_strategy"] = "asgi-prefix-gateway-v7-no-main-router-mutation"
    try:
        module.validate_runtime_route_contract(erroneous)
    except module.VerifyError:
        pass
    else:
        raise AssertionError("Architecture label must not be confused with the health API strategy value.")

    health = {
        "ok": True,
        "version": module.RUNTIME_VERSION,
        "build_marker": module.RUNTIME_MARKER,
        "function_id": module.EVENT_ID,
        "route_registration_version": module.ROUTE_REGISTRATION_VERSION,
        "routes": routes,
    }

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt: str, *values: object) -> None:
            return

        def write_response(self, status: int, body: bytes, content_type: str, headers=None) -> None:
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

        def do_GET(self) -> None:
            path = urlsplit(self.path).path
            if path == "/study-tutor/health":
                self.write_response(200, json.dumps(health).encode("utf-8"), "application/json; charset=utf-8")
            elif path == "/study-tutor/canvas":
                self.write_response(200, b"<!doctype html><html><title>VUT AI Tutor</title><body>VUT AI Tutor Canvas</body></html>", "text/html; charset=utf-8")
            else:
                self.write_response(404, b"{}", "application/json")

        def do_OPTIONS(self) -> None:
            if urlsplit(self.path).path == "/study-tutor/api/state":
                self.write_response(204, b"", "text/plain", {"Access-Control-Allow-Origin": "null"})
            else:
                self.write_response(404, b"", "text/plain")

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        config = module.InstallerConfig(
            action="verify",
            platform="remote",
            base_url=base_url,
            request_timeout=2.0,
            route_timeout=3.0,
            bootstrap_path=str(bootstrap_path),
            pipe_path=str(pipe_path),
            report_path=str(engine_path.parent / "unused-route-contract-report.json"),
        )
        config.validate()
        report = {"warnings": []}
        api = module.OpenWebUIApi(config, base_url, report)
        verified = module.wait_for_runtime(config, api, report=report, timeout=3.0)
        if verified["route_contract"]["registration_strategy"] != "asgi-prefix-gateway-v7":
            raise AssertionError(verified)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)

    event_contract = module.verify_payload(bootstrap_path, module.EVENT_ID, "event")
    pipe_contract = module.verify_payload(pipe_path, module.PIPE_ID, "pipe")
    print(json.dumps({
        "ok": True,
        "installer_version": module.INSTALLER_VERSION,
        "runtime_version": module.RUNTIME_VERSION,
        "declared_health_strategy": sorted(declared),
        "accepted_health_strategy": contract["registration_strategy"],
        "architecture_label": contract["architecture"],
        "wait_for_runtime": "pass",
        "event_sha256": event_contract.sha256,
        "pipe_sha256": pipe_contract.sha256,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

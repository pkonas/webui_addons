#!/usr/bin/env python3
from __future__ import annotations

import copy
import importlib.util
import json
import pathlib
import sys
import tempfile
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
ENGINE_PATH = ROOT / "engine" / "vut_ai_tutor_universal_installer_v2.0.6.py"
BOOTSTRAP_PATH = ROOT / "runtime" / "vut_ai_tutor_bootstrap_v1.26.5_server_desktop_windows_mock_transport_complete.py"
PIPE_PATH = ROOT / "runtime" / "vut_ai_tutor_pipe_v1.26.5_server_desktop_windows_mock_transport_complete.py"
MOCK_PATH = ROOT / "tests" / "mock_openwebui_api_v2.3.4.py"


def load_module(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


engine = load_module("vut_engine_203_test", ENGINE_PATH)
mock = load_module("vut_mock_230_test", MOCK_PATH)


def stable_functions(value: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for key, item in value.items():
        result[key] = {k: copy.deepcopy(v) for k, v in item.items() if k != "updated_at"}
    return result


def config(temp: pathlib.Path, base_url: str, token_file: pathlib.Path, platform: str, action: str, suffix: str):
    return engine.InstallerConfig.from_mapping(
        {
            "action": action,
            "platform": platform,
            "base_url": base_url,
            "token_file": str(token_file),
            "request_timeout": 2.0,
            "startup_timeout": 2.0,
            "route_timeout": 2.0,
            "restart_policy": "never",
            "report_path": str(temp / f"{platform}-{action}-{suffix}.json"),
            "backup_dir": str(temp / "backups"),
            "bootstrap_path": str(BOOTSTRAP_PATH),
            "pipe_path": str(PIPE_PATH),
            "container_engine": "auto",
        }
    )


def run_platform_cycle(temp: pathlib.Path, platform: str, prefix: str = "") -> dict[str, Any]:
    server, state, thread, base_url = mock.start_server(prefix)
    token_file = temp / f"{platform}-token.txt"
    token_file.write_text(state.token + "\n", encoding="utf-8")
    try:
        with state.lock:
            state.functions["study_tutor_bootstrap"] = {
                "id": "study_tutor_bootstrap",
                "name": "Legacy Tutor",
                "content": "class Event:\n    pass\n",
                "type": "event",
                "is_active": True,
                "is_global": False,
                "meta": {},
                "updated_at": 1,
            }
        install_report = engine.run(config(temp, base_url, token_file, platform, "install", "cycle"))
        assert install_report["ok"] is True
        with state.lock:
            assert engine.EVENT_ID in state.functions
            assert engine.PIPE_ID in state.functions
            assert state.functions[engine.EVENT_ID]["is_active"] is True
            assert state.functions[engine.PIPE_ID]["is_active"] is True
            assert "study_tutor_bootstrap" not in state.functions
        verify_report = engine.run(config(temp, base_url, token_file, platform, "verify", "cycle"))
        assert verify_report["ok"] is True
        uninstall_report = engine.run(config(temp, base_url, token_file, platform, "uninstall", "cycle"))
        assert uninstall_report["ok"] is True
        with state.lock:
            for function_id in engine.MANAGED_IDS:
                assert function_id not in state.functions
        return {
            "platform": platform,
            "prefix": prefix,
            "install": install_report["ok"],
            "verify": verify_report["ok"],
            "uninstall": uninstall_report["ok"],
            "operations": len(state.operations),
        }
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def rollback_cycle(temp: pathlib.Path) -> dict[str, Any]:
    server, state, thread, base_url = mock.start_server("")
    token_file = temp / "rollback-token.txt"
    token_file.write_text(state.token + "\n", encoding="utf-8")
    try:
        engine.run(config(temp, base_url, token_file, "remote", "install", "rollback-base"))
        with state.lock:
            before_functions = stable_functions(state.functions)
            before_valves = copy.deepcopy(state.valves)
            state.force_health_failure = True
        failing = config(temp, base_url, token_file, "remote", "repair", "rollback-fail")
        failing.route_timeout = 0.25
        failed = False
        try:
            engine.run(failing)
        except engine.VerifyError:
            failed = True
        assert failed, "forced health failure did not fail the transaction"
        with state.lock:
            state.force_health_failure = False
            after_functions = stable_functions(state.functions)
            after_valves = copy.deepcopy(state.valves)
        assert after_functions == before_functions, "rollback did not restore Function records"
        normalize_valves = lambda value: {key: item for key, item in value.items() if item}
        assert normalize_valves(after_valves) == normalize_valves(before_valves), "rollback did not restore valves"
        verify_report = engine.run(config(temp, base_url, token_file, "remote", "verify", "rollback-after"))
        assert verify_report["ok"] is True
        return {"forced_failure": True, "rollback_restored": True, "post_rollback_verify": True}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)



def future_version_capability_cycle(temp: pathlib.Path) -> dict[str, Any]:
    """Unknown future Open WebUI versions are accepted only after capability tests pass."""
    server, state, thread, base_url = mock.start_server("")
    state.openwebui_version = "0.12.7"
    token_file = temp / "future-version-token.txt"
    token_file.write_text(state.token + "\n", encoding="utf-8")
    try:
        install_report = engine.run(config(temp, base_url, token_file, "remote", "install", "future-version"))
        assert install_report["ok"] is True
        warnings = install_report.get("warnings") or []
        assert any("outside the release's tested families" in str(item) for item in warnings)
        assert install_report["runtime_verification"]["route_contract"]["registration_strategy"] == "asgi-prefix-gateway-v7"
        verify_report = engine.run(config(temp, base_url, token_file, "remote", "verify", "future-version"))
        assert verify_report["ok"] is True
        engine.run(config(temp, base_url, token_file, "remote", "uninstall", "future-version"))
        return {
            "reported_openwebui_version": state.openwebui_version,
            "capability_gated_install": True,
            "warning_recorded": True,
            "verify": True,
        }
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

def main() -> int:
    with tempfile.TemporaryDirectory(prefix="vut-api-e2e-") as tmp:
        temp = pathlib.Path(tmp)
        results = [
            run_platform_cycle(temp, "remote", "/openwebui"),
            run_platform_cycle(temp, "docker"),
            run_platform_cycle(temp, "baremetal"),
        ]
        rollback = rollback_cycle(temp)
        future_version = future_version_capability_cycle(temp)
        output = {
            "ok": True,
            "engine_version": engine.INSTALLER_VERSION,
            "runtime_version": engine.RUNTIME_VERSION,
            "cycles": results,
            "rollback": rollback,
            "future_version": future_version,
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

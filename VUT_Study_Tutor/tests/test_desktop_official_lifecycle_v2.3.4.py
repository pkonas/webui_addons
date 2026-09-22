#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
MANAGER_PATH = ROOT / "runtime" / "vut_ai_tutor_manager_v1.26.5_server_desktop_windows_mock_transport_complete.py"


def load(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def args(mode: str, target: str = "Desktop", no_auto: bool = False) -> argparse.Namespace:
    return argparse.Namespace(
        mode=mode,
        target=target,
        no_auto_start_desktop=no_auto,
        http_timeout=15.0,
    )


def main() -> int:
    manager = load("vut_desktop_manager_231", MANAGER_PATH)
    assert manager.DESKTOP_ADAPTER_REVISION == "2.3.1-official-desktop-lifecycle-r1"

    calls: list[tuple[str, bool, str]] = []
    original_wait = manager.wait_for_backend
    original_discover = manager.discover_backend
    try:
        def fake_wait(ns, report, *, auto_start_desktop, operation):
            calls.append((ns.mode, bool(auto_start_desktop), operation))
            return "http://127.0.0.1:8099"

        def fake_discover(ns, report, **kwargs):
            calls.append((f"discover:{ns.mode}", False, ""))
            return "http://127.0.0.1:18080"

        manager.wait_for_backend = fake_wait
        manager.discover_backend = fake_discover

        assert manager.ensure_backend(args("TutorOnly"), {}, operation="install") == "http://127.0.0.1:8099"
        assert calls[-1] == ("TutorOnly", True, "install")
        assert manager.ensure_backend(args("Verify"), {}, operation="verify") == "http://127.0.0.1:8099"
        assert calls[-1] == ("Verify", True, "verify")
        assert manager.ensure_backend(args("Verify", no_auto=True), {}, operation="verify-noauto") == "http://127.0.0.1:8099"
        assert calls[-1] == ("Verify", False, "verify-noauto")
        assert manager.ensure_backend(args("Verify", target="Server"), {}, operation="server-verify") == "http://127.0.0.1:18080"
        assert calls[-1][0] == "discover:Verify"
    finally:
        manager.wait_for_backend = original_wait
        manager.discover_backend = original_discover

    # Exercise the actual wait/autostart state machine used by Verify.  The
    # first probe sees a closed backend, start_desktop is invoked exactly once,
    # and the mandatory post-launch probe returns a dynamic runtime URL.
    state = {"launched": 0, "probes": 0}
    lifecycle_report: dict[str, object] = {}
    original_wait_discover = manager.discover_backend
    original_start_desktop = manager.start_desktop
    original_default_local = manager._desktop_default_connection_is_local
    try:
        def staged_discover(ns, report, **kwargs):
            state["probes"] += 1
            if state["launched"] == 0:
                raise manager.TutorInstallError("mock backend is not running")
            return "http://127.0.0.1:8097"

        def staged_start(ns, report):
            state["launched"] += 1
            report.setdefault("desktop_start_attempts", []).append({"executable": "mock-open-webui.exe"})

        manager.discover_backend = staged_discover
        manager.start_desktop = staged_start
        manager._desktop_default_connection_is_local = lambda ns: (True, [{"default_connection_id": "local"}])
        lifecycle_args = argparse.Namespace(
            target="Desktop",
            mode="Verify",
            no_auto_start_desktop=False,
            startup_timeout=3.0,
            http_timeout=1.0,
            desktop_config_root="",
        )
        resolved_url = manager.ensure_backend(lifecycle_args, lifecycle_report, operation="verify-regression")
        assert resolved_url == "http://127.0.0.1:8097"
        assert state["launched"] == 1
        assert state["probes"] >= 2
        wait_report = lifecycle_report["backend_wait"]
        assert wait_report["launch_attempted"] is True
        assert wait_report["post_launch_probe_performed"] is True
        assert wait_report["success"] is True
    finally:
        manager.discover_backend = original_wait_discover
        manager.start_desktop = original_start_desktop
        manager._desktop_default_connection_is_local = original_default_local

    old_appdata = os.environ.get("APPDATA")
    old_localappdata = os.environ.get("LOCALAPPDATA")
    try:
        with tempfile.TemporaryDirectory(prefix="vut-official-desktop-") as tmp:
            temp = pathlib.Path(tmp)
            appdata = temp / "Roaming"
            localapp = temp / "Local"
            config_root = appdata / "open-webui"
            config_root.mkdir(parents=True)
            install_root = temp / "web-ui"
            install_root.mkdir()
            config = {
                "version": 1,
                "defaultConnectionId": "local",
                "connections": [],
                "installDir": str(install_root),
                "dataDir": "",
                "localServer": {"port": 8080, "serveOnLocalNetwork": False, "autoUpdate": False},
            }
            (config_root / "config.json").write_text(json.dumps(config), encoding="utf-8")
            logs = config_root / "logs"
            logs.mkdir()
            (logs / "main.log").write_text(
                "Server started: http://127.0.0.1:8087 12345\n",
                encoding="utf-8",
            )
            official_exe = localapp / "Programs" / "open-webui" / "open-webui.exe"
            official_exe.parent.mkdir(parents=True)
            official_exe.write_bytes(b"MZ")

            os.environ["APPDATA"] = str(appdata)
            os.environ["LOCALAPPDATA"] = str(localapp)

            entries = manager.desktop_config_entries("")
            assert entries and entries[0][1] == config_root
            assert manager.discover_log_urls(config_root)[0] == "http://127.0.0.1:8087"
            candidates = manager._desktop_executable_candidates("")
            assert official_exe in candidates

            ns = argparse.Namespace(
                desktop_install_root="",
                desktop_config_root="",
                desktop_data_root="",
                desktop_executable="",
            )
            report: dict[str, object] = {}
            resolved = manager.resolve_desktop(ns, report)
            assert resolved["root"] == install_root.resolve()
            assert resolved["config_root"] == config_root
            assert resolved["executable"] == official_exe
            assert resolved["default_connection_id"] == "local"
            assert int(resolved["local_server"]["port"]) == 8080
    finally:
        if old_appdata is None:
            os.environ.pop("APPDATA", None)
        else:
            os.environ["APPDATA"] = old_appdata
        if old_localappdata is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = old_localappdata

    print(json.dumps({
        "ok": True,
        "adapter_revision": manager.DESKTOP_ADAPTER_REVISION,
        "verify_autostart": True,
        "official_config_root": "%APPDATA%\\open-webui",
        "official_executable": "%LOCALAPPDATA%\\Programs\\open-webui\\open-webui.exe",
        "dynamic_log_url": True,
        "verify_launch_count": state["launched"],
        "verify_probe_passes": state["probes"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

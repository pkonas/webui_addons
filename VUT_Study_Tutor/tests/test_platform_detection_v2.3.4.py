#!/usr/bin/env python3
from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import json
import os
import pathlib
import stat
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
ENGINE_PATH = ROOT / "engine" / "vut_ai_tutor_universal_installer_v2.0.6.py"
DISPATCHER_PATH = ROOT / "install-vut-ai-tutor-universal-v2.3.4.py"
MOCK_PATH = ROOT / "tests" / "mock_openwebui_api_v2.3.4.py"


def load(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


engine = load("vut_engine_203_detection", ENGINE_PATH)
dispatcher = load("vut_dispatcher_230_detection", DISPATCHER_PATH)
mock = load("vut_mock_230_detection", MOCK_PATH)


def args(**overrides):
    values = dict(
        platform="auto",
        base_url=None,
        container_engine="auto",
        container_name=None,
        service_name=None,
        restart_command=None,
    )
    values.update(overrides)
    return argparse.Namespace(**values)


def make_executable(path: pathlib.Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def main() -> int:
    server, state, thread, base_url = mock.start_server("")
    host_port = server.server_address[1]
    old_path = os.environ.get("PATH", "")
    try:
        with tempfile.TemporaryDirectory(prefix="vut-fake-docker-") as tmp:
            bindir = pathlib.Path(tmp)
            make_executable(
                bindir / "docker",
                f'''#!/usr/bin/env bash
set -e
case "$1" in
  ps) echo '{{"ID":"mockid","Image":"ghcr.io/open-webui/open-webui:main","Names":"open-webui","State":"running","Status":"Up 1 minute"}}' ;;
  inspect) echo '[{{"NetworkSettings":{{"Ports":{{"8080/tcp":[{{"HostIp":"127.0.0.1","HostPort":"{host_port}"}}]}}}}}}]' ;;
  restart) exit 0 ;;
  *) exit 1 ;;
esac
''',
            )
            os.environ["PATH"] = str(bindir) + os.pathsep + old_path

            report: dict = {}
            config = engine.InstallerConfig.from_mapping(
                {
                    "action": "preflight",
                    "platform": "docker",
                    "request_timeout": 2.0,
                    "startup_timeout": 2.0,
                    "route_timeout": 2.0,
                    "report_path": str(bindir / "docker-report.json"),
                    "bootstrap_path": str(ROOT / "runtime" / "vut_ai_tutor_bootstrap_v1.26.5_server_desktop_windows_mock_transport_complete.py"),
                    "pipe_path": str(ROOT / "runtime" / "vut_ai_tutor_pipe_v1.26.5_server_desktop_windows_mock_transport_complete.py"),
                }
            )
            adapter = engine.DockerAdapter(config, report)
            assert adapter.container and adapter.container["running"]
            selected = engine.select_backend(config, adapter, report, allow_start=False)
            assert selected == base_url
            detected = dispatcher.detect_platform(args())
            assert detected["selected"] == "docker"
            assert detected["container"]["engine"] == "docker"

        # Stopped containers must remain discoverable and may be started when the
        # user selected the deployment explicitly.
        with tempfile.TemporaryDirectory(prefix="vut-fake-docker-stopped-") as tmp:
            bindir = pathlib.Path(tmp)
            started = bindir / "started.flag"
            make_executable(
                bindir / "docker",
                f'''#!/usr/bin/env bash
set -e
case "$1" in
  ps) echo '{{"ID":"stoppedid","Image":"ghcr.io/open-webui/open-webui:main","Names":"open-webui-stopped","State":"exited","Status":"Exited (0)"}}' ;;
  inspect) echo '[{{"NetworkSettings":{{"Ports":{{"8080/tcp":[{{"HostIp":"127.0.0.1","HostPort":"{host_port}"}}]}}}}}}]' ;;
  start) touch '{started}' ;;
  restart) exit 0 ;;
  *) exit 1 ;;
esac
''',
            )
            os.environ["PATH"] = str(bindir) + os.pathsep + old_path
            stopped_config = engine.InstallerConfig.from_mapping(
                {
                    "action": "preflight",
                    "platform": "docker",
                    "container_name": "open-webui-stopped",
                    "request_timeout": 2.0,
                    "startup_timeout": 2.0,
                    "route_timeout": 2.0,
                    "report_path": str(bindir / "stopped-report.json"),
                    "bootstrap_path": str(ROOT / "runtime" / "vut_ai_tutor_bootstrap_v1.26.5_server_desktop_windows_mock_transport_complete.py"),
                    "pipe_path": str(ROOT / "runtime" / "vut_ai_tutor_pipe_v1.26.5_server_desktop_windows_mock_transport_complete.py"),
                }
            )
            stopped_report: dict = {}
            stopped_adapter = engine.DockerAdapter(stopped_config, stopped_report)
            assert stopped_adapter.container and not stopped_adapter.container["running"]
            stopped_detected = dispatcher.detect_platform(args())
            assert stopped_detected["selected"] == "docker"
            assert stopped_adapter.can_start()
            stopped_adapter.start()
            assert started.is_file()
            assert stopped_adapter.container["running"]

        os.environ["PATH"] = old_path
        remote = dispatcher.detect_platform(args(base_url="https://example.invalid/openwebui"))
        assert remote["selected"] == "remote"
        bare = dispatcher.detect_platform(args(service_name="open-webui"))
        assert bare["selected"] == "baremetal"
        parser = dispatcher.build_parser()
        rejected_server_alias = False
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                parser.parse_args(["--platform", "server"])
        except SystemExit:
            rejected_server_alias = True
        assert rejected_server_alias
        print(
            json.dumps(
                {
                    "ok": True,
                    "docker_selected_url": selected,
                    "docker_auto_detection": True,
                    "stopped_container_start": True,
                    "remote_base_url_precedence": True,
                    "baremetal_service_detection": True,
                    "server_alias_rejected": True,
                },
                indent=2,
            )
        )
        return 0
    finally:
        os.environ["PATH"] = old_path
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


if __name__ == "__main__":
    raise SystemExit(main())

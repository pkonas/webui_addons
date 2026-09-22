#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
MOCK_PATH = ROOT / "tests" / "mock_openwebui_api_v2.3.4.py"


def load(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


mock = load("vut_mock_230_cli", MOCK_PATH)


def run(command: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed ({result.returncode}): {' '.join(command)}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
    return result


def main() -> int:
    server, state, thread, base_url = mock.start_server("/openwebui")
    try:
        with tempfile.TemporaryDirectory(prefix="vut-cli-e2e-") as tmp:
            temp = pathlib.Path(tmp)
            token = temp / "token.txt"
            token.write_text(state.token + "\n", encoding="utf-8")
            env = os.environ.copy()
            env["PYTHON_BIN"] = sys.executable
            common = [
                "--platform",
                "remote",
                "--base-url",
                base_url,
                "--token-file",
                str(token),
                "--request-timeout",
                "2",
                "--startup-timeout",
                "2",
                "--route-timeout",
                "2",
                "--restart-policy",
                "never",
            ]
            install = run(
                [
                    "bash",
                    str(ROOT / "install-vut-ai-tutor-universal-v2.3.4.sh"),
                    "--action",
                    "install",
                    *common,
                    "--report-path",
                    str(temp / "install.json"),
                ],
                env,
            )
            verify = run(
                [
                    "bash",
                    str(ROOT / "verify-vut-ai-tutor-universal-v2.3.4.sh"),
                    *common,
                    "--report-path",
                    str(temp / "verify.json"),
                ],
                env,
            )
            uninstall = run(
                [
                    sys.executable,
                    str(ROOT / "install-vut-ai-tutor-universal-v2.3.4.py"),
                    "--action",
                    "uninstall",
                    *common,
                    "--report-path",
                    str(temp / "uninstall.json"),
                ],
                env,
            )
            with state.lock:
                assert not state.functions
            output = {
                "ok": True,
                "bash_install": install.returncode == 0,
                "bash_verify": verify.returncode == 0,
                "python_uninstall": uninstall.returncode == 0,
                "reverse_proxy_prefix": "/openwebui",
            }
            print(json.dumps(output, indent=2))
        return 0
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import ast
import hashlib
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]

EXPECTED_RUNTIME_HASHES = {'runtime/vut_ai_tutor_bootstrap_v1.26.5_server_desktop_windows_mock_transport_complete.py': 'bdf315b89c38fbc1417e04936871498ea5ac64f59d0eb0f46eada4b4572ac32f', 'runtime/vut_ai_tutor_pipe_v1.26.5_server_desktop_windows_mock_transport_complete.py': '9bebab54e1f8cbe841973c4ab06e2e88358542027233f64f4ea7a4f691603893', 'runtime/vut_ai_tutor_manager_v1.26.5_server_desktop_windows_mock_transport_complete.py': 'ab014514e13d520313e4d6fc41aa5f18e131b31a9ee676a3d3b27c0fd001c092', 'adapters/desktop/repair-install-vut-ai-tutor-v1.26.5-server-desktop-windows-mock-transport-complete.ps1': 'dd2dfd552ed54f963389e2ac90a91f27e8fbb280c3c88cc59f14c3d83e3c4a03', 'adapters/desktop/verify-vut-ai-tutor-v1.26.5-server-desktop-windows-mock-transport-complete.ps1': '9cd08fb74d669e052625fbd706388a312696e2af7d416ba8cdb7df2745008581', 'adapters/einfra/install-vut-ai-tutor-einfra-windows-server-v2.1.8.ps1': 'f1b8f0fd5b5ff403e2bdb3b74402ba52eb58a8e3dd2b82cdce39e48698ef5ced'}


def sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def assignment(tree: ast.Module, name: str):
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(target, ast.Name) and target.id == name for target in targets):
                value = node.value
                if isinstance(value, ast.Constant):
                    return value.value
    return None


def main() -> int:
    required = [
        "install-vut-ai-tutor-universal-v2.3.4.ps1",
        "verify-vut-ai-tutor-universal-v2.3.4.ps1",
        "install-vut-ai-tutor-universal-v2.3.4.py",
        "install-vut-ai-tutor-universal-v2.3.4.sh",
        "verify-vut-ai-tutor-universal-v2.3.4.sh",
        "engine/vut_ai_tutor_universal_installer_v2.0.6.py",
        *EXPECTED_RUNTIME_HASHES,
    ]
    missing = [item for item in required if not (ROOT / item).is_file()]
    assert not missing, missing

    for relative, expected in EXPECTED_RUNTIME_HASHES.items():
        actual = sha(ROOT / relative)
        assert actual == expected, (relative, expected, actual)

    engine_path = ROOT / "engine/vut_ai_tutor_universal_installer_v2.0.6.py"
    engine_source = engine_path.read_text(encoding="utf-8")
    tree = ast.parse(engine_source)
    assert assignment(tree, "INSTALLER_VERSION") == "2.0.6"
    assert assignment(tree, "RUNTIME_VERSION") == "1.26.5"
    assert assignment(tree, "RUNTIME_HEALTH_ROUTE_STRATEGY") == "asgi-prefix-gateway-v7"
    assert assignment(tree, "RUNTIME_ARCHITECTURE_LABEL") == "asgi-prefix-gateway-v7-no-main-router-mutation"
    assert "prompt_for_credential: bool = False" in engine_source

    manager_source = (ROOT / "runtime/vut_ai_tutor_manager_v1.26.5_server_desktop_windows_mock_transport_complete.py").read_text(encoding="utf-8")
    assert 'DESKTOP_ADAPTER_REVISION = "2.3.1-official-desktop-lifecycle-r1"' in manager_source
    assert 'args.mode in {"TutorOnly", "Verify"}' in manager_source
    assert 'official-electron-autostart-for-install-and-verify-v3' in manager_source
    assert 'parser.add_argument("--prompt-for-credential"' in engine_source
    assert 'self._run("ps", "-a", "--format", "{{json .}}")' in engine_source
    assert 'child_env["VUT_TUTOR_SERVICE_NAME"]' in engine_source
    assert 'Restart-Service -Name $env:VUT_TUTOR_SERVICE_NAME -Force' in engine_source

    for ps_name in (
        "install-vut-ai-tutor-universal-v2.3.4.ps1",
        "verify-vut-ai-tutor-universal-v2.3.4.ps1",
        "test-vut-ai-tutor-universal-v2.3.4-windows.ps1",
    ):
        raw = (ROOT / ps_name).read_bytes()
        assert raw.startswith(b"\xef\xbb\xbf"), f"{ps_name} must have UTF-8 BOM for Windows PowerShell 5.1"
        assert b"\n" not in raw.replace(b"\r\n", b""), f"{ps_name} must use CRLF only"

    ps_source = (ROOT / "install-vut-ai-tutor-universal-v2.3.4.ps1").read_text(encoding="utf-8-sig")
    assert "'Server'" not in ps_source
    assert "vut_ai_tutor_universal_installer_v2.0.6.py" in ps_source
    assert "v2.0.1" not in ps_source
    assert "'TutorOnly'" in ps_source

    bash_source = (ROOT / "install-vut-ai-tutor-universal-v2.3.4.sh").read_text(encoding="utf-8")
    verify_bash_source = (ROOT / "verify-vut-ai-tutor-universal-v2.3.4.sh").read_text(encoding="utf-8")
    safe_test_bash_source = (ROOT / "test-vut-ai-tutor-universal-v2.3.4.sh").read_text(encoding="utf-8")
    assert "install-vut-ai-tutor-universal-v2.3.4.py" in bash_source
    assert "exec" in bash_source
    assert 'exec bash "$HERE/install-vut-ai-tutor-universal-v2.3.4.sh"' in verify_bash_source
    assert 'bash "$HERE/install-vut-ai-tutor-universal-v2.3.4.sh" --action self-test' in safe_test_bash_source

    stale_files = [str(path.relative_to(ROOT)) for path in ROOT.rglob("*") if path.is_file() and "2.0.1" in path.name]
    assert not stale_files, stale_files
    output = {
        "ok": True,
        "installer_version": "2.3.4",
        "engine_version": "2.0.6",
        "runtime_version": "1.26.5",
        "tutor_event_pipe_pdf_hotfix_integrated": True,
        "desktop_manager_intentionally_revised": True,
        "desktop_adapter_revision": "2.3.1-official-desktop-lifecycle-r1",
        "desktop_verify_autostart": True,
        "einfra_lifecycle_preserved_payloads_updated": True,
        "native_bash_python_entry": True,
        "server_alias_present": False,
        "stale_generic_engine_2_0_1_present": False,
        "stopped_container_start_supported": True,
        "windows_service_restart_uses_environment": True,
    }
    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

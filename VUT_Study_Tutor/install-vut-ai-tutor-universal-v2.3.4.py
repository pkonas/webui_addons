#!/usr/bin/env python3
"""Cross-platform dispatcher for VUT AI Tutor Universal Installer 2.3.4.

Windows Desktop and e-INFRA deployments intentionally use their dedicated,
previously validated PowerShell adapters. Docker, Podman, generic bare-metal,
and remote/web deployments use the portable API-first engine 2.0.6.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import pathlib
import re
import shutil
import socket
import subprocess
import sys
import urllib.error
import urllib.request
from typing import Any

INSTALLER_VERSION = "2.3.4"
RUNTIME_VERSION = "1.26.5"
ROOT = pathlib.Path(__file__).resolve().parent
ENGINE_PATH = ROOT / "engine" / "vut_ai_tutor_universal_installer_v2.0.6.py"
BOOTSTRAP_PATH = ROOT / "runtime" / "vut_ai_tutor_bootstrap_v1.26.5_server_desktop_windows_mock_transport_complete.py"
PIPE_PATH = ROOT / "runtime" / "vut_ai_tutor_pipe_v1.26.5_server_desktop_windows_mock_transport_complete.py"
MANIFEST_PATH = ROOT / "PACKAGE-MANIFEST.json"


class DispatchError(RuntimeError):
    pass


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_package() -> dict[str, Any]:
    required = (ENGINE_PATH, BOOTSTRAP_PATH, PIPE_PATH)
    for path in required:
        if not path.is_file():
            raise DispatchError(f"Required package file is missing: {path}")
    checked = 0
    if MANIFEST_PATH.is_file():
        data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8-sig"))
        files = data.get("files") if isinstance(data, dict) else None
        if not isinstance(files, list):
            raise DispatchError("PACKAGE-MANIFEST.json does not contain a files array.")
        for item in files:
            if not isinstance(item, dict):
                raise DispatchError("PACKAGE-MANIFEST.json contains an invalid file record.")
            relative = str(item.get("path") or "")
            expected = str(item.get("sha256") or "").lower()
            if not relative or not re.fullmatch(r"[0-9a-f]{64}", expected):
                raise DispatchError(f"Invalid manifest record: {item!r}")
            path = ROOT / pathlib.PurePosixPath(relative)
            if not path.is_file():
                raise DispatchError(f"Manifest file is missing: {relative}")
            actual = sha256_file(path)
            if actual != expected:
                raise DispatchError(
                    f"SHA-256 mismatch for {relative}: expected {expected}, found {actual}"
                )
            checked += 1
    return {"manifest_verified": MANIFEST_PATH.is_file(), "files_checked": checked}


def load_engine():
    spec = importlib.util.spec_from_file_location("vut_ai_tutor_engine_203", ENGINE_PATH)
    if spec is None or spec.loader is None:
        raise DispatchError(f"Cannot load API engine: {ENGINE_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def api_version_works(base_url: str, timeout: float = 0.8) -> bool:
    url = base_url.rstrip("/") + "/api/version"
    handlers: list[Any] = []
    host = urllib.request.urlparse(url).hostname if hasattr(urllib.request, "urlparse") else None
    # urllib.request has no urlparse attribute on supported Python; use urllib.parse lazily.
    import urllib.parse

    host = urllib.parse.urlsplit(url).hostname
    if host in {"localhost", "127.0.0.1", "::1"}:
        handlers.append(urllib.request.ProxyHandler({}))
    opener = urllib.request.build_opener(*handlers)
    request = urllib.request.Request(url, headers={"Accept": "application/json", "Connection": "close"})
    try:
        with opener.open(request, timeout=timeout) as response:
            if int(response.status) != 200:
                return False
            body = response.read()
        if body.lstrip().startswith(b"<"):
            return False
        value = json.loads(body.decode("utf-8-sig"))
        return isinstance(value, dict) and isinstance(value.get("version"), str)
    except Exception:
        return False


def detect_windows_specialized() -> dict[str, Any]:
    evidence: dict[str, Any] = {"einfra": None, "desktop": None}
    if os.name != "nt":
        return evidence
    program_data = pathlib.Path(os.environ.get("ProgramData", r"C:\ProgramData"))
    runtime_path = program_data / "EInfra-OpenWebUI" / "config" / "runtime.json"
    if runtime_path.is_file():
        try:
            value = json.loads(runtime_path.read_text(encoding="utf-8-sig"))
        except Exception as exc:
            evidence["einfra"] = {"detected": False, "path": str(runtime_path), "error": str(exc)}
        else:
            product = str(value.get("ProductId") or value.get("product_id") or "") if isinstance(value, dict) else ""
            evidence["einfra"] = {
                "detected": product in {"", "EInfra-OpenWebUI"},
                "path": str(runtime_path),
                "product_id": product,
            }
    appdata = os.environ.get("APPDATA")
    roots: list[pathlib.Path] = []
    if appdata:
        roots.extend(pathlib.Path(appdata) / name for name in ("Open WebUI", "open-webui", "OpenWebUI"))
    known_roots = [pathlib.Path(r"D:\web-ui"), pathlib.Path(r"C:\web-ui")]
    desktop_config = next((root for root in roots if root.exists()), None)
    desktop_install = next((root for root in known_roots if root.exists()), None)
    if desktop_config or desktop_install:
        evidence["desktop"] = {
            "detected": True,
            "config_root": str(desktop_config) if desktop_config else None,
            "install_root": str(desktop_install) if desktop_install else None,
        }
    return evidence


def detect_container(engine_preference: str, explicit_name: str | None) -> dict[str, Any] | None:
    choices = [engine_preference] if engine_preference != "auto" else ["docker", "podman"]
    for engine in choices:
        executable = shutil.which(engine)
        if not executable:
            continue
        try:
            completed = subprocess.run(
                [executable, "ps", "-a", "--format", "{{.Image}} {{.Names}}"],
                text=True,
                capture_output=True,
                timeout=10,
                check=False,
            )
            if completed.returncode != 0:
                completed = subprocess.run(
                    [executable, "ps", "--format", "{{.Image}} {{.Names}}"],
                    text=True,
                    capture_output=True,
                    timeout=10,
                    check=False,
                )
        except Exception:
            continue
        if completed.returncode != 0:
            continue
        lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
        if explicit_name:
            matches = [line for line in lines if explicit_name in line]
        else:
            matches = [line for line in lines if re.search(r"open[-_ ]?webui", line, re.I)]
        if matches:
            return {"engine": engine, "matches": matches}
    return None


def detect_platform(args: argparse.Namespace) -> dict[str, Any]:
    requested = args.platform.lower()
    evidence: dict[str, Any] = {
        "requested": requested,
        "base_url": args.base_url,
        "windows": detect_windows_specialized(),
        "container": None,
        "local_urls": [],
    }
    if requested != "auto":
        evidence["selected"] = requested
        return evidence
    if args.base_url:
        evidence["selected"] = "remote"
        return evidence
    win = evidence["windows"]
    einfra = bool((win.get("einfra") or {}).get("detected"))
    desktop = bool((win.get("desktop") or {}).get("detected"))
    if einfra and desktop:
        raise DispatchError(
            "Both e-INFRA Windows Server and Open WebUI Desktop were detected. "
            "Select --platform einfra-windows or --platform desktop explicitly in the Windows PowerShell dispatcher."
        )
    if einfra:
        evidence["selected"] = "einfra-windows"
        return evidence
    if desktop:
        evidence["selected"] = "desktop"
        return evidence
    container = detect_container(args.container_engine, args.container_name)
    evidence["container"] = container
    if container:
        evidence["selected"] = "docker"
        return evidence
    if args.service_name or args.restart_command:
        evidence["selected"] = "baremetal"
        return evidence
    for url in ("http://127.0.0.1:8080", "http://127.0.0.1:3000", "http://127.0.0.1:18080"):
        if api_version_works(url):
            evidence["local_urls"].append(url)
    if evidence["local_urls"]:
        evidence["selected"] = "baremetal"
        return evidence
    raise DispatchError(
        "The Open WebUI deployment could not be detected. Supply --platform and, for remote/bare-metal, --base-url."
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--action", default="repair", choices=["detect", "install", "repair", "verify", "preflight", "uninstall", "self-test"])
    parser.add_argument("--platform", default="auto", choices=["auto", "desktop", "einfra-windows", "docker", "baremetal", "remote"])
    parser.add_argument("--base-url")
    parser.add_argument("--token-file")
    parser.add_argument("--email")
    parser.add_argument("--password-file")
    parser.add_argument("--prompt-for-credential", action="store_true")
    parser.add_argument("--ca-certificate")
    parser.add_argument("--insecure-tls", action="store_true")
    parser.add_argument("--request-timeout", type=float, default=15.0)
    parser.add_argument("--startup-timeout", type=float, default=300.0)
    parser.add_argument("--route-timeout", type=float, default=180.0)
    parser.add_argument("--restart-policy", choices=["never", "on-failure", "always"], default="on-failure")
    parser.add_argument("--no-start-backend", action="store_true")
    parser.add_argument("--no-rollback", action="store_true")
    parser.add_argument("--keep-legacy-disabled", action="store_true")
    parser.add_argument("--report-path", default="./vut-ai-tutor-universal-report.json")
    parser.add_argument("--backup-dir")
    parser.add_argument("--container-engine", choices=["auto", "docker", "podman"], default="auto")
    parser.add_argument("--container-name")
    parser.add_argument("--service-name")
    parser.add_argument("--restart-command")
    parser.add_argument("--debug", action="store_true")
    return parser


def run_api_engine(args: argparse.Namespace, selected: str) -> int:
    if selected in {"desktop", "einfra-windows"}:
        raise DispatchError(
            f"Platform {selected} requires the Windows PowerShell entry install-vut-ai-tutor-universal-v2.3.4.ps1."
        )
    engine = load_engine()
    mapping: dict[str, Any] = {
        "action": args.action,
        "platform": selected,
        "base_url": args.base_url,
        "token_file": args.token_file,
        "email": args.email,
        "password_file": args.password_file,
        "prompt_for_credential": bool(args.prompt_for_credential),
        "ca_certificate": args.ca_certificate,
        "insecure_tls": bool(args.insecure_tls),
        "request_timeout": args.request_timeout,
        "startup_timeout": args.startup_timeout,
        "route_timeout": args.route_timeout,
        "restart_policy": args.restart_policy,
        "start_backend": not args.no_start_backend,
        "no_rollback": bool(args.no_rollback),
        "keep_legacy_disabled": bool(args.keep_legacy_disabled),
        "report_path": args.report_path,
        "backup_dir": args.backup_dir,
        "bootstrap_path": str(BOOTSTRAP_PATH),
        "pipe_path": str(PIPE_PATH),
        "container_engine": args.container_engine,
        "container_name": args.container_name,
        "service_name": args.service_name,
        "restart_command": args.restart_command,
        "debug": bool(args.debug),
    }
    config = engine.InstallerConfig.from_mapping(mapping)
    report = engine.run(config)
    print(json.dumps(engine.redact(report), ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        integrity = verify_package()
        if args.action == "self-test":
            engine = load_engine()
            config = engine.InstallerConfig.from_mapping(
                {
                    "action": "self-test",
                    "platform": "remote",
                    "report_path": args.report_path,
                    "bootstrap_path": str(BOOTSTRAP_PATH),
                    "pipe_path": str(PIPE_PATH),
                    "debug": bool(args.debug),
                }
            )
            report = engine.run(config)
            report["dispatcher_version"] = INSTALLER_VERSION
            report["package_integrity"] = integrity
            engine.atomic_write_json(pathlib.Path(args.report_path).expanduser().resolve(), report)
            print(json.dumps(engine.redact(report), ensure_ascii=False, indent=2))
            return 0
        detection = detect_platform(args)
        if args.action == "detect":
            print(json.dumps({"installer_version": INSTALLER_VERSION, "runtime_version": RUNTIME_VERSION, "package_integrity": integrity, **detection}, ensure_ascii=False, indent=2))
            return 0
        selected = str(detection["selected"])
        return run_api_engine(args, selected)
    except DispatchError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        if getattr(args, "debug", False):
            import traceback
            traceback.print_exc()
        return int(getattr(exc, "exit_code", 6))


if __name__ == "__main__":
    raise SystemExit(main())

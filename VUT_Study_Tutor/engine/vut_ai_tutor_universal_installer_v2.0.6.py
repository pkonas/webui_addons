#!/usr/bin/env python3
"""Universal, API-first installer 2.0.6 for the known-good VUT AI Tutor runtime 1.26.5.

The installer deliberately separates the portable Open WebUI Functions API transaction
from platform-specific discovery and recovery.  Normal installation never imports or
modifies Open WebUI's Python environment and never touches its database.
"""

from __future__ import annotations

import argparse
import ast
import concurrent.futures
import contextlib
import dataclasses
import datetime as dt
import getpass
import hashlib
import http.client
import io
import json
import os
import pathlib
import platform as py_platform
import re
import shlex
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

INSTALLER_VERSION: Final = "2.0.6"
RUNTIME_VERSION: Final = "1.26.5"
RUNTIME_MARKER: Final = "VUT-AI-TUTOR-1.26.5-SERVER-DESKTOP-WINDOWS-MOCK-TRANSPORT-COMPLETE"
EVENT_ID: Final = "study_tutor_gateway_bootstrap"
PIPE_ID: Final = "study_tutor_pipe"
ROUTE_REGISTRATION_VERSION: Final = 7
# The runtime exposes a compact, stable value in /study-tutor/health.  Keep it
# separate from the longer architecture label used in reports and documentation;
# conflating the two caused the 2.0.1 false-negative on the e-INFRA server.
RUNTIME_HEALTH_ROUTE_STRATEGY: Final = "asgi-prefix-gateway-v7"
RUNTIME_ARCHITECTURE_LABEL: Final = "asgi-prefix-gateway-v7-no-main-router-mutation"
LEGACY_IDS: Final[tuple[str, ...]] = (
    "study_tutor_bootstrap",
    "study_tutor_canvas_bootstrap",
    "vut_ai_tutor_bootstrap",
    "vut_ai_tutor_pipe",
    "study_tutor_pipe_managed",
)
MANAGED_IDS: Final[tuple[str, ...]] = (EVENT_ID, PIPE_ID, *LEGACY_IDS)

EXIT_OK = 0
EXIT_CONFIG = 2
EXIT_BACKEND = 3
EXIT_AUTH = 4
EXIT_API = 5
EXIT_INSTALL = 6
EXIT_VERIFY = 7
EXIT_ROLLBACK = 8


class InstallerError(RuntimeError):
    """Base exception with a stable process exit code."""

    exit_code = EXIT_INSTALL


class ConfigError(InstallerError):
    exit_code = EXIT_CONFIG


class BackendError(InstallerError):
    exit_code = EXIT_BACKEND


class AuthError(InstallerError):
    exit_code = EXIT_AUTH


class ApiError(InstallerError):
    exit_code = EXIT_API


class VerifyError(InstallerError):
    exit_code = EXIT_VERIFY


class RollbackError(InstallerError):
    exit_code = EXIT_ROLLBACK


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def normalize_source(text: str) -> str:
    return text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")


def source_sha256(text: str) -> str:
    return hashlib.sha256(normalize_source(text).encode("utf-8")).hexdigest()


def redact(value: Any) -> Any:
    """Recursively redact values whose keys may carry secrets."""
    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(marker in lowered for marker in ("password", "token", "secret", "api_key", "apikey")):
                out[str(key)] = "<redacted>" if item not in (None, "") else item
            else:
                out[str(key)] = redact(item)
        return out
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def atomic_write_json(path: pathlib.Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False, newline="\n") as handle:
        json.dump(redact(data), handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        temp_name = handle.name
    os.replace(temp_name, path)


def read_json_file(path: pathlib.Path) -> Any:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def read_text_file(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def normalize_base_url(value: str) -> str:
    raw = value.strip()
    if not raw:
        raise ConfigError("Base URL is empty.")
    if "://" not in raw:
        raw = "http://" + raw
    parsed = urllib.parse.urlsplit(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ConfigError(f"Invalid Open WebUI URL: {value!r}")
    path = parsed.path.rstrip("/")
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def endpoint_url(base_url: str, endpoint: str, query: Mapping[str, Any] | None = None) -> str:
    """Join an endpoint without losing an optional reverse-proxy path prefix."""
    base = normalize_base_url(base_url)
    path = endpoint if endpoint.startswith("/") else "/" + endpoint
    result = base.rstrip("/") + path
    if query:
        encoded = urllib.parse.urlencode({k: v for k, v in query.items() if v is not None})
        if encoded:
            result += "?" + encoded
    return result


def is_loopback_url(url: str) -> bool:
    host = (urllib.parse.urlsplit(url).hostname or "").strip("[]").lower()
    if host in {"localhost", "127.0.0.1", "::1"}:
        return True
    try:
        return bool(__import__("ipaddress").ip_address(host).is_loopback)
    except ValueError:
        return False


def compact_body(body: bytes, limit: int = 500) -> str:
    text = body.decode("utf-8", errors="replace")
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= limit else text[:limit] + "…"


@dataclass(slots=True)
class HttpResult:
    status: int
    headers: dict[str, str]
    body: bytes
    url: str
    elapsed_ms: int

    def json(self) -> Any:
        try:
            return json.loads(self.body.decode("utf-8-sig"))
        except Exception as exc:
            raise ApiError(
                f"Endpoint {self.url} did not return valid JSON (HTTP {self.status}): {compact_body(self.body)}"
            ) from exc


@dataclass(slots=True)
class InstallerConfig:
    action: str = "install"
    platform: str = "auto"
    base_url: str | None = None
    token_file: str | None = None
    email: str | None = None
    password_file: str | None = None
    prompt_for_credential: bool = False
    ca_certificate: str | None = None
    insecure_tls: bool = False
    request_timeout: float = 15.0
    startup_timeout: float = 300.0
    route_timeout: float = 180.0
    restart_policy: str = "on-failure"
    start_backend: bool = True
    no_rollback: bool = False
    keep_legacy_disabled: bool = False
    report_path: str = "vut-ai-tutor-universal-report.json"
    backup_dir: str | None = None
    bootstrap_path: str | None = None
    pipe_path: str | None = None
    desktop_install_root: str | None = None
    desktop_config_root: str | None = None
    desktop_executable: str | None = None
    container_engine: str = "auto"
    container_name: str | None = None
    service_name: str | None = None
    restart_command: str | None = None
    debug: bool = False

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "InstallerConfig":
        allowed = {item.name for item in dataclasses.fields(cls)}
        unknown = sorted(set(raw) - allowed)
        if unknown:
            raise ConfigError("Unknown configuration keys: " + ", ".join(unknown))
        kwargs: dict[str, Any] = {}
        for field_info in dataclasses.fields(cls):
            if field_info.name in raw and raw[field_info.name] is not None:
                kwargs[field_info.name] = raw[field_info.name]
        config = cls(**kwargs)
        config.validate()
        return config

    def validate(self) -> None:
        self.action = self.action.lower().replace("_", "-")
        self.platform = self.platform.lower().replace("_", "-")
        self.restart_policy = self.restart_policy.lower()
        self.container_engine = self.container_engine.lower()
        if self.action not in {"install", "repair", "verify", "preflight", "uninstall", "self-test"}:
            raise ConfigError(f"Unsupported action: {self.action}")
        if self.platform not in {"auto", "desktop", "docker", "baremetal", "remote"}:
            raise ConfigError(f"Unsupported platform: {self.platform}")
        if self.restart_policy not in {"never", "on-failure", "always"}:
            raise ConfigError("restart_policy must be never, on-failure, or always.")
        if self.container_engine not in {"auto", "docker", "podman"}:
            raise ConfigError("container_engine must be auto, docker, or podman.")
        if self.platform == "remote" and self.action != "self-test" and not self.base_url:
            raise ConfigError("Remote platform requires base_url.")
        for name in ("request_timeout", "startup_timeout", "route_timeout"):
            value = float(getattr(self, name))
            if value <= 0:
                raise ConfigError(f"{name} must be positive.")
            setattr(self, name, value)
        if self.insecure_tls and self.ca_certificate:
            raise ConfigError("Use either ca_certificate or insecure_tls, not both.")
        if self.platform == "remote" and not self.base_url and self.action != "self-test":
            raise ConfigError("Remote mode requires base_url.")
        if self.action in {"install", "repair", "verify", "uninstall"}:
            if not self.bootstrap_path or not self.pipe_path:
                raise ConfigError("bootstrap_path and pipe_path are required for this action.")


@dataclass(slots=True)
class PayloadContract:
    path: str
    function_id: str
    function_type: str
    version: str
    marker: str
    sha256: str


def parse_frontmatter(source: str) -> dict[str, str]:
    match = re.match(r"\s*['\"]{3}\s*\n(?P<body>.*?)\n['\"]{3}", source, re.S)
    if not match:
        return {}
    body = match.group("body")
    data: dict[str, str] = {}
    for line in body.splitlines():
        found = re.match(r"\s*([A-Za-z_][A-Za-z0-9_-]*)\s*:\s*(.*?)\s*$", line)
        if found:
            data[found.group(1).lower()] = found.group(2).strip().strip("'\"")
    return data


def literal_assignments(source: str) -> dict[str, Any]:
    tree = ast.parse(source)
    result: dict[str, Any] = {}
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            value_node = node.value
            if value_node is None:
                continue
            try:
                value = ast.literal_eval(value_node)
            except Exception:
                continue
            for target in targets:
                if isinstance(target, ast.Name):
                    result[target.id] = value
    return result


def top_level_classes(source: str) -> set[str]:
    tree = ast.parse(source)
    return {node.name for node in tree.body if isinstance(node, ast.ClassDef)}


def verify_payload(path: pathlib.Path, expected_id: str, expected_type: str) -> PayloadContract:
    source = read_text_file(path)
    assignments = literal_assignments(source)
    frontmatter = parse_frontmatter(source)
    classes = top_level_classes(source)
    version = str(assignments.get("PLUGIN_VERSION") or frontmatter.get("version") or "")
    marker = str(assignments.get("TUTOR_BUILD_MARKER") or "")
    frontmatter_id = frontmatter.get("id", "")
    required_class = "Event" if expected_type == "event" else "Pipe"
    if version != RUNTIME_VERSION:
        raise ConfigError(f"Payload {path} has runtime version {version!r}; expected {RUNTIME_VERSION!r}.")
    if marker != RUNTIME_MARKER:
        raise ConfigError(f"Payload {path} has an unexpected release marker.")
    if frontmatter_id and frontmatter_id != expected_id:
        raise ConfigError(f"Payload {path} has frontmatter id {frontmatter_id!r}; expected {expected_id!r}.")
    if required_class not in classes:
        raise ConfigError(f"Payload {path} does not define top-level class {required_class}.")
    return PayloadContract(
        path=str(path.resolve()),
        function_id=expected_id,
        function_type=expected_type,
        version=version,
        marker=marker,
        sha256=source_sha256(source),
    )

class HttpClient:
    """Small stdlib-only HTTP client with explicit loopback proxy bypass."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float,
        ca_certificate: str | None,
        insecure_tls: bool,
        token: str | None = None,
    ) -> None:
        self.base_url = normalize_base_url(base_url)
        self.timeout = timeout
        self.token = token
        self.ssl_context = self._make_ssl_context(ca_certificate, insecure_tls)
        self._lock = threading.Lock()

    @staticmethod
    def _make_ssl_context(ca_certificate: str | None, insecure_tls: bool) -> ssl.SSLContext:
        if insecure_tls:
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            return context
        if ca_certificate:
            path = pathlib.Path(ca_certificate).expanduser().resolve()
            if not path.is_file():
                raise ConfigError(f"CA certificate does not exist: {path}")
            return ssl.create_default_context(cafile=str(path))
        return ssl.create_default_context()

    def _opener(self, url: str) -> urllib.request.OpenerDirector:
        handlers: list[Any] = []
        if is_loopback_url(url):
            handlers.append(urllib.request.ProxyHandler({}))
        if urllib.parse.urlsplit(url).scheme == "https":
            handlers.append(urllib.request.HTTPSHandler(context=self.ssl_context))
        return urllib.request.build_opener(*handlers)

    def request(
        self,
        method: str,
        endpoint: str,
        *,
        data: Any = None,
        headers: Mapping[str, str] | None = None,
        expected: Iterable[int] = (200,),
        retries: int = 0,
        retry_delay: float = 0.25,
        query: Mapping[str, Any] | None = None,
    ) -> HttpResult:
        url = endpoint if endpoint.startswith(("http://", "https://")) else endpoint_url(self.base_url, endpoint, query)
        body: bytes | None
        request_headers = {
            "Accept": "application/json",
            "User-Agent": f"VUT-AI-Tutor-Universal-Installer/{INSTALLER_VERSION}",
            "Connection": "close",
        }
        if self.token:
            request_headers["Authorization"] = f"Bearer {self.token}"
        if headers:
            request_headers.update(headers)
        if data is None:
            body = None
        elif isinstance(data, bytes):
            body = data
        else:
            body = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            request_headers.setdefault("Content-Type", "application/json")
        last_exc: Exception | None = None
        attempts = max(1, retries + 1)
        for attempt in range(attempts):
            started = time.monotonic()
            req = urllib.request.Request(url, data=body, headers=request_headers, method=method.upper())
            try:
                with self._opener(url).open(req, timeout=self.timeout) as response:
                    response_body = response.read()
                    result = HttpResult(
                        status=int(response.status),
                        headers={str(k).lower(): str(v) for k, v in response.headers.items()},
                        body=response_body,
                        url=str(response.geturl()),
                        elapsed_ms=int((time.monotonic() - started) * 1000),
                    )
                    if result.status not in set(expected):
                        raise ApiError(
                            f"Unexpected HTTP {result.status} from {url}: {compact_body(result.body)}"
                        )
                    return result
            except urllib.error.HTTPError as exc:
                response_body = exc.read()
                result = HttpResult(
                    status=int(exc.code),
                    headers={str(k).lower(): str(v) for k, v in exc.headers.items()},
                    body=response_body,
                    url=str(exc.geturl()),
                    elapsed_ms=int((time.monotonic() - started) * 1000),
                )
                if result.status in set(expected):
                    return result
                last_exc = ApiError(f"HTTP {result.status} from {url}: {compact_body(result.body)}")
                # HTTP status failures are not transport retries unless explicitly transient.
                if result.status not in {408, 425, 429, 502, 503, 504}:
                    raise last_exc
            except (urllib.error.URLError, ConnectionError, TimeoutError, OSError, http.client.HTTPException) as exc:
                last_exc = exc
            if attempt + 1 < attempts:
                time.sleep(retry_delay * (attempt + 1))
        raise ApiError(f"Cannot connect to {url}: {type(last_exc).__name__}: {last_exc}") from last_exc

    def with_token(self, token: str) -> "HttpClient":
        self.token = token.strip()
        return self


@dataclass(slots=True)
class BackendCandidate:
    url: str
    source: str
    priority: int = 100


@dataclass(slots=True)
class BackendProbe:
    url: str
    source: str
    reachable: bool
    version: str | None = None
    deployment_id: str | None = None
    status: int | None = None
    content_type: str | None = None
    body_preview: str | None = None
    error: str | None = None
    elapsed_ms: int | None = None


class PlatformAdapter:
    name = "remote"

    def __init__(self, config: InstallerConfig, report: dict[str, Any]) -> None:
        self.config = config
        self.report = report
        self.selected_base_url: str | None = None

    def candidates(self) -> list[BackendCandidate]:
        if self.config.base_url:
            return [BackendCandidate(normalize_base_url(self.config.base_url), "explicit base_url", 0)]
        return []

    def can_start(self) -> bool:
        return False

    def start(self) -> None:
        raise BackendError(f"Platform {self.name} cannot start a backend automatically.")

    def can_restart(self) -> bool:
        return False

    def restart(self) -> None:
        raise BackendError(f"Platform {self.name} does not support automatic restart.")

    def describe(self) -> dict[str, Any]:
        return {"platform": self.name}


class RemoteAdapter(PlatformAdapter):
    name = "remote"


class DesktopAdapter(PlatformAdapter):
    name = "desktop"

    URL_PATTERN = re.compile(r"https?://(?:127\.0\.0\.1|localhost|\[?::1\]?)(?::\d+)?(?:/[A-Za-z0-9._~!$&'()*+,;=:@%/-]*)?", re.I)

    def __init__(self, config: InstallerConfig, report: dict[str, Any]) -> None:
        super().__init__(config, report)
        self.config_root = self._resolve_config_root()
        self.desktop_config = self._read_desktop_config()
        self.install_root = self._resolve_install_root()
        self.executable = self._resolve_executable()
        self._launched_pid: int | None = None

    def _resolve_config_root(self) -> pathlib.Path | None:
        if self.config.desktop_config_root:
            return pathlib.Path(self.config.desktop_config_root).expanduser().resolve()
        candidates: list[pathlib.Path] = []
        appdata = os.environ.get("APPDATA")
        home = pathlib.Path.home()
        if appdata:
            base = pathlib.Path(appdata)
            candidates.extend([base / "Open WebUI", base / "open-webui", base / "OpenWebUI"])
        if sys.platform == "darwin":
            candidates.extend([home / "Library/Application Support/Open WebUI", home / "Library/Application Support/open-webui"])
        elif os.name != "nt":
            candidates.extend([home / ".config/Open WebUI", home / ".config/open-webui"])
        for candidate in candidates:
            if candidate.exists():
                return candidate.resolve()
        return candidates[0].resolve() if candidates else None

    def _read_desktop_config(self) -> dict[str, Any]:
        if not self.config_root:
            return {}
        for name in ("config.json", "settings.json"):
            path = self.config_root / name
            if path.is_file():
                try:
                    value = read_json_file(path)
                    if isinstance(value, dict):
                        return value
                except Exception as exc:
                    self.report.setdefault("warnings", []).append(f"Cannot parse Desktop config {path}: {exc}")
        return {}

    def _resolve_install_root(self) -> pathlib.Path | None:
        raw = self.config.desktop_install_root or self.desktop_config.get("installDir")
        if raw:
            return pathlib.Path(str(raw)).expanduser().resolve()
        return None

    def _resolve_executable(self) -> pathlib.Path | None:
        if self.config.desktop_executable:
            path = pathlib.Path(self.config.desktop_executable).expanduser().resolve()
            return path if path.is_file() else None
        candidates: list[pathlib.Path] = []
        local = os.environ.get("LOCALAPPDATA")
        if local:
            base = pathlib.Path(local) / "Programs"
            for directory in ("open-webui", "Open WebUI", "OpenWebUI"):
                candidates.extend(
                    [
                        base / directory / "open-webui.exe",
                        base / directory / "Open WebUI.exe",
                        base / directory / "OpenWebUI.exe",
                    ]
                )
        if sys.platform == "darwin":
            candidates.extend(
                [
                    pathlib.Path("/Applications/Open WebUI.app/Contents/MacOS/Open WebUI"),
                    pathlib.Path.home() / "Applications/Open WebUI.app/Contents/MacOS/Open WebUI",
                ]
            )
        for candidate in candidates:
            if candidate.is_file():
                return candidate.resolve()
        return None

    def _log_urls(self) -> list[BackendCandidate]:
        if not self.config_root:
            return []
        files: list[pathlib.Path] = []
        for folder in (self.config_root / "logs", self.config_root):
            for name in ("main.log", "server.log"):
                path = folder / name
                if path.is_file():
                    files.append(path)
        candidates: list[BackendCandidate] = []
        for path in files:
            try:
                with path.open("rb") as handle:
                    handle.seek(0, io.SEEK_END)
                    size = handle.tell()
                    handle.seek(max(0, size - 2_000_000))
                    text = handle.read().decode("utf-8", errors="replace")
            except OSError:
                continue
            authoritative_urls: list[str] = []
            for line in text.splitlines():
                if "OpenTerminal" in line:
                    continue
                if not re.search(r"Server started with PID:|Server started:\s*https?://|Starting Open-WebUI server", line, re.I):
                    continue
                authoritative_urls.extend(self.URL_PATTERN.findall(line))
            for offset, url in enumerate(reversed(authoritative_urls[-50:])):
                try:
                    candidates.append(BackendCandidate(normalize_base_url(url), f"Desktop log {path.name}", 10 + offset))
                except ConfigError:
                    continue
        return candidates

    def _configured_port(self) -> int:
        local = self.desktop_config.get("localServer")
        if isinstance(local, dict):
            try:
                port = int(local.get("port", 8080))
                if 1 <= port <= 65535:
                    return port
            except (TypeError, ValueError):
                pass
        return 8080

    def _open_range_ports(self, start: int, count: int = 101) -> list[int]:
        ports = [port for port in range(start, min(65536, start + count))]

        def open_port(port: int) -> int | None:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.08):
                    return port
            except OSError:
                return None

        with concurrent.futures.ThreadPoolExecutor(max_workers=min(32, len(ports) or 1)) as pool:
            return sorted(port for port in pool.map(open_port, ports) if port is not None)

    def candidates(self) -> list[BackendCandidate]:
        result = super().candidates()
        result.extend(self._log_urls())
        configured = self._configured_port()
        result.append(BackendCandidate(f"http://127.0.0.1:{configured}", "Desktop configured port", 20))
        if configured != 8080:
            result.append(BackendCandidate("http://127.0.0.1:8080", "Desktop conventional port", 90))
        for port in self._open_range_ports(configured):
            result.append(BackendCandidate(f"http://127.0.0.1:{port}", "open Desktop port range", 30))
        return deduplicate_candidates(result)

    def can_start(self) -> bool:
        return bool(self.executable and self.config.start_backend)

    def start(self) -> None:
        if not self.executable:
            raise BackendError("Open WebUI Desktop executable was not found. Supply desktop_executable.")
        process = subprocess.Popen(
            [str(self.executable)],
            cwd=str(self.executable.parent),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=(os.name != "nt"),
        )
        self._launched_pid = int(process.pid)
        self.report.setdefault("platform_actions", []).append(
            {"action": "desktop-start", "executable": str(self.executable), "pid": process.pid, "at": utc_now()}
        )

    def _windows_process_inventory(self) -> list[dict[str, Any]]:
        if os.name != "nt":
            return []
        command = (
            "Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId,ExecutablePath,CommandLine | "
            "ConvertTo-Json -Compress -Depth 3"
        )
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
        if completed.returncode != 0 or not completed.stdout.strip():
            return []
        try:
            data = json.loads(completed.stdout)
            return data if isinstance(data, list) else [data]
        except json.JSONDecodeError:
            return []

    def _safe_desktop_root_pids(self) -> list[int]:
        inventory = self._windows_process_inventory()
        if not inventory:
            return []
        by_pid = {int(item.get("ProcessId")): item for item in inventory if item.get("ProcessId") is not None}
        parent = {pid: int(item.get("ParentProcessId") or 0) for pid, item in by_pid.items()}
        protected: set[int] = {os.getpid()}
        cursor = os.getpid()
        for _ in range(32):
            cursor = parent.get(cursor, 0)
            if not cursor or cursor in protected:
                break
            protected.add(cursor)
        roots: set[int] = set()
        install_root = str(self.install_root).lower().rstrip("\\/") if self.install_root else ""
        desktop_exe = str(self.executable).lower() if self.executable else ""
        for pid, item in by_pid.items():
            executable = str(item.get("ExecutablePath") or "").lower()
            if pid in protected or not executable:
                continue
            if desktop_exe and executable == desktop_exe:
                roots.add(pid)
            elif install_root and (executable == install_root or executable.startswith(install_root + "\\")):
                roots.add(pid)
        # Never return a PID whose ancestry reaches a protected process.
        safe: list[int] = []
        for pid in roots:
            cursor = pid
            unsafe = False
            for _ in range(64):
                cursor = parent.get(cursor, 0)
                if not cursor:
                    break
                if cursor in protected:
                    unsafe = True
                    break
            if not unsafe:
                safe.append(pid)
        return sorted(safe)

    def can_restart(self) -> bool:
        return bool(self.executable)

    def restart(self) -> None:
        if os.name == "nt":
            pids = self._safe_desktop_root_pids()
            for pid in pids:
                subprocess.run(["taskkill.exe", "/PID", str(pid), "/T", "/F"], capture_output=True, text=True, timeout=30)
            self.report.setdefault("platform_actions", []).append(
                {"action": "desktop-stop", "pids": pids, "at": utc_now()}
            )
        elif self._launched_pid:
            with contextlib.suppress(OSError):
                os.kill(self._launched_pid, 15)
        time.sleep(1.0)
        self.start()

    def describe(self) -> dict[str, Any]:
        return {
            "platform": self.name,
            "config_root": str(self.config_root) if self.config_root else None,
            "install_root": str(self.install_root) if self.install_root else None,
            "executable": str(self.executable) if self.executable else None,
            "configured_port": self._configured_port(),
        }

class DockerAdapter(PlatformAdapter):
    name = "docker"

    def __init__(self, config: InstallerConfig, report: dict[str, Any]) -> None:
        super().__init__(config, report)
        self.engine = self._resolve_engine()
        self.container: dict[str, Any] | None = self._resolve_container()

    def _resolve_engine(self) -> str | None:
        choices = [self.config.container_engine] if self.config.container_engine != "auto" else ["docker", "podman"]
        for command in choices:
            if shutil.which(command):
                return command
        return None

    def _run(self, *args: str, timeout: int = 30) -> subprocess.CompletedProcess[str]:
        if not self.engine:
            raise BackendError("Neither docker nor podman CLI is available.")
        return subprocess.run([self.engine, *args], text=True, capture_output=True, timeout=timeout, check=False)

    def _resolve_container(self) -> dict[str, Any] | None:
        if not self.engine:
            return None
        # Include stopped containers so an explicit Docker/Podman deployment can be
        # started by the installer.  Older CLIs that reject ``ps -a`` fall back to
        # the running-container query.
        completed = self._run("ps", "-a", "--format", "{{json .}}")
        if completed.returncode != 0:
            completed = self._run("ps", "--format", "{{json .}}")
        if completed.returncode != 0:
            self.report.setdefault("warnings", []).append(f"{self.engine} ps failed: {completed.stderr.strip()}")
            return None
        entries: list[dict[str, Any]] = []
        for line in completed.stdout.splitlines():
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(item, dict):
                continue
            name = str(item.get("Names") or item.get("Name") or "")
            image = str(item.get("Image") or "")
            identifier = str(item.get("ID") or item.get("Id") or name)
            state = str(item.get("State") or "").strip().lower()
            status = str(item.get("Status") or "").strip()
            running = state == "running" or status.lower().startswith("up ") or status.lower() == "up"
            score = 0
            if self.config.container_name and self.config.container_name in {name, identifier}:
                score = 1000
            elif re.search(r"open[-_ ]?webui", name, re.I):
                score = 100
            elif re.search(r"open[-_ ]?webui", image, re.I):
                score = 80
            if score:
                entries.append(
                    {
                        "id": identifier,
                        "name": name,
                        "image": image,
                        "state": state or None,
                        "status": status or None,
                        "running": running,
                        "score": score,
                    }
                )
        if not entries:
            return None
        entries.sort(key=lambda item: (-int(item["score"]), not bool(item["running"]), str(item["name"])))
        if len(entries) > 1 and entries[0]["score"] == entries[1]["score"] and not self.config.container_name:
            names = ", ".join(item["name"] for item in entries[:5])
            raise ConfigError(f"Multiple Open WebUI containers match ({names}); specify container_name.")
        return entries[0]

    def _published_urls(self) -> list[BackendCandidate]:
        if not self.container:
            return []
        completed = self._run("inspect", self.container["id"])
        if completed.returncode != 0:
            self.report.setdefault("warnings", []).append(f"{self.engine} inspect failed: {completed.stderr.strip()}")
            return []
        try:
            docs = json.loads(completed.stdout)
            doc = docs[0] if isinstance(docs, list) and docs else docs
        except json.JSONDecodeError:
            return []
        ports = (((doc or {}).get("NetworkSettings") or {}).get("Ports") or {}) if isinstance(doc, dict) else {}
        result: list[BackendCandidate] = []
        preferred_keys = ["8080/tcp", "3000/tcp"]
        keys = preferred_keys + [key for key in ports if key not in preferred_keys]
        for key in keys:
            bindings = ports.get(key)
            if not isinstance(bindings, list):
                continue
            for binding in bindings:
                if not isinstance(binding, dict):
                    continue
                host_port = binding.get("HostPort")
                host_ip = str(binding.get("HostIp") or "127.0.0.1")
                try:
                    port = int(host_port)
                except (TypeError, ValueError):
                    continue
                host = "127.0.0.1" if host_ip in {"", "0.0.0.0", "::", "127.0.0.1"} else host_ip
                if ":" in host and not host.startswith("["):
                    host = f"[{host}]"
                result.append(BackendCandidate(f"http://{host}:{port}", f"{self.engine} published {key}", 10))
        return result

    def candidates(self) -> list[BackendCandidate]:
        result = super().candidates()
        result.extend(self._published_urls())
        return deduplicate_candidates(result)

    def can_start(self) -> bool:
        return bool(
            self.config.start_backend
            and self.engine
            and self.container
            and not bool(self.container.get("running"))
        )

    def start(self) -> None:
        if not self.container:
            raise BackendError("Open WebUI container was not found.")
        completed = self._run("start", self.container["id"], timeout=180)
        if completed.returncode != 0:
            raise BackendError(f"{self.engine} start failed: {completed.stderr.strip()}")
        self.container["running"] = True
        self.container["state"] = "running"
        self.report.setdefault("platform_actions", []).append(
            {"action": "container-start", "engine": self.engine, "container": self.container, "at": utc_now()}
        )

    def can_restart(self) -> bool:
        return bool(self.engine and self.container)

    def restart(self) -> None:
        if not self.container:
            raise BackendError("Open WebUI container was not found.")
        completed = self._run("restart", self.container["id"], timeout=180)
        if completed.returncode != 0:
            raise BackendError(f"{self.engine} restart failed: {completed.stderr.strip()}")
        self.report.setdefault("platform_actions", []).append(
            {"action": "container-restart", "engine": self.engine, "container": self.container, "at": utc_now()}
        )

    def describe(self) -> dict[str, Any]:
        return {"platform": self.name, "engine": self.engine, "container": self.container}


class BareMetalAdapter(PlatformAdapter):
    name = "baremetal"

    def _runtime_json_urls(self) -> list[BackendCandidate]:
        candidates: list[pathlib.Path] = []
        if os.name == "nt":
            candidates.extend(
                [
                    pathlib.Path(r"C:\ProgramData\EInfra-OpenWebUI\config\runtime.json"),
                    pathlib.Path(r"C:\ProgramData\OpenWebUI\config\runtime.json"),
                ]
            )
        else:
            candidates.extend(
                [
                    pathlib.Path("/etc/open-webui/runtime.json"),
                    pathlib.Path("/var/lib/open-webui/runtime.json"),
                ]
            )
        result: list[BackendCandidate] = []
        for path in candidates:
            if not path.is_file():
                continue
            try:
                data = read_json_file(path)
            except Exception:
                continue
            for key in ("base_url", "backend_url", "url", "listen_url", "public_url"):
                value = data.get(key) if isinstance(data, dict) else None
                if isinstance(value, str) and value.strip():
                    with contextlib.suppress(ConfigError):
                        result.append(BackendCandidate(normalize_base_url(value), f"runtime file {path}", 10))
            if isinstance(data, dict):
                port = data.get("port") or data.get("backend_port")
                host = data.get("host") or "127.0.0.1"
                try:
                    port_int = int(port)
                    result.append(BackendCandidate(f"http://{host}:{port_int}", f"runtime file {path}", 15))
                except (TypeError, ValueError):
                    pass
        return result

    def candidates(self) -> list[BackendCandidate]:
        result = super().candidates()
        env_url = os.environ.get("OPENWEBUI_URL") or os.environ.get("OPEN_WEBUI_URL")
        if env_url:
            with contextlib.suppress(ConfigError):
                result.append(BackendCandidate(normalize_base_url(env_url), "environment", 5))
        result.extend(self._runtime_json_urls())
        for port in (8080, 3000, 18080):
            result.append(BackendCandidate(f"http://127.0.0.1:{port}", "common bare-metal port", 80))
        return deduplicate_candidates(result)

    def can_restart(self) -> bool:
        if self.config.restart_command:
            return True
        if self.config.service_name:
            return bool(shutil.which("systemctl") or os.name == "nt")
        return False

    def restart(self) -> None:
        if self.config.restart_command:
            completed = subprocess.run(
                self.config.restart_command,
                shell=True,
                text=True,
                capture_output=True,
                timeout=180,
            )
            if completed.returncode != 0:
                raise BackendError(f"restart_command failed: {completed.stderr.strip()}")
            self.report.setdefault("platform_actions", []).append(
                {"action": "restart-command", "command": self.config.restart_command, "at": utc_now()}
            )
            return
        if not self.config.service_name:
            raise BackendError("Bare-metal restart requires service_name or restart_command.")
        if os.name == "nt":
            # Pass the service name through the child environment rather than
            # interpolating it into PowerShell source.  This handles spaces and
            # quotes without creating a command-injection surface.
            child_env = os.environ.copy()
            child_env["VUT_TUTOR_SERVICE_NAME"] = self.config.service_name
            completed = subprocess.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    "$ErrorActionPreference='Stop'; Restart-Service -Name $env:VUT_TUTOR_SERVICE_NAME -Force",
                ],
                text=True,
                capture_output=True,
                timeout=180,
                env=child_env,
            )
        else:
            completed = subprocess.run(
                ["systemctl", "restart", self.config.service_name], text=True, capture_output=True, timeout=180
            )
        if completed.returncode != 0:
            raise BackendError(f"Service restart failed: {completed.stderr.strip()}")
        self.report.setdefault("platform_actions", []).append(
            {"action": "service-restart", "service": self.config.service_name, "at": utc_now()}
        )

    def describe(self) -> dict[str, Any]:
        return {
            "platform": self.name,
            "service_name": self.config.service_name,
            "restart_command_configured": bool(self.config.restart_command),
        }


def deduplicate_candidates(candidates: Sequence[BackendCandidate]) -> list[BackendCandidate]:
    best: dict[str, BackendCandidate] = {}
    for item in candidates:
        try:
            url = normalize_base_url(item.url)
        except ConfigError:
            continue
        current = best.get(url)
        normalized = BackendCandidate(url, item.source, item.priority)
        if current is None or normalized.priority < current.priority:
            best[url] = normalized
    return sorted(best.values(), key=lambda item: (item.priority, item.url))


def detect_platform(config: InstallerConfig) -> str:
    if config.platform != "auto":
        return config.platform
    if config.base_url:
        return "remote"
    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        if config.desktop_install_root or config.desktop_config_root:
            return "desktop"
        if appdata and any((pathlib.Path(appdata) / name).exists() for name in ("Open WebUI", "open-webui", "OpenWebUI")):
            return "desktop"
    for engine in ("docker", "podman"):
        if shutil.which(engine):
            completed = subprocess.run([engine, "ps", "--format", "{{.Image}} {{.Names}}"], text=True, capture_output=True, timeout=10, check=False)
            if completed.returncode == 0 and re.search(r"open[-_ ]?webui", completed.stdout, re.I):
                return "docker"
    return "baremetal"


def make_adapter(config: InstallerConfig, report: dict[str, Any]) -> PlatformAdapter:
    platform_name = detect_platform(config)
    report["platform_detected"] = platform_name
    if platform_name == "desktop":
        return DesktopAdapter(config, report)
    if platform_name == "docker":
        return DockerAdapter(config, report)
    if platform_name == "baremetal":
        return BareMetalAdapter(config, report)
    return RemoteAdapter(config, report)


def probe_candidate(config: InstallerConfig, candidate: BackendCandidate) -> BackendProbe:
    started = time.monotonic()
    try:
        client = HttpClient(
            candidate.url,
            timeout=min(config.request_timeout, 5.0),
            ca_certificate=config.ca_certificate,
            insecure_tls=config.insecure_tls,
        )
        result = client.request("GET", "/api/version", expected=(200,), retries=1)
        content_type = result.headers.get("content-type", "")
        preview = compact_body(result.body)
        if result.body.lstrip().startswith(b"<"):
            raise BackendError(f"SPA/HTML response instead of /api/version JSON: {preview}")
        data = result.json()
        if not isinstance(data, dict) or not isinstance(data.get("version"), str):
            raise BackendError(f"Unsupported /api/version response: {preview}")
        return BackendProbe(
            url=candidate.url,
            source=candidate.source,
            reachable=True,
            version=data.get("version"),
            deployment_id=str(data.get("deployment_id")) if data.get("deployment_id") is not None else None,
            status=result.status,
            content_type=content_type,
            body_preview=preview,
            elapsed_ms=int((time.monotonic() - started) * 1000),
        )
    except Exception as exc:
        return BackendProbe(
            url=candidate.url,
            source=candidate.source,
            reachable=False,
            error=f"{type(exc).__name__}: {exc}",
            elapsed_ms=int((time.monotonic() - started) * 1000),
        )


def select_backend(config: InstallerConfig, adapter: PlatformAdapter, report: dict[str, Any], allow_start: bool) -> str:
    deadline = time.monotonic() + config.startup_timeout
    launched = False
    passes = 0
    all_probes: list[dict[str, Any]] = []
    while True:
        passes += 1
        candidates = adapter.candidates()
        if not candidates and adapter.name == "remote":
            raise BackendError("No base URL was supplied for remote Open WebUI.")
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(12, max(1, len(candidates)))) as pool:
            probes = list(pool.map(lambda item: probe_candidate(config, item), candidates))
        all_probes.extend(dataclasses.asdict(item) for item in probes)
        reachable = [item for item in probes if item.reachable]
        if reachable:
            reachable.sort(key=lambda item: next((c.priority for c in candidates if c.url == item.url), 100))
            selected = reachable[0]
            adapter.selected_base_url = selected.url
            report["backend"] = {
                "selected": dataclasses.asdict(selected),
                "probe_passes": passes,
                "launched": launched,
                "probes": all_probes,
            }
            return selected.url
        if not launched and allow_start and adapter.can_start():
            adapter.start()
            launched = True
            deadline = time.monotonic() + config.startup_timeout
        elif not launched and (not allow_start or not adapter.can_start()):
            break
        if time.monotonic() >= deadline:
            break
        time.sleep(1.0)
    report["backend"] = {"selected": None, "probe_passes": passes, "launched": launched, "probes": all_probes}
    detail = "; ".join(f"{item['url']} -> {item.get('error') or item.get('body_preview')}" for item in all_probes[-12:])
    raise BackendError("No reachable Open WebUI backend returned valid JSON from /api/version." + (f" Last probes: {detail}" if detail else ""))

class OpenWebUIApi:
    def __init__(self, config: InstallerConfig, base_url: str, report: dict[str, Any]) -> None:
        self.config = config
        self.base_url = base_url
        self.report = report
        self.client = HttpClient(
            base_url,
            timeout=config.request_timeout,
            ca_certificate=config.ca_certificate,
            insecure_tls=config.insecure_tls,
        )

    def authenticate(self) -> str:
        token = self._load_token()
        if token:
            self.client.with_token(token)
            self._validate_admin_api()
            self.report["authentication"] = {"method": "token", "validated": True}
            return token
        email = self.config.email or os.environ.get("VUT_INSTALL_EMAIL") or os.environ.get("OPENWEBUI_EMAIL")
        password = self._load_password()
        if self.config.prompt_for_credential and (not email or not password):
            if not sys.stdin.isatty():
                raise AuthError("Interactive credentials were requested, but stdin is not a terminal.")
            if not email:
                email = input("Open WebUI admin email: ").strip()
            if not password:
                password = getpass.getpass("Open WebUI admin password: ")
        if not email or not password:
            raise AuthError("Admin token or admin email/password is required.")
        try:
            result = self.client.request(
                "POST",
                "/api/v1/auths/signin",
                data={"email": email, "password": password},
                expected=(200,),
                retries=1,
            )
            data = result.json()
            token_value = data.get("token") or data.get("access_token") if isinstance(data, dict) else None
            if not isinstance(token_value, str) or not token_value.strip():
                raise AuthError("Open WebUI sign-in response did not contain a token.")
            self.client.with_token(token_value)
            self._validate_admin_api()
            self.report["authentication"] = {"method": "credentials", "email": email, "validated": True}
            return token_value
        except InstallerError:
            raise
        except Exception as exc:
            raise AuthError(f"Open WebUI administrator sign-in failed: {exc}") from exc

    def _load_token(self) -> str | None:
        env_token = os.environ.get("VUT_INSTALL_TOKEN") or os.environ.get("OPENWEBUI_TOKEN")
        if env_token and env_token.strip():
            return env_token.strip()
        if self.config.token_file:
            path = pathlib.Path(self.config.token_file).expanduser().resolve()
            if not path.is_file():
                raise ConfigError(f"Token file does not exist: {path}")
            value = read_text_file(path).strip()
            if not value:
                raise ConfigError(f"Token file is empty: {path}")
            return value
        return None

    def _load_password(self) -> str | None:
        env_password = os.environ.get("VUT_INSTALL_PASSWORD") or os.environ.get("OPENWEBUI_PASSWORD")
        if env_password is not None:
            return env_password
        if self.config.password_file:
            path = pathlib.Path(self.config.password_file).expanduser().resolve()
            if not path.is_file():
                raise ConfigError(f"Password file does not exist: {path}")
            return read_text_file(path).rstrip("\r\n")
        return None

    def _validate_admin_api(self) -> None:
        try:
            result = self.client.request("GET", "/api/v1/functions/", expected=(200,), retries=1)
            data = result.json()
            if not isinstance(data, list):
                raise AuthError("Functions API returned an unexpected payload.")
        except ApiError as exc:
            raise AuthError(f"Token is not accepted by the Open WebUI Functions API: {exc}") from exc

    def list_functions(self) -> list[dict[str, Any]]:
        data = self.client.request("GET", "/api/v1/functions/", expected=(200,)).json()
        if not isinstance(data, list):
            raise ApiError("Functions API list response is not an array.")
        return [item for item in data if isinstance(item, dict)]

    def get_function(self, function_id: str) -> dict[str, Any] | None:
        present = any(str(item.get("id")) == function_id for item in self.list_functions())
        if not present:
            return None
        result = self.client.request(
            "GET",
            f"/api/v1/functions/id/{urllib.parse.quote(function_id, safe='')}",
            expected=(200, 401, 404),
        )
        if result.status in {401, 404}:
            raise ApiError(f"Function {function_id} appears in the list but cannot be read by ID (HTTP {result.status}).")
        data = result.json()
        if not isinstance(data, dict):
            raise ApiError(f"Function {function_id} response is not an object.")
        return data

    def get_valves(self, function_id: str) -> dict[str, Any] | None:
        if self.get_function(function_id) is None:
            return None
        result = self.client.request(
            "GET",
            f"/api/v1/functions/id/{urllib.parse.quote(function_id, safe='')}/valves",
            expected=(200,),
        )
        data = result.json()
        if data is None:
            return None
        if not isinstance(data, dict):
            raise ApiError(f"Valves response for {function_id} is not an object.")
        return data

    def set_valves(self, function_id: str, valves: dict[str, Any] | None) -> None:
        if valves is None:
            return
        result = self.client.request(
            "POST",
            f"/api/v1/functions/id/{urllib.parse.quote(function_id, safe='')}/valves/update",
            data=valves,
            expected=(200,),
        )
        data = result.json()
        if data is not None and not isinstance(data, dict):
            raise ApiError(f"Valves update response for {function_id} is unexpected: {data!r}")

    def set_global(self, function_id: str, desired: bool) -> None:
        current = self.get_function(function_id)
        if current is None:
            return
        if bool(current.get("is_global")) != desired:
            result = self.client.request(
                "POST",
                f"/api/v1/functions/id/{urllib.parse.quote(function_id, safe='')}/toggle/global",
                expected=(200,),
            )
            data = result.json()
            if not isinstance(data, dict) or bool(data.get("is_global")) != desired:
                raise ApiError(f"Function {function_id} did not reach is_global={desired}.")

    @staticmethod
    def _form(function_id: str, name: str, source: str, meta: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "id": function_id,
            "name": name,
            "content": normalize_source(source),
            "meta": meta
            or {
                "description": f"VUT AI Tutor runtime {RUNTIME_VERSION}, installed by universal installer {INSTALLER_VERSION}.",
                "manifest": {},
            },
        }

    def set_active(self, function_id: str, desired: bool) -> dict[str, Any] | None:
        current = self.get_function(function_id)
        if current is None:
            return None
        active = bool(current.get("is_active"))
        if active != desired:
            result = self.client.request(
                "POST",
                f"/api/v1/functions/id/{urllib.parse.quote(function_id, safe='')}/toggle",
                expected=(200,),
            )
            data = result.json()
            if not isinstance(data, dict):
                raise ApiError(f"Toggle response for {function_id} is not an object.")
            current = data
        return current

    def upsert_function(
        self,
        function_id: str,
        name: str,
        source: str,
        desired_type: str,
        active: bool,
        *,
        meta: dict[str, Any] | None = None,
        desired_global: bool | None = None,
        valves: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        current = self.get_function(function_id)
        if current and current.get("is_active"):
            self.set_active(function_id, False)
            current = self.get_function(function_id)
        form = self._form(function_id, name, source, meta=meta)
        if current is None:
            result = self.client.request("POST", "/api/v1/functions/create", data=form, expected=(200,))
        else:
            result = self.client.request(
                "POST",
                f"/api/v1/functions/id/{urllib.parse.quote(function_id, safe='')}/update",
                data=form,
                expected=(200,),
            )
        data = result.json()
        if not isinstance(data, dict):
            raise ApiError(f"Create/update response for {function_id} is not an object.")
        fetched = self.get_function(function_id)
        if fetched is None:
            raise ApiError(f"Function {function_id} disappeared after create/update.")
        actual_type = str(fetched.get("type") or "")
        if actual_type != desired_type:
            raise ApiError(f"Function {function_id} has type {actual_type!r}; expected {desired_type!r}.")
        stored_source = str(fetched.get("content") or "")
        if source_sha256(stored_source) != source_sha256(source):
            raise ApiError(f"Function {function_id} stored source hash does not match the release payload.")
        self.set_active(function_id, active)
        if desired_global is not None:
            self.set_global(function_id, desired_global)
        if valves is not None:
            self.set_valves(function_id, valves)
        final = self.get_function(function_id)
        if final is None or bool(final.get("is_active")) != active:
            raise ApiError(f"Function {function_id} did not reach active={active}.")
        return final

    def delete_function(self, function_id: str) -> bool:
        current = self.get_function(function_id)
        if current is None:
            return False
        if current.get("is_active"):
            self.set_active(function_id, False)
        result = self.client.request(
            "DELETE",
            f"/api/v1/functions/id/{urllib.parse.quote(function_id, safe='')}/delete",
            expected=(200,),
        )
        data = result.json()
        if data not in {True, 1, "true"}:
            raise ApiError(f"Delete response for {function_id} was unexpected: {data!r}")
        return True


@dataclass(slots=True)
class FunctionSnapshot:
    function_id: str
    existed: bool
    record: dict[str, Any] | None
    valves: dict[str, Any] | None = None


def snapshot_functions(api: OpenWebUIApi) -> list[FunctionSnapshot]:
    snapshots: list[FunctionSnapshot] = []
    for function_id in MANAGED_IDS:
        record = api.get_function(function_id)
        valves = api.get_valves(function_id) if record is not None else None
        snapshots.append(FunctionSnapshot(function_id, record is not None, record, valves))
    return snapshots


def save_snapshot(path: pathlib.Path, base_url: str, snapshots: Sequence[FunctionSnapshot]) -> None:
    atomic_write_json(
        path,
        {
            "created_at": utc_now(),
            "base_url": base_url,
            "installer_version": INSTALLER_VERSION,
            "runtime_version": RUNTIME_VERSION,
            "functions": [dataclasses.asdict(item) for item in snapshots],
        },
    )


def restore_snapshot(api: OpenWebUIApi, snapshots: Sequence[FunctionSnapshot], report: dict[str, Any]) -> None:
    errors: list[str] = []
    # Remove the current managed state first, then recreate exact previous records.
    for function_id in reversed(MANAGED_IDS):
        try:
            api.delete_function(function_id)
        except Exception as exc:
            errors.append(f"delete {function_id}: {exc}")
    for snapshot in snapshots:
        if not snapshot.existed or not snapshot.record:
            continue
        record = snapshot.record
        try:
            api.upsert_function(
                snapshot.function_id,
                str(record.get("name") or snapshot.function_id),
                str(record.get("content") or ""),
                str(record.get("type") or ""),
                bool(record.get("is_active")),
                meta=record.get("meta") if isinstance(record.get("meta"), dict) else None,
                desired_global=bool(record.get("is_global")),
                valves=snapshot.valves,
            )
        except Exception as exc:
            errors.append(f"restore {snapshot.function_id}: {exc}")
    report["rollback"] = {"attempted": True, "errors": errors, "completed": not errors}
    if errors:
        raise RollbackError("Rollback was incomplete: " + "; ".join(errors))


def verify_function_record(record: dict[str, Any] | None, contract: PayloadContract) -> dict[str, Any]:
    if record is None:
        raise VerifyError(f"Required Function {contract.function_id} does not exist.")
    actual_type = str(record.get("type") or "")
    if actual_type != contract.function_type:
        raise VerifyError(f"Function {contract.function_id} has type {actual_type!r}, expected {contract.function_type!r}.")
    if not bool(record.get("is_active")):
        raise VerifyError(f"Function {contract.function_id} is not active.")
    actual_hash = source_sha256(str(record.get("content") or ""))
    if actual_hash != contract.sha256:
        raise VerifyError(
            f"Function {contract.function_id} contains a different source (expected {contract.sha256}, got {actual_hash})."
        )
    return {
        "id": contract.function_id,
        "type": actual_type,
        "active": True,
        "sha256": actual_hash,
        "updated_at": record.get("updated_at"),
    }



def runtime_declared_route_strategies(source: str) -> set[str]:
    """Return literal health-route strategy values declared by the Event source."""
    tree = ast.parse(source)
    values: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        for key_node, value_node in zip(node.keys, node.values):
            if (
                isinstance(key_node, ast.Constant)
                and key_node.value == "registration_strategy"
                and isinstance(value_node, ast.Constant)
                and isinstance(value_node.value, str)
            ):
                values.add(value_node.value)
    return values


def validate_runtime_route_contract(routes: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the exact route-health contract emitted by runtime 1.26.5.

    The compact ``registration_strategy`` value is an API field.  The longer
    architecture label is intentionally *not* accepted as a replacement; the
    independent flags below prove that the main Open WebUI router stayed intact.
    """
    if not isinstance(routes, Mapping):
        raise VerifyError("Tutor health does not contain a routes object.")

    strategy = str(routes.get("registration_strategy") or routes.get("strategy") or "")
    if strategy != RUNTIME_HEALTH_ROUTE_STRATEGY:
        raise VerifyError(
            f"Tutor route strategy {strategy!r} does not match the runtime health contract "
            f"{RUNTIME_HEALTH_ROUTE_STRATEGY!r}."
        )
    if routes.get("healthy") is not True:
        raise VerifyError(f"Tutor route health is false: {json.dumps(dict(routes), ensure_ascii=False)}")
    if routes.get("gateway_active") is not True:
        raise VerifyError("Tutor ASGI prefix gateway is not active.")
    if routes.get("main_router_mutated") is not False:
        raise VerifyError("Tutor did not prove that the Open WebUI main router stayed unmodified.")
    if routes.get("before_spa") is not True:
        raise VerifyError("Tutor ASGI gateway is not confirmed ahead of the Open WebUI SPA fallback.")
    if routes.get("required_complete") is not True:
        raise VerifyError("Tutor route table is incomplete.")
    if list(routes.get("missing_required") or []):
        raise VerifyError(f"Tutor reports missing required routes: {routes.get('missing_required')!r}")
    if list(routes.get("duplicate_method_paths") or []):
        raise VerifyError(f"Tutor reports duplicate method/path entries: {routes.get('duplicate_method_paths')!r}")
    try:
        route_count = int(routes.get("study_routes") or 0)
    except (TypeError, ValueError) as exc:
        raise VerifyError("Tutor route count is not an integer.") from exc
    if route_count <= 0:
        raise VerifyError("Tutor route table contains no study routes.")

    runtime_id = str(routes.get("runtime_id") or "")
    registered_runtime_id = str(routes.get("registered_runtime_id") or "")
    if routes.get("bound_to_current_runtime") is not True:
        raise VerifyError("Tutor routes are not bound to the current runtime.")
    if runtime_id and registered_runtime_id and runtime_id != registered_runtime_id:
        raise VerifyError("Tutor route runtime IDs do not match.")

    return {
        "registration_strategy": strategy,
        "architecture": RUNTIME_ARCHITECTURE_LABEL,
        "gateway_active": True,
        "main_router_mutated": False,
        "study_routes": route_count,
    }

def wait_for_runtime(
    config: InstallerConfig,
    api: OpenWebUIApi,
    *,
    report: dict[str, Any],
    timeout: float | None = None,
) -> dict[str, Any]:
    deadline = time.monotonic() + (timeout if timeout is not None else config.route_timeout)
    attempts: list[dict[str, Any]] = []
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        nonce = uuid.uuid4().hex
        try:
            health_result = api.client.request(
                "GET",
                "/study-tutor/health",
                query={"_": nonce},
                headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
                expected=(200,),
            )
            if health_result.body.lstrip().startswith(b"<"):
                raise VerifyError("Tutor health path returned the Open WebUI SPA HTML fallback.")
            health = health_result.json()
            if not isinstance(health, dict):
                raise VerifyError("Tutor health response is not an object.")
            version = str(health.get("version") or "")
            marker = str(health.get("build_marker") or health.get("marker") or "")
            function_id = str(health.get("function_id") or "")
            route_version = health.get("route_registration_version")
            routes = health.get("routes") if isinstance(health.get("routes"), dict) else {}
            if version != RUNTIME_VERSION:
                raise VerifyError(f"Tutor health reports runtime version {version!r}, expected {RUNTIME_VERSION!r}.")
            if marker != RUNTIME_MARKER:
                raise VerifyError("Tutor health reports a stale or unknown build marker.")
            if function_id != EVENT_ID:
                raise VerifyError(f"Tutor health reports Event Function {function_id!r}, expected {EVENT_ID!r}.")
            if int(route_version or routes.get("registration_version") or 0) != ROUTE_REGISTRATION_VERSION:
                raise VerifyError("Tutor route registration version is stale.")
            route_contract = validate_runtime_route_contract(routes)

            canvas_result = api.client.request(
                "GET",
                "/study-tutor/canvas",
                query={"_": nonce},
                headers={"Accept": "text/html", "Cache-Control": "no-store"},
                expected=(200,),
            )
            canvas_type = canvas_result.headers.get("content-type", "")
            canvas_text = canvas_result.body.decode("utf-8", errors="replace")
            if "text/html" not in canvas_type.lower() or "VUT AI Tutor" not in canvas_text:
                raise VerifyError(f"Canvas endpoint is not Tutor HTML: {compact_body(canvas_result.body)}")
            if "LICENSE covers this Open WebUI branding surface" in canvas_text[:5000]:
                raise VerifyError("Canvas endpoint returned the Open WebUI SPA fallback.")

            cors_result = api.client.request(
                "OPTIONS",
                "/study-tutor/api/state",
                headers={
                    "Origin": "null",
                    "Access-Control-Request-Method": "GET",
                    "Access-Control-Request-Headers": "authorization,content-type",
                },
                expected=(200, 204),
            )
            allow_origin = cors_result.headers.get("access-control-allow-origin", "")
            if allow_origin not in {"null", "*"}:
                raise VerifyError(f"Canvas CORS preflight did not allow Origin:null (got {allow_origin!r}).")
            if allow_origin == "*":
                report.setdefault("warnings", []).append(
                    "Open WebUI returned Access-Control-Allow-Origin: * for Tutor preflight; the Tutor route works, but restrict global CORS in production."
                )
            verified = {
                "health": health,
                "health_url": health_result.url,
                "canvas": {"status": canvas_result.status, "content_type": canvas_type, "bytes": len(canvas_result.body)},
                "cors": {"status": cors_result.status, "allow_origin": allow_origin},
                "route_contract": route_contract,
                "attempts": attempts + [{"at": utc_now(), "ok": True}],
            }
            report["runtime_verification"] = verified
            return verified
        except Exception as exc:
            last_error = exc
            attempts.append({"at": utc_now(), "ok": False, "error": f"{type(exc).__name__}: {exc}"})
            time.sleep(1.0)
    report["runtime_verification"] = {"attempts": attempts, "ok": False}
    raise VerifyError(f"Tutor runtime did not become healthy within the timeout: {last_error}") from last_error

def compatibility_observation(version: str, report: dict[str, Any]) -> None:
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)", version)
    if not match:
        report.setdefault("warnings", []).append(f"Open WebUI version {version!r} is not semantic; capability probes are authoritative.")
        return
    major, minor, patch = map(int, match.groups())
    report["openwebui_compatibility"] = {
        "reported_version": version,
        "tested_families": ["0.10.x", "0.11.2", "0.11.3"],
        "capability_probes_authoritative": True,
    }
    if major != 0 or minor not in {10, 11}:
        report.setdefault("warnings", []).append(
            f"Open WebUI {version} is outside the release's tested families; installation proceeds only because API and runtime capability probes pass."
        )


def install_or_repair(
    config: InstallerConfig,
    adapter: PlatformAdapter,
    base_url: str,
    report: dict[str, Any],
    event_contract: PayloadContract,
    pipe_contract: PayloadContract,
    event_source: str,
    pipe_source: str,
) -> None:
    api = OpenWebUIApi(config, base_url, report)
    token = api.authenticate()
    snapshots = snapshot_functions(api)
    backup_root = pathlib.Path(config.backup_dir).expanduser().resolve() if config.backup_dir else pathlib.Path(config.report_path).expanduser().resolve().parent / "vut-ai-tutor-backups"
    backup_path = backup_root / f"functions-before-{dt.datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    save_snapshot(backup_path, base_url, snapshots)
    report["function_backup"] = str(backup_path)
    transaction_started = True
    try:
        # Disable every known legacy Event before touching the canonical pair.
        for function_id in MANAGED_IDS:
            current = api.get_function(function_id)
            if current and current.get("is_active"):
                api.set_active(function_id, False)
        if config.action == "repair":
            # Delete/recreate clears Open WebUI's module cache without affecting unrelated Functions.
            api.delete_function(EVENT_ID)
            api.delete_function(PIPE_ID)

        snapshot_by_id = {item.function_id: item for item in snapshots}
        pipe_previous = snapshot_by_id.get(PIPE_ID)
        event_previous = snapshot_by_id.get(EVENT_ID)
        pipe_record = api.upsert_function(
            PIPE_ID,
            "VUT AI Tutor",
            pipe_source,
            "pipe",
            True,
            desired_global=bool(pipe_previous.record.get("is_global")) if pipe_previous and pipe_previous.record else False,
            valves=pipe_previous.valves if pipe_previous else None,
        )
        event_record = api.upsert_function(
            EVENT_ID,
            "VUT AI Tutor Canvas Gateway",
            event_source,
            "event",
            True,
            desired_global=bool(event_previous.record.get("is_global")) if event_previous and event_previous.record else False,
            valves=event_previous.valves if event_previous else None,
        )
        report["function_verification"] = {
            "pipe": verify_function_record(api.get_function(PIPE_ID), pipe_contract),
            "event": verify_function_record(api.get_function(EVENT_ID), event_contract),
        }

        if config.restart_policy == "always":
            if not adapter.can_restart():
                raise BackendError(f"restart_policy=always was requested, but {adapter.name} cannot restart this instance.")
            adapter.restart()
            base_url = select_backend(config, adapter, report, allow_start=True)
            api = OpenWebUIApi(config, base_url, report)
            api.client.with_token(token)
            api._validate_admin_api()

        try:
            wait_for_runtime(config, api, report=report)
        except VerifyError as first_error:
            report.setdefault("warnings", []).append(f"Initial runtime activation failed: {first_error}")
            # One deterministic cache-busting cycle through the public Functions API.
            api.delete_function(EVENT_ID)
            api.upsert_function(
                EVENT_ID,
                "VUT AI Tutor Canvas Gateway",
                event_source,
                "event",
                True,
                desired_global=bool(event_previous.record.get("is_global")) if event_previous and event_previous.record else False,
                valves=event_previous.valves if event_previous else None,
            )
            try:
                wait_for_runtime(config, api, report=report, timeout=min(config.route_timeout, 45.0))
            except VerifyError as second_error:
                if config.restart_policy == "on-failure" and adapter.can_restart():
                    report.setdefault("warnings", []).append(
                        f"API cache refresh did not activate the gateway; restarting only the selected {adapter.name} instance: {second_error}"
                    )
                    adapter.restart()
                    base_url = select_backend(config, adapter, report, allow_start=True)
                    api = OpenWebUIApi(config, base_url, report)
                    api.client.with_token(token)
                    api._validate_admin_api()
                    # Persistent Functions must survive the platform restart.
                    verify_function_record(api.get_function(PIPE_ID), pipe_contract)
                    verify_function_record(api.get_function(EVENT_ID), event_contract)
                    wait_for_runtime(config, api, report=report)
                else:
                    raise

        # Remove historical IDs only after the canonical pair and runtime have passed acceptance.
        legacy_results: dict[str, bool] = {}
        for function_id in LEGACY_IDS:
            if config.keep_legacy_disabled:
                current = api.get_function(function_id)
                if current and current.get("is_active"):
                    api.set_active(function_id, False)
                legacy_results[function_id] = current is not None
            else:
                legacy_results[function_id] = api.delete_function(function_id)
        report["legacy_cleanup"] = legacy_results
        report["base_url"] = base_url
        report["ok"] = True
        report["completed_at"] = utc_now()
    except Exception:
        if transaction_started and not config.no_rollback:
            try:
                restore_snapshot(api, snapshots, report)
            except Exception as rollback_exc:
                report.setdefault("errors", []).append(f"Rollback failed: {rollback_exc}")
        raise


def verify_installation(
    config: InstallerConfig,
    base_url: str,
    report: dict[str, Any],
    event_contract: PayloadContract,
    pipe_contract: PayloadContract,
) -> None:
    api = OpenWebUIApi(config, base_url, report)
    api.authenticate()
    report["function_verification"] = {
        "pipe": verify_function_record(api.get_function(PIPE_ID), pipe_contract),
        "event": verify_function_record(api.get_function(EVENT_ID), event_contract),
    }
    legacy_active: list[str] = []
    for function_id in LEGACY_IDS:
        record = api.get_function(function_id)
        if record and record.get("is_active"):
            legacy_active.append(function_id)
    if legacy_active:
        raise VerifyError("Legacy Tutor Event/pipe Functions are still active: " + ", ".join(legacy_active))
    report["legacy_active"] = legacy_active
    wait_for_runtime(config, api, report=report)
    report["base_url"] = base_url
    report["ok"] = True
    report["completed_at"] = utc_now()


def uninstall(config: InstallerConfig, base_url: str, report: dict[str, Any]) -> None:
    api = OpenWebUIApi(config, base_url, report)
    api.authenticate()
    snapshots = snapshot_functions(api)
    backup_root = pathlib.Path(config.backup_dir).expanduser().resolve() if config.backup_dir else pathlib.Path(config.report_path).expanduser().resolve().parent / "vut-ai-tutor-backups"
    backup_path = backup_root / f"functions-before-uninstall-{dt.datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    save_snapshot(backup_path, base_url, snapshots)
    report["function_backup"] = str(backup_path)
    deleted: dict[str, bool] = {}
    for function_id in MANAGED_IDS:
        deleted[function_id] = api.delete_function(function_id)
    report["deleted"] = deleted
    report["ok"] = True
    report["completed_at"] = utc_now()


def preflight(config: InstallerConfig, adapter: PlatformAdapter, base_url: str, report: dict[str, Any]) -> None:
    probe = probe_candidate(config, BackendCandidate(base_url, "selected preflight", 0))
    if not probe.reachable:
        raise BackendError(probe.error or "Open WebUI preflight failed.")
    compatibility_observation(probe.version or "", report)
    report["preflight"] = {
        "backend": dataclasses.asdict(probe),
        "platform": adapter.describe(),
        "tls": {
            "scheme": urllib.parse.urlsplit(base_url).scheme,
            "custom_ca": bool(config.ca_certificate),
            "insecure": config.insecure_tls,
        },
        "mutating": False,
    }
    # Auth/API capability is checked only when credentials are supplied.
    credentials_available = bool(
        config.token_file
        or os.environ.get("VUT_INSTALL_TOKEN")
        or config.email
        or os.environ.get("VUT_INSTALL_EMAIL")
    )
    if credentials_available:
        api = OpenWebUIApi(config, base_url, report)
        api.authenticate()
        report["preflight"]["functions_api"] = {"available": True, "function_count": len(api.list_functions())}
    else:
        report["preflight"]["functions_api"] = {"available": None, "reason": "credentials not supplied"}
    report["ok"] = True
    report["completed_at"] = utc_now()


def self_test(config: InstallerConfig) -> dict[str, Any]:
    event_path = pathlib.Path(config.bootstrap_path or "")
    pipe_path = pathlib.Path(config.pipe_path or "")
    event_contract = verify_payload(event_path, EVENT_ID, "event")
    pipe_contract = verify_payload(pipe_path, PIPE_ID, "pipe")
    event_source = read_text_file(event_path)
    declared_strategies = runtime_declared_route_strategies(event_source)
    if RUNTIME_HEALTH_ROUTE_STRATEGY not in declared_strategies:
        raise ConfigError(
            "Event bootstrap does not declare the route strategy required by the installer: "
            f"expected {RUNTIME_HEALTH_ROUTE_STRATEGY!r}, found {sorted(declared_strategies)!r}."
        )
    route_contract = validate_runtime_route_contract(
        {
            "registration_strategy": RUNTIME_HEALTH_ROUTE_STRATEGY,
            "healthy": True,
            "gateway_active": True,
            "main_router_mutated": False,
            "before_spa": True,
            "required_complete": True,
            "missing_required": [],
            "duplicate_method_paths": [],
            "study_routes": 43,
            "runtime_id": "self-test-runtime",
            "registered_runtime_id": "self-test-runtime",
            "bound_to_current_runtime": True,
        }
    )
    assert endpoint_url("https://example.invalid/prefix/", "/api/version") == "https://example.invalid/prefix/api/version"
    assert is_loopback_url("http://127.0.0.1:8080")
    assert is_loopback_url("http://[::1]:8080")
    assert not is_loopback_url("https://example.invalid")
    return {
        "ok": True,
        "installer_version": INSTALLER_VERSION,
        "runtime_version": RUNTIME_VERSION,
        "runtime_marker": RUNTIME_MARKER,
        "event": dataclasses.asdict(event_contract),
        "pipe": dataclasses.asdict(pipe_contract),
        "managed_ids": list(MANAGED_IDS),
        "health_route_strategies_declared_by_runtime": sorted(declared_strategies),
        "route_contract": route_contract,
        "architecture": "api-first-platform-adapters-asgi-gateway",
    }


def run(config: InstallerConfig) -> dict[str, Any]:
    report_path = pathlib.Path(config.report_path).expanduser().resolve()
    report: dict[str, Any] = {
        "ok": False,
        "started_at": utc_now(),
        "installer_version": INSTALLER_VERSION,
        "runtime_version": RUNTIME_VERSION,
        "runtime_marker": RUNTIME_MARKER,
        "requested": redact(dataclasses.asdict(config)),
        "host": {"os": os.name, "platform": sys.platform, "python": sys.version.split()[0]},
        "warnings": [],
        "errors": [],
    }
    try:
        if config.action == "self-test":
            result = self_test(config)
            report.update(result)
            report["completed_at"] = utc_now()
            return report
        event_path = pathlib.Path(config.bootstrap_path or "").expanduser().resolve()
        pipe_path = pathlib.Path(config.pipe_path or "").expanduser().resolve()
        event_contract = verify_payload(event_path, EVENT_ID, "event")
        pipe_contract = verify_payload(pipe_path, PIPE_ID, "pipe")
        event_source = read_text_file(event_path)
        pipe_source = read_text_file(pipe_path)
        report["payloads"] = {"event": dataclasses.asdict(event_contract), "pipe": dataclasses.asdict(pipe_contract)}
        adapter = make_adapter(config, report)
        report["platform"] = adapter.describe()
        allow_start = config.action in {"install", "repair"} and config.start_backend
        base_url = select_backend(config, adapter, report, allow_start=allow_start)
        selected = report.get("backend", {}).get("selected", {})
        compatibility_observation(str(selected.get("version") or ""), report)
        if config.action == "preflight":
            preflight(config, adapter, base_url, report)
        elif config.action in {"install", "repair"}:
            install_or_repair(config, adapter, base_url, report, event_contract, pipe_contract, event_source, pipe_source)
        elif config.action == "verify":
            verify_installation(config, base_url, report, event_contract, pipe_contract)
        elif config.action == "uninstall":
            uninstall(config, base_url, report)
        else:
            raise ConfigError(f"Unsupported action: {config.action}")
        return report
    except Exception as exc:
        report["ok"] = False
        report["completed_at"] = utc_now()
        report["errors"].append({"type": type(exc).__name__, "message": str(exc)})
        if config.debug:
            report["traceback"] = traceback.format_exc()
        raise
    finally:
        atomic_write_json(report_path, report)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", help="JSON configuration file generated by a wrapper.")
    parser.add_argument("--action", choices=["install", "repair", "verify", "preflight", "uninstall", "self-test"])
    parser.add_argument("--platform", choices=["auto", "desktop", "docker", "baremetal", "remote"])
    parser.add_argument("--base-url")
    parser.add_argument("--token-file")
    parser.add_argument("--email")
    parser.add_argument("--password-file")
    parser.add_argument("--prompt-for-credential", action="store_true")
    parser.add_argument("--ca-certificate")
    parser.add_argument("--insecure-tls", action="store_true")
    parser.add_argument("--request-timeout", type=float)
    parser.add_argument("--startup-timeout", type=float)
    parser.add_argument("--route-timeout", type=float)
    parser.add_argument("--restart-policy", choices=["never", "on-failure", "always"])
    parser.add_argument("--no-start-backend", action="store_true")
    parser.add_argument("--no-rollback", action="store_true")
    parser.add_argument("--keep-legacy-disabled", action="store_true")
    parser.add_argument("--report-path")
    parser.add_argument("--backup-dir")
    parser.add_argument("--bootstrap-path")
    parser.add_argument("--pipe-path")
    parser.add_argument("--desktop-install-root")
    parser.add_argument("--desktop-config-root")
    parser.add_argument("--desktop-executable")
    parser.add_argument("--container-engine", choices=["auto", "docker", "podman"])
    parser.add_argument("--container-name")
    parser.add_argument("--service-name")
    parser.add_argument("--restart-command")
    parser.add_argument("--debug", action="store_true")
    return parser


def config_from_args(args: argparse.Namespace) -> InstallerConfig:
    raw: dict[str, Any] = {}
    if args.config:
        value = read_json_file(pathlib.Path(args.config).expanduser().resolve())
        if not isinstance(value, dict):
            raise ConfigError("Configuration JSON must contain an object.")
        raw.update(value)
    for key, value in vars(args).items():
        if key == "config" or value is None or value is False:
            continue
        if key == "no_start_backend":
            raw["start_backend"] = False
        else:
            raw[key] = value
    return InstallerConfig.from_mapping(raw)


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        config = config_from_args(args)
        report = run(config)
        print(json.dumps(redact(report), ensure_ascii=False, indent=2))
        return EXIT_OK
    except InstallerError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return exc.exit_code
    except KeyboardInterrupt:
        print("[FAIL] Operation cancelled.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"[FAIL] Unexpected error: {type(exc).__name__}: {exc}", file=sys.stderr)
        if getattr(args, "debug", False):
            traceback.print_exc()
        return EXIT_INSTALL


if __name__ == "__main__":
    raise SystemExit(main())

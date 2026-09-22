from __future__ import annotations

import argparse
import contextlib
import concurrent.futures
import ast
import base64
import getpass
import hashlib
import json
import ntpath
import os
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

RELEASE_VERSION = "1.26.5"
RELEASE_MARKER = "VUT-AI-TUTOR-1.26.5-SERVER-DESKTOP-WINDOWS-MOCK-TRANSPORT-COMPLETE"
DESKTOP_ADAPTER_REVISION = "2.3.1-official-desktop-lifecycle-r1"
BOOTSTRAP_ID = "study_tutor_gateway_bootstrap"
PIPE_ID = "study_tutor_pipe"
LEGACY_IDS = ("study_tutor_canvas_bootstrap", "study_tutor_bootstrap", "vut_ai_tutor_bootstrap", "vut_ai_tutor_pipe", "study_tutor_pipe_managed")
MIN_DESKTOP_OPENWEBUI_VERSION = "0.11.3"
KNOWN_MIGRATION_BUG_MAX_VERSION = "0.11.2"
DATABASE_OVERRIDE_KEYS = frozenset({
    "DATABASE_URL", "DATABASE_TYPE", "DATABASE_HOST", "DATABASE_PORT",
    "DATABASE_NAME", "DATABASE_USER", "DATABASE_PASSWORD", "DATABASE_SCHEMA",
})
REQUIRED_TIMER_INDEXES = frozenset({
    "timer_at_idx", "user_id_updated_at_id_idx", "user_id_timer_at_idx",
    "user_id_folder_unread_idx", "chat_message_chat_role_done_idx",
})
BACKEND_POLL_INTERVAL_SECONDS = 2.0
BACKEND_MAX_LOG_URLS_PER_ROOT = 12
BACKEND_MAX_CANDIDATES_PER_PASS = 48
BACKEND_RANGE_SCAN_TIMEOUT_SECONDS = 0.10
BACKEND_RANGE_SCAN_WORKERS = 32
HTTP_TRANSIENT_RETRY_BASE_DELAY_SECONDS = 0.20
HTTP_VERSION_TRANSIENT_RETRIES = 2
HTTP_SIGNIN_TRANSIENT_RETRIES = 3


def configure_console_streams() -> None:
    for stream in (getattr(sys, "stdout", None), getattr(sys, "stderr", None)):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
            except (OSError, ValueError):
                pass


configure_console_streams()


class TutorInstallError(RuntimeError):
    pass


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def atomic_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    temp.replace(path)


def parse_version(value: str) -> tuple[int, ...]:
    numbers = re.findall(r"\d+", str(value))
    return tuple(int(item) for item in numbers[:4]) if numbers else (0,)


def normalize_base_url(value: str) -> str:
    value = str(value or "").strip().rstrip("/")
    if not value:
        return ""
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise TutorInstallError(f"Neplatná Open WebUI URL: {value!r}")
    if parsed.query or parsed.fragment or parsed.username or parsed.password:
        raise TutorInstallError("BaseUrl nesmí obsahovat přihlašovací údaje, query ani fragment.")
    path = parsed.path.rstrip("/")
    for suffix in ("/api/version", "/study-tutor/health", "/study-tutor/canvas"):
        if path.endswith(suffix):
            path = path[: -len(suffix)]
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, path.rstrip("/"), "", ""))


_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def _urlopen(request: urllib.request.Request, timeout: float):
    """Open local Desktop URLs directly, without inherited corporate proxy settings."""
    parsed = urllib.parse.urlsplit(request.full_url)
    hostname = (parsed.hostname or "").casefold()
    if hostname in _LOOPBACK_HOSTS:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        return opener.open(request, timeout=timeout)
    return urllib.request.urlopen(request, timeout=timeout)


def strip_ansi(text: str) -> str:
    return re.sub(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))", "", text)


def find_first_existing(paths: Iterable[Path]) -> Path | None:
    for path in paths:
        if path and path.exists():
            return path
    return None


def extract_frontmatter(source: str) -> dict[str, str]:
    try:
        module = ast.parse(source)
        doc = ast.get_docstring(module, clean=False) or ""
    except SyntaxError as exc:
        raise TutorInstallError(f"Python source se neparsuje: {exc}") from exc
    result: dict[str, str] = {}
    for line in doc.splitlines():
        match = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_-]*)\s*:\s*(.*?)\s*$", line)
        if match:
            result[match.group(1).lower()] = match.group(2)
    return result


def literal_assignment(module: ast.Module, name: str) -> Any:
    for node in module.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    try:
                        return ast.literal_eval(node.value)
                    except Exception:
                        return None
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == name:
            try:
                return ast.literal_eval(node.value)
            except Exception:
                return None
    return None


@dataclass
class SourceContract:
    path: str
    function_id: str
    function_type: str
    version: str
    marker: str
    sha256: str
    content: str = field(repr=False)


def validate_source(path: Path, expected_id: str, expected_type: str) -> SourceContract:
    if not path.is_file():
        raise TutorInstallError(f"Chybí zdroj Function: {path}")
    source = read_text(path)
    try:
        module = ast.parse(source)
    except SyntaxError as exc:
        raise TutorInstallError(f"{path.name}: syntaktická chyba Pythonu: {exc}") from exc
    frontmatter = extract_frontmatter(source)
    fm_id = frontmatter.get("id", "").strip()
    fm_version = frontmatter.get("version", "").strip()
    plugin_version = str(literal_assignment(module, "PLUGIN_VERSION") or "").strip()
    marker = str(literal_assignment(module, "TUTOR_BUILD_MARKER") or "").strip()
    top_classes = {node.name for node in module.body if isinstance(node, ast.ClassDef)}
    expected_class = "Event" if expected_type == "event" else "Pipe"
    other_class = "Pipe" if expected_type == "event" else "Event"
    failures: list[str] = []
    if fm_id != expected_id:
        failures.append(f"frontmatter id={fm_id!r}, očekáváno {expected_id!r}")
    if fm_version != RELEASE_VERSION:
        failures.append(f"frontmatter version={fm_version!r}, očekáváno {RELEASE_VERSION!r}")
    if plugin_version != RELEASE_VERSION:
        failures.append(f"PLUGIN_VERSION={plugin_version!r}, očekáváno {RELEASE_VERSION!r}")
    if marker != RELEASE_MARKER:
        failures.append(f"TUTOR_BUILD_MARKER={marker!r}, očekáváno {RELEASE_MARKER!r}")
    if expected_class not in top_classes:
        failures.append(f"chybí top-level class {expected_class}")
    if other_class in top_classes:
        failures.append(f"zdroj nesmí současně obsahovat top-level class {other_class}")
    if failures:
        raise TutorInstallError(f"Neplatný release contract {path}: " + "; ".join(failures))
    return SourceContract(
        path=str(path.resolve()), function_id=expected_id, function_type=expected_type,
        version=RELEASE_VERSION, marker=RELEASE_MARKER, sha256=sha256_text(source), content=source,
    )


def extract_embedded_pipe_source(bootstrap_source: str) -> str:
    """Decode the exact PIPE_SOURCE that the Event may provision at runtime."""
    try:
        module = ast.parse(bootstrap_source)
    except SyntaxError as exc:
        raise TutorInstallError(f"Bootstrap se neparsuje při kontrole vložené Pipe: {exc}") from exc
    for node in module.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if not any(isinstance(target, ast.Name) and target.id == "PIPE_SOURCE" for target in targets):
            continue
        value = node.value
        if not (isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and value.func.id == "_decode_asset" and value.args):
            raise TutorInstallError("Bootstrap PIPE_SOURCE není deklarována podporovaným _decode_asset(...) zápisem.")
        try:
            encoded = ast.literal_eval(value.args[0])
            return zlib.decompress(base64.b85decode(str(encoded).encode("ascii"))).decode("utf-8")
        except Exception as exc:
            raise TutorInstallError(f"Vloženou PIPE_SOURCE nelze dekódovat: {exc}") from exc
    raise TutorInstallError("Bootstrap neobsahuje vloženou PIPE_SOURCE.")


def validate_source_pair(bootstrap: SourceContract, pipe: SourceContract) -> dict[str, str]:
    embedded = extract_embedded_pipe_source(bootstrap.content)
    embedded_contract = validate_source_text(embedded, PIPE_ID, "pipe")
    embedded_sha = sha256_text(embedded)
    if embedded != pipe.content:
        raise TutorInstallError(
            "Vložená PIPE_SOURCE v bootstrapu není bajtově shodná se samostatnou Pipe; "
            f"embedded sha256={embedded_sha}, external sha256={pipe.sha256}."
        )
    return {
        "embedded_pipe_sha256": embedded_sha,
        "external_pipe_sha256": pipe.sha256,
        "version": embedded_contract["version"],
        "marker": embedded_contract["marker"],
    }


@dataclass
class HttpResponse:
    status: int
    headers: dict[str, str]
    body: bytes
    url: str

    def json(self) -> Any:
        try:
            return json.loads(self.body.decode("utf-8-sig"))
        except Exception as exc:
            preview = self.body[:500].decode("utf-8", errors="replace")
            raise TutorInstallError(f"Endpoint {self.url} nevrátil JSON (HTTP {self.status}): {preview}") from exc


class OpenWebUIClient:
    def __init__(self, base_url: str, *, timeout: float = 15.0, token: str = "") -> None:
        self.base_url = normalize_base_url(base_url)
        self.timeout = float(timeout)
        self.token = token.strip()

    def request(
        self, method: str, path: str, *, data: Any = None, auth: bool = False,
        expected: Iterable[int] = (200,), headers: dict[str, str] | None = None,
        transient_retries: int = 0,
    ) -> HttpResponse:
        url = self.base_url + (path if path.startswith("/") else "/" + path)
        payload = None
        request_headers = {"Accept": "application/json", "User-Agent": f"VUT-AI-Tutor-Installer/{RELEASE_VERSION}"}
        if data is not None:
            payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
            request_headers["Content-Type"] = "application/json"
        if auth:
            if not self.token:
                raise TutorInstallError("Chybí administrátorský bearer token.")
            request_headers["Authorization"] = f"Bearer {self.token}"
        if headers:
            request_headers.update(headers)

        attempts = max(1, int(transient_retries) + 1)
        result: HttpResponse | None = None
        last_transport_error: BaseException | None = None
        for attempt in range(1, attempts + 1):
            req = urllib.request.Request(url, data=payload, headers=request_headers, method=method.upper())
            try:
                with _urlopen(req, timeout=self.timeout) as response:
                    result = HttpResponse(
                        int(response.status),
                        {k.lower(): v for k, v in response.headers.items()},
                        response.read(),
                        response.geturl(),
                    )
            except urllib.error.HTTPError as exc:
                result = HttpResponse(
                    int(exc.code),
                    {k.lower(): v for k, v in exc.headers.items()},
                    exc.read(),
                    exc.geturl(),
                )
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_transport_error = exc
                if attempt >= attempts:
                    raise TutorInstallError(
                        f"Nelze se spojit s {url} po {attempts} pokusu/pokusech: {exc}"
                    ) from exc
                delay = min(
                    HTTP_TRANSIENT_RETRY_BASE_DELAY_SECONDS * (2 ** (attempt - 1)),
                    1.0,
                )
                time.sleep(delay)
                continue
            break

        if result is None:
            raise TutorInstallError(
                f"Nelze se spojit s {url}: {last_transport_error or 'neznámá transportní chyba'}"
            )
        expected_set = set(expected)
        if result.status not in expected_set:
            preview = result.body[:1000].decode("utf-8", errors="replace")
            raise TutorInstallError(
                f"{method.upper()} {url} vrátil HTTP {result.status}, "
                f"očekáváno {sorted(expected_set)}: {preview}"
            )
        return result

    def version(self) -> dict[str, Any]:
        data = self.request("GET", "/api/version", expected=(200,), transient_retries=HTTP_VERSION_TRANSIENT_RETRIES).json()
        if not isinstance(data, dict):
            raise TutorInstallError(f"{self.base_url}/api/version nevrátil objekt.")
        return data

    def sign_in(self, email: str, password: str) -> str:
        data = self.request(
            "POST",
            "/api/v1/auths/signin",
            data={"email": email, "password": password},
            expected=(200,),
            transient_retries=HTTP_SIGNIN_TRANSIENT_RETRIES,
        ).json()
        if not isinstance(data, dict):
            raise TutorInstallError("Přihlášení nevrátilo JSON objekt.")
        token = data.get("token") or data.get("access_token")
        if not token and isinstance(data.get("data"), dict):
            token = data["data"].get("token") or data["data"].get("access_token")
        if not isinstance(token, str) or not token.strip():
            raise TutorInstallError("Přihlášení proběhlo bez bearer tokenu.")
        self.token = token.strip()
        return self.token

    def get_function(self, function_id: str) -> dict[str, Any] | None:
        response = self.request("GET", f"/api/v1/functions/id/{urllib.parse.quote(function_id)}", auth=True, expected=(200, 401, 404))
        if response.status in {401, 404}:
            # Distinguish authorization failure from not-found by trying the list endpoint.
            try:
                items = self.request("GET", "/api/v1/functions/", auth=True, expected=(200,)).json()
            except TutorInstallError:
                raise TutorInstallError(f"Administrátorský token nemá přístup k Functions API ({function_id}).")
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict) and item.get("id") == function_id:
                        return item
            return None
        data = response.json()
        return data if isinstance(data, dict) else None

    @staticmethod
    def form(contract: SourceContract) -> dict[str, Any]:
        label = "Bootstrap" if contract.function_type == "event" else "Pipe"
        return {
            "id": contract.function_id,
            "name": "VUT AI Tutor" if contract.function_type == "pipe" else "VUT AI Tutor Bootstrap",
            "content": contract.content,
            "meta": {
                "description": f"Managed VUT AI Tutor {label} {RELEASE_VERSION}; {RELEASE_MARKER}",
                "manifest": {
                    "managed_by": RELEASE_MARKER,
                    "version": RELEASE_VERSION,
                    "function_id": contract.function_id,
                    "function_type": contract.function_type,
                    "sha256": contract.sha256,
                },
            },
        }

    def upsert_function(self, contract: SourceContract) -> dict[str, Any]:
        existing = self.get_function(contract.function_id)
        form = self.form(contract)
        if existing is None:
            data = self.request("POST", "/api/v1/functions/create", data=form, auth=True, expected=(200, 201)).json()
        else:
            data = self.request("POST", f"/api/v1/functions/id/{contract.function_id}/update", data=form, auth=True, expected=(200,)).json()
        if not isinstance(data, dict):
            raise TutorInstallError(f"Upsert {contract.function_id} nevrátil Function objekt.")
        # Force a fresh module/lifecycle cycle. Update of an active Event alone does not guarantee setup execution.
        current = self.get_function(contract.function_id) or data
        if bool(current.get("is_active")):
            self.request("POST", f"/api/v1/functions/id/{contract.function_id}/toggle", auth=True, expected=(200,))
        enabled = self.request("POST", f"/api/v1/functions/id/{contract.function_id}/toggle", auth=True, expected=(200,)).json()
        if not isinstance(enabled, dict) or not bool(enabled.get("is_active")):
            raise TutorInstallError(f"Function {contract.function_id} se nepodařilo aktivovat.")
        return enabled

    def deactivate_and_delete_legacy(self, function_id: str) -> dict[str, Any]:
        existing = self.get_function(function_id)
        if existing is None:
            return {"id": function_id, "present": False}
        if bool(existing.get("is_active")):
            self.request("POST", f"/api/v1/functions/id/{function_id}/toggle", auth=True, expected=(200,))
        response = self.request("DELETE", f"/api/v1/functions/id/{function_id}/delete", auth=True, expected=(200, 404))
        deleted = response.status == 200 and bool(response.json())
        return {"id": function_id, "present": True, "deleted": deleted}

    def verify_function(self, contract: SourceContract) -> dict[str, Any]:
        function = self.get_function(contract.function_id)
        if function is None:
            raise TutorInstallError(f"Function {contract.function_id} po instalaci chybí.")
        failures: list[str] = []
        actual_type = str(function.get("type") or "")
        if actual_type != contract.function_type:
            failures.append(f"type={actual_type!r}, očekáváno {contract.function_type!r}")
        if not bool(function.get("is_active")):
            failures.append("is_active není true")
        content = function.get("content")
        if not isinstance(content, str):
            # GET /id returns FunctionModel including content in current Server/Desktop versions.
            full = self.request("GET", f"/api/v1/functions/id/{contract.function_id}", auth=True, expected=(200,)).json()
            content = full.get("content") if isinstance(full, dict) else None
        actual_sha = sha256_text(content) if isinstance(content, str) else ""
        if actual_sha != contract.sha256:
            failures.append(f"content sha256={actual_sha or '<missing>'}, očekáváno {contract.sha256}")
        if isinstance(content, str):
            try:
                returned = validate_source_text(content, contract.function_id, contract.function_type)
            except TutorInstallError as exc:
                failures.append(str(exc))
            else:
                if returned["version"] != RELEASE_VERSION or returned["marker"] != RELEASE_MARKER:
                    failures.append("release contract vráceného zdroje se neshoduje")
        if failures:
            raise TutorInstallError(f"Ověření Function {contract.function_id} selhalo: " + "; ".join(failures))
        return {
            "id": contract.function_id,
            "type": actual_type,
            "is_active": True,
            "content_sha256": actual_sha,
            "updated_at": function.get("updated_at"),
        }


    def verify_tutor_routes(self, *, timeout: float = 45.0) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        last: str = ''
        attempts = 0
        while time.monotonic() < deadline:
            attempts += 1
            try:
                response = self.request(
                    'GET',
                    '/study-tutor/health',
                    expected=(200, 404),
                    headers={'Accept': 'application/json'},
                )
                if response.status == 200:
                    content_type = str(response.headers.get('content-type') or '').lower()
                    preview = response.body[:500].decode('utf-8', errors='replace').lstrip()
                    if 'text/html' in content_type or preview.lower().startswith(('<!doctype html', '<html')):
                        last = (
                            'Health endpoint byl pohlcen Open WebUI SPA fallbackem; '
                            'Event Function runtime v tomto procesu nezaregistroval tutor router.'
                        )
                    else:
                        data = response.json()
                        if (
                            isinstance(data, dict)
                            and str(data.get('version')) == RELEASE_VERSION
                            and str(data.get('build_marker')) == RELEASE_MARKER
                        ):
                            route_state = data.get('routes') if isinstance(data.get('routes'), dict) else {}
                            if str(data.get('function_id') or '') != BOOTSTRAP_ID:
                                last = f'Health route patří jiné Event Function: {data.get("function_id")!r}; očekáváno {BOOTSTRAP_ID!r}'
                                time.sleep(1.0)
                                continue
                            if int(data.get('route_registration_version') or 0) != 7 or int(route_state.get('registration_version') or 0) != 7:
                                last = f'Health route používá starou registraci: top={data.get("route_registration_version")!r}, routes={route_state.get("registration_version")!r}'
                                time.sleep(1.0)
                                continue
                            if not bool(data.get('ok')):
                                last = f'Health route hlásí ok=false: {route_state!r}'
                                time.sleep(1.0)
                                continue
                            if not bool(route_state.get('healthy')):
                                last = f'Health route hlásí nefunkční route tabulku: {route_state!r}'
                                time.sleep(1.0)
                                continue
                            if str(route_state.get('registration_strategy') or '') != 'asgi-prefix-gateway-v7':
                                last = f'Health route nepoužívá očekávanou izolovanou ASGI gateway v6: {route_state!r}'
                                time.sleep(1.0)
                                continue
                            if not bool(route_state.get('gateway_active')) or route_state.get('main_router_mutated') is not False:
                                last = f'ASGI gateway není aktivní nebo byl změněn hlavní router Open WebUI: {route_state!r}'
                                time.sleep(1.0)
                                continue
                            canvas = self.request('GET', '/study-tutor/canvas', expected=(200,))
                            body = canvas.body.decode('utf-8', errors='replace')
                            if '<!doctype html' not in body.lower() and '<html' not in body.lower():
                                last = 'Canvas endpoint nevrátil HTML.'
                            elif 'Open WebUI branding surface' in body and 'study-tutor' not in body.lower():
                                last = 'Canvas endpoint vrátil Open WebUI SPA fallback.'
                            else:
                                cors = self.request(
                                    'OPTIONS',
                                    '/study-tutor/api/state',
                                    expected=(200, 204),
                                    headers={
                                        'Origin': 'null',
                                        'Access-Control-Request-Method': 'GET',
                                        'Access-Control-Request-Headers': 'authorization,content-type',
                                    },
                                )
                                return {
                                    'health': data,
                                    'canvas_status': canvas.status,
                                    'cors_status': cors.status,
                                    'attempts': attempts,
                                }
                        else:
                            last = f'Health route má jiný release contract: {data!r}'
                else:
                    last = 'Health route zatím není zaregistrována.'
            except Exception as exc:
                last = str(exc)
            time.sleep(1.0)
        error = TutorInstallError(f'Tutor routy nebyly do {timeout:g} s připraveny: {last}')
        setattr(error, 'route_diagnostics', {'attempts': attempts, 'last': last})
        raise error

def validate_source_text(source: str, expected_id: str, expected_type: str) -> dict[str, str]:
    module = ast.parse(source)
    fm = extract_frontmatter(source)
    expected_class = "Event" if expected_type == "event" else "Pipe"
    classes = {n.name for n in module.body if isinstance(n, ast.ClassDef)}
    version = str(literal_assignment(module, "PLUGIN_VERSION") or "")
    marker = str(literal_assignment(module, "TUTOR_BUILD_MARKER") or "")
    if fm.get("id") != expected_id or fm.get("version") != RELEASE_VERSION or version != RELEASE_VERSION or marker != RELEASE_MARKER or expected_class not in classes:
        raise TutorInstallError(
            f"release contract nesouhlasí: id={fm.get('id')!r}, frontmatter version={fm.get('version')!r}, "
            f"PLUGIN_VERSION={version!r}, marker={marker!r}, classes={sorted(classes)}"
        )
    return {"version": version, "marker": marker}



def _tcp_probe(host: str, port: int, timeout: float = 0.15) -> tuple[bool, str]:
    try:
        with socket.create_connection((host, int(port)), timeout=max(0.02, float(timeout))):
            return True, ""
    except OSError as exc:
        return False, f"{type(exc).__name__}: {exc}"


def _scan_open_loopback_ports(ports: Iterable[int], timeout: float = BACKEND_RANGE_SCAN_TIMEOUT_SECONDS) -> list[int]:
    """Return only listening ports, with a bounded concurrent localhost scan.

    Sequentially probing the complete 101-port Desktop fallback range can exceed
    StartupTimeout on Windows hosts where closed loopback ports are silently
    dropped instead of rejected. The scan is therefore concurrent and only open
    ports are promoted to HTTP candidates.
    """
    unique = sorted({int(port) for port in ports if 1 <= int(port) <= 65535})
    if not unique:
        return []
    workers = max(1, min(BACKEND_RANGE_SCAN_WORKERS, len(unique)))
    opened: list[int] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers, thread_name_prefix="vut-backend-scan") as pool:
        futures = {
            pool.submit(_tcp_probe, "127.0.0.1", port, timeout): port
            for port in unique
        }
        for future in concurrent.futures.as_completed(futures):
            port = futures[future]
            try:
                ok, _ = future.result()
            except Exception:
                ok = False
            if ok:
                opened.append(port)
    return sorted(opened)


def http_openwebui_probe(url: str, timeout: float = 2.5) -> dict[str, Any]:
    started = time.monotonic()
    result: dict[str, Any] = {
        "url": "",
        "reachable": False,
        "version_response": None,
        "error": "",
        "elapsed_ms": 0,
    }
    try:
        normalized = normalize_base_url(url)
        result["url"] = normalized
        parsed = urllib.parse.urlsplit(normalized)
        host = parsed.hostname or ""
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        result["host"] = host
        result["port"] = int(port)
        if host.casefold() in _LOOPBACK_HOSTS:
            tcp_ok, tcp_error = _tcp_probe(host, int(port), timeout=min(0.35, max(0.10, float(timeout) * 0.10)))
            result["tcp_open"] = tcp_ok
            if not tcp_ok:
                result["error"] = "tcp-closed: " + tcp_error
                return result
        value = OpenWebUIClient(normalized, timeout=max(0.5, float(timeout))).version()
        version = str(value.get("version") or value.get("current") or "").strip() if isinstance(value, dict) else ""
        if not isinstance(value, dict) or not version:
            result["error"] = f"/api/version returned an unsupported object: {value!r}"[:2000]
            return result
        result["reachable"] = True
        result["version_response"] = value
        result["openwebui_version"] = version
        return result
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"[:3000]
        return result
    finally:
        result["elapsed_ms"] = int((time.monotonic() - started) * 1000)


def http_openwebui_version(url: str, timeout: float = 1.2) -> dict[str, Any] | None:
    probe = http_openwebui_probe(url, timeout=timeout)
    value = probe.get("version_response")
    return value if probe.get("reachable") and isinstance(value, dict) else None


def parse_desktop_config_roots(explicit: str = "") -> list[Path]:
    # An explicitly supplied root identifies one standalone Desktop instance and
    # must not be mixed with stale logs from other per-user installations.
    if explicit:
        return [Path(explicit).expanduser()]
    roots: list[Path] = []
    appdata = os.getenv("APPDATA")
    if appdata:
        parent = Path(appdata)
        for name in ("Open WebUI", "open-webui", "open-webui-desktop", "OpenWebUI", "com.openwebui.desktop"):
            roots.append(parent / name)
    result: list[Path] = []
    seen: set[str] = set()
    for path in roots:
        key = os.path.normcase(os.path.abspath(os.fspath(path)))
        if key not in seen:
            seen.add(key)
            result.append(path)
    return result


def desktop_config_entries(explicit_root: str = "") -> list[tuple[dict[str, Any], Path]]:
    entries: list[tuple[dict[str, Any], Path]] = []
    for root in parse_desktop_config_roots(explicit_root):
        path = root / "config.json"
        if not path.is_file():
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception:
            continue
        if isinstance(value, dict):
            entries.append((value, root))
    return entries


def desktop_config(explicit_root: str = "") -> tuple[dict[str, Any], Path | None]:
    entries = desktop_config_entries(explicit_root)
    return entries[0] if entries else ({}, None)


def discover_log_urls(root: Path | None) -> list[str]:
    if root is None:
        return []
    candidates: list[tuple[float, int, str]] = []
    patterns = [
        re.compile(r"Server started(?: with PID:.*?, URL:|:)\s*(https?://[^\s]+)", re.I),
        re.compile(r"SERVER_URL\s*[=:]\s*['\"]?(https?://[^\s'\"]+)", re.I),
        re.compile(r"Uvicorn running on\s*(https?://[^\s]+)", re.I),
    ]
    for log_dir in (root / "logs", root):
        if not log_dir.exists():
            continue
        for path in list(log_dir.glob("main*.log")) + list(log_dir.glob("server*.log")):
            try:
                mtime = path.stat().st_mtime
                text = strip_ansi(path.read_text(encoding="utf-8", errors="replace"))
            except Exception:
                continue
            for pattern in patterns:
                for match in pattern.finditer(text):
                    try:
                        url = normalize_base_url(match.group(1).rstrip(".,;)"))
                        candidates.append((mtime, match.start(), url))
                    except Exception:
                        pass
    candidates.sort(reverse=True)
    result: list[str] = []
    for _, _, url in candidates:
        if url not in result:
            result.append(url)
    return result


def server_runtime_url(runtime_path: str = "") -> str:
    paths = [Path(runtime_path)] if runtime_path else []
    programdata = os.getenv("ProgramData", r"C:\ProgramData")
    paths.append(Path(programdata) / "EInfra-OpenWebUI" / "config" / "runtime.json")
    for path in paths:
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception:
            continue
        for key in ("BackendUrl", "BackendURL", "LocalBackendUrl"):
            if data.get(key):
                return normalize_base_url(str(data[key]))
        host = data.get("BackendHost", "127.0.0.1")
        port = data.get("BackendPort")
        if port:
            return f"http://{host}:{int(port)}"
    return ""


def _windows_listening_loopback_ports() -> list[int]:
    if os.name != "nt":
        return []
    try:
        proc = subprocess.run(
            ["netstat", "-ano", "-p", "tcp"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=20,
            check=False,
        )
        text = proc.stdout.decode("utf-8", errors="replace")
    except Exception:
        return []
    ports: set[int] = set()
    for line in text.splitlines():
        if "LISTENING" not in line.upper():
            continue
        fields = line.split()
        if len(fields) < 4 or fields[0].upper() != "TCP":
            continue
        local = fields[1]
        match = re.search(r"(?:\[([^\]]+)\]|([^:]+)):(\d+)$", local)
        if not match:
            continue
        host = (match.group(1) or match.group(2) or "").casefold()
        if host not in {"127.0.0.1", "0.0.0.0", "::", "::1"}:
            continue
        port = int(match.group(3))
        if 1 <= port <= 65535:
            ports.add(port)
    return sorted(ports)


def _desktop_config_summary(config: dict[str, Any], root: Path) -> dict[str, Any]:
    local = config.get("localServer") if isinstance(config.get("localServer"), dict) else {}
    return {
        "root": str(root),
        "defaultConnectionId": config.get("defaultConnectionId"),
        "installDir": config.get("installDir"),
        "dataDir": config.get("dataDir"),
        "localServer": local,
    }


def build_backend_candidates(
    args: argparse.Namespace,
    report: dict[str, Any],
    *,
    scan_port_range: bool = False,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(url: str, source: str, score: int) -> None:
        if not url:
            return
        try:
            normalized = normalize_base_url(url)
        except Exception:
            return
        if normalized in seen:
            return
        seen.add(normalized)
        candidates.append({"url": normalized, "source": source, "score": int(score)})

    add(args.base_url, "explicit BaseUrl", 2000)
    if args.target.lower() == "server":
        add(server_runtime_url(args.server_runtime_config), "server runtime.json", 1900)
        add("http://127.0.0.1:18080", "server default", 100)
    else:
        entries = desktop_config_entries(args.desktop_config_root)
        report["desktop_config_roots"] = [_desktop_config_summary(config, root) for config, root in entries]
        desired_ports: list[int] = []
        for index, (config, config_root) in enumerate(entries):
            for url in discover_log_urls(config_root)[:BACKEND_MAX_LOG_URLS_PER_ROOT]:
                add(url, f"Desktop runtime log ({config_root})", 1800 - index)
            local = config.get("localServer") if isinstance(config.get("localServer"), dict) else {}
            try:
                desired = int(local.get("port") or 8080)
            except (TypeError, ValueError):
                desired = 8080
            if 1 <= desired <= 65535 and desired not in desired_ports:
                desired_ports.append(desired)
        if not desired_ports:
            desired_ports.append(8080)

        listening = _windows_listening_loopback_ports()
        report["desktop_listening_loopback_ports"] = listening
        range_ports: set[int] = set()
        for desired in desired_ports:
            add(f"http://127.0.0.1:{desired}", "Desktop configured port", 1700)
            upper = min(desired + 100, 65535)
            range_ports.update(range(desired, upper + 1))
            for port in listening:
                if desired <= port <= upper:
                    add(
                        f"http://127.0.0.1:{port}",
                        "live loopback listener in Desktop port range",
                        1650 - (port - desired),
                    )

        scan_record: dict[str, Any] = {
            "enabled": bool(scan_port_range and not args.only_base_url),
            "ports_considered": len(range_ports),
            "open_ports": [],
            "elapsed_ms": 0,
        }
        if scan_record["enabled"]:
            scan_started = time.monotonic()
            open_ports = _scan_open_loopback_ports(range_ports)
            scan_record["open_ports"] = open_ports
            scan_record["elapsed_ms"] = int((time.monotonic() - scan_started) * 1000)
            for port in open_ports:
                distance = min(abs(port - desired) for desired in desired_ports)
                add(
                    f"http://127.0.0.1:{port}",
                    "bounded concurrent Desktop port-range scan",
                    1500 - distance,
                )
        report["desktop_port_range_scan"] = scan_record
        add("http://127.0.0.1:8080", "Desktop default", 800)

    if args.only_base_url:
        candidates = [item for item in candidates if item["source"] == "explicit BaseUrl"]
    candidates.sort(key=lambda item: item["score"], reverse=True)
    if len(candidates) > BACKEND_MAX_CANDIDATES_PER_PASS:
        report["backend_candidates_truncated"] = {
            "original_count": len(candidates),
            "kept_count": BACKEND_MAX_CANDIDATES_PER_PASS,
        }
        candidates = candidates[:BACKEND_MAX_CANDIDATES_PER_PASS]
    return candidates


def discover_backend(
    args: argparse.Namespace,
    report: dict[str, Any],
    *,
    probe_timeout: float = 2.5,
    scan_port_range: bool = False,
) -> str:
    candidates = build_backend_candidates(args, report, scan_port_range=scan_port_range)
    probes: list[dict[str, Any]] = []
    for item in candidates:
        probe = {**item, **http_openwebui_probe(item["url"], timeout=probe_timeout)}
        probes.append(probe)
        if probe.get("reachable"):
            report["backend_candidates"] = probes
            return str(item["url"])
    report["backend_candidates"] = probes
    preview = "; ".join(
        f"{item.get('url')} ({item.get('error') or 'unreachable'})"
        for item in probes[:8]
    )
    raise TutorInstallError(
        "Nebyl nalezen dostupný Open WebUI backend."
        + (f" Ověřené kandidáty: {preview}" if preview else "")
    )

def _desktop_default_connection_is_local(args: argparse.Namespace) -> tuple[bool, list[dict[str, Any]]]:
    entries = desktop_config_entries(args.desktop_config_root)
    summaries = [_desktop_config_summary(config, root) for config, root in entries]
    if not entries:
        return True, summaries
    values = [str(config.get("defaultConnectionId") or "local").casefold() for config, _ in entries]
    return any(value in {"", "local"} for value in values), summaries


def wait_for_backend(
    args: argparse.Namespace,
    report: dict[str, Any],
    *,
    auto_start_desktop: bool,
    operation: str,
) -> str:
    started = time.monotonic()
    startup_window = max(1.0, float(args.startup_timeout))
    can_launch = (
        args.target == "Desktop"
        and auto_start_desktop
        and not args.no_auto_start_desktop
    )
    # When auto-start is possible, StartupTimeout is measured from the launch
    # attempt, not consumed by a pre-launch discovery pass.
    deadline = None if can_launch else started + startup_window
    launch_attempted = False
    launch_started_at: float | None = None
    launch_error = ""
    attempts: list[dict[str, Any]] = []
    last_error = ""
    probe_pass = 0
    post_launch_probe_performed = False

    while True:
        probe_pass += 1
        phase = "post-launch" if launch_attempted else "pre-launch"
        if launch_attempted:
            post_launch_probe_performed = True
        try:
            url = discover_backend(
                args,
                report,
                probe_timeout=min(max(float(args.http_timeout), 1.0), 4.0),
                scan_port_range=launch_attempted,
            )
            report["backend_wait"] = {
                "operation": operation,
                "elapsed_seconds": round(time.monotonic() - started, 3),
                "auto_start_desktop": bool(auto_start_desktop),
                "launch_attempted": launch_attempted,
                "launch_elapsed_seconds": (
                    round(time.monotonic() - launch_started_at, 3)
                    if launch_started_at is not None else None
                ),
                "launch_error": launch_error or None,
                "probe_passes": probe_pass,
                "post_launch_probe_performed": post_launch_probe_performed,
                "success": True,
            }
            return url
        except TutorInstallError as exc:
            last_error = str(exc)
            attempts.append({
                "at": now_iso(),
                "phase": phase,
                "probe_pass": probe_pass,
                "error": last_error,
                "candidates": list(report.get("backend_candidates") or [])[:20],
                "range_scan": dict(report.get("desktop_port_range_scan") or {}),
            })

        if can_launch and not launch_attempted:
            launch_attempted = True
            local_default, configs = _desktop_default_connection_is_local(args)
            report["desktop_config_before_autostart"] = configs
            report["desktop_default_connection_is_local"] = bool(local_default)
            if not local_default:
                launch_error = (
                    "Open WebUI Desktop má jako výchozí zvolenu vzdálenou connection; "
                    "lokální backend se nemusí automaticky spustit."
                )
            try:
                start_desktop(args, report)
                print(
                    "[INFO] Lokální backend nebyl dostupný; spustil jsem standalone Open WebUI Desktop "
                    "a čekám na dokončení jeho startupu.",
                    flush=True,
                )
            except TutorInstallError as exc:
                launch_error = str(exc)
                report["desktop_autostart_error"] = launch_error
            launch_started_at = time.monotonic()
            deadline = launch_started_at + startup_window
            # Always perform at least one post-launch probe. The old code checked
            # the already-expired pre-launch deadline here and could fail without
            # ever probing the backend that had just been started.
            continue

        if deadline is None:
            deadline = time.monotonic() + startup_window
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(BACKEND_POLL_INTERVAL_SECONDS, max(0.01, remaining)))

    report["backend_wait"] = {
        "operation": operation,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "auto_start_desktop": bool(auto_start_desktop),
        "launch_attempted": launch_attempted,
        "launch_elapsed_seconds": (
            round(time.monotonic() - launch_started_at, 3)
            if launch_started_at is not None else None
        ),
        "launch_error": launch_error or None,
        "probe_passes": probe_pass,
        "post_launch_probe_performed": post_launch_probe_performed,
        "success": False,
        "attempts": attempts[-12:],
    }
    if args.target == "Desktop":
        try:
            desktop_state = resolve_desktop(args, report)
            config_root = desktop_state.get("config_root")
            report["desktop_startup_log_tails"] = collect_desktop_log_tails(
                config_root if isinstance(config_root, Path) else None
            )
        except Exception as exc:
            report["desktop_resolution_error"] = f"{type(exc).__name__}: {exc}"

    detail = (
        f" Po {round(time.monotonic() - started, 1)} s nebyl nalezen žádný backend, "
        f"který by vracel platný JSON z /api/version."
    )
    if launch_attempted:
        detail += " Pokus o spuštění Desktopu byl proveden a následovalo alespoň jedno nové ověření."
    if launch_error:
        detail += f" Chyba spuštění: {launch_error}"
    detail += f" Poslední diagnostika: {last_error}"
    raise TutorInstallError("Nebyl nalezen dostupný Open WebUI backend." + detail)

def ensure_backend(args: argparse.Namespace, report: dict[str, Any], *, operation: str) -> str:
    """Resolve a live backend; Desktop TutorOnly and Verify may start the official Electron app."""
    if args.target == "Desktop" and args.mode in {"TutorOnly", "Verify"}:
        return wait_for_backend(
            args,
            report,
            auto_start_desktop=not args.no_auto_start_desktop,
            operation=operation,
        )
    return discover_backend(args, report, probe_timeout=min(max(float(args.http_timeout), 1.0), 4.0), scan_port_range=False)


def _desktop_executable_candidates(explicit: str = "") -> list[Path]:
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit).expanduser())
    localapp = os.getenv("LOCALAPPDATA")
    if localapp:
        programs = Path(localapp) / "Programs"
        directories = (
            programs / "open-webui",
            programs / "Open WebUI",
            programs / "open-webui-desktop",
        )
        names = ("open-webui.exe", "Open WebUI.exe", "OpenWebUI.exe")
        for directory in directories:
            for name in names:
                candidates.append(directory / name)
            if directory.is_dir():
                try:
                    for path in directory.glob("*.exe"):
                        if "open" in path.name.casefold() and "webui" in path.name.casefold().replace(" ", ""):
                            candidates.append(path)
                except OSError:
                    pass
    result: list[Path] = []
    seen: set[str] = set()
    for path in candidates:
        try:
            key = os.path.normcase(os.path.abspath(os.fspath(path)))
        except Exception:
            continue
        if key not in seen:
            seen.add(key)
            result.append(path)
    return result


def resolve_desktop(args: argparse.Namespace, report: dict[str, Any]) -> dict[str, Any]:
    root = Path(args.desktop_install_root).expanduser() if args.desktop_install_root else None
    config, config_root = desktop_config(args.desktop_config_root)
    if root is None and config.get("installDir"):
        root = Path(str(config["installDir"]))
    if root is None:
        raise TutorInstallError("DesktopInstallRoot nebyl zadán ani nalezen v Desktop config.json.")
    root = root.resolve()
    bundled_python = root / "python" / ("python.exe" if os.name == "nt" else "bin/python")
    if args.desktop_data_root:
        data_root = Path(args.desktop_data_root).expanduser().resolve()
    elif config.get("dataDir"):
        data_root = Path(str(config["dataDir"])).expanduser().resolve()
    else:
        data_root = root / "data"
    db = data_root / "webui.db"

    exe_candidates = _desktop_executable_candidates(args.desktop_executable)
    executable = find_first_existing(exe_candidates)
    local_server = config.get("localServer") if isinstance(config.get("localServer"), dict) else {}
    env_vars = config.get("envVars") if isinstance(config.get("envVars"), dict) else {}
    database_overrides = {
        str(k): str(v)
        for k, v in env_vars.items()
        if str(k).upper() in DATABASE_OVERRIDE_KEYS and str(v).strip()
    }
    result: dict[str, Any] = {
        "root": root,
        "bundled_python": bundled_python,
        "data_root": data_root,
        "database": db,
        "executable": executable,
        "executable_candidates": exe_candidates,
        "config_root": config_root,
        "default_connection_id": str(config.get("defaultConnectionId") or ""),
        "local_server": local_server,
        "config_env_vars": {str(k): str(v) for k, v in env_vars.items()},
        "database_overrides": database_overrides,
    }
    report["desktop"] = {
        "root": str(root),
        "bundled_python": str(bundled_python),
        "data_root": str(data_root),
        "database": str(db),
        "executable": str(executable) if executable else None,
        "executable_candidates": [str(item) for item in exe_candidates],
        "config_root": str(config_root) if config_root else None,
        "default_connection_id": result["default_connection_id"],
        "local_server": local_server,
        "database_overrides": sorted(database_overrides),
    }
    return result


def sqlite_status(db: Path) -> dict[str, Any]:
    if not db.is_file():
        return {"exists": False, "path": str(db)}
    stat = db.stat()
    result: dict[str, Any] = {
        "exists": True,
        "path": str(db.resolve()),
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
    }
    connection = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True, timeout=10)
    try:
        result["integrity_check"] = [row[0] for row in connection.execute("PRAGMA integrity_check").fetchall()]
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        result["tables"] = sorted(tables)
        result["chat_present"] = "chat" in tables
        if "chat" in tables:
            columns = [row[1] for row in connection.execute("PRAGMA table_info(chat)")]
            result["chat_columns"] = columns
            result["chat_timer_at_present"] = "timer_at" in columns
        else:
            result["chat_columns"] = []
            result["chat_timer_at_present"] = False
        indexes = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='index'")}
        result["indexes"] = sorted(indexes)
        result["required_timer_indexes_missing"] = sorted(REQUIRED_TIMER_INDEXES - indexes)
        try:
            rows = connection.execute("SELECT version_num FROM alembic_version ORDER BY version_num").fetchall()
            result["alembic_versions"] = [str(row[0]) for row in rows]
            result["alembic_version"] = result["alembic_versions"][0] if len(result["alembic_versions"]) == 1 else None
        except sqlite3.Error:
            result["alembic_versions"] = []
            result["alembic_version"] = None
        result["journal_mode"] = connection.execute("PRAGMA journal_mode").fetchone()[0]
    finally:
        connection.close()
    return result

def _windows_path_key(value: Any) -> str:
    """Normalize a Windows path without depending on the host platform."""
    raw = str(value or "").strip().strip('"').replace("/", "\\")
    if not raw:
        return ""
    return ntpath.normcase(ntpath.normpath(raw)).rstrip("\\")


def _windows_path_is_within(candidate: Any, root: Any) -> bool:
    candidate_key = _windows_path_key(candidate)
    root_key = _windows_path_key(root)
    return bool(candidate_key and root_key and (candidate_key == root_key or candidate_key.startswith(root_key + "\\")))


def _command_executable(command_line: Any) -> str:
    """Return only argv[0] from a Windows command line; never match arbitrary arguments."""
    value = str(command_line or "").lstrip()
    if not value:
        return ""
    if value.startswith('"'):
        end = value.find('"', 1)
        token = value[1:end] if end > 1 else value[1:]
    else:
        token = value.split(None, 1)[0]
    return _windows_path_key(token)


def _record_value(record: dict[str, Any], *names: str) -> Any:
    lowered = {str(key).lower(): value for key, value in record.items()}
    for name in names:
        if name.lower() in lowered:
            return lowered[name.lower()]
    return None


def _record_pid(record: dict[str, Any], *names: str) -> int:
    value = _record_value(record, *names)
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _normalize_process_inventory(records: Iterable[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    normalized: dict[int, dict[str, Any]] = {}
    for source in records:
        if not isinstance(source, dict):
            continue
        pid = _record_pid(source, "ProcessId", "pid")
        if pid <= 0:
            continue
        ppid = _record_pid(source, "ParentProcessId", "ppid")
        executable = _windows_path_key(_record_value(source, "ExecutablePath", "executable", "path"))
        if not executable:
            executable = _command_executable(_record_value(source, "CommandLine", "command_line"))
        normalized[pid] = {
            "pid": pid,
            "ppid": ppid,
            "name": str(_record_value(source, "Name", "name") or ""),
            "executable": executable,
            "command_line": str(_record_value(source, "CommandLine", "command_line") or ""),
        }
    return normalized


def _ancestor_process_ids(inventory: dict[int, dict[str, Any]], starting: Iterable[int]) -> set[int]:
    protected = {int(pid) for pid in starting if int(pid) > 0}
    pending = list(protected)
    while pending:
        pid = pending.pop()
        parent = int(inventory.get(pid, {}).get("ppid") or 0)
        if parent > 0 and parent not in protected:
            protected.add(parent)
            pending.append(parent)
    return protected


def select_desktop_process_targets(
    records: Iterable[dict[str, Any]],
    desktop_root: Path | str,
    desktop_executable: Path | str | None = None,
    protected_pids: Iterable[int] = (),
) -> dict[str, Any]:
    """Create a kill plan using executable ownership, never a root substring in arguments.

    The old implementation matched CommandLine.Contains(desktop_root). Because the
    manager itself receives ``--desktop-install-root D:\\web-ui``, that predicate
    selected and force-killed the manager. This selector only considers argv[0] or
    ExecutablePath and explicitly protects the manager and all of its ancestors.
    """
    inventory = _normalize_process_inventory(records)
    protected = _ancestor_process_ids(inventory, protected_pids)
    root_key = _windows_path_key(desktop_root)
    desktop_exe_key = _windows_path_key(desktop_executable)
    seeds: dict[int, str] = {}
    for pid, item in inventory.items():
        if pid in protected:
            continue
        executable = str(item.get("executable") or "")
        if executable and _windows_path_is_within(executable, root_key):
            seeds[pid] = "executable-under-desktop-root"
        elif desktop_exe_key and executable == desktop_exe_key:
            seeds[pid] = "configured-desktop-electron"
        elif executable.endswith("\\programs\\open-webui\\open-webui.exe"):
            seeds[pid] = "official-desktop-electron"

    targets = dict(seeds)
    changed = True
    while changed:
        changed = False
        for pid, item in inventory.items():
            if pid in protected or pid in targets:
                continue
            parent = int(item.get("ppid") or 0)
            if parent in targets:
                targets[pid] = f"descendant-of-{parent}"
                changed = True

    def depth(pid: int) -> int:
        value = 0
        seen: set[int] = set()
        current = pid
        while current in targets and current not in seen:
            seen.add(current)
            parent = int(inventory.get(current, {}).get("ppid") or 0)
            if parent not in targets:
                break
            value += 1
            current = parent
        return value

    selected: list[dict[str, Any]] = []
    for pid in sorted(targets, key=lambda value: (depth(value), value), reverse=True):
        item = inventory[pid]
        selected.append({
            "pid": pid,
            "ppid": item.get("ppid"),
            "name": item.get("name"),
            "executable": item.get("executable"),
            "reason": targets[pid],
            "depth": depth(pid),
        })
    return {
        "desktop_root": root_key,
        "desktop_executable": desktop_exe_key or None,
        "protected_pids": sorted(protected),
        "selected": selected,
    }


def query_windows_process_inventory() -> list[dict[str, Any]]:
    if os.name != "nt":
        return []
    script = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
Get-CimInstance Win32_Process |
    Select-Object ProcessId, ParentProcessId, Name, ExecutablePath, CommandLine |
    ConvertTo-Json -Compress -Depth 3
"""
    proc = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=60,
    )
    stdout = proc.stdout.decode("utf-8-sig", errors="replace")
    stderr = proc.stderr.decode("utf-8-sig", errors="replace")
    if proc.returncode != 0:
        raise TutorInstallError(f"Nelze načíst Windows process inventory: {stderr or stdout}")
    text = stdout.strip()
    if not text:
        return []
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise TutorInstallError(f"Windows process inventory není platný JSON: {text[-2000:]}") from exc
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    raise TutorInstallError("Windows process inventory má nepodporovaný tvar.")


def _safe_stop_selection_self_test() -> dict[str, Any]:
    root = r"D:\web-ui"
    desktop_exe = r"C:\Users\petr\AppData\Local\Programs\open-webui\open-webui.exe"
    records = [
        {"ProcessId": 100, "ParentProcessId": 90, "Name": "python.exe", "ExecutablePath": r"D:\Anaconda\envs\ai_services\python.exe", "CommandLine": r'"D:\Anaconda\envs\ai_services\python.exe" manager.py --desktop-install-root D:\web-ui'},
        {"ProcessId": 90, "ParentProcessId": 80, "Name": "powershell.exe", "ExecutablePath": r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe", "CommandLine": r"powershell.exe repair.ps1 -DesktopInstallRoot D:\web-ui"},
        {"ProcessId": 80, "ParentProcessId": 0, "Name": "explorer.exe", "ExecutablePath": r"C:\Windows\explorer.exe", "CommandLine": r"C:\Windows\explorer.exe"},
        {"ProcessId": 110, "ParentProcessId": 100, "Name": "powershell.exe", "ExecutablePath": r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe", "CommandLine": r"powershell.exe -Command $root='D:\web-ui'"},
        {"ProcessId": 200, "ParentProcessId": 300, "Name": "python.exe", "ExecutablePath": r"D:\web-ui\python\python.exe", "CommandLine": r'"D:\web-ui\python\python.exe" -m uv run open-webui serve'},
        {"ProcessId": 201, "ParentProcessId": 200, "Name": "open-webui.exe", "ExecutablePath": r"D:\web-ui\python\Scripts\open-webui.exe", "CommandLine": r'"D:\web-ui\python\Scripts\open-webui.exe" serve'},
        {"ProcessId": 300, "ParentProcessId": 80, "Name": "open-webui.exe", "ExecutablePath": desktop_exe, "CommandLine": f'"{desktop_exe}"'},
        {"ProcessId": 400, "ParentProcessId": 80, "Name": "python.exe", "ExecutablePath": r"D:\OtherPython\python.exe", "CommandLine": r'"D:\OtherPython\python.exe" unrelated.py --path D:\web-ui'},
        {"ProcessId": 500, "ParentProcessId": 80, "Name": "open-webui.exe", "ExecutablePath": r"C:\ProgramData\EInfra-OpenWebUI\venv\Scripts\open-webui.exe", "CommandLine": r"open-webui.exe serve --port 18080"},
    ]
    plan = select_desktop_process_targets(records, root, desktop_exe, protected_pids={100})
    selected = {int(item["pid"]) for item in plan["selected"]}
    expected = {200, 201, 300}
    forbidden = {80, 90, 100, 110, 400, 500}
    if selected != expected or selected.intersection(forbidden):
        raise AssertionError(f"safe stop selector: selected={sorted(selected)}, expected={sorted(expected)}")
    return {"ok": True, "selected_pids": sorted(selected), "protected_pids": plan["protected_pids"]}


def stop_desktop_processes(root: Path, desktop_executable: Path | None = None) -> dict[str, Any]:
    if os.name != "nt":
        return {"platform": os.name, "selected": [], "terminated": [], "remaining": []}
    inventory = query_windows_process_inventory()
    normalized = _normalize_process_inventory(inventory)
    protected = _ancestor_process_ids(normalized, {os.getpid(), os.getppid()})
    plan = select_desktop_process_targets(
        inventory,
        root,
        desktop_executable,
        protected_pids=protected,
    )
    terminated: list[dict[str, Any]] = []
    for item in plan["selected"]:
        pid = int(item["pid"])
        proc = subprocess.run(
            ["taskkill.exe", "/PID", str(pid), "/F"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
        )
        stdout = proc.stdout.decode("utf-8", errors="replace").strip()
        stderr = proc.stderr.decode("utf-8", errors="replace").strip()
        terminated.append({**item, "returncode": proc.returncode, "stdout": stdout[-1000:], "stderr": stderr[-1000:]})

    deadline = time.monotonic() + 12.0
    remaining: set[int] = {int(item["pid"]) for item in plan["selected"]}
    while remaining and time.monotonic() < deadline:
        time.sleep(0.25)
        current = _normalize_process_inventory(query_windows_process_inventory())
        remaining.intersection_update(current)
    result = {**plan, "terminated": terminated, "remaining": sorted(remaining)}
    if remaining:
        raise TutorInstallError(
            "Některé procesy standalone Desktopu se nepodařilo ukončit: "
            + ", ".join(str(pid) for pid in sorted(remaining))
        )
    return result


def backup_sqlite(db: Path, data_root: Path) -> Path:
    backup_dir = data_root / "backups" / ("vut-tutor-recovery-" + time.strftime("%Y%m%d-%H%M%S"))
    backup_dir.mkdir(parents=True, exist_ok=False)
    target = backup_dir / db.name
    src = sqlite3.connect(str(db), timeout=30)
    dst = sqlite3.connect(str(target), timeout=30)
    try:
        src.backup(dst)
    finally:
        dst.close(); src.close()
    for suffix in ("-wal", "-shm"):
        side = Path(str(db) + suffix)
        if side.exists():
            shutil.copy2(side, backup_dir / side.name)
    return target


def bundled_env(data_root: Path, db: Path, config_env_vars: dict[str, str] | None = None) -> dict[str, str]:
    # Start from the caller environment, but remove database selectors inherited
    # from Anaconda/PowerShell.  The migration must target exactly the same SQLite
    # file that standalone Desktop derives from DATA_DIR.
    env = os.environ.copy()
    for key in set(DATABASE_OVERRIDE_KEYS) | {"DATA_DIR", "ENABLE_DB_MIGRATIONS"}:
        env.pop(key, None)
    for key, value in (config_env_vars or {}).items():
        if str(key).upper() not in DATABASE_OVERRIDE_KEYS and str(key).upper() != "DATA_DIR":
            env[str(key)] = str(value)
    env["DATA_DIR"] = str(data_root.resolve())
    env["DATABASE_URL"] = "sqlite:///" + db.resolve().as_posix()
    # Never invoke the buggy import-time migration runner from Open WebUI 0.11.2.
    env["ENABLE_DB_MIGRATIONS"] = "False"
    for candidate in (data_root / ".key", data_root / ".webui_secret_key", data_root.parent / ".webui_secret_key"):
        if candidate.is_file():
            secret = candidate.read_text(encoding="utf-8", errors="ignore").strip()
            if secret:
                env["WEBUI_SECRET_KEY"] = secret
                break
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUNBUFFERED"] = "1"
    return env

def run_checked(command: list[str], *, env: dict[str, str], timeout: int, label: str) -> dict[str, Any]:
    started = time.monotonic()
    try:
        proc = subprocess.run(
            command,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        record = {
            "label": label,
            "command": command,
            "returncode": None,
            "timed_out": True,
            "duration_seconds": round(time.monotonic() - started, 3),
            "stdout": str(exc.stdout or "")[-12000:],
            "stderr": str(exc.stderr or "")[-12000:],
        }
        error = TutorInstallError(f"{label} překročilo timeout {timeout} s.")
        setattr(error, "command_record", record)
        raise error from exc
    record = {
        "label": label,
        "command": command,
        "returncode": proc.returncode,
        "timed_out": False,
        "duration_seconds": round(time.monotonic() - started, 3),
        "stdout": proc.stdout[-12000:],
        "stderr": proc.stderr[-12000:],
    }
    if proc.returncode != 0:
        error = TutorInstallError(
            f"{label} selhalo kódem {proc.returncode}:\n{proc.stdout[-4000:]}\n{proc.stderr[-4000:]}"
        )
        setattr(error, "command_record", record)
        raise error
    return record

def inspect_bundled_openwebui(bundled_python: Path, env: dict[str, str], timeout: int = 60) -> tuple[dict[str, Any], dict[str, Any]]:
    code = r"""
import importlib.metadata as md
import importlib.util as iu
import json
from pathlib import Path
result = {"distribution_version": None, "package_root": None, "alembic_ini": None, "migrations_dir": None}
try:
    result["distribution_version"] = md.version("open-webui")
except Exception as exc:
    result["metadata_error"] = f"{type(exc).__name__}: {exc}"
spec = iu.find_spec("open_webui")
if spec and spec.submodule_search_locations:
    root = Path(next(iter(spec.submodule_search_locations))).resolve()
    result["package_root"] = str(root)
    result["alembic_ini"] = str(root / "alembic.ini")
    result["migrations_dir"] = str(root / "migrations")
print("VUT_PACKAGE_INFO=" + json.dumps(result, ensure_ascii=True))
"""
    record = run_checked([str(bundled_python), "-c", code], env=env, timeout=timeout, label="Kontrola Desktop Open WebUI balíčku bez importu config.py")
    marker = next((line[len("VUT_PACKAGE_INFO="):] for line in record["stdout"].splitlines() if line.startswith("VUT_PACKAGE_INFO=")), None)
    if marker is None:
        raise TutorInstallError("Kontrola balíčku nevrátila VUT_PACKAGE_INFO marker.")
    try:
        info = json.loads(marker)
    except json.JSONDecodeError as exc:
        raise TutorInstallError(f"Neplatný VUT_PACKAGE_INFO JSON: {exc}") from exc
    if not info.get("package_root") or not Path(info["migrations_dir"]).is_dir() or not Path(info["alembic_ini"]).is_file():
        raise TutorInstallError(f"Desktop Open WebUI balíček neobsahuje použitelnou Alembic konfiguraci: {info}")
    return info, record


def direct_alembic_upgrade(bundled_python: Path, env: dict[str, str], timeout: int) -> tuple[dict[str, Any], dict[str, Any]]:
    # Open WebUI 0.11.2 imports utils.automations while Alembic imports the
    # calendar model.  The temporary module below supplies only the validator
    # symbol needed to construct model metadata and prevents the circular import.
    # No package file is modified.
    code = r"""
import json
import os
import sys
import types
from pathlib import Path
from importlib.util import find_spec
os.environ["ENABLE_DB_MIGRATIONS"] = "False"
shim = types.ModuleType("open_webui.utils.automations")
def rrule_interval_seconds(value):
    raise RuntimeError("rrule_interval_seconds migration shim must not be executed")
shim.rrule_interval_seconds = rrule_interval_seconds
sys.modules["open_webui.utils.automations"] = shim
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
spec = find_spec("open_webui")
if not spec or not spec.submodule_search_locations:
    raise RuntimeError("open_webui package root not found")
root = Path(next(iter(spec.submodule_search_locations))).resolve()
ini = root / "alembic.ini"
migrations = root / "migrations"
if not ini.is_file() or not migrations.is_dir():
    raise RuntimeError(f"Alembic files missing: ini={ini} migrations={migrations}")
cfg = Config(str(ini))
cfg.set_main_option("script_location", str(migrations))
script = ScriptDirectory.from_config(cfg)
heads = list(script.get_heads())
target = "heads" if len(heads) > 1 else "head"
command.upgrade(cfg, target)
print("VUT_ALEMBIC_RESULT=" + json.dumps({"heads": heads, "target": target, "package_root": str(root)}, ensure_ascii=True))
"""
    record = run_checked([str(bundled_python), "-c", code], env=env, timeout=timeout, label="Přímá Open WebUI Alembic migrace s izolovaným 0.11.2 import shimem")
    marker = next((line[len("VUT_ALEMBIC_RESULT="):] for line in record["stdout"].splitlines() if line.startswith("VUT_ALEMBIC_RESULT=")), None)
    if marker is None:
        raise TutorInstallError("Alembic proces skončil bez potvrzovacího VUT_ALEMBIC_RESULT markeru.")
    try:
        result = json.loads(marker)
    except json.JSONDecodeError as exc:
        raise TutorInstallError(f"Neplatný VUT_ALEMBIC_RESULT JSON: {exc}") from exc
    heads = result.get("heads")
    if not isinstance(heads, list) or not heads:
        raise TutorInstallError(f"Alembic neoznámil žádný head: {result}")
    return result, record


def reinstall_openwebui_package(bundled_python: Path, env: dict[str, str], timeout: int) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    uv_command = [
        str(bundled_python), "-m", "uv", "pip", "install", "--python", str(bundled_python),
        "--reinstall", "--no-cache", f"open-webui=={MIN_DESKTOP_OPENWEBUI_VERSION}", "platformdirs",
    ]
    try:
        records.append(run_checked(uv_command, env=env, timeout=timeout, label="Oprava Desktop Open WebUI balíčku přes uv"))
        return records
    except TutorInstallError as exc:
        record = getattr(exc, "command_record", None)
        if record:
            records.append(record)
    pip_command = [
        str(bundled_python), "-m", "pip", "install", "--force-reinstall", "--no-cache-dir",
        f"open-webui=={MIN_DESKTOP_OPENWEBUI_VERSION}", "platformdirs",
    ]
    records.append(run_checked(pip_command, env=env, timeout=timeout, label="Oprava Desktop Open WebUI balíčku přes pip"))
    return records


def validate_database_after_migration(status: dict[str, Any], alembic_result: dict[str, Any]) -> None:
    if status.get("integrity_check") != ["ok"]:
        raise TutorInstallError(f"SQLite integrity_check po migraci není 'ok': {status.get('integrity_check')}")
    if not status.get("chat_timer_at_present"):
        raise TutorInstallError(f"Alembic skončil, ale cílová databáze stále nemá chat.timer_at: {status}")
    missing_indexes = status.get("required_timer_indexes_missing") or []
    if missing_indexes:
        raise TutorInstallError("Alembic skončil, ale chybí indexy migrace timer_at: " + ", ".join(missing_indexes))
    expected = {str(item) for item in alembic_result.get("heads", [])}
    actual = {str(item) for item in status.get("alembic_versions", [])}
    if expected and actual != expected:
        raise TutorInstallError(f"Alembic revision databáze nesouhlasí s package heads: actual={sorted(actual)} expected={sorted(expected)}")


def restore_sqlite_backup(db: Path, backup: Path) -> None:
    for suffix in ("", "-wal", "-shm"):
        target = Path(str(db) + suffix)
        try:
            target.unlink(missing_ok=True)
        except Exception:
            pass
    shutil.copy2(backup, db)


def collect_desktop_log_tails(config_root: Path | None, max_chars: int = 12000) -> dict[str, str]:
    result: dict[str, str] = {}
    if config_root is None:
        return result
    candidates: list[Path] = []
    for log_dir in (config_root / "logs", config_root):
        if log_dir.is_dir():
            candidates.extend(log_dir.glob("main*.log"))
            candidates.extend(log_dir.glob("server*.log"))
    for path in sorted({item.resolve() for item in candidates if item.is_file()}, key=lambda item: item.stat().st_mtime, reverse=True)[:4]:
        try:
            result[str(path)] = strip_ansi(path.read_text(encoding="utf-8", errors="replace"))[-max_chars:]
        except Exception as exc:
            result[str(path)] = f"<read failed: {type(exc).__name__}: {exc}>"
    return result



TUTOR_RECOVERY_IDS = (
    "study_tutor_gateway_bootstrap",
    "study_tutor_canvas_bootstrap",
    "study_tutor_bootstrap",
    "vut_ai_tutor_bootstrap",
    "study_tutor_pipe",
    "vut_ai_tutor_pipe",
    "study_tutor_pipe_managed",
)


def recover_desktop_startup(args: argparse.Namespace, report: dict[str, Any]) -> str:
    """Deactivate all Tutor Functions offline and restart standalone Desktop.

    This path deliberately uses only sqlite3 and process/executable discovery. It
    never imports the bundled Open WebUI package, never runs migrations, and never
    starts the test suite with the production interpreter.
    """
    if args.target != "Desktop":
        raise TutorInstallError("RecoverStartup je podporován pouze pro standalone Desktop.")
    desktop = resolve_desktop(args, report)
    root = desktop["root"]
    data_root = desktop["data_root"]
    db = desktop["database"]
    assert isinstance(root, Path) and isinstance(data_root, Path) and isinstance(db, Path)
    if not db.is_file():
        raise TutorInstallError(f"Chybí Desktop databáze: {db}")
    if desktop.get("database_overrides"):
        raise TutorInstallError(
            "Desktop config.json obsahuje DATABASE_* override; offline recovery odmítá hádat jinou databázi: "
            + ", ".join(sorted(desktop["database_overrides"]))
        )
    print("[INFO] Nouzová obnova ukončí pouze procesy standalone Desktopu; externí manager a jeho rodiče jsou chráněni.", flush=True)
    stop_report = stop_desktop_processes(
        root,
        desktop.get("executable") if isinstance(desktop.get("executable"), Path) else None,
    )
    report["desktop_process_stop"] = stop_report
    time.sleep(1.0)

    before = sqlite_status(db)
    report["database_before_recovery"] = before
    if before.get("integrity_check") != ["ok"]:
        raise TutorInstallError(f"SQLite integrity_check není 'ok': {before.get('integrity_check')}")
    backup = backup_sqlite(db, data_root)
    report["startup_recovery_backup"] = str(backup)

    connection = sqlite3.connect(str(db), timeout=30)
    try:
        connection.execute("PRAGMA foreign_keys=ON")
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "function" not in tables:
            raise TutorInstallError("Databáze neobsahuje tabulku function; nic nebylo změněno.")
        columns = {row[1] for row in connection.execute("PRAGMA table_info(function)")}
        if not {"id", "is_active"}.issubset(columns):
            raise TutorInstallError("Tabulka function nemá očekávané sloupce id a is_active.")
        placeholders = ",".join("?" for _ in TUTOR_RECOVERY_IDS)
        selected = connection.execute(
            f"SELECT id,type,is_active,updated_at FROM function WHERE id IN ({placeholders}) OR id LIKE 'study_tutor_%' OR id LIKE 'vut_ai_tutor_%' ORDER BY id",
            tuple(TUTOR_RECOVERY_IDS),
        ).fetchall()
        now = int(time.time())
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            f"UPDATE function SET is_active=0, updated_at=? WHERE id IN ({placeholders}) OR id LIKE 'study_tutor_%' OR id LIKE 'vut_ai_tutor_%'",
            (now, *TUTOR_RECOVERY_IDS),
        )
        connection.commit()
        report["tutor_functions_before_recovery"] = [
            {"id": row[0], "type": row[1], "is_active": bool(row[2]), "updated_at": row[3]}
            for row in selected
        ]
        after_rows = connection.execute(
            f"SELECT id,type,is_active,updated_at FROM function WHERE id IN ({placeholders}) OR id LIKE 'study_tutor_%' OR id LIKE 'vut_ai_tutor_%' ORDER BY id",
            tuple(TUTOR_RECOVERY_IDS),
        ).fetchall()
        report["tutor_functions_after_recovery"] = [
            {"id": row[0], "type": row[1], "is_active": bool(row[2]), "updated_at": row[3]}
            for row in after_rows
        ]
        integrity = [row[0] for row in connection.execute("PRAGMA integrity_check").fetchall()]
        if integrity != ["ok"]:
            raise TutorInstallError(f"SQLite integrity_check po deaktivaci není 'ok': {integrity}")
    except Exception:
        connection.rollback()
        connection.close()
        restore_sqlite_backup(db, backup)
        report["startup_recovery_restored_from"] = str(backup)
        raise
    else:
        connection.close()

    # A disk cache is not authoritative, but removing only Tutor-specific cache
    # directories prevents a stale source from being selected after restart.
    removed_cache: list[str] = []
    for cache_root in (data_root / "cache" / "functions", data_root / "cache" / "function"):
        for function_id in TUTOR_RECOVERY_IDS:
            candidate = cache_root / function_id
            if candidate.exists():
                shutil.rmtree(candidate, ignore_errors=True)
                if not candidate.exists():
                    removed_cache.append(str(candidate))
    report["removed_tutor_cache_paths"] = removed_cache
    report["database_after_recovery"] = sqlite_status(db)
    report["startup_recovery_ok"] = True

    if args.no_start_after_recovery:
        print(f"[OK] Tutor Function byly offline deaktivovány. Záloha: {backup}", flush=True)
        return ""
    start_desktop(args, report)
    deadline = time.monotonic() + args.startup_timeout
    last_error = ""
    while time.monotonic() < deadline:
        try:
            url = discover_backend(args, report)
            report["recovered_base_url"] = url
            print(f"[OK] Open WebUI Desktop po offline deaktivaci Tutor Function odpovídá na {url}.", flush=True)
            return url
        except Exception as exc:
            last_error = str(exc)
            time.sleep(2.0)
    report["desktop_startup_log_tails"] = collect_desktop_log_tails(
        desktop.get("config_root") if isinstance(desktop.get("config_root"), Path) else None
    )
    raise TutorInstallError(
        "Tutor Function byly deaktivovány a databáze je konzistentní, ale Desktop backend se nespustil. "
        f"Konce logů jsou v reportu. Poslední detekční chyba: {last_error}"
    )

def repair_database(args: argparse.Namespace, report: dict[str, Any]) -> None:
    desktop = resolve_desktop(args, report)
    root = desktop["root"]
    bundled_python = desktop["bundled_python"]
    data_root = desktop["data_root"]
    db = desktop["database"]
    assert isinstance(root, Path) and isinstance(bundled_python, Path) and isinstance(data_root, Path) and isinstance(db, Path)
    if not bundled_python.is_file():
        raise TutorInstallError(f"Chybí Desktop bundled Python: {bundled_python}")
    if not db.is_file():
        raise TutorInstallError(f"Chybí Desktop databáze: {db}")
    if desktop.get("database_overrides"):
        raise TutorInstallError(
            "Desktop config.json obsahuje explicitní DATABASE_* override, takže nelze bezpečně určit skutečnou databázi: "
            + ", ".join(sorted(desktop["database_overrides"]))
            + ". Odstraňte override nebo zadejte správný DesktopDataRoot a sjednoťte konfiguraci."
        )
    if os.name == "nt" and _windows_path_is_within(sys.executable, root):
        raise TutorInstallError(
            "Manager nesmí při Repair/DatabaseRepair běžet z Desktop bundled Pythonu pod DesktopInstallRoot; "
            "použijte externí Python, například z Anacondy."
        )
    if args.stop_desktop_processes:
        print("[INFO] Bezpečně ukončuji pouze procesy vlastněné standalone Desktop instalací; manager a jeho rodiče jsou chráněni.", flush=True)
        stop_report = stop_desktop_processes(root, desktop.get("executable") if isinstance(desktop.get("executable"), Path) else None)
        report["desktop_process_stop"] = stop_report
        report["stopped_processes"] = stop_report.get("terminated", [])
        print(f"[INFO] Ukončeno procesů standalone Desktopu: {len(stop_report.get('terminated', []))}.", flush=True)
        time.sleep(1.0)
    before = sqlite_status(db)
    report["database_before"] = before
    if before.get("integrity_check") != ["ok"]:
        raise TutorInstallError(f"SQLite integrity_check není 'ok': {before.get('integrity_check')}")
    backup = backup_sqlite(db, data_root)
    report["database_backup"] = str(backup)
    env = bundled_env(data_root, db, desktop.get("config_env_vars"))
    report["migration_environment"] = {
        "DATA_DIR": env.get("DATA_DIR"),
        "DATABASE_URL": env.get("DATABASE_URL"),
        "ENABLE_DB_MIGRATIONS": env.get("ENABLE_DB_MIGRATIONS"),
        "inherited_database_keys_removed": sorted(DATABASE_OVERRIDE_KEYS),
    }
    commands: list[dict[str, Any]] = []
    try:
        package_info, package_record = inspect_bundled_openwebui(bundled_python, env)
        commands.append(package_record)
        report["desktop_openwebui_package_before"] = package_info
        print(
            f"[INFO] Desktop Open WebUI package {package_info.get('distribution_version') or 'unknown'}; "
            "spouštím přímo Alembic, nikoli import-time run_migrations().",
            flush=True,
        )
        alembic_result: dict[str, Any] | None = None
        first_error: str | None = None
        try:
            alembic_result, migration_record = direct_alembic_upgrade(bundled_python, env, args.migration_timeout)
            commands.append(migration_record)
        except TutorInstallError as exc:
            record = getattr(exc, "command_record", None)
            if record:
                commands.append(record)
            first_error = str(exc)
            report["direct_alembic_first_error"] = first_error
            if args.skip_openwebui_reinstall:
                raise
            print("[WARN] Přímá migrace z instalovaného balíčku selhala; opravuji balíček na 0.11.3 a opakuji ji.", flush=True)
            commands.extend(reinstall_openwebui_package(bundled_python, env, args.package_timeout))
            package_info_after, package_record_after = inspect_bundled_openwebui(bundled_python, env)
            commands.append(package_record_after)
            report["desktop_openwebui_package_after_reinstall"] = package_info_after
            alembic_result, migration_record = direct_alembic_upgrade(bundled_python, env, args.migration_timeout)
            commands.append(migration_record)
        assert alembic_result is not None
        after = sqlite_status(db)
        report["database_after"] = after
        report["alembic_result"] = alembic_result
        validate_database_after_migration(after, alembic_result)
        report["database_repair_ok"] = True
        report["migration_strategy"] = "direct-alembic-with-0.11.2-calendar-import-shim"
        print(
            f"[OK] Databáze {db} je na Alembic head {', '.join(alembic_result.get('heads', []))}; "
            "chat.timer_at a všechny související indexy existují.",
            flush=True,
        )
    except Exception:
        restore_sqlite_backup(db, backup)
        report["database_restored_from"] = str(backup)
        report["database_after_restore"] = sqlite_status(db)
        raise
    finally:
        report["database_commands"] = commands

def start_desktop(args: argparse.Namespace, report: dict[str, Any]) -> None:
    desktop = resolve_desktop(args, report)
    executable = desktop.get("executable")
    if not isinstance(executable, Path) or not executable.is_file():
        searched = ", ".join(str(item) for item in desktop.get("executable_candidates") or [])
        raise TutorInstallError(
            "Open WebUI Desktop executable nebyl nalezen. "
            "Zadejte -DesktopExecutable s úplnou cestou."
            + (f" Prohledané cesty: {searched}" if searched else "")
        )
    child_env = os.environ.copy()
    removed = []
    for key in ("VUT_TUTOR_ADMIN_EMAIL", "VUT_TUTOR_ADMIN_PASSWORD", "VUT_TUTOR_ADMIN_TOKEN"):
        if key in child_env:
            child_env.pop(key, None)
            removed.append(key)
    kwargs: dict[str, Any] = {
        "cwd": str(executable.parent),
        "close_fds": True,
        "env": child_env,
    }
    # Launch the official GUI executable normally. Detached-process flags can
    # suppress or alter Electron startup on some Windows builds.
    process = subprocess.Popen([str(executable)], **kwargs)
    report.setdefault("desktop_start_attempts", []).append({
        "at": now_iso(),
        "executable": str(executable),
        "launcher_pid": int(process.pid),
        "default_connection_id": desktop.get("default_connection_id"),
        "local_server": desktop.get("local_server"),
    })
    report["desktop_started"] = str(executable)
    report["desktop_start_environment_sanitized"] = removed

def load_token(args: argparse.Namespace, client: OpenWebUIClient) -> str:
    if args.token_file:
        lines = [line.strip() for line in Path(args.token_file).read_text(encoding="utf-8-sig").splitlines() if line.strip()]
        if len(lines) != 1:
            raise TutorInstallError("TokenFile musí obsahovat právě jeden neprázdný řádek.")
        client.token = lines[0]
        return client.token
    env_token = os.getenv("VUT_TUTOR_ADMIN_TOKEN", "").strip()
    if env_token:
        client.token = env_token
        return env_token
    email = args.email or os.getenv("VUT_TUTOR_ADMIN_EMAIL", "").strip()
    password = os.getenv("VUT_TUTOR_ADMIN_PASSWORD", "")
    if args.prompt_for_credential and not email:
        email = input("Open WebUI admin e-mail: ").strip()
    if args.prompt_for_credential and not password:
        password = getpass.getpass("Open WebUI admin heslo: ")
    if not email or not password:
        raise TutorInstallError("Zadejte -TokenFile nebo -PromptForCredential (případně VUT_TUTOR_ADMIN_* v prostředí).")
    return client.sign_in(email, password)



def restart_desktop_for_tutor_activation(
    args: argparse.Namespace,
    report: dict[str, Any],
    preferred_base_url: str,
) -> str:
    if args.target != 'Desktop':
        raise TutorInstallError('Automatický restart po chybě hot-aktivace je dostupný pouze pro standalone Desktop.')
    if os.name != 'nt':
        raise TutorInstallError('Automatický restart standalone Desktopu je podporován pouze ve Windows.')

    desktop = resolve_desktop(args, report)
    root = desktop.get('root')
    executable = desktop.get('executable')
    config_root = desktop.get('config_root')
    if not isinstance(root, Path):
        raise TutorInstallError('Nelze určit DesktopInstallRoot pro restart aktivačního runtime.')

    recovery: dict[str, Any] = {
        'strategy': 'controlled-desktop-restart',
        'preferred_base_url': preferred_base_url,
        'started_at': now_iso(),
    }
    report['tutor_activation_recovery'] = recovery
    print(
        '[WARN] Hot aktivace tutor rout nebyla stabilní. Bezpečně restartuji pouze procesy standalone Desktopu '
        'a ověřím startup lifecycle znovu.',
        flush=True,
    )
    stop_result = stop_desktop_processes(
        root,
        executable if isinstance(executable, Path) else None,
    )
    recovery['process_stop'] = stop_result
    time.sleep(1.0)
    start_desktop(args, report)

    deadline = time.monotonic() + args.startup_timeout
    attempts: list[dict[str, Any]] = []
    last_error = ''
    while time.monotonic() < deadline:
        if preferred_base_url:
            version = http_openwebui_version(preferred_base_url, timeout=min(args.http_timeout, 2.0))
            attempts.append({'url': preferred_base_url, 'reachable': version is not None, 'version': version})
            if version is not None:
                recovery['backend_attempts'] = attempts[-20:]
                recovery['finished_at'] = now_iso()
                return preferred_base_url
        try:
            discovered = discover_backend(args, report)
            recovery['backend_attempts'] = attempts[-20:]
            recovery['finished_at'] = now_iso()
            return discovered
        except Exception as exc:
            last_error = str(exc)
        time.sleep(2.0)

    recovery['backend_attempts'] = attempts[-20:]
    recovery['finished_at'] = now_iso()
    recovery['log_tails'] = collect_desktop_log_tails(config_root if isinstance(config_root, Path) else None)
    raise TutorInstallError(
        'Standalone Desktop backend se po řízeném restartu nespustil. '
        f'Konce logů jsou v reportu. Poslední detekční chyba: {last_error}'
    )


def install_pair(args: argparse.Namespace, report: dict[str, Any], base_url: str) -> str:
    bootstrap = validate_source(Path(args.bootstrap_path), BOOTSTRAP_ID, 'event')
    pipe = validate_source(Path(args.pipe_path), PIPE_ID, 'pipe')
    report['source_contracts'] = [
        {k: v for k, v in asdict(c).items() if k != 'content'} for c in (bootstrap, pipe)
    ]
    report['embedded_pipe_contract'] = validate_source_pair(bootstrap, pipe)
    client = OpenWebUIClient(base_url, timeout=args.http_timeout)
    report['openwebui_version'] = client.version()
    load_token(args, client)
    client.request('GET', '/api/v1/functions/', auth=True, expected=(200,))
    report['operations'] = []
    backup_records = []
    for function_id in dict.fromkeys((*LEGACY_IDS, BOOTSTRAP_ID, PIPE_ID)):
        existing = client.get_function(function_id)
        if existing is not None:
            valves_response = client.request('GET', f'/api/v1/functions/id/{function_id}/valves', auth=True, expected=(200,))
            backup_records.append({'function': existing, 'valves': valves_response.json()})
    backup_parent = Path(args.report_path).resolve().parent if args.report_path else Path.cwd()
    backup_parent.mkdir(parents=True, exist_ok=True)
    backup_path = backup_parent / ('vut-pdf-hotfix-functions-before-' + time.strftime('%Y%m%d-%H%M%S') + '-' + os.urandom(4).hex() + '.json')
    with backup_path.open('x', encoding='utf-8') as handle:
        with contextlib.suppress(OSError):
            os.chmod(backup_path, 0o600)
        json.dump({'schema': 1, 'created_at': now_iso(), 'functions': backup_records}, handle, ensure_ascii=False, indent=2)
    report['functions_backup_path'] = str(backup_path)
    print('[INFO] Function backup: ' + str(backup_path), flush=True)

    # Remove every historical Event ID before creating the fresh canonical ID.
    # This prevents Open WebUI's Function module cache from continuing to dispatch
    # an older register_routes() implementation under study_tutor_bootstrap.
    removed_functions: list[dict[str, Any]] = []
    for function_id in (*LEGACY_IDS, BOOTSTRAP_ID):
        if function_id == PIPE_ID:
            continue
        result = client.deactivate_and_delete_legacy(function_id)
        result['absent_after_cleanup'] = client.get_function(function_id) is None
        if result.get('present') and (not result.get('deleted') or not result['absent_after_cleanup']):
            raise TutorInstallError(f'Function {function_id} se nepodařilo úplně odstranit před čerstvou instalací.')
        removed_functions.append(result)
        report['operations'].append({'fresh_event_cleanup': function_id, 'result': result})
    report['fresh_event_cleanup'] = removed_functions

    # Pipe is installed first, then the new Event is created under a never-before-used
    # ID. The Event setup may provision the Pipe again; therefore reconcile it once.
    report['operations'].append({'upsert': PIPE_ID, 'result': client.upsert_function(pipe)})
    report['operations'].append({'create_fresh_event': BOOTSTRAP_ID, 'result': client.upsert_function(bootstrap)})
    report['operations'].append({'reconcile': PIPE_ID, 'result': client.upsert_function(pipe)})
    for record in backup_records:
        old_id = record['function'].get('id')
        if old_id in {BOOTSTRAP_ID, PIPE_ID} and isinstance(record.get('valves'), dict):
            client.request('POST', f'/api/v1/functions/id/{old_id}/valves/update', data=record['valves'], auth=True, expected=(200,))


    verified_pipe = client.verify_function(pipe)
    verified_bootstrap = client.verify_function(bootstrap)
    report['verified_functions'] = [verified_bootstrap, verified_pipe]
    remaining_legacy = [function_id for function_id in LEGACY_IDS if client.get_function(function_id) is not None]
    report['remaining_legacy_functions'] = remaining_legacy
    if remaining_legacy:
        raise TutorInstallError('Po instalaci zůstaly aktivní nebo uložené staré Tutor Function: ' + ', '.join(remaining_legacy))

    try:
        report['routes'] = client.verify_tutor_routes(timeout=args.route_timeout)
        report['activation_strategy'] = 'fresh-event-id-asgi-prefix-gateway-v7'
        report['installation_ok'] = True
        return base_url
    except TutorInstallError as hot_error:
        report['hot_activation_error'] = str(hot_error)
        diagnostics = getattr(hot_error, 'route_diagnostics', None)
        if diagnostics:
            report['hot_activation_route_diagnostics'] = diagnostics
        if args.target != 'Desktop':
            raise

    restarted_url = restart_desktop_for_tutor_activation(args, report, base_url)
    restarted_client = OpenWebUIClient(restarted_url, timeout=args.http_timeout, token=client.token)
    report['openwebui_version_after_activation_restart'] = restarted_client.version()
    try:
        restarted_client.request('GET', '/api/v1/functions/', auth=True, expected=(200,))
    except TutorInstallError:
        load_token(args, restarted_client)
        restarted_client.request('GET', '/api/v1/functions/', auth=True, expected=(200,))

    try:
        verified_pipe = restarted_client.verify_function(pipe)
        verified_bootstrap = restarted_client.verify_function(bootstrap)
        report['verified_functions_after_activation_restart'] = [verified_bootstrap, verified_pipe]
        remaining_legacy = [function_id for function_id in LEGACY_IDS if restarted_client.get_function(function_id) is not None]
        if remaining_legacy:
            raise TutorInstallError('Po restartu se znovu objevily staré Tutor Function: ' + ', '.join(remaining_legacy))
        report['routes'] = restarted_client.verify_tutor_routes(timeout=args.route_timeout)
    except TutorInstallError as restart_error:
        desktop = resolve_desktop(args, report)
        config_root = desktop.get('config_root')
        recovery = report.setdefault('tutor_activation_recovery', {})
        recovery['verification_error'] = str(restart_error)
        recovery['log_tails'] = collect_desktop_log_tails(
            config_root if isinstance(config_root, Path) else None
        )
        raise TutorInstallError(
            'Event Function je zapsána, ale izolovaná Canvas ASGI gateway nebyla aktivní ani po restartu Desktopu. '
            'Report obsahuje přesný uložený Function kontrakt a konce Desktop logů.'
        ) from restart_error

    report['activation_strategy'] = 'asgi-prefix-gateway-v7-after-controlled-desktop-restart'
    report['installation_ok'] = True
    print('[OK] Canvas ASGI gateway byla ověřena po řízeném restartu standalone Desktopu.', flush=True)
    return restarted_url

def verify_pair(args: argparse.Namespace, report: dict[str, Any], base_url: str) -> None:
    bootstrap = validate_source(Path(args.bootstrap_path), BOOTSTRAP_ID, "event")
    pipe = validate_source(Path(args.pipe_path), PIPE_ID, "pipe")
    report["embedded_pipe_contract"] = validate_source_pair(bootstrap, pipe)
    client = OpenWebUIClient(base_url, timeout=args.http_timeout)
    report["openwebui_version"] = client.version()
    load_token(args, client)
    report["verified_functions"] = [client.verify_function(bootstrap), client.verify_function(pipe)]
    remaining_legacy = [function_id for function_id in LEGACY_IDS if client.get_function(function_id) is not None]
    report["remaining_legacy_functions"] = remaining_legacy
    if remaining_legacy:
        raise TutorInstallError('Verifikace našla staré Tutor Function: ' + ', '.join(remaining_legacy))
    report["routes"] = client.verify_tutor_routes(timeout=args.route_timeout)
    report["verification_ok"] = True


def self_test(args: argparse.Namespace) -> dict[str, Any]:
    bootstrap = validate_source(Path(args.bootstrap_path), BOOTSTRAP_ID, "event")
    pipe = validate_source(Path(args.pipe_path), PIPE_ID, "pipe")
    assert BOOTSTRAP_ID != PIPE_ID
    assert bootstrap.sha256 != pipe.sha256
    assert "class Pipe" in pipe.content
    assert "class Event" in bootstrap.content
    pair_contract = validate_source_pair(bootstrap, pipe)
    safe_stop_contract = _safe_stop_selection_self_test()
    return {
        "ok": True,
        "version": RELEASE_VERSION,
        "marker": RELEASE_MARKER,
        "bootstrap": {k: v for k, v in asdict(bootstrap).items() if k != "content"},
        "pipe": {k: v for k, v in asdict(pipe).items() if k != "content"},
        "embedded_pipe_contract": pair_contract,
        "safe_stop_contract": safe_stop_contract,
        "migration_strategy": "direct-alembic-with-0.11.2-calendar-import-shim",
        "event_lifecycle_policy": "fresh-event-id-exact-subject-sync-disable-started-v7",
        "route_registration_strategy": "asgi-prefix-gateway-v7-no-main-router-mutation",
        "desktop_activation_fallback": "controlled-restart",
        "desktop_backend_resolution": "official-electron-autostart-for-install-and-verify-v3",
        "desktop_adapter_revision": DESKTOP_ADAPTER_REVISION,
        "native_stderr_policy": "handled-by-powershell-wrapper-without-NativeCommandError",
        "http_transport_readiness": "bounded-version-signin-retry-and-mock-body-drain-v1",
    }


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="VUT AI Tutor complete Server/Desktop installer with offline startup recovery and isolated ASGI prefix gateway")
    parser.add_argument("--mode", default="TutorOnly", choices=("Repair", "TutorOnly", "DatabaseRepair", "RecoverStartup", "Verify"))
    parser.add_argument("--target", default="Desktop", choices=("Desktop", "Server"))
    parser.add_argument("--bootstrap-path", required=True)
    parser.add_argument("--pipe-path", required=True)
    parser.add_argument("--base-url", default="")
    parser.add_argument("--only-base-url", action="store_true")
    parser.add_argument("--desktop-install-root", default="")
    parser.add_argument("--desktop-data-root", default="")
    parser.add_argument("--desktop-config-root", default="")
    parser.add_argument("--desktop-executable", default="")
    parser.add_argument("--server-runtime-config", default="")
    parser.add_argument("--token-file", default="")
    parser.add_argument("--email", default="")
    parser.add_argument("--prompt-for-credential", action="store_true")
    parser.add_argument("--stop-desktop-processes", action="store_true")
    parser.add_argument("--skip-openwebui-reinstall", action="store_true")
    parser.add_argument("--report-path", default="")
    parser.add_argument("--http-timeout", type=float, default=15.0)
    parser.add_argument("--route-timeout", type=float, default=60.0)
    parser.add_argument("--startup-timeout", type=float, default=180.0)
    parser.add_argument("--package-timeout", type=int, default=1800)
    parser.add_argument("--migration-timeout", type=int, default=600)
    parser.add_argument("--no-start-after-recovery", action="store_true")
    parser.add_argument("--no-auto-start-desktop", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = make_parser()
    args = parser.parse_args(argv)
    report: dict[str, Any] = {
        "schema": 2,
        "release_version": RELEASE_VERSION,
        "release_marker": RELEASE_MARKER,
        "desktop_adapter_revision": DESKTOP_ADAPTER_REVISION,
        "started_at": now_iso(),
        "mode": args.mode,
        "target": args.target,
        "success": False,
    }
    report_path = Path(args.report_path).resolve() if args.report_path else None
    try:
        print(f"[INFO] Manager {RELEASE_VERSION} zahájil operaci mode={args.mode} target={args.target} pid={os.getpid()}.", flush=True)
        if args.self_test:
            report["self_test"] = self_test(args)
            report["success"] = True
            print(json.dumps(report["self_test"], ensure_ascii=False, indent=2))
            return 0
        if args.mode == "RecoverStartup":
            recovered_url = recover_desktop_startup(args, report)
            if recovered_url:
                report["base_url"] = recovered_url
            report["success"] = True
            return 0
        if args.mode in {"Repair", "DatabaseRepair"}:
            if args.target != "Desktop":
                raise TutorInstallError("DatabaseRepair je podporován pouze pro standalone Desktop.")
            repair_database(args, report)
            if args.mode == "DatabaseRepair":
                report["success"] = True
                print("[OK] Desktop databáze byla zálohována, migrována a ověřena.")
                return 0
            # Repair may have stopped Desktop; start it and wait for a verified /api/version.
            start_desktop(args, report)
            base_url = wait_for_backend(
                args,
                report,
                auto_start_desktop=False,
                operation="post-database-repair-startup",
            )
        else:
            base_url = ensure_backend(args, report, operation=f"{args.mode.lower()}-backend-resolution")
        report["base_url"] = base_url
        print(f"[INFO] Cílový Open WebUI backend: {base_url}")
        if args.mode in {"Repair", "TutorOnly"}:
            base_url = install_pair(args, report, base_url)
            report["base_url_after_install"] = base_url
            print(f"[OK] Aktivní Function {BOOTSTRAP_ID} (event) i {PIPE_ID} (pipe) byly přímo vytvořeny a ověřeny.")
        elif args.mode == "Verify":
            verify_pair(args, report, base_url)
            print(f"[OK] Function {BOOTSTRAP_ID} i {PIPE_ID} mají správný typ, aktivaci a obsah.")
        report["success"] = True
        return 0
    except TutorInstallError as exc:
        report["error"] = str(exc)
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 4
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        print(f"[FAIL] Neočekávaná chyba: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 5
    finally:
        report["finished_at"] = now_iso()
        if report_path:
            atomic_json(report_path, report)
            print(f"[INFO] Report: {report_path}")


if __name__ == "__main__":
    raise SystemExit(main())

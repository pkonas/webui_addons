#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import types
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'engineering_mcp_unified-v2.9.18.py'


def load_module(tag: str):
    home = Path(tempfile.mkdtemp(prefix=f'emcp-v2911-{tag}-'))
    os.environ['ENGINEERING_MCP_HOME'] = str(home)
    spec = importlib.util.spec_from_file_location(f'emcp_v2911_{tag}', SOURCE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, home


def test_component_contract() -> None:
    module, _ = load_module('component')
    component = module.physnemo_component()
    assert module.BOOTSTRAPPER_VERSION == '2.9.18'
    assert component.BOOTSTRAPPER_VERSION == '1.2.10'
    assert component.NAT_FUNCTION_CONTRACT == 'NAT_1_9_GENERAL_AGENT_ARTIFACT_GALLERY_V2'
    assert component.NAT_DEPENDENCY_CONTRACT == 'NAT_1_9_FUNCTION_REF_DEPENDENCY_V1'
    assert 'agent_name: FunctionRef | None = None' in component.PLUGIN_REGISTER
    assert component.WSL_MANAGED_ROOT_MARKER == 'ENGINEERING_MCP_PHYSNEMO_ROOT_V4_ARTIFACTS_ALLOWED'
    assert component.MANAGED_ROOT_ARTIFACTS_CONTRACT == 'MANAGED_ROOT_ARTIFACTS_DIRECTORY_V1'
    assert 'artifacts' in component.MANAGED_ROOT_DIRECTORIES
    assert module.PHYSNEMO_OPENAPI_EXPECTED_TOOLS == (
        'physnemo__environment_info',
        'physnemo__solve',
        'physnemo__job_status',
        'physnemo__list_artifacts',
        'physnemo__get_artifact',
        'physnemo__render_artifacts',
    )
    assert 'physnemo__render_artifacts' not in component.EXPECTED_TOOLS
    assert 'Call physnemo__render_artifacts' in component.PLUGIN_REGISTER
    assert 'clipboard artifacts' in component.PLUGIN_REGISTER


def test_completed_job_id_extraction() -> None:
    module, _ = load_module('extract')
    job = 'job-20260919T120000Z-0123456789ab'
    payloads = [
        {'job_id': job, 'state': 'completed'},
        json.dumps({'job_id': job, 'state': 'completed'}),
        {'result': json.dumps({'job_id': job, 'status': 'success'})},
        {'content': [{'type': 'text', 'text': json.dumps({'job_id': job, 'state': 'done'})}]},
    ]
    for payload in payloads:
        raw = json.dumps(payload).encode('utf-8')
        assert module._physnemo_completed_job_id_from_tool_response(raw) == job
    assert module._physnemo_completed_job_id_from_tool_response(
        json.dumps({'job_id': job, 'state': 'failed'}).encode()
    ) == ''


def test_gallery_renders_all_supported_types_and_escapes() -> None:
    module, _ = load_module('gallery')
    job = 'job-20260919T120000Z-0123456789ab'
    root = '/managed/artifacts'
    files: dict[str, bytes] = {
        f'{root}/{job}/manifest.json': json.dumps({
            'job_id': job,
            'created_at': '2026-09-19T12:00:00Z',
            'artifacts': [
                {'name': 'plot.png', 'media_type': 'image/png', 'size': 8, 'sha256': 'a'*64},
                {'name': 'vector.svg', 'media_type': 'image/svg+xml', 'size': 20, 'sha256': 'b'*64},
                {'name': 'table.csv', 'media_type': 'text/csv', 'size': 20, 'sha256': 'c'*64},
                {'name': 'metrics.json', 'media_type': 'application/json', 'size': 20, 'sha256': 'd'*64},
                {'name': 'solution.py', 'media_type': 'text/x-python', 'size': 20, 'sha256': 'e'*64},
                {'name': 'report.pdf', 'media_type': 'application/pdf', 'size': 20, 'sha256': 'f'*64},
                {'name': 'bundle.zip', 'media_type': 'application/zip', 'size': 20, 'sha256': '0'*64},
            ],
        }).encode(),
        f'{root}/{job}/artifacts/table.csv': b'name,value\n<script>,42\n',
        f'{root}/{job}/artifacts/metrics.json': b'{"loss": 0.125, "unsafe": "<img>"}',
        f'{root}/{job}/artifacts/solution.py': b'print("<unsafe>")\n',
    }
    runtime = {
        'configured': True,
        'distro': 'Ubuntu',
        'artifact_root': root,
        'artifact_secret': 's' * 64,
        'artifact_base_url': 'http://127.0.0.1:8200/physnemo/artifacts',
    }
    module._physnemo_runtime_storage = lambda: runtime
    module.load_state = lambda: {'mcpo_port': 8200, 'physnemo_runtime': runtime}

    def read(_runtime, path, *, allowed_prefix, max_bytes):
        assert path.startswith(allowed_prefix.rstrip('/') + '/') or path == allowed_prefix.rstrip('/')
        data = files.get(path)
        if data is None:
            # image/pdf/binary previews do not read bytes while rendering HTML
            raise FileNotFoundError(path)
        assert len(data) <= max_bytes
        return data

    module._physnemo_wsl_read_file = read
    html = module._physnemo_render_gallery(job)
    assert 'PhysicsNeMo artifact gallery' in html
    assert '<img' in html and 'plot.png' in html and 'vector.svg' in html
    assert '<table>' in html and '&lt;script&gt;' in html
    assert '&quot;loss&quot;: 0.125' in html and '&lt;img&gt;' in html
    assert 'print(&quot;&lt;unsafe&gt;&quot;)' in html
    assert '<iframe class="pdf"' in html
    assert 'Binary artifact' in html
    assert html.count('>Download</a>') == 7
    assert 'signature=' in html and 'download=1' in html
    assert '<script>' not in html.split('<div class="grid">', 1)[1].split("<script>function h()", 1)[0]


def build_named_mcpo_app(module, solve_payload=None):
    captured: dict[str, Any] = {}
    mcpo_pkg = types.ModuleType('mcpo')
    mcpo_main = types.ModuleType('mcpo.main')

    async def fake_run(*_args, **_kwargs):
        app = mcpo_main.FastAPI(title='physnemo')

        @app.post('/physnemo__solve')
        async def fake_solve():
            return json.dumps(solve_payload if solve_payload is not None else {
                'job_id': 'job-20260919T120000Z-0123456789ab',
                'state': 'completed',
                'artifact_count': 2,
            })

        captured['app'] = app

    mcpo_main.run = fake_run
    # Placeholder replaced by run_named_mcpo.
    from fastapi import FastAPI
    mcpo_main.FastAPI = FastAPI
    mcpo_pkg.main = mcpo_main
    old_mcpo = sys.modules.get('mcpo')
    old_main = sys.modules.get('mcpo.main')
    sys.modules['mcpo'] = mcpo_pkg
    sys.modules['mcpo.main'] = mcpo_main
    try:
        rc = module.run_named_mcpo([
            '--host', '127.0.0.1', '--port', '8200', '--api-key', 'secret',
            '--config', 'dummy.json', '--name', 'Engineering MCP Gateway',
        ])
    finally:
        if old_mcpo is None:
            sys.modules.pop('mcpo', None)
        else:
            sys.modules['mcpo'] = old_mcpo
        if old_main is None:
            sys.modules.pop('mcpo.main', None)
        else:
            sys.modules['mcpo.main'] = old_main
    assert rc == 0
    return captured['app']


def test_openapi_gallery_route_and_automatic_solve_render() -> None:
    module, _ = load_module('fastapi')
    module._physnemo_render_gallery = lambda job_id: f'<html><body>gallery:{job_id}</body></html>'
    app = build_named_mcpo_app(module)
    schema = app.openapi()
    operation_ids = {
        operation.get('operationId')
        for methods in schema.get('paths', {}).values()
        for method, operation in methods.items()
        if method.lower() in {'get', 'post', 'put', 'patch', 'delete'} and isinstance(operation, dict)
    }
    assert 'physnemo__render_artifacts' in operation_ids

    from fastapi.testclient import TestClient
    client = TestClient(app)
    explicit = client.post('/render-artifacts', json={'job_id': 'job-20260919T120000Z-0123456789ab'})
    assert explicit.status_code == 200
    assert explicit.headers['content-type'].startswith('text/html')
    assert explicit.headers['content-disposition'] == 'inline'
    assert 'gallery:job-20260919T120000Z-0123456789ab' in explicit.text

    automatic = client.post('/physnemo__solve', json={})
    assert automatic.status_code == 200
    assert automatic.headers['content-type'].startswith('text/html')
    assert automatic.headers['content-disposition'] == 'inline'
    assert automatic.headers['x-engineering-mcp-artifact-job'] == 'job-20260919T120000Z-0123456789ab'
    assert 'gallery:job-20260919T120000Z-0123456789ab' in automatic.text

    # Signed artifact route returns real bytes and rejects a forged signature.
    runtime = {
        'configured': True, 'distro': 'Ubuntu', 'artifact_root': '/managed/artifacts',
        'artifact_secret': 'k' * 64, 'artifact_base_url': 'http://testserver/artifacts',
    }
    module._physnemo_runtime_storage = lambda: runtime
    module.load_state = lambda: {'mcpo_port': 8200, 'physnemo_runtime': runtime}
    module._physnemo_wsl_read_file = lambda *_args, **_kwargs: b'actual-artifact-bytes'
    signed = module._physnemo_artifact_url(
        runtime, 'job-20260919T120000Z-0123456789ab', 'bundle.zip', download=True
    )
    from urllib.parse import urlsplit
    parsed = urlsplit(signed)
    download = client.get('/artifacts' + parsed.path.split('/artifacts', 1)[1] + '?' + parsed.query)
    assert download.status_code == 200 and download.content == b'actual-artifact-bytes'
    assert download.headers['content-disposition'].startswith('attachment;')
    forged = parsed.query.replace('signature=', 'signature=' + '0' * 64 + '&ignored=')
    rejected = client.get('/artifacts' + parsed.path.split('/artifacts', 1)[1] + '?' + forged)
    assert rejected.status_code == 403


def test_openwebui_live_tool_server_refresh() -> None:
    module, home = load_module('sync')
    received: dict[str, Any] = {'posts': []}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            return

        def _json(self, status: int, payload: Any):
            raw = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers(); self.wfile.write(raw)

        def do_GET(self):  # noqa: N802
            assert self.headers.get('Authorization') == 'Bearer admin-key'
            if self.path == '/api/v1/configs/tool_servers':
                self._json(200, {'TOOL_SERVER_CONNECTIONS': [
                    {
                        'type': 'openapi', 'url': 'http://old/physnemo', 'path': 'old.json',
                        'auth_type': 'bearer', 'key': 'old', 'config': {'enable': True},
                        'info': {'id': 'physnemo', 'name': 'Old PhysicsNeMo'},
                    },
                    {
                        'type': 'openapi', 'url': 'http://other', 'path': 'other.json',
                        'auth_type': 'none', 'key': '', 'config': {'enable': True},
                        'info': {'id': 'other', 'name': 'Other'},
                    },
                ]})
                return
            self._json(404, {})

        def do_POST(self):  # noqa: N802
            assert self.headers.get('Authorization') == 'Bearer admin-key'
            length = int(self.headers.get('Content-Length', '0'))
            payload = json.loads(self.rfile.read(length) or b'{}')
            received['posts'].append((self.path, payload))
            if self.path in {'/api/v1/configs/tool_servers', '/api/v1/configs/tool_servers/verify'}:
                self._json(200, {'status': True})
                return
            self._json(404, {})

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    try:
        module.PHYSNEMO_AGENT_SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
        module.atomic_write_json(module.PHYSNEMO_AGENT_SECRET_FILE, {
            'openwebui_base_url': f'http://127.0.0.1:{server.server_port}',
            'openwebui_api_key': 'admin-key',
        }, private=True)
        state = {
            'api_key': 'gateway-token',
            'mcpo_port': 8200,
            'routes': ['physnemo'],
            'scan': {'docker': {'openwebui_container': 'open-webui', 'containers': []}},
            'servers': {
                'physnemo': {
                    'id': 'physnemo',
                    'route': 'physnemo',
                    'name': 'Engineering MCP - PhysicsNeMo (NVIDIA NeMo Agent Toolkit)',
                    'description': 'PhysicsNeMo',
                }
            },
        }
        # build_connection_records primarily consumes installed state; use a deterministic import payload here.
        desired = {
            'type': 'openapi', 'url': 'http://host.docker.internal:8200/physnemo',
            'spec_type': 'url', 'spec': '', 'path': 'physnemo-openapi.json',
            'auth_type': 'bearer', 'key': 'gateway-token', 'config': {'enable': True},
            'info': {'id': 'physnemo', 'name': 'Engineering MCP - PhysicsNeMo', 'description': 'new'},
        }
        module.build_openwebui_import = lambda _state, docker_backend: [json.loads(json.dumps(desired))]
        report = module.sync_physnemo_openwebui_tool_server(state)
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)
    assert report['updated'] is True and report['verified'] is True, report
    config_post = next(payload for path, payload in received['posts'] if path == '/api/v1/configs/tool_servers')
    connections = config_post['TOOL_SERVER_CONNECTIONS']
    assert len([c for c in connections if (c.get('info') or {}).get('id') == 'physnemo']) == 1
    phys = next(c for c in connections if (c.get('info') or {}).get('id') == 'physnemo')
    assert phys['path'] == 'physnemo-openapi.json'
    assert phys['config']['enable'] is True
    verify_post = next(payload for path, payload in received['posts'] if path == '/api/v1/configs/tool_servers/verify')
    assert verify_post['info']['id'] == 'physnemo'
    report_text = module.PHYSNEMO_OPENWEBUI_SYNC_REPORT.read_text(encoding='utf-8')
    assert 'admin-key' not in report_text
    assert 'gateway-token' not in report_text


def test_static_contract() -> None:
    text = SOURCE.read_text(encoding='utf-8')
    for marker in (
        'OPENWEBUI_INLINE_HTML_GALLERY_V1',
        'OPENWEBUI_TOOL_SERVER_LIVE_REFRESH_V1',
        'physnemo__render_artifacts',
        'Content-Disposition": "inline"',
        'auto_render_completed_physnemo_solve',
        'sync_physnemo_openwebui_tool_server',
    ):
        assert marker in text, marker
    assert 'physnemo__start_pinn_karman' not in text
    assert 'physnemo__pinn_run_status' not in text


def main() -> None:
    tests = [
        test_component_contract,
        test_completed_job_id_extraction,
        test_gallery_renders_all_supported_types_and_escapes,
        test_openapi_gallery_route_and_automatic_solve_render,
        test_openwebui_live_tool_server_refresh,
        test_static_contract,
    ]
    for test in tests:
        test()
        print(f'PASS: {test.__name__}')
    print('UNIFIED_V2912_NATIVE_ARTIFACT_TESTS_OK')


if __name__ == '__main__':
    main()

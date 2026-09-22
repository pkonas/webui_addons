#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import yaml

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'engineering_mcp_unified-v2.9.18.py'


def load_module(home: Path, runtime: Path | None, tag: str):
    os.environ['ENGINEERING_MCP_HOME'] = str(home)
    if runtime is None:
        os.environ.pop('EINFRA_OPENWEBUI_RUNTIME', None)
    else:
        os.environ['EINFRA_OPENWEBUI_RUNTIME'] = str(runtime)
    spec = importlib.util.spec_from_file_location(f'engineering_mcp_unified_v293_test_{tag}', SOURCE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class OpenWebUIMock:
    def __init__(self) -> None:
        self.requests: list[dict[str, str]] = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                return

            def _send(self, status: int, payload: object) -> None:
                raw = json.dumps(payload).encode('utf-8')
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self):  # noqa: N802
                owner.requests.append({
                    'path': self.path,
                    'authorization': self.headers.get('Authorization', ''),
                })
                if self.path == '/_app/version.json':
                    self._send(200, {'version': 'test'})
                    return
                if self.path == '/api/models':
                    if self.headers.get('Authorization') != 'Bearer openwebui-user-key':
                        self._send(401, {'detail': 'unauthorized'})
                    else:
                        self._send(200, {'data': [{'id': 'e-infra.test-model'}]})
                    return
                self._send(404, {'detail': 'not found'})

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def root(self) -> str:
        return f'http://127.0.0.1:{self.server.server_port}'

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


def test_direct_runtime_provider(root: Path) -> None:
    home = root / 'direct-home'
    runtime = root / 'runtime.json'
    runtime.write_text(json.dumps({
        'BackendPort': 8080,
        'PrimaryUrl': 'https://webui.example',
        'Environment': {
            'OPENAI_API_BASE_URL': 'https://llm.example/v1',
            'OPENAI_API_KEY': 'provider-secret',
            'DEFAULT_MODELS': 'generic-engineering-model,other',
            'WEBUI_URL': 'https://webui.example',
        },
    }), encoding='utf-8')
    module = load_module(home, runtime, 'direct')
    component = module.physnemo_component()
    assert module.BOOTSTRAPPER_VERSION == '2.9.18'
    assert component.BOOTSTRAPPER_VERSION == '1.2.10'
    assert module.PHYSNEMO_AGENT_OPTIONAL_INSTALL_CONTRACT == 'NAT_AGENT_OPTIONAL_INSTALL_V1'
    assert component.AGENT_OPTIONAL_INSTALL_CONTRACT == 'NAT_AGENT_OPTIONAL_INSTALL_V1'
    assert component.NAT_DEPENDENCY_CONTRACT == 'NAT_1_9_FUNCTION_REF_DEPENDENCY_V1'
    secret = module._resolve_physnemo_agent_secret({'physnemo_agent_auto_detect': True})
    assert secret['configured'] is True
    assert secret['agent_transport'] == 'direct-provider'
    assert secret['agent_base_url'] == 'https://llm.example/v1'
    assert secret['agent_model'] == 'generic-engineering-model'
    assert secret['agent_api_key'] == 'provider-secret'
    summary = module._physnemo_agent_secret_safe_summary(secret)
    assert summary['configured'] is True
    assert 'provider-secret' not in json.dumps(summary)
    assert module.PHYSNEMO_AGENT_DETECTION_REPORT.exists()

    rendered = component.render_nat_config(
        '/managed/physicsnemo-source', 'v2.2.2', '/managed/artifacts',
        'http://127.0.0.1:8200/physnemo/artifacts', 'x' * 64,
        agent_model='generic-engineering-model', agent_base_url='https://llm.example/v1',
        openwebui_bridge_url='', openwebui_bridge_secret='', agent_configured=True,
    )
    config = yaml.safe_load(rendered)
    assert config['llms']['physnemo_llm']['_type'] == 'openai'
    assert config['functions']['physnemo_agent']['_type'] == 'physnemo_native_agent'
    assert config['functions']['physnemo_agent']['max_turns'] == 32
    assert config['functions']['physnemo__solve']['agent_configured'] is True
    assert config['functions']['physnemo__solve']['agent_name'] == 'physnemo_agent'


def test_unconfigured_install_mode(root: Path) -> None:
    home = root / 'unconfigured-home'
    module = load_module(home, None, 'unconfigured')
    # Keep this test deterministic and independent of any service on the build host.
    module._detect_einfra_openwebui_runtime = lambda: {'attempts': []}
    module._discover_local_openwebui_base_url = lambda *_args: ('', [])
    secret = module._resolve_physnemo_agent_secret({
        'physnemo_agent_auto_detect': True,
        'physnemo_agent_base_url': '',
        'physnemo_agent_model': '',
        'physnemo_agent_api_key_file': '',
        'physnemo_openwebui_url': '',
        'physnemo_openwebui_api_key_file': '',
    })
    assert secret['configured'] is False
    assert secret['agent_transport'] == 'unconfigured'
    assert 'not configured' in secret['configuration_error']
    component = module.physnemo_component()
    rendered = component.render_nat_config(
        '/managed/source', 'v2.2.2', '/managed/artifacts',
        'http://127.0.0.1:8200/physnemo/artifacts', 'y' * 64,
        agent_model='engineering-mcp-unconfigured',
        agent_base_url='http://127.0.0.1:9/api',
        agent_configured=False,
        agent_configuration_error=secret['configuration_error'],
    )
    config = yaml.safe_load(rendered)
    assert 'llms' not in config
    assert 'physnemo_agent' not in config['functions']
    assert config['functions']['physnemo__solve']['agent_configured'] is False
    assert config['functions']['physnemo__solve']['agent_name'] is None
    assert 'configuration_error' in config['functions']['physnemo__solve']
    assert set(component.EXPECTED_TOOLS).issubset(config['functions'])

    # Exercise the exact production asset-writing path that previously raised
    # "The general NeMo Agent Toolkit workflow requires an OpenAI-compatible LLM".
    written: dict[str, tuple[str, str]] = {}
    original_write = component.wsl_write_file
    component.wsl_write_file = lambda _distro, path, content, mode='600': written.__setitem__(path, (content, mode))
    try:
        module._write_integrated_physnemo_assets({
            'distro': 'TestDistro',
            'linux_install_dir': '/managed',
            'source_ref': 'v2.2.2',
            'artifact_root': '/managed/artifacts',
            'artifact_base_url': 'http://127.0.0.1:8200/physnemo/artifacts',
            'artifact_secret': 'z' * 64,
            'nat_port': 9911,
            'agent_base_url_for_wsl': 'http://127.0.0.1:9/api',
            'openwebui_bridge_url': '',
        })
    finally:
        component.wsl_write_file = original_write
    managed_config = written['/managed/config/physnemo.yml'][0]
    assert 'llms:' not in managed_config
    assert 'agent_configured: false' in managed_config
    managed_env = written['/managed/config/runtime.env'][0]
    assert 'PHYSNEMO_AGENT_API_KEY_B64=' in managed_env


def test_openwebui_as_agent_transport(root: Path) -> None:
    home = root / 'openwebui-home'
    module = load_module(home, None, 'openwebui')
    module._detect_einfra_openwebui_runtime = lambda: {'attempts': []}
    key_file = root / 'openwebui.key'
    key_file.write_text('openwebui-user-key\n', encoding='utf-8')
    with OpenWebUIMock() as mock:
        secret = module._resolve_physnemo_agent_secret({
            'physnemo_agent_auto_detect': False,
            'physnemo_agent_base_url': '',
            'physnemo_agent_model': '',
            'physnemo_agent_api_key_file': '',
            'physnemo_openwebui_url': mock.root,
            'physnemo_openwebui_api_key_file': str(key_file),
        })
    assert secret['configured'] is True, secret
    assert secret['agent_transport'] == 'openwebui-chat-api'
    assert secret['agent_base_url'] == mock.root + '/api'
    assert secret['agent_model'] == 'e-infra.test-model'
    assert secret['agent_api_key'] == 'openwebui-user-key'
    assert secret['openwebui_base_url'] == mock.root
    report = json.loads(module.PHYSNEMO_AGENT_DETECTION_REPORT.read_text(encoding='utf-8'))
    assert report['configured'] is True
    assert report['openwebui_model_ids'] == ['e-infra.test-model']
    assert any(item['path'] == '/api/models' for item in mock.requests)


def test_static_contract(root: Path) -> None:
    module = load_module(root / 'static-home', None, 'static')
    component = module.physnemo_component()
    assert component.EXPECTED_TOOLS == (
        'physnemo__environment_info', 'physnemo__solve', 'physnemo__job_status',
        'physnemo__list_artifacts', 'physnemo__get_artifact'
    )
    text = SOURCE.read_text(encoding='utf-8')
    assert 'upload_file_to_openwebui' in text  # validator data only
    assert 'ToolCall="python"' in text       # validator data only
    assert 'upload_file_to_openwebui' not in component.PLUGIN_REGISTER
    assert 'ToolCall="python"' not in component.PLUGIN_REGISTER
    assert 'physnemo__start_pinn_karman' not in text
    assert 'physnemo__pinn_run_status' not in text
    assert 'NAT_AGENT_OPTIONAL_INSTALL_V1' in text
    assert 'PHYSNEMO_AGENT_DETECTION_REPORT' in text
    assert 'configuration_required' in component.PLUGIN_REGISTER
    assert module._url_for_wsl('http://127.0.0.1:11434/v1', '172.20.16.1') == 'http://172.20.16.1:11434/v1'
    assert module._url_for_wsl('https://provider.example/v1', '172.20.16.1') == 'https://provider.example/v1'

    parser = module.build_parser()
    args = parser.parse_args([
        '--resume', '--physnemo-agent-base-url', 'http://localhost:11434/v1',
        '--physnemo-agent-model', 'local-model', '--no-physnemo-agent-auto-detect',
        '--physnemo-openwebui-url', 'http://localhost:8080',
        '--physnemo-artifact-base-url', 'http://localhost:8200/physnemo/artifacts',
    ])
    assert args.physnemo_agent_base_url == 'http://localhost:11434/v1'
    assert args.physnemo_agent_model == 'local-model'
    assert args.physnemo_agent_auto_detect is False
    assert args.physnemo_openwebui_url == 'http://localhost:8080'


def main() -> None:
    with tempfile.TemporaryDirectory(prefix='unified-v293-test-') as td:
        root = Path(td)
        test_direct_runtime_provider(root)
        print('PASS: direct runtime provider')
        test_unconfigured_install_mode(root)
        print('PASS: LLM-unconfigured installation mode')
        test_openwebui_as_agent_transport(root)
        print('PASS: Open WebUI API as agent transport')
        test_static_contract(root)
        print('PASS: static contracts')
    print('UNIFIED_V2912_AGENT_OPTIONAL_TESTS_OK')


if __name__ == '__main__':
    main()

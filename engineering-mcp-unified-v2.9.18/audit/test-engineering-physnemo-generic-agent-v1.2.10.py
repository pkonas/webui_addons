from __future__ import annotations

import asyncio
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

from pydantic import BaseModel
from pydantic_core import core_schema

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'engineering_physnemo_nat-register-v1.2.10.py'

REGISTRY: dict[type, Any] = {}

class FunctionBaseConfig(BaseModel):
    model_config = {'extra': 'forbid'}
    def __init_subclass__(cls, name=None, **kwargs):
        super().__init_subclass__(**kwargs)
        cls.__nat_name__ = name

class FunctionRef(str):
    @classmethod
    def __get_pydantic_core_schema__(cls, _source_type, _handler, **_kwargs):
        return core_schema.no_info_plain_validator_function(cls)

class Builder: ...

class FunctionInfo:
    def __init__(self, fn, input_schema=None, description=''):
        self.fn = fn
        self.input_schema = input_schema
        self.description = description
    @classmethod
    def from_fn(cls, fn, input_schema=None, description=''):
        return cls(fn, input_schema, description)

def register_function(*, config_type):
    def deco(fn):
        REGISTRY[config_type] = fn
        return fn
    return deco

mods = {
    'nat': types.ModuleType('nat'),
    'nat.builder': types.ModuleType('nat.builder'),
    'nat.builder.builder': types.ModuleType('nat.builder.builder'),
    'nat.builder.function_info': types.ModuleType('nat.builder.function_info'),
    'nat.cli': types.ModuleType('nat.cli'),
    'nat.cli.register_workflow': types.ModuleType('nat.cli.register_workflow'),
    'nat.data_models': types.ModuleType('nat.data_models'),
    'nat.data_models.component_ref': types.ModuleType('nat.data_models.component_ref'),
    'nat.data_models.function': types.ModuleType('nat.data_models.function'),
}
mods['nat.builder.builder'].Builder = Builder
mods['nat.builder.function_info'].FunctionInfo = FunctionInfo
mods['nat.cli.register_workflow'].register_function = register_function
mods['nat.data_models.component_ref'].FunctionRef = FunctionRef
mods['nat.data_models.component_ref'].LLMRef = FunctionRef
mods['nat.data_models.function'].FunctionBaseConfig = FunctionBaseConfig
old = {name: sys.modules.get(name) for name in mods}
sys.modules.update(mods)
try:
    spec = importlib.util.spec_from_file_location('generic_physnemo_plugin_test', SOURCE)
    assert spec and spec.loader
    plugin = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = plugin
    spec.loader.exec_module(plugin)
    plugin.PhysNeMoSolveConfig.model_rebuild(_types_namespace=plugin.__dict__)
finally:
    for name, value in old.items():
        if value is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = value

async def first_yield(generator):
    async for item in generator:
        return item
    raise AssertionError('registration yielded nothing')

class FakeAgent:
    async def ainvoke(self, prompt: str) -> str:
        assert 'general engineering' in prompt.lower()
        assert 'predefined benchmark' in prompt.lower()
        ctx = plugin._current_context()
        artifacts = Path(ctx['artifacts'])
        workspace = Path(ctx['workspace'])
        staged = plugin._workspace_read(
            plugin.WorkspaceReadInput(relative_path='inputs/problem.txt'), Path(ctx['job_root'])
        )
        assert 'arbitrary PDE' in staged['content']
        webui_staged = plugin._workspace_read(
            plugin.WorkspaceReadInput(relative_path='inputs/webui.txt'), Path(ctx['job_root'])
        )
        assert 'real Open WebUI file bytes' in webui_staged['content']
        (workspace / 'solution.py').write_text("print('general test')\n", encoding='utf-8')
        # Minimal valid PNG (1x1 transparent)
        png = bytes.fromhex(
            '89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489'
            '0000000d49444154789c6360000000020001e221bc330000000049454e44ae426082'
        )
        (artifacts / 'result.png').write_bytes(png)
        (artifacts / 'report.md').write_text('# General result\nNo benchmark is hard-coded.\n', encoding='utf-8')
        return 'Solved a general engineering task and produced result.png and report.md.'

class FakeBuilder:
    async def get_function(self, name: str):
        assert name == 'physnemo_agent'
        return FakeAgent()

async def run_test() -> None:
    with tempfile.TemporaryDirectory(prefix='physnemo-generic-test-') as td:
        root = Path(td)
        source_root = root / 'source'
        source_root.mkdir()
        (source_root / 'README.md').write_text('PhysicsNeMo generic source\n', encoding='utf-8')
        artifact_root = root / 'jobs'

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                return
            def do_GET(self):
                assert self.path == '/input-files/file_real_12345678'
                assert self.headers.get('X-Engineering-MCP-Bridge') == 'bridge-secret'
                data = b'real Open WebUI file bytes\n'
                self.send_response(200)
                self.send_header('Content-Type', 'text/plain')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            unconfigured = plugin.PhysNeMoSolveConfig(
                agent_name='',
                agent_configured=False,
                configuration_error='No LLM credentials were supplied',
                source_root=str(source_root),
                source_ref='test-ref',
                artifact_root=str(artifact_root),
                artifact_base_url='http://127.0.0.1:8200/physnemo/artifacts',
                artifact_secret='s' * 64,
            )
            unconfigured_info = await first_yield(plugin.register_solve(unconfigured, FakeBuilder()))
            unconfigured_result = json.loads(await unconfigured_info.fn(plugin.SolveInput(task='general task')))
            assert unconfigured_result['status'] == 'configuration_required'
            assert unconfigured_result['configured'] is False

            config = plugin.PhysNeMoSolveConfig(
                agent_name='physnemo_agent',
                agent_configured=True,
                source_root=str(source_root),
                source_ref='test-ref',
                artifact_root=str(artifact_root),
                artifact_base_url='http://127.0.0.1:8200/physnemo/artifacts',
                artifact_secret='s' * 64,
                openwebui_bridge_url=f'http://127.0.0.1:{server.server_port}',
                openwebui_bridge_secret='bridge-secret',
            )
            info = await first_yield(plugin.register_solve(config, FakeBuilder()))
            raw = await info.fn(plugin.SolveInput(
                task='Find an appropriate PhysicsNeMo solution for an arbitrary PDE.',
                input_files=[
                    plugin.InputFile(name='problem.txt', text='arbitrary PDE input data'),
                    plugin.InputFile(name='webui.txt', openwebui_file_id='file_real_12345678'),
                ],
                expected_artifacts=['report', 'plot'],
            ))
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=5)
        response = json.loads(raw)
        assert response['state'] == 'completed', response
        assert 'physnemo__render_artifacts' in response['artifact_usage']
        assert 'clipboard' in response['artifact_usage']
        assert response['artifact_count'] >= 4, response  # report, solution, PNG, ZIP
        names = {entry['name'] for entry in response['artifacts']}
        assert 'result.png' in names
        assert 'report.md' in names
        assert any(name.endswith('.zip') for name in names)
        assert not any('karman' in name.lower() for name in names)
        job_id = response['job_id']

        get_config = plugin.PhysNeMoPublicConfig(
            operation='get_artifact',
            source_root=str(source_root),
            source_ref='test-ref',
            artifact_root=str(artifact_root),
            artifact_base_url='http://127.0.0.1:8200/physnemo/artifacts',
            artifact_secret='s' * 64,
        )
        get_info = await first_yield(plugin.register_public(get_config, FakeBuilder()))
        image = await get_info.fn(plugin.GetArtifactInput(job_id=job_id, artifact_name='result.png'))
        assert image.startswith('data:image/png;base64,')
        text = json.loads(await get_info.fn(plugin.GetArtifactInput(job_id=job_id, artifact_name='report.md')))
        assert 'General result' in text['content']
        assert text['download_url'].startswith('http://127.0.0.1:8200/physnemo/artifacts/')

        status_config = plugin.PhysNeMoPublicConfig(
            operation='job_status', source_root=str(source_root), source_ref='test-ref',
            artifact_root=str(artifact_root), artifact_base_url='http://x', artifact_secret='s' * 64,
        )
        status_info = await first_yield(plugin.register_public(status_config, FakeBuilder()))
        status = json.loads(await status_info.fn(plugin.JobStatusInput(job_id=job_id)))
        assert status['state'] == 'completed'

        assert 'start_pinn_karman' not in SOURCE.read_text(encoding='utf-8')
        assert 'pinn_run_status' not in SOURCE.read_text(encoding='utf-8')
        print('GENERIC_PHYSNEMO_PLUGIN_TEST_OK')

if __name__ == '__main__':
    asyncio.run(run_test())

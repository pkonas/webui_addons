"""Installed-config and installer-wiring tests; MOCK SDK/model/WSL, real files and subprocesses.
The end-to-end in-process probe uses the actual native dispatcher, not a fake success report.
"""
import asyncio
import base64
import importlib.util
import json
import shlex
import subprocess
import sys
import types
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
import test_native_dispatch_v2918 as native

ROOT=Path(__file__).resolve().parents[1]
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
main=load('native_preflight_main',ROOT/'audit/engineering_mcp_unified-v2.9.18.py')
probe=load('native_installed_check',ROOT/'check-physnemo-native-tools-v2.9.18.py')
CONTRACT=probe.CONTRACT

def good():
    phase = {'success':True,'missing_tools':[], 'exact_content_roundtrip':True, 'script_exact':True,
             'execution_summary':{'succeeded':1,'attempts':1,'failed':0},
             'tool_summary':{'succeeded':7,'attempts':7,'failed':0}}
    return {**phase,'contract':CONTRACT,'preflight_contract':'PHYSNEMO_NATIVE_TOOL_PREFLIGHT_V5',
            'local_probe':dict(phase),'model_probe':dict(phase),'model_summary':{'tool_calls':7},
            'selected_tool_transport':'native','native_tool_calls_verified':True,'model_tool_execution_verified':True}


def values():
    return {'PHYSNEMO_AGENT_BASE_URL':'https://provider.example/v1','PHYSNEMO_AGENT_MODEL':'test-only',
            'PHYSNEMO_AGENT_API_KEY':'TEST_ONLY_DO_NOT_EXPOSE'}

def test_base64_runtime_env_and_never_source_shell(tmp_path):
    sentinel=tmp_path/'no-side-effects'
    v=values(); v['PHYSNEMO_AGENT_MODEL']='Kármán model'
    env=tmp_path/'runtime.env'
    env.write_text('\ufeff'+''.join(k+'_B64='+shlex.quote(base64.b64encode(x.encode()).decode())+'\n' for k,x in v.items())+
        f'touch {shlex.quote(str(sentinel))}\nUNKNOWN_B64=notbase64\n')
    assert probe.read_env(env)==v and not sentinel.exists()

@pytest.mark.parametrize('raw',['@@@@','aGVsbG8= other'])
def test_malformed_private_assignments_fail(tmp_path,raw):
    f=tmp_path/'runtime.env';f.write_text('PHYSNEMO_AGENT_API_KEY_B64='+raw)
    with pytest.raises(Exception):probe.read_env(f)

@pytest.mark.parametrize('host,expected',[('172.20.16.1','172.20.16.1'),('2001:db8::1','[2001:db8::1]')])
def test_openwebui_runtime_host_is_reconstructed(monkeypatch,host,expected):
    monkeypatch.setattr(probe,'windows_host',lambda:host)
    v=values();v.update(PHYSNEMO_AGENT_TRANSPORT='openwebui-chat-api',PHYSNEMO_GATEWAY_PORT='8200',PHYSNEMO_GATEWAY_ROUTE='physnemo')
    assert probe.resolve_env(v)['PHYSNEMO_AGENT_BASE_URL']==f'http://{expected}:8200/physnemo/openwebui-api'
    assert v['PHYSNEMO_AGENT_BASE_URL']=='https://provider.example/v1'

def test_direct_provider_preserved_without_host_resolution(monkeypatch):
    monkeypatch.setattr(probe,'windows_host',lambda:pytest.fail('not a bridge'))
    assert probe.resolve_env(values())==values()

@pytest.mark.parametrize('change',[{'PHYSNEMO_AGENT_MODEL':''},{'PHYSNEMO_AGENT_API_KEY':'a\nb'},
    {'PHYSNEMO_AGENT_BASE_URL':'https://user:secret@provider.example/v1'},
    {'PHYSNEMO_AGENT_TRANSPORT':'openwebui-chat-api','PHYSNEMO_GATEWAY_ROUTE':'../api'},
    {'PHYSNEMO_AGENT_TRANSPORT':'openwebui-chat-api','PHYSNEMO_GATEWAY_PORT':'65536'}])
def test_bad_runtime_config_rejected(change):
    v=values();v.update(change)
    with pytest.raises((RuntimeError,ValueError)):probe.resolve_env(v)

@pytest.fixture
def wiring(tmp_path,monkeypatch):
    secret=tmp_path/'secret.json';secret.write_text(json.dumps({'agent_model':'test-only'}))
    monkeypatch.setattr(main,'PHYSNEMO_AGENT_SECRET_FILE',secret)
    monkeypatch.setattr(main,'PHYSNEMO_AGENT_BRIDGE_PREFLIGHT_REPORT',tmp_path/'bridge.json')
    return {'physnemo_runtime':{'configured':True,'distro':'test-distro','linux_install_dir':'/managed/root with space'}}

@pytest.mark.parametrize('report,rc,ok',[(good(),0,True),(good(),2,False),
    ({'success':True},0,False),({**good(),'contract':'old'},0,False),
    ({**good(),'missing_tools':['workspace_run_python']},0,False),
    ({**good(),'execution_summary':None},0,False),
    ({**good(),'execution_summary':{'succeeded':0}},0,False),
    ({**good(),'exact_content_roundtrip':False},0,False)])
def test_install_gate_requires_real_contract_not_bare_success(wiring,tmp_path,monkeypatch,report,rc,ok):
    class Component:
        shell_path=staticmethod(shlex.quote)
        def wsl_run(self,distro,script,**kw):
            assert distro=='test-distro' and kw['check'] is False and kw['timeout']>=240
            assert kw['stage']=='physnemo-native-tools-preflight'
            assert 'TEST_ONLY_DO_NOT_EXPOSE' not in script
            subprocess.run(['bash','-n'],input=script,text=True,check=True,capture_output=True)
            return types.SimpleNamespace(returncode=rc,stdout='noise\n'+json.dumps(report)+'\n')
    monkeypatch.setattr(main,'physnemo_component',lambda:Component())
    result=main.probe_physnemo_native_tools(wiring)
    assert result['success'] is ok and result['attempted'] is True
    assert (tmp_path/'physnemo-native-tools-preflight.json').exists()
    if not ok:assert result.get('error')

def test_unconfigured_agent_cannot_become_verified(wiring,monkeypatch,tmp_path):
    (tmp_path/'secret.json').write_text('{}')
    monkeypatch.setattr(main,'physnemo_component',lambda:pytest.fail('no WSL without configuration'))
    r=main.probe_physnemo_native_tools(wiring)
    assert not r['success'] and not r['attempted'] and r['skipped']

def test_installed_checker_uses_shared_dispatcher_with_real_process(tmp_path,monkeypatch):
    # MOCK SDK and NAT imports. All six underlying tools and stdlib subprocess are REAL.
    messages=types.ModuleType('langchain_core.messages')
    for name in ('HumanMessage','SystemMessage','ToolMessage'):setattr(messages,name,native.Message)
    monkeypatch.setitem(sys.modules,'langchain_core',types.ModuleType('langchain_core'))
    monkeypatch.setitem(sys.modules,'langchain_core.messages',messages)
    module=types.ModuleType('langchain_openai')
    def client(**kw):
        assert kw['api_key']==values()['PHYSNEMO_AGENT_API_KEY'] and kw['max_retries']==0
        return native.ProbeModel()
    module.ChatOpenAI=client
    monkeypatch.setitem(sys.modules,'langchain_openai',module)
    monkeypatch.setitem(sys.modules,'engineering_physnemo_nat',types.ModuleType('engineering_physnemo_nat'))
    monkeypatch.setitem(sys.modules,'engineering_physnemo_nat.register',native.p)
    monkeypatch.setattr(probe.importlib.metadata,'version',lambda name:'TEST-DOUBLE-NOT-INSTALLED')
    (tmp_path/'physicsnemo-source').mkdir();(tmp_path/'physicsnemo-source/README.md').write_text('PhysicsNeMo fixture')
    r=asyncio.run(probe.check(tmp_path,values()))
    assert r['success'] and r['execution_summary']['succeeded']==1 and r['missing_tools']==[]
    assert 'TEST_ONLY_DO_NOT_EXPOSE' not in json.dumps(r)
    assert json.loads((Path(r['probe_directory'])/'status.json').read_text())['state']=='completed'

def test_embedded_native_diagnostic_is_exact_file():
    assert main.PHYSNEMO_NATIVE_TOOLS_CHECK_SOURCE==(ROOT/'check-physnemo-native-tools-v2.9.18.py').read_text()
    source=(ROOT/'audit/engineering_mcp_unified-v2.9.18.py').read_text()
    assert 'package_failures.append("physnemo-native-tools-roundtrip")' in source

@pytest.mark.parametrize('marker,ok',[(CONTRACT,True),('old-version',False),(None,False)])
def test_mcp_probe_checks_running_plugin_not_only_installed_files(monkeypatch,capsys,marker,ok):
    class Session:
        def __init__(self,*a):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*a):pass
        async def initialize(self):return types.SimpleNamespace(serverInfo=types.SimpleNamespace(name='test'))
        async def list_tools(self):return types.SimpleNamespace(tools=[types.SimpleNamespace(name=n) for n in main.PHYSNEMO_EXPECTED_TOOLS])
        async def call_tool(self,name,args):
            assert name=='physnemo__environment_info' and args=={'detail':False}
            return types.SimpleNamespace(isError=False,content=[types.SimpleNamespace(text=json.dumps({'native_tool_contract':marker}))])
    @asynccontextmanager
    async def streamablehttp_client(**kwargs):yield ('reader','writer')
    mod=types.ModuleType('mcp');mod.ClientSession=Session
    nested=types.ModuleType('mcp.client.streamable_http');nested.streamablehttp_client=streamablehttp_client
    monkeypatch.setitem(sys.modules,'mcp',mod);monkeypatch.setitem(sys.modules,'mcp.client',types.ModuleType('mcp.client'))
    monkeypatch.setitem(sys.modules,'mcp.client.streamable_http',nested)
    rc=main.run_mcp_http_probe(['--url','http://test-only/mcp','--route','physnemo'])
    result=json.loads(capsys.readouterr().out)
    assert result['success'] is ok and (rc==0) is ok
    if not ok:assert 'PHYSNEMO_NATIVE_RUNNING_PLUGIN_STALE' in result['error']

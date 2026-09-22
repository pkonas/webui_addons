# Historical native-only branch tests. Automatic compatibility is tested separately.
"""v2.9.18 incident regressions: real filesystem/subprocess, MOCK model/NAT/SDK."""
import asyncio
import json
from pathlib import Path
import types

import pytest
import test_native_dispatch_v2918 as n
import test_native_preflight_v2918 as installer

p = n.p

@pytest.fixture(autouse=True)
def message_sdk(monkeypatch):
    import sys
    module=types.ModuleType('langchain_core.messages')
    for name in ('SystemMessage','HumanMessage','ToolMessage'):setattr(module,name,n.Message)
    monkeypatch.setitem(sys.modules,'langchain_core',types.ModuleType('langchain_core'))
    monkeypatch.setitem(sys.modules,'langchain_core.messages',module)

@pytest.fixture
def source(tmp_path):
    root=tmp_path/'source';root.mkdir();(root/'README.md').write_text('PhysicsNeMo local test fixture\n')
    return root


def test_no_tool_calls_is_not_a_missing_diagnostic_file(source,tmp_path):
    model=n.Model(n.AI('No native functions are available.'))
    result=asyncio.run(p.native_tool_preflight(model,source,tmp_path/'probes', tool_transport="native"))
    assert result['error']=='PHYSNEMO_NATIVE_TOOL_CALLS_MISSING'
    assert result['exception_type']=='NativeToolProtocolError'
    assert result['failed_stage']=='model_probe.source_search'
    assert result['local_probe']['success'] and result['local_probe']['execution_summary']['succeeded']==1
    assert result['model_probe']['attempted'] and not result['model_probe']['success']
    assert result['execution_summary']['attempts']==0  # MUST NOT inherit local run
    assert result['tool_summary']['attempts']==0
    assert result['model_summary']['requests']==result['model_summary']['responses']==1
    assert result['model_summary']['tool_calls']==0
    assert len(model.histories)==1  # No blind retry or another model
    assert result['model_summary']['last_response']['text_present'] is True
    assert p._JOB_CONTEXT.get() is None
    model_root=Path(result['model_probe']['probe_directory'])
    assert (model_root/'tool-events.jsonl').read_text()==''
    events=[json.loads(line) for line in (model_root/'model-events.jsonl').read_text().splitlines()]
    assert [e['phase'] for e in events if e['phase'] in {'request','response'}]==['request','response']
    assert [e['phase'] for e in events if e['phase'].startswith('request_')]==['request_started','request_finished']
    assert json.loads((Path(result['probe_directory'])/'preflight.json').read_text())==result
    assert json.loads((model_root/'status.json').read_text())['state']=='failed'


def test_model_phase_does_not_accept_local_files_as_proof(source,tmp_path):
    result=asyncio.run(p.native_tool_preflight(n.Model(n.AI('Success!')),source,tmp_path/'probes', tool_transport="native"))
    local=Path(result['local_probe']['probe_directory']);model=Path(result['model_probe']['probe_directory'])
    assert local!=model
    assert (local/'artifacts/tool_probe.json').is_file()
    assert not (model/'artifacts/tool_probe.json').exists()
    assert not result['exact_content_roundtrip'] and not result['success']
    assert len(result['missing_tools'])==6


def test_all_seven_explicit_calls_reach_the_real_implementations(source,tmp_path):
    model=n.ProbeModel()
    result=asyncio.run(p.native_tool_preflight(model,source,tmp_path/'probes', tool_transport="native"))
    assert result['success']
    assert result['preflight_contract']=='PHYSNEMO_NATIVE_TOOL_PREFLIGHT_V5'
    assert result['model_summary']['tool_calls']==result['model_summary']['requests']==7
    assert len(model.histories)==7
    for mode in ('local_probe','model_probe'):
        phase=result[mode]
        assert phase['success'] and phase['script_exact'] and phase['exact_content_roundtrip']
        assert phase['tool_summary']['succeeded']==7 and phase['execution_summary']['succeeded']==1
        root=Path(phase['probe_directory'])
        assert (root/'workspace/tool_probe.py').is_file()
        assert json.loads((root/'artifacts/tool_probe.json').read_text())['text'].startswith('Kármán:')
    assert result['local_probe']['model_summary']['requests']==0
    assert p._JOB_CONTEXT.get() is None


@pytest.mark.parametrize('response,code',[
    (n.AI(''), 'PHYSNEMO_NATIVE_TOOL_CALLS_MISSING'),
    (n.AI('No',finish='content_filter'),'PHYSNEMO_NATIVE_MODEL_REFUSED'),
    (n.AI('Truncated',finish='length'),'PHYSNEMO_MODEL_OUTPUT_TRUNCATED'),
    (n.AI(invalid=[{'args':'malformed private arguments'}]),'PHYSNEMO_NATIVE_ARGUMENTS_INVALID'),
    (n.AI(calls=[n.call('workspace_list',{})]),'PHYSNEMO_NATIVE_TOOL_CHOICE_NOT_HONORED'),
    (n.AI(calls=[n.call('source_search',{'query':'PhysicsNeMo','max_results':1}),n.call('source_search',{'query':'PhysicsNeMo'},'x')]),'PHYSNEMO_NATIVE_TOOL_CHOICE_NOT_HONORED'),
    (n.AI(calls=[n.call('source_search',{'query':'different-private-query'})]),'PHYSNEMO_NATIVE_PROBE_ARGUMENT_MISMATCH'),
    (n.AI(calls=[n.call('source_search',{'query':'PhysicsNeMo','max_results':1},'')]),'PHYSNEMO_DUPLICATE_OR_INVALID_TOOL_CALL_ID'),
])
def test_model_protocol_errors_remain_distinct(source,tmp_path,response,code):
    result=asyncio.run(p.native_tool_preflight(n.Model(response),source,tmp_path/'probes', tool_transport="native"))
    assert result['error']==code and not result['success']
    assert result['local_probe']['success']
    assert result['tool_summary']['attempts']==0
    assert 'private arguments' not in json.dumps(result)
    assert 'different-private-query' not in json.dumps(result)


def test_provider_exception_preserves_stack_shape_but_not_secret_text(source,tmp_path):
    class BadRequestError(RuntimeError):status_code=400
    class Model(n.Model):
        async def ainvoke(self,messages):
            raise BadRequestError('api_key=TOP_SECRET and PRIVATE_MODEL_CONTENT')
    result=asyncio.run(p.native_tool_preflight(Model(),source,tmp_path/'probes', tool_transport="native"))
    assert result['exception_type']=='BadRequestError' and result['http_status']==400
    assert result['failed_stage']=='model_probe.source_search'
    assert result['model_summary']['requests']==1 and result['model_summary']['responses']==0
    assert result['stack_locations']
    for file in Path(result['probe_directory']).rglob('*.json*'):
        assert 'TOP_SECRET' not in file.read_text() and 'PRIVATE_MODEL_CONTENT' not in file.read_text()
    assert p._JOB_CONTEXT.get() is None


def test_real_missing_source_stops_local_probe_before_any_model_request(tmp_path):
    model=n.Model()
    result=asyncio.run(p.native_tool_preflight(model,tmp_path/'missing-source',tmp_path/'probes', tool_transport="native"))
    assert result['error']=='PHYSNEMO_LOCAL_TOOL_PREFLIGHT_FAILED'
    assert result['failed_stage']=='local_probe.source_search'
    assert result['local_probe']['tool_error_code']=='PHYSNEMO_SOURCE_UNAVAILABLE'
    assert result['model_probe']['attempted'] is False and not model.histories
    assert result['local_probe']['tool_summary']['failed']==1
    assert p._JOB_CONTEXT.get() is None


def test_missing_readme_is_not_confused_with_model_transport_failure(tmp_path):
    source=tmp_path/'source';source.mkdir()
    result=asyncio.run(p.native_tool_preflight(n.Model(),source,tmp_path/'probes', tool_transport="native"))
    assert result['failed_stage']=='local_probe.source_read'
    assert result['local_probe']['tool_error_code']=='FILE_NOT_FOUND'
    assert result['model_probe']['attempted'] is False


def test_missing_event_file_is_an_empty_snapshot_not_exception(tmp_path):
    paths=p._job_paths(tmp_path,'probe-snapshot')
    paths['root'].mkdir()
    r=p._native_probe_snapshot(paths,{'nonce':'expected'},'script')
    assert r['event_log_present'] is False and r['success'] is False
    assert r['execution_summary']['attempts']==0 and len(r['missing_tools'])==6


def test_changed_probe_script_is_not_executed(source,tmp_path):
    class Modified(n.ProbeModel):
        async def ainvoke(self,messages):
            response=await super().ainvoke(messages)
            call=response.tool_calls[0]
            if call['name'].endswith('__workspace_write'):
                call['args']['content'] += 'raise RuntimeError("extra content")\n'
            return response
    r=asyncio.run(p.native_tool_preflight(Modified(),source,tmp_path/'probes', tool_transport="native"))
    assert r['error']=='PHYSNEMO_NATIVE_PROBE_ARGUMENT_MISMATCH'
    assert r['failed_stage']=='model_probe.workspace_write'
    assert r['execution_summary']['attempts']==0
    assert not list((Path(r['model_probe']['probe_directory'])/'workspace').iterdir())


def test_optional_defaults_can_be_explicit_without_changing_requested_call(source,tmp_path):
    class Defaults(n.ProbeModel):
        async def ainvoke(self,messages):
            response=await super().ainvoke(messages)
            call=response.tool_calls[0];op=call['name'].split('__')[-1]
            call['args']=p.TOOL_SPECS[op][0].model_validate(call['args']).model_dump()
            return response
    assert asyncio.run(p.native_tool_preflight(Defaults(),source,tmp_path/'probes', tool_transport="native"))['success']


def test_cancelled_probe_resets_context(source,tmp_path):
    class Cancel(n.Model):
        async def ainvoke(self,messages):raise asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(p.native_tool_preflight(Cancel(),source,tmp_path/'probes', tool_transport="native"))
    assert p._JOB_CONTEXT.get() is None
    status=next((tmp_path/'probes').glob('probe-*/model-*/status.json'))
    assert json.loads(status.read_text())['state']=='cancelled'


def test_required_mode_returns_to_auto_after_successful_execution(tmp_path):
    class Track(n.Model):
        def __init__(self,*args):super().__init__(*args);self.choices=[]
        def bind_tools(self,schemas,**kwargs):
            parent=self
            class Bound:
                async def ainvoke(self,messages):
                    parent.choices.append(kwargs.get('tool_choice','auto'))
                    return await parent.ainvoke(messages)
            return Bound()
    model=Track(n.AI(calls=[n.call('workspace_write',{'relative_path':'workspace/a.py','content':'print("ok")\n'},'a'),
                            n.call('workspace_run_python',{'script_relative_path':'workspace/a.py'},'b')]),n.AI('Actual run completed'))
    with n.job(tmp_path,True):
        assert asyncio.run(p._run_native_agent(model,'Execute a script',tmp_path/'source', tool_transport="native"))=='Actual run completed'
    assert model.choices==['required','auto']


@pytest.mark.parametrize('change',[
    {'preflight_contract':'old'},{'local_probe':{'success':False}}, {'model_probe':{'success':False}},
    {'model_summary':{'tool_calls':0}}, {'model_summary':None}, {'contract':'PHYSNEMO_NATIVE_TOOL_DISPATCH_V1'},
    {'model_probe':None}, {'local_probe':None}, {'model_summary':{'tool_calls':6}},
])
def test_installer_rejects_stale_or_partially_passed_native_report(tmp_path,monkeypatch,change):
    main=installer.main
    secret=tmp_path/'secret.json';secret.write_text('{"agent_model":"test-model"}')
    monkeypatch.setattr(main,'PHYSNEMO_AGENT_SECRET_FILE',secret)
    monkeypatch.setattr(main,'PHYSNEMO_AGENT_BRIDGE_PREFLIGHT_REPORT',tmp_path/'bridge.json')
    data={**installer.good(),**change}
    class Component:
        shell_path=staticmethod(lambda s:"'"+s+"'")
        def wsl_run(self,*a,**kw):return types.SimpleNamespace(returncode=0,stdout=json.dumps(data))
    monkeypatch.setattr(main,'physnemo_component',lambda:Component())
    r=main.probe_physnemo_native_tools({'physnemo_runtime':{'configured':True,'distro':'test','linux_install_dir':'/test'}})
    assert not r['success'] and r['returncode']==0
    assert r.get('error')

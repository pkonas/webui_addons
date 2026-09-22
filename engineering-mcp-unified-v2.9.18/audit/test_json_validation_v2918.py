"""JSON validation/repair regressions: scripted model, real Pydantic, files and Python processes.
The rejected responses are synthetic scenarios, NOT captures of the user's model response.
"""
import asyncio
import copy
import json
from pathlib import Path
import pytest
import test_model_transport_v2918 as t
import test_native_dispatch_v2918 as n
p = n.p

@pytest.fixture(autouse=True)
def sdk(monkeypatch):
    import types, sys
    module = types.ModuleType('langchain_core.messages')
    for name in ('HumanMessage', 'SystemMessage', 'ToolMessage'):
        setattr(module, name, n.Message)
    monkeypatch.setitem(sys.modules, 'langchain_core', types.ModuleType('langchain_core'))
    monkeypatch.setitem(sys.modules, 'langchain_core.messages', module)

@pytest.fixture
def source(tmp_path):
    source = tmp_path / 'source'
    source.mkdir()
    (source / 'README.md').write_text('PhysicsNeMo local regression fixture\n')
    return source


def mutate(action, reason):
    a=copy.deepcopy(action)
    if reason=='request_id_mismatch':a['request_id']='old-nonce'
    elif reason=='tool_envelope_fields':a['unwanted_field']='UNLOGGED-SECRET'
    elif reason=='arguments_not_object':a['arguments']=json.dumps(a['arguments'])
    elif reason=='argument_schema':a['arguments']['max_chars']='120000'
    elif reason=='tool_choice_mismatch':a['name']='physnemo_internal__workspace_list'
    elif reason=='protocol_mismatch':a['protocol']='wrong-protocol'
    elif reason=='json_syntax':return n.AI(json.dumps(a)[:-1])
    elif reason=='markdown_fence':return n.AI('```json\n'+json.dumps(a)+'\n```')
    else:raise AssertionError(reason)
    return a

@pytest.mark.parametrize('reason',[
    'request_id_mismatch','tool_envelope_fields','arguments_not_object','argument_schema',
    'tool_choice_mismatch','protocol_mismatch','json_syntax','markdown_fence'])
def test_report_shaped_fifth_step_failure_can_be_regenerated_before_execution(source,tmp_path,reason):
    def change(a,req,index):
        return mutate(a,reason) if index==5 else a
    model=t.JsonProbeModel(change=change)
    report=asyncio.run(p.native_tool_preflight(model,source,tmp_path/'probes'))
    assert report['success'],report
    assert model.native_requests==1 and model.json_requests==8
    assert report['model_summary']['json_repair_requests']==1
    assert report['model_summary']['json_validation_failures']==1
    assert report['model_summary']['last_validation_error']['reason']==reason
    assert report['tool_summary']['attempts']==report['tool_summary']['succeeded']==7
    assert report['execution_summary']['attempts']==report['execution_summary']['succeeded']==1
    assert report['script_exact'] if 'script_exact' in report else report['model_probe']['script_exact']
    assert report['model_tool_execution_verified'] is True
    root=Path(report['model_probe']['probe_directory'])
    events=[json.loads(x) for x in (root/'tool-events.jsonl').read_text().splitlines()]
    assert [e['tool'] for e in events if e['phase']=='started']==[
        'source_search','source_read','workspace_list','workspace_write','workspace_read','workspace_run_python','workspace_read']
    assert (root/'artifacts/tool_probe.json').stat().st_size>0
    logs=json.dumps(report)+(root/'model-events.jsonl').read_text()
    assert 'UNLOGGED-SECRET' not in logs and 'old-nonce' not in logs


def test_persistent_invalid_fifth_step_has_bounded_requests_and_precise_diagnostic(source,tmp_path):
    model=t.JsonProbeModel(change=lambda a,req,index: mutate(a,'request_id_mismatch') if index>=5 else a)
    report=asyncio.run(p.native_tool_preflight(model,source,tmp_path/'probes'))
    assert not report['success'] and report['error']=='PHYSNEMO_JSON_ACTION_INVALID'
    assert report['failed_stage']=='model_probe.workspace_read'
    assert report['validation_error']['reason']=='request_id_mismatch'
    assert report['validation_error']['attempt']==3
    assert model.json_requests==7
    assert report['tool_summary']['succeeded']==4 and report['execution_summary']['attempts']==0
    assert report['model_summary']['json_repair_requests']==2
    assert report['model_summary']['json_validation_failures']==3
    assert not t.ins.main._physnemo_model_execution_verified(report)


def test_repair_prompt_has_fresh_nonce_actual_schema_and_only_pending_named_tool(tmp_path):
    seen=[]
    class Model:
        def bind(self,**options):assert options=={'tools':[]};return self
        async def ainvoke(self,messages):
            request=json.loads(messages[-1].content);seen.append(request)
            schema=request['response_schema']['oneOf']
            assert schema[0]['properties']['request_id']=={'const':request['request_id']}
            assert schema[0]['properties']['name']['const']=='physnemo_internal__workspace_read'
            assert len(request['tools'])==1
            action={'protocol':request['protocol'],'request_id':request['request_id'],
                    'type':'tool','name':'physnemo_internal__workspace_read',
                    'arguments':{'relative_path':'workspace/a.py'}}
            if len(seen)==1:action['extra']='SECRET-NOT-SENT-BACK'
            return n.AI(json.dumps(action))
    with n.job(tmp_path):
        action=asyncio.run(p._request_json_action(Model(),[n.Message(content='read the pending file')],choice='physnemo_internal__workspace_read'))
        assert action['request_id']==seen[-1]['request_id']
        assert len(seen)==2 and seen[0]['request_id']!=seen[1]['request_id']
        assert 'validation_feedback' not in seen[0]
        assert seen[1]['validation_feedback']['operation_executed'] is False
        assert 'SECRET-NOT-SENT-BACK' not in json.dumps(seen[1])

@pytest.mark.parametrize('response,code',[
    (n.AI('Sorry, I cannot assist with this request.'),'PHYSNEMO_JSON_ACTION_INVALID'),
    (n.AI('output',finish='length'),'PHYSNEMO_MODEL_OUTPUT_TRUNCATED'),
    (n.AI('refused',finish='content_filter'),'PHYSNEMO_NATIVE_MODEL_REFUSED'),
    (n.AI(calls=[n.call('workspace_read',{'relative_path':'x'})]),'PHYSNEMO_JSON_UNEXPECTED_NATIVE_CALL'),
])
def test_refusal_truncation_prose_unexpected_native_are_never_retried(source,tmp_path,response,code):
    model=t.JsonProbeModel(change=lambda *_:response)
    report=asyncio.run(p.native_tool_preflight(model,source,tmp_path/'probes'))
    assert not report['success'] and report['error']==code
    assert model.json_requests==1 and report['tool_summary']['attempts']==0
    assert report['model_summary'].get('json_repair_requests',0)==0

@pytest.mark.parametrize('kind',['valid_block','bad_nonce_block','bad_fields_block','fenced_block','error_object','refusal_field'])
def test_explicit_blocker_never_retried_or_executed(source,tmp_path,kind):
    def change(a,req,index):
        block={'protocol':a['protocol'],'request_id':a['request_id'],'type':'blocked','reason':'PRIVATE REASON'}
        if kind=='bad_nonce_block':block['request_id']='wrong'
        if kind=='bad_fields_block':block['extra']='x'
        if kind=='fenced_block':return n.AI('```json\n'+json.dumps(block)+'\n```')
        if kind=='error_object':block={'error':'PRIVATE REASON'}
        if kind=='refusal_field':block={'refusal':'PRIVATE REASON'}
        return block
    model=t.JsonProbeModel(change=change)
    report=asyncio.run(p.native_tool_preflight(model,source,tmp_path/'probes'))
    assert not report['success'] and report['error']=='PHYSNEMO_JSON_MODEL_BLOCKED'
    assert model.json_requests==1 and report['tool_summary']['attempts']==0
    assert 'PRIVATE REASON' not in json.dumps(report)


def test_successful_format_repair_cannot_relax_exact_probe_script(source,tmp_path):
    def change(a,req,index):
        if index==4:return mutate(a,'tool_envelope_fields')
        if a['name'].endswith('__workspace_write'):
            a['arguments']['content']+='\nprint("MUTATED-SCRIPT")\n'
        return a
    model=t.JsonProbeModel(change=change)
    report=asyncio.run(p.native_tool_preflight(model,source,tmp_path/'probes'))
    assert not report['success'] and report['error']=='PHYSNEMO_NATIVE_PROBE_ARGUMENT_MISMATCH'
    assert not (Path(report['model_probe']['probe_directory'])/'workspace/tool_probe.py').exists()
    assert report['execution_summary']['attempts']==0

@pytest.mark.parametrize('raw,reason',[
    ('{"a":1,"a":2}','duplicate_key'),('{"a":NaN}','nonfinite_number'),
    ('[1]','root_not_object'),('','empty_response'),('ordinary prose','non_json_text'),
    ('{"x":','json_syntax')])
def test_diagnostic_is_host_metadata_only(raw,reason):
    with pytest.raises(p.JsonActionValidationError) as caught:p._parse_json_action(raw,'current')
    err=caught.value
    assert err.diagnostic['reason']==reason
    assert str(err)=='PHYSNEMO_JSON_ACTION_INVALID'
    safe=p._safe_native_exception(err)
    assert safe['validation_error']['reason']==reason
    assert 'response' not in safe and 'message' not in safe


def test_argument_diagnostic_redacts_unknown_keys_and_values():
    a=t.valid();a['arguments']['PRIVATE-KEY-NAME']='PRIVATE-VALUE'
    with pytest.raises(p.JsonActionValidationError) as caught:p._parse_json_action(json.dumps(a),'current-id')
    text=json.dumps(caught.value.diagnostic)
    assert 'PRIVATE' not in text
    assert '<extra>' in text


def test_normal_agent_repairs_write_format_and_never_duplicates_completed_operation(tmp_path):
    class Model(t.JsonProbeModel):
        async def ainvoke(self,messages):
            if self.mode=='native':return await super().ainvoke(messages)
            self.json_requests+=1;req=json.loads(messages[-1].content)
            a={'protocol':req['protocol'],'request_id':req['request_id'],'type':'tool'}
            if self.json_requests<=2:
                a.update(name='physnemo_internal__workspace_write',arguments={'relative_path':'workspace/a.py',
                    'content':'import os\nfrom pathlib import Path\nPath(os.environ["PHYSNEMO_ARTIFACT_DIR"],"ok.txt").write_text("real run")\n'})
                if self.json_requests==1:a['extra']=False
            elif self.json_requests==3:
                a.update(name='physnemo_internal__workspace_run_python',arguments={'script_relative_path':'workspace/a.py'})
            else:
                a.update(type='final',answer='Run finished. No scientific validation.')
            return n.AI(json.dumps(a))
    with n.job(tmp_path,requires=True):
        answer=asyncio.run(p._run_native_agent(Model(),'Execute the requested Python test',tmp_path/'source'))
        status=p._read_json(tmp_path/'status.json')
        assert 'finished' in answer and status['execution_summary']['attempts']==1
        assert status['tool_summary']['attempts']==2 and status['model_summary']['json_repair_requests']==1
        assert (tmp_path/'artifacts/ok.txt').read_text()=='real run'


def test_cancelled_context_sends_no_request(tmp_path):
    with n.job(tmp_path):
        p._current_context()['cancel_event'].set()
        model=t.JsonProbeModel()
        with pytest.raises(asyncio.CancelledError):asyncio.run(p._request_json_action(model,[]))
        assert model.json_requests==0


def test_recheck_wrapper_integrity_and_no_install_commands():
    import hashlib, re
    root=Path(__file__).resolve().parents[1]
    path=root/'check-installed-physnemo-v2.9.18.ps1'
    data=path.read_bytes()
    assert data.startswith(b'\xef\xbb\xbf') and b'\n' not in data.replace(b'\r\n',b'')
    source=data.decode('utf-8-sig')
    expected=re.search(r'\$ExpectedCheckerSha256 = "([a-f0-9]{64})"',source)[1]
    assert expected==hashlib.sha256((root/'check-physnemo-native-tools-v2.9.18.py').read_bytes()).hexdigest()
    assert '--runtime-env' in source and '--root' in source and '--exec' in source
    assert 'pip install' not in source and 'Remove-Item' not in source
    assert 'physnemo-model-tools-recheck.json' in source


def test_json_validation_diagnostic_is_exposed_without_response_text(tmp_path):
    with n.job(tmp_path):
        diagnostic={'reason':'argument_schema','retryable':True,'attempt':3,'max_attempts':3}
        result=p._public_job_summary({'job_id':'test-job-id','state':'failed','validation_error':diagnostic})
        assert result['validation_error']==diagnostic

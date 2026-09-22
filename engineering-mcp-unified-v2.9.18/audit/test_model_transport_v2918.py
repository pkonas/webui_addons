"""New transport regressions. MOCK model/SDK; REAL files, Python subprocess and dispatcher."""
import asyncio
import copy
import json
from pathlib import Path
import types
import sys
import pytest
import test_native_dispatch_v2918 as n
import test_native_preflight_v2918 as ins
p=n.p

@pytest.fixture(autouse=True)
def sdk(monkeypatch):
    mod=types.ModuleType('langchain_core.messages')
    for name in ('HumanMessage','SystemMessage','ToolMessage'):setattr(mod,name,n.Message)
    monkeypatch.setitem(sys.modules,'langchain_core',types.ModuleType('langchain_core'))
    monkeypatch.setitem(sys.modules,'langchain_core.messages',mod)

@pytest.fixture
def source(tmp_path):
    s=tmp_path/'source';s.mkdir();(s/'README.md').write_text('PhysicsNeMo local fixture\n')
    return s

class JsonProbeModel:
    """Simulate a text-only Pipe, then honor explicitly negotiated JSON actions."""
    def __init__(self, change=None, native_response=None):
        self.mode='native';self.native_requests=0;self.json_requests=0;self.options=[];self.change=change
        self.native_response=native_response or n.AI('This model path returns text only, without native tool calls.')
    def bind_tools(self, schemas, **kwargs):
        self.mode='native';self.options.append(kwargs);return self
    def bind(self, **kwargs):
        assert kwargs=={'tools':[]}
        self.mode='json';return self
    async def ainvoke(self, messages):
        if self.mode=='native':
            self.native_requests+=1
            if isinstance(self.native_response,Exception):raise self.native_response
            return self.native_response
        self.json_requests+=1
        req=json.loads(messages[-1].content)
        last=req['conversation'][-1]['content']
        expected=json.loads(last[last.index('{'):])
        action={'protocol':req['protocol'],'request_id':req['request_id'],'type':'tool',
                'name':expected['name'],'arguments':expected['arguments']}
        if self.change:action=self.change(action,req,self.json_requests)
        return action if isinstance(action,n.AI) else n.AI(json.dumps(action,ensure_ascii=False))


def test_reported_text_only_native_path_can_execute_all_tools_with_explicit_json(source,tmp_path):
    model=JsonProbeModel()
    r=asyncio.run(p.native_tool_preflight(model,source,tmp_path/'probes'))
    assert r['success'],r
    assert model.native_requests==1 and model.json_requests==7
    assert r['selected_tool_transport']=='json_actions_v1'
    assert r['native_probe_error']=='PHYSNEMO_NATIVE_TOOL_CALLS_MISSING'
    assert r['native_tool_calls_verified'] is False and r['model_tool_execution_verified'] is True
    assert r['model_summary']['requests']==r['model_summary']['responses']==8
    assert r['model_summary']['tool_calls']==0 and r['model_summary']['json_actions']==7
    assert r['execution_summary']['succeeded']==1 and r['tool_summary']['succeeded']==7
    assert r['local_probe']['execution_summary']['succeeded']==1
    assert r['local_probe']['probe_directory']!=r['model_probe']['probe_directory']
    model_root=Path(r['model_probe']['probe_directory'])
    assert json.loads((model_root/'artifacts/tool_probe.json').read_text())['text']=='Kármán: \'single\' and "double"\nsecond line'
    assert ins.main._physnemo_model_execution_verified(r) is True
    assert p._JOB_CONTEXT.get() is None


def test_native_still_preferred_no_compatibility_request_when_supported(source,tmp_path):
    model=n.ProbeModel()
    r=asyncio.run(p.native_tool_preflight(model,source,tmp_path/'probes'))
    assert r['success'] and r['native_tool_calls_verified'] and r['selected_tool_transport']=='native'
    assert r['model_summary']['tool_calls']==7 and r['model_summary'].get('json_actions',0)==0
    assert r['model_summary']['requests']==7
    assert ins.main._physnemo_model_execution_verified(r)


def test_direct_json_mode_has_no_native_attempt(source,tmp_path):
    m=JsonProbeModel();r=asyncio.run(p.native_tool_preflight(m,source,tmp_path/'probes',tool_transport='json_actions_v1'))
    assert r['success'] and m.native_requests==0 and m.json_requests==7


def test_explicit_native_mode_never_falls_back(source,tmp_path):
    m=JsonProbeModel();r=asyncio.run(p.native_tool_preflight(m,source,tmp_path/'probes',tool_transport='native'))
    assert not r['success'] and r['error']=='PHYSNEMO_NATIVE_TOOL_CALLS_MISSING'
    assert m.native_requests==1 and m.json_requests==0

@pytest.mark.parametrize('response,code',[
    (n.AI('No',finish='content_filter'),'PHYSNEMO_NATIVE_MODEL_REFUSED'),
    (n.AI('cut',finish='length'),'PHYSNEMO_MODEL_OUTPUT_TRUNCATED'),
    (n.AI('broken',invalid=[{'args':'broken'}]),'PHYSNEMO_NATIVE_ARGUMENTS_INVALID'),
    (n.AI(''),'PHYSNEMO_NATIVE_TOOL_CALLS_MISSING'),
    (n.AI(calls=[n.call('workspace_list',{})]),'PHYSNEMO_NATIVE_TOOL_CHOICE_NOT_HONORED'),
])
def test_no_fallback_on_refusal_truncation_invalid_or_empty_response(source,tmp_path,response,code):
    m=JsonProbeModel(native_response=response)
    r=asyncio.run(p.native_tool_preflight(m,source,tmp_path/'probes'))
    assert not r['success'] and r['error']==code and m.json_requests==0


def test_provider_error_is_not_bypassed(source,tmp_path):
    class BadRequest(RuntimeError):status_code=403
    m=JsonProbeModel(native_response=BadRequest('SECRET'))
    r=asyncio.run(p.native_tool_preflight(m,source,tmp_path/'probes'))
    assert not r['success'] and r['http_status']==403 and m.json_requests==0
    assert 'SECRET' not in json.dumps(r)


def test_json_refusal_flag_is_not_bypassed(source,tmp_path):
    refusal=n.AI('');refusal.additional_kwargs={'refusal':'private refusal'}
    m=JsonProbeModel(change=lambda *_:refusal)
    r=asyncio.run(p.native_tool_preflight(m,source,tmp_path/'probes'))
    assert not r['success'] and r['error']=='PHYSNEMO_NATIVE_MODEL_REFUSED'
    assert m.json_requests==1 and r['tool_summary']['attempts']==0


def test_compatibility_prose_is_never_treated_as_success(source,tmp_path):
    m=JsonProbeModel(change=lambda *_:n.AI('I performed all operations successfully.'))
    r=asyncio.run(p.native_tool_preflight(m,source,tmp_path/'probes'))
    assert not r['success'] and r['error']=='PHYSNEMO_JSON_ACTION_INVALID'
    assert r['local_probe']['success'] and r['execution_summary']['attempts']==0
    assert m.json_requests==1 and r['model_summary']['requests']==2
    assert not ins.main._physnemo_model_execution_verified(r)


def test_model_modified_code_rejected_before_write(source,tmp_path):
    def alter(action,request,index):
        if action['name'].endswith('__workspace_write'):
            action['arguments']['content']+='\nraise RuntimeError("UNREVIEWED-CODE")\n'
        return action
    m=JsonProbeModel(change=alter);r=asyncio.run(p.native_tool_preflight(m,source,tmp_path/'probes'))
    assert not r['success'] and r['error']=='PHYSNEMO_NATIVE_PROBE_ARGUMENT_MISMATCH'
    assert not (Path(r['model_probe']['probe_directory'])/'workspace/tool_probe.py').exists()
    assert r['execution_summary']['attempts']==0
    assert 'UNREVIEWED-CODE' not in json.dumps(r)


def valid():
    return {'protocol':p.JSON_ACTION_PROTOCOL,'request_id':'current-id','type':'tool',
            'name':'physnemo_internal__workspace_list','arguments':{'relative_path':'.'}}

@pytest.mark.parametrize('mutate',[
    lambda a:{**a,'request_id':'old-id'},lambda a:{**a,'protocol':'old'},
    lambda a:{**a,'extra':1},lambda a:{**a,'type':'exec'},lambda a:[a],
    lambda a:{**a,'name':'os.system'},lambda a:{**a,'name':'physnemo_internal__unknown'},
    lambda a:{**a,'arguments':'{"relative_path":"."}'},
    lambda a:{**a,'arguments':{'relative_path':123}},lambda a:{**a,'arguments':{'relative_path':'.','extra':1}},
    lambda a:{**a,'arguments':None},lambda a:{**a,'name':123},
])
def test_strict_json_action_parser_rejects_invalid_envelopes(mutate):
    with pytest.raises(p.NativeToolProtocolError,match='PHYSNEMO_JSON_ACTION_INVALID'):
        p._parse_json_action(json.dumps(mutate(valid())),'current-id')

@pytest.mark.parametrize('text',[
    'Action: workspace_list\nAction Input: {}','```json\n{}\n```','preface {}','{}{}',
    '{"protocol":"PHYSNEMO_JSON_ACTION_V1","protocol":"PHYSNEMO_JSON_ACTION_V1"}',
    '{"anything":NaN}','{"anything":Infinity}',"{'type': 'tool'}",'null','[]','42',
])
def test_never_repairs_or_extracts_executable_json_from_prose(text):
    with pytest.raises(p.NativeToolProtocolError,match='INVALID'):p._parse_json_action(text,'current-id')


def test_valid_parser_returns_unmodified_arguments():
    a=valid();a.update(name='physnemo_internal__workspace_write',arguments={
        'relative_path':'workspace/a.py','content':'\n  \'single\' "double" \\n Kármán\n','overwrite':False})
    assert p._parse_json_action(json.dumps(a,ensure_ascii=False),'current-id')==a


def test_named_choice_and_final_before_execution_are_rejected():
    with pytest.raises(p.NativeToolProtocolError,match='INVALID'):
        p._parse_json_action(json.dumps(valid()),'current-id','physnemo_internal__workspace_run_python')
    a={k:v for k,v in valid().items() if k in {'protocol','request_id'}};a.update(type='final',answer='Done')
    with pytest.raises(p.NativeToolProtocolError,match='TOOL_ACTION_REQUIRED'):
        p._parse_json_action(json.dumps(a),'current-id','required')
    assert p._parse_json_action(json.dumps(a),'current-id','auto')==a


def test_blocked_action_is_explicit_failure(source,tmp_path):
    def block(a,*_):return {'protocol':a['protocol'],'request_id':a['request_id'],'type':'blocked','reason':'No permission.'}
    r=asyncio.run(p.native_tool_preflight(JsonProbeModel(change=block),source,tmp_path/'probes'))
    assert not r['success'] and r['error']=='PHYSNEMO_JSON_MODEL_BLOCKED'
    assert r['tool_summary']['attempts']==0


def test_normal_agent_json_path_writes_runs_reads_and_then_finishes(tmp_path):
    class Agent(JsonProbeModel):
        async def ainvoke(self,messages):
            if self.mode=='native':return await super().ainvoke(messages)
            self.json_requests+=1;req=json.loads(messages[-1].content)
            a={'protocol':req['protocol'],'request_id':req['request_id'],'type':'tool'}
            if self.json_requests==1:
                a.update(name='physnemo_internal__workspace_write',arguments={'relative_path':'workspace/run.py',
                  'content':'import os\nfrom pathlib import Path\nPath(os.environ["PHYSNEMO_ARTIFACT_DIR"], "result.txt").write_text("ACTUAL-PYTHON-OUTPUT")\n'})
            elif self.json_requests==2:a.update(name='physnemo_internal__workspace_run_python',arguments={'script_relative_path':'workspace/run.py'})
            elif self.json_requests==3:a.update(name='physnemo_internal__workspace_read',arguments={'relative_path':'artifacts/result.txt'})
            else:
                assert 'ACTUAL-PYTHON-OUTPUT' in req['conversation'][-1]['content']
                assert req['tool_choice']=='auto'
                a.update(type='final',answer='Actual local test completed, no scientific claim.')
            return n.AI(json.dumps(a))
    with n.job(tmp_path,True):
        m=Agent();answer=asyncio.run(p._run_native_agent(m,'Execute the local test',tmp_path/'source'))
        assert 'Actual local test completed' in answer
        assert m.native_requests==1 and m.json_requests==4
        status=p._read_json(tmp_path/'status.json')
        assert status['execution_summary']['succeeded']==1
        assert status['model_summary']['tool_calls']==0 and status['model_summary']['json_actions']==3
        assert (tmp_path/'artifacts/result.txt').read_text()=='ACTUAL-PYTHON-OUTPUT'

@pytest.mark.parametrize('change',[
    {'native_tool_calls_verified':True,'selected_tool_transport':'json_actions_v1'},
    {'model_tool_execution_verified':False}, {'selected_tool_transport':'unknown'},
    {'tool_summary':{'succeeded':0}}, {'script_exact':False},
    {'model_summary':{'tool_calls':True}}, {'model_probe':{'success':True}},
])
def test_readiness_never_accepts_unverified_or_mislabelled_modes(change):
    assert not ins.main._physnemo_model_execution_verified({**ins.good(),**change})


def test_health_report_does_not_copy_signing_key_or_mutate_runtime():
    runtime={'artifact_secret':'PRIVATE-SIGNING-KEY','configured':True,'distro':'Ubuntu'}
    safe=ins.main._physnemo_runtime_report_for_log(runtime)
    assert safe=={'artifact_secret_present':True,'configured':True,'distro':'Ubuntu'}
    assert runtime['artifact_secret']=='PRIVATE-SIGNING-KEY'

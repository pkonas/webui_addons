# Historical native-only branch tests. Automatic compatibility is tested separately.
"""Local regression tests: REAL Python filesystem/subprocess; MOCK NAT and LangChain/model.
These do not claim execution against installed Windows/WSL/GLM/Open WebUI.
"""
import asyncio
import importlib.util
import json
import sys
import threading
import types
from contextlib import contextmanager
from pathlib import Path

import pytest

ROOT = Path(__file__).parent
spec = importlib.util.spec_from_file_location('native_harness', ROOT/'test-engineering-physnemo-generic-agent-v1.2.10.py')
harness = importlib.util.module_from_spec(spec); spec.loader.exec_module(harness)
p = harness.plugin

class Message:
    def __init__(self, content='', **kw): self.content=content; self.__dict__.update(kw)
class AI(Message):
    def __init__(self, content='', calls=None, invalid=None, finish='stop'):
        super().__init__(content,tool_calls=calls or [],invalid_tool_calls=invalid or [],response_metadata={'finish_reason':finish})

def call(op,args,cid='call-1'):
    return {'id':cid,'name':'physnemo_internal__'+op,'args':args,'type':'tool_call'}

@pytest.fixture(autouse=True)
def fake_lc(monkeypatch):
    package=types.ModuleType('langchain_core'); module=types.ModuleType('langchain_core.messages')
    module.HumanMessage=Message; module.SystemMessage=Message; module.ToolMessage=Message
    monkeypatch.setitem(sys.modules,'langchain_core',package)
    monkeypatch.setitem(sys.modules,'langchain_core.messages',module)

@contextmanager
def job(root,requires=False):
    root.mkdir(parents=True,exist_ok=True)
    for key in ('workspace','artifacts','inputs','source'): (root/key).mkdir(exist_ok=True)
    (root/'source/README.md').write_text('PhysicsNeMo test fixture\n')
    p._atomic_json(root/'status.json', {'state':'running','execution_summary':{'attempts':0,'succeeded':0,'failed':0},'progress':[]})
    token=p._JOB_CONTEXT.set({'job_root':str(root),'workspace':str(root/'workspace'),'artifacts':str(root/'artifacts'),
        'source_root':str(root/'source'),'cancel_event':threading.Event(),'require_execution':requires})
    try: yield root
    finally:p._JOB_CONTEXT.reset(token)

class Model:
    def __init__(self,*responses): self.responses=list(responses);self.histories=[];self.schemas=None
    def bind_tools(self,schemas,**kwargs): self.schemas=schemas;self.bind_options=kwargs;return self
    async def ainvoke(self,messages):
        self.histories.append(list(messages))
        assert self.responses,'Unexpected model request'
        await asyncio.sleep(0)
        response=self.responses.pop(0)
        return response(messages) if callable(response) else response


def test_all_schemas_are_flat_strict_and_content_unmodified():
    schemas=p._native_schemas()
    assert len(schemas)==6
    write=next(s['function']['parameters'] for s in schemas if s['function']['name'].endswith('__workspace_write'))
    assert set(write['properties'])=={'relative_path','content','overwrite'} and write['additionalProperties'] is False
    text="\n  'quotes' \"double\" \\n Kármán\n"
    assert p.WorkspaceWriteInput(relative_path='workspace/a.py',content=text).content==text


def test_write_run_read_same_native_response_is_sequential(tmp_path):
    text='import os, json\nfrom pathlib import Path\npayload = {"a": "Kármán: \'single\' \\\"double\\\"\\nnew"}\n'
    text+='Path(os.environ["PHYSNEMO_ARTIFACT_DIR"],"result.json").write_text(json.dumps(payload),encoding="utf-8")\n'
    responses=AI(calls=[call('workspace_write',{'relative_path':'workspace/run.py','content':text}),
        call('workspace_run_python',{'script_relative_path':'workspace/run.py'},'call-2'),
        call('workspace_read',{'relative_path':'artifacts/result.json'},'call-3')])
    def final(messages):
        assert len(messages)==6 # system, user, AI, and three real tool response messages
        assert messages[2] is responses
        for i in range(3):
            assert messages[3+i].tool_call_id==f'call-{i+1}'
            assert json.loads(messages[3+i].content)['ok'] is True
        return AI('Actual execution finished.')
    model=Model(responses,final)
    with job(tmp_path):
        answer=asyncio.run(p._run_native_agent(model,'Test requested execution',tmp_path/'source', tool_transport="native"))
        assert answer=='Actual execution finished.'
        assert (tmp_path/'workspace/run.py').read_text()==text
        assert json.loads((tmp_path/'artifacts/result.json').read_text())['a'].startswith('Kármán')
        status=p._read_json(tmp_path/'status.json')
        assert status['execution_summary']['attempts']==1
        assert status['execution_summary']['succeeded']==1
        assert status['tool_summary']['succeeded']==3
        assert 'Kármán' not in (tmp_path/'tool-events.jsonl').read_text()

@pytest.mark.parametrize('args,code',[
    ({'relative_path':'workspace/x.py'},'TOOL_SCHEMA_VALIDATION_FAILED'),
    ({'request':{'relative_path':'workspace/x.py','content':'x'}},'TOOL_SCHEMA_VALIDATION_FAILED'),
    ({'relative_path':'workspace/x.py','content':'x','extra':True},'TOOL_SCHEMA_VALIDATION_FAILED'),
    ('{"relative_path":"workspace/x.py","content":"x"}','TOOL_ARGUMENTS_NOT_OBJECT'),
    ({'relative_path':'../x.py','content':'x'},'INVALID_PATH_OR_VALUE'),
])
def test_bad_arguments_are_diagnostic_without_side_effects(tmp_path,args,code):
    with job(tmp_path):
        r=asyncio.run(p._dispatch_native_tool('physnemo_internal__workspace_write',args,tmp_path/'source','x'))
        assert not r['ok'] and r['error_code']==code
        assert not list((tmp_path/'workspace').iterdir())
        assert p._read_json(tmp_path/'status.json')['tool_summary']['failed']==1
        assert '"content":' not in (tmp_path/'tool-events.jsonl').read_text()

def test_empty_source_search_is_success_and_missing_source_is_error(tmp_path):
    with job(tmp_path):
        r=asyncio.run(p._dispatch_native_tool('physnemo_internal__source_search',{'query':'not-found-unique'},tmp_path/'source','a'))
        assert r['ok'] and r['result']['results']==[]
        r=asyncio.run(p._dispatch_native_tool('physnemo_internal__source_search',{'query':'x'},tmp_path/'missing','b'))
        assert not r['ok'] and r['error_code']=='PHYSNEMO_SOURCE_UNAVAILABLE'

def test_missing_workspace_file_reports_real_failure(tmp_path):
    with job(tmp_path):
        r=asyncio.run(p._dispatch_native_tool('physnemo_internal__workspace_read',{'relative_path':'workspace/missing.py'},tmp_path/'source','a'))
        assert not r['ok'] and r['error_code']=='FILE_NOT_FOUND'

def test_runtime_failure_is_not_retried_blindly(tmp_path):
    with job(tmp_path):
        (tmp_path/'workspace/fail.py').write_text('raise RuntimeError("bad shape")\n')
        r=asyncio.run(p._dispatch_native_tool('physnemo_internal__workspace_run_python',{'script_relative_path':'workspace/fail.py'},tmp_path/'source','a'))
        assert not r['ok'] and r['error_code']=='PYTHON_EXECUTION_FAILED'
        assert 'bad shape' in r['result']['output']
        assert p._read_json(tmp_path/'status.json')['execution_summary']['attempts']==1

@pytest.mark.parametrize('response,code',[
    (AI('Action: workspace_write\nAction Input: {broken}'),'PHYSNEMO_NATIVE_TOOL_CALLS_REQUIRED'),
    (AI(''), 'PHYSNEMO_EMPTY_NATIVE_RESPONSE'),
    (AI(invalid=[{'args':'broken'}]), 'PHYSNEMO_NATIVE_ARGUMENTS_INVALID'),
    (AI(calls=[call('workspace_write',{})],finish='length'),'PHYSNEMO_MODEL_OUTPUT_TRUNCATED'),
    (AI(calls=[call('workspace_list',{}),call('workspace_list',{})]),'PHYSNEMO_DUPLICATE_OR_INVALID_TOOL_CALL_ID'),
    (AI(calls=[call('workspace_write','bad')]), 'PHYSNEMO_NATIVE_ARGUMENTS_INVALID'),
])
def test_protocol_failure_is_not_silently_parsed_or_executed(tmp_path,response,code):
    with job(tmp_path):
        with pytest.raises(p.NativeToolProtocolError,match=code):
            asyncio.run(p._run_native_agent(Model(response),'test',tmp_path/'source', tool_transport="native"))
        assert not list((tmp_path/'workspace').iterdir())

def test_duplicate_id_across_turns_cannot_run_twice(tmp_path):
    with job(tmp_path):
        model=Model(AI(calls=[call('workspace_list',{})]),AI(calls=[call('workspace_list',{})]))
        with pytest.raises(p.NativeToolProtocolError,match='DUPLICATE'):
            asyncio.run(p._run_native_agent(model,'test',tmp_path/'source', tool_transport="native"))
        assert p._read_json(tmp_path/'status.json')['tool_summary']['attempts']==1

def test_answer_without_execution_gets_one_bounded_continuation(tmp_path):
    with job(tmp_path,True):
        model=Model(AI('Proposed code only.'),AI('Unable to execute; no results claimed.'))
        with pytest.raises(p.NativeToolProtocolError,match='PHYSNEMO_NATIVE_TOOL_CALLS_MISSING'):
            asyncio.run(p._run_native_agent(model,'Train the model',tmp_path/'source', tool_transport="native"))
        assert len(model.histories)==2 and model.bind_options['tool_choice']=='required'
        assert not p._read_json(tmp_path/'status.json')['execution_summary']['succeeded']

def test_tool_limit_is_error(tmp_path):
    with job(tmp_path):
        m=Model(AI(calls=[call('workspace_list',{},'a')]),AI(calls=[call('workspace_list',{},'b')]))
        with pytest.raises(p.NativeToolProtocolError,match='TURN_LIMIT'):
            asyncio.run(p._run_native_agent(m,'test',tmp_path/'source',2, tool_transport="native"))

def test_no_implicit_fallback_job_context(tmp_path):
    with pytest.raises(RuntimeError,match='only while'):
        asyncio.run(p._dispatch_native_tool('physnemo_internal__workspace_list',{},tmp_path,'c'))

def test_concurrent_jobs_never_share_files(tmp_path):
    async def go(i):
        with job(tmp_path/str(i)):
            await p._dispatch_native_tool('physnemo_internal__workspace_write',
                {'relative_path':'workspace/value.txt','content':str(i)},tmp_path/str(i)/'source',str(i))
            await asyncio.sleep(.01)
            r=await p._dispatch_native_tool('physnemo_internal__workspace_read',{'relative_path':'workspace/value.txt'},tmp_path/str(i)/'source',str(i)+'r')
            assert r['result']['content']==f'1: {i}'
    async def all_jobs():await asyncio.gather(*(go(i) for i in range(8)))
    asyncio.run(all_jobs())

class ProbeModel(Model):
    def __init__(self):super().__init__();self.n=0
    async def ainvoke(self,messages):
        self.n+=1
        # A transparent SDK test double. It checks the requested native name,
        # returns one structured call and lets the REAL dispatcher perform IO.
        self.histories.append(list(messages))
        args=json.loads(messages[-1].content.split('argument object:\n')[1])
        name=self.bind_options['tool_choice']['function']['name']
        assert self.bind_options['tool_choice']['type']=='function'
        for message in messages[2:-1]:
            if hasattr(message,'tool_call_id'):
                assert json.loads(message.content)['ok'] is True
        return AI(calls=[call(name.removeprefix('physnemo_internal__'),args,f'probe-{self.n}')])

def test_live_probe_function_uses_all_six_tools_and_actual_python(tmp_path):
    source=tmp_path/'source';source.mkdir();(source/'README.md').write_text('PhysicsNeMo fixture\n')
    r=asyncio.run(p.native_tool_preflight(ProbeModel(),source,tmp_path/'probes', tool_transport="native"))
    assert r['success'] and r['missing_tools']==[] and r['exact_content_roundtrip']
    assert r['execution_summary']['succeeded']==1 and r['tool_summary']['succeeded']==7
    assert p._JOB_CONTEXT.get() is None

def test_probe_will_not_execute_model_modified_code(tmp_path):
    with job(tmp_path):
        p._current_context()['probe_script']='print("trusted")\n'
        r=asyncio.run(p._dispatch_native_tool('physnemo_internal__workspace_write',
            {'relative_path':'workspace/tool_probe.py','content':'print("changed")\n'},tmp_path/'source','1'))
        assert r['error_code']=='PROBE_SCRIPT_MISMATCH' and not list((tmp_path/'workspace').iterdir())

def test_symbolic_deliverables_not_ignored_when_unrelated_plot_exists():
    req=p.SolveInput(task='Train and visualize',expected_artifacts=['training_loss_curve','vorticity_field_animation'])
    m={'artifacts':[{'name':'unrelated.png','role':'deliverable','size':3}]}
    r=p._deliverable_check(req,m,{'succeeded':1})
    assert set(r['missing'])==set(req.expected_artifacts) and r['unchecked_expectations']==[]


def test_expected_basename_with_extension_is_accepted():
    req=p.SolveInput(task='Train and visualize',expected_artifacts=['training_loss_curve'])
    m={'artifacts':[{'name':'training_loss_curve.png','role':'deliverable','size':3}]}
    assert p._deliverable_check(req,m,{'succeeded':1})['missing']==[]


def test_native_writes_cannot_replace_job_status(tmp_path):
    with job(tmp_path):
        r=asyncio.run(p._dispatch_native_tool('physnemo_internal__workspace_write',
            {'relative_path':'status.json','content':'{}','overwrite':True},tmp_path/'source','reserved'))
        assert not r['ok'] and r['error_code']=='WORKSPACE_WRITE_SCOPE_INVALID'
        assert p._read_json(tmp_path/'status.json')['state']=='running'


def test_failed_probe_keeps_diagnostic_directory_and_terminal_state(tmp_path):
    (tmp_path/'source').mkdir()
    (tmp_path/'source/README.md').write_text('PhysicsNeMo fixture')
    model=Model(AI('',finish='length'))
    r=asyncio.run(p.native_tool_preflight(model,tmp_path/'source',tmp_path/'probes', tool_transport="native"))
    assert not r['success'] and r['error']=='PHYSNEMO_MODEL_OUTPUT_TRUNCATED'
    status=p._read_json(Path(r['probe_directory'])/'status.json')
    assert status['state']=='failed' and status['probe_only'] is True
    assert p._JOB_CONTEXT.get() is None


def test_native_registration_resolves_declared_llm_dependency(tmp_path,monkeypatch):
    from enum import Enum
    class Framework(Enum): LANGCHAIN='langchain'
    mod=types.ModuleType('nat.builder.framework_enum');mod.LLMFrameworkEnum=Framework
    monkeypatch.setitem(sys.modules,'nat.builder.framework_enum',mod)
    model=Model(AI('Observed real answer without execution requested.'))
    class Builder:
        async def get_llm(self,name,wrapper_type):
            assert name=='physnemo_llm' and wrapper_type is Framework.LANGCHAIN
            return model
    cfg=p.PhysNeMoNativeAgentConfig(llm_name='physnemo_llm',source_root=str(tmp_path/'source'))
    assert isinstance(cfg.llm_name,harness.FunctionRef)  # Declared mock LLMRef subtype in this harness.
    async def run():
        generator=p.register_native_agent(cfg,Builder())
        fn=await anext(generator)
        try:return await fn.fn('Read-only question')
        finally:await generator.aclose()
    with job(tmp_path):
        assert asyncio.run(run()).startswith('Observed real answer')

"""Real local I/O/subprocess + async lifecycle tests; NAT SDK/model/Open WebUI are test doubles.

No Windows/WSL or actual model execution is implied. The production functions and
actual FastAPI middleware are imported from the shipping, embedded source tree.
"""
from __future__ import annotations
import asyncio
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace
import uuid

import pytest
from pydantic import ValidationError

ROOT=Path(__file__).resolve().parent

def load(name, path):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m)
    return m

harness=load('lifecycle_nat_harness',ROOT/'test-engineering-physnemo-generic-agent-v1.2.10.py')
plugin=harness.plugin
router=load('lifecycle_router',ROOT/'openwebui-engineering-tool-router-v1.1.0.py')
gateway=load('lifecycle_gateway',ROOT/'engineering_mcp_unified-v2.9.18.py')
gateway_harness=load('lifecycle_gateway_harness',ROOT/'test-engineering-mcp-unified-v2.9.18.py')
PNG=bytes.fromhex('89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360000000020001e221bc330000000049454e44ae426082')
JOB='job-20260921T090000Z-0123456789ab'

async def registered(root,agent):
    class Builder:
        async def get_function(self,name): return agent
    config=plugin.PhysNeMoSolveConfig(agent_name='physnemo_agent',agent_configured=True,
        source_root=str(root/'source'),source_ref='test-only',artifact_root=str(root/'jobs'),
        artifact_base_url='http://127.0.0.1:8200/physnemo/artifacts',artifact_secret='s'*64)
    (root/'source').mkdir(exist_ok=True,parents=True)
    solve=await harness.first_yield(plugin.register_solve(config,Builder()))
    sc=plugin.PhysNeMoPublicConfig(operation='job_status',source_root=config.source_root,
        source_ref=config.source_ref,artifact_root=config.artifact_root,
        artifact_base_url=config.artifact_base_url,artifact_secret=config.artifact_secret)
    status=await harness.first_yield(plugin.register_public(sc,Builder()))
    return solve.fn,status.fn

class AnswerAgent:
    def __init__(self,answer='Skutečná vysvětlující odpověď.',files=None,delay=0):
        self.answer=answer;self.files=files or {};self.delay=delay;self.calls=0
    async def ainvoke(self,prompt):
        self.calls+=1
        await asyncio.sleep(self.delay)
        for name,data in self.files.items():
            p=Path(plugin._current_context()['artifacts'])/name
            p.parent.mkdir(parents=True,exist_ok=True)
            p.write_bytes(data if isinstance(data,bytes) else data.encode())
        return self.answer

@pytest.mark.parametrize('value',[None,'',{}, {'output':None}, {'content':[]}])
def test_empty_agent_result_never_claimed_success(tmp_path,value):
    async def go():
        solve,_=await registered(tmp_path,AnswerAgent(value))
        d=json.loads(await solve(plugin.SolveInput(task='Vysvětli metodu.')))
        assert d['state']=='failed' and 'EMPTY_AGENT_RESULT' in d['error']
    asyncio.run(go())

@pytest.mark.parametrize('value,expected',[
    ({'output':'actual'},'actual'),({'content':[{'text':'real'},{'text':'answer'}]},'real\nanswer'),
    (SimpleNamespace(content='sdk content'),'sdk content'),(' text ','text')])
def test_final_answer_extraction(value,expected):
    assert plugin._agent_text(value)==expected

@pytest.mark.parametrize('task,expected,files',[
    ('Vysvětli metodu.',['plot'],{}),('Vykresli graf řešení.',[],{}),
    ('Simuluj proudění.',[],{'report.md':'Only a claim.'}),
    ('Vysvětli metodu.',['result.csv'],{'result.csv':b''}),
    ('Vysvětli metodu.',['report'],{})])
def test_missing_deliverables_are_incomplete(tmp_path,task,expected,files):
    async def go():
        solve,_=await registered(tmp_path,AnswerAgent(files=files))
        d=json.loads(await solve(plugin.SolveInput(task=task,expected_artifacts=expected)))
        assert d['state']=='incomplete',d
        assert d['delivery']['missing']
        assert d['answer'] and d['artifacts']  # preserve explanation/downloads on partial success
    asyncio.run(go())

def test_text_only_is_explicit_and_auto_report_does_not_count(tmp_path):
    async def go():
        solve,_=await registered(tmp_path,AnswerAgent())
        d=json.loads(await solve(plugin.SolveInput(task='Vysvětli metodu.')))
        assert d['state']=='completed' and d['result_kind']=='answer_only'
        assert d['delivery']['deliverable_count']==0 and not d['delivery']['execution_observed']
        assert {a['role'] for a in d['artifacts']}=={'bundle','agent_report'}
    asyncio.run(go())

def test_authored_solution_preserved_and_expected_file_verified(tmp_path):
    async def go():
        agent=AnswerAgent(files={'solution.md':'AUTHORED FILE','result.png':PNG})
        solve,status=await registered(tmp_path,agent)
        rid=uuid.uuid4().hex
        d=json.loads(await solve(plugin.SolveInput(task='Vykresli graf.',client_request_id=rid,
                        expected_artifacts=['solution.md','plot','custom quality criterion'])))
        assert d['state']=='completed' and d['presentation_mode']=='structured'
        assert d['delivery']['unchecked_expectations']==['custom quality criterion']
        assert (tmp_path/'jobs'/d['job_id']/'artifacts/solution.md').read_text()=='AUTHORED FILE'
        assert sum(a['role']=='agent_report' for a in d['artifacts'])==1
        s=json.loads(await status(plugin.JobStatusInput(client_request_id=rid)))
        assert s['job_id']==d['job_id'] and s['stage']=='finished'
        assert s['execution_summary']['attempts']==0
        again=json.loads(await solve(plugin.SolveInput(task='Vykresli graf.',client_request_id=rid)))
        assert again['state']=='failed' and again['error']=='CLIENT_REQUEST_ID_REUSED'
        assert agent.calls==1
    asyncio.run(go())

@pytest.mark.parametrize('kwargs',[{}, {'job_id':JOB,'client_request_id':'a'*32}, {'client_request_id':'../private'}])
def test_status_identifiers_are_unambiguous_and_safe(kwargs):
    with pytest.raises(ValidationError): plugin.JobStatusInput(**kwargs)

def test_progress_reads_during_actual_subprocess_and_numeric_telemetry(tmp_path):
    class ExecutingAgent:
        async def ainvoke(self,prompt):
            ctx=plugin._current_context()
            script=Path(ctx['workspace'])/'run.py'
            script.write_text('import time, os\nfrom pathlib import Path\n'
                'print("epoch=2 loss=0.125 PRIVATE-TEXT-NOT-FOR-PROGRESS",flush=True)\n'
                'time.sleep(2.5)\nPath(os.environ["PHYSNEMO_ARTIFACT_DIR"],"result.csv").write_text("x,y\\n0,1\\n")\n')
            cfg=plugin.PhysNeMoInternalConfig(operation='workspace_run_python',source_root=str(tmp_path/'source'))
            info=await harness.first_yield(plugin.register_internal(cfg,None))
            out=json.loads(await info.fn(plugin.WorkspaceRunPythonInput(script_relative_path='workspace/run.py')))
            assert out['returncode']==0
            return 'Actual local subprocess produced result.csv; this is not a PhysicsNeMo model test.'
    async def go():
        solve,status=await registered(tmp_path,ExecutingAgent());rid=uuid.uuid4().hex
        task=asyncio.create_task(solve(plugin.SolveInput(task='Spusť výpočet.',expected_artifacts=['result.csv'],client_request_id=rid)))
        snapshots=[]
        while not task.done():
            await asyncio.sleep(.05)
            start=time.monotonic()
            s=json.loads(await status(plugin.JobStatusInput(client_request_id=rid)))
            assert time.monotonic()-start<.5  # loop remains responsive while process runs
            snapshots.append(s)
        d=json.loads(await task)
        assert d['state']=='completed' and d['delivery']['execution_observed']
        assert d['execution_summary']=={'attempts':1,'succeeded':1,'failed':0,'last_returncode':0}
        running=[s for s in snapshots if s.get('stage')=='executing']
        assert len(running)>5
        assert any(s.get('metrics',{}).get('loss')==.125 for s in running)
        assert 'PRIVATE-TEXT-NOT-FOR-PROGRESS' not in json.dumps(snapshots)
        assert max(s.get('progress_seq',0) for s in snapshots)>2
    asyncio.run(go())

def test_python_timeout_recorded_not_success(tmp_path):
    class Agent:
        async def ainvoke(self,prompt):
            ctx=plugin._current_context();p=Path(ctx['workspace'])/'slow.py';p.write_text('import time; time.sleep(20)')
            result=await asyncio.to_thread(plugin._workspace_run_python,
                plugin.WorkspaceRunPythonInput(script_relative_path='workspace/slow.py',timeout_seconds=1),Path(ctx['job_root']))
            assert result['timed_out'] and result['returncode']==124
            return 'The execution timed out.'
    async def go():
        solve,_=await registered(tmp_path,Agent());d=json.loads(await solve(plugin.SolveInput(task='Spusť výpočet.')))
        assert d['state']=='incomplete' and d['execution_summary']['failed']==1
    asyncio.run(go())

async def make_router(solve,status=None,render=None,emitter=None,correlated=True):
    f=router.Filter();f.valves.progress_poll_seconds=.2
    body={'messages':[{'role':'user','content':'PhysicsNeMo vytvoř model.'}]}
    meta={'chat_id':'test-chat','message_id':'test-message'}
    await f.inlet(body,__metadata__=meta)
    props={'task':{'type':'string'}}
    if correlated: props['client_request_id']={'type':'string'}
    tools={'physnemo__solve':{'callable':solve,'spec':{'name':'physnemo__solve','parameters':{'properties':props}}}}
    if status: tools['physnemo__job_status']={'callable':status}
    if render: tools['physnemo__render_artifacts']={'callable':render}
    meta['tools']=tools
    await f.request(body,__metadata__=meta,__event_emitter__=emitter)
    return f,body,meta,tools['physnemo__solve']['callable']

def output(answer='real result',state='completed',artifacts=None):
    return {'job_id':JOB,'state':state,'answer':answer,'artifacts':artifacts or []}

def test_automatic_status_display_without_user_prompt_and_concurrent_dedup():
    async def go():
        events=[];calls=[];finished=False
        async def emit(e): events.append((time.monotonic(),copy.deepcopy(e),finished))
        async def solve(**kw):
            nonlocal finished
            calls.append(kw);await asyncio.sleep(.55);finished=True
            return json.dumps(output(artifacts=[{'name':'plot.png','download_url':'http://localhost/a'}])),{'Content-Type':'application/json'}
        async def status(**kw):
            return json.dumps({'state':'running','client_request_id':kw['client_request_id'],'job_id':JOB,
                              'stage':'executing','message':'Python běží.','progress_seq':3,'metrics':{'step':5,'loss':.5}}),{}
        async def render(**kw):
            assert kw['job_id']==JOB
            return '<!doctype html><html>PhysicsNeMo REAL GALLERY</html>',{'Content-Type':'text/html'}
        f,body,meta,wrapped=await make_router(solve,status,render,emit)
        a,b=await asyncio.gather(wrapped(task='job'),wrapped(task='job'))
        assert a==b and len(calls)==1
        assert len(calls[0]['client_request_id'])==32
        d=f._job_result(a);assert d['answer']=='real result'
        assert d['presentation']['state']=='emitted' and not d['presentation']['delivery_confirmed_by_browser']
        assert any(e['type']=='status' and not is_finished for _,e,is_finished in events)
        assert any('loss=0.5' in e['data'].get('description','') for _,e,_ in events)
        assert sum(e['type']=='embeds' for _,e,_ in events)==1
        assert 'REAL GALLERY' in next(e['data']['embeds'][0] for _,e,_ in events if e['type']=='embeds')
        assert events[-1][1]['data']['done'] is True
        await f.request(body,__metadata__=meta,__event_emitter__=emit)
        assert 'tool_choice' not in body
        assert not hasattr(wrapped,'__function__') and not hasattr(wrapped,'__extra_params__')
    asyncio.run(go())

def test_gallery_failure_has_visible_fallback_and_preserves_answer():
    async def go():
        events=[]
        async def emit(e):events.append(e)
        async def solve(**kw):return output('<unsafe>ACTUAL</unsafe>','incomplete',[{'name':'report.md','download_url':'http://localhost/a'}])
        async def render(**kw):raise RuntimeError('SECRET TRACE MUST NOT BE SHOWN')
        f,body,meta,fn=await make_router(solve,render=render,emitter=emit)
        d=f._job_result(await fn(task='job'))
        html=next(e['data']['embeds'][0] for e in events if e['type']=='embeds')
        assert '&lt;unsafe&gt;ACTUAL&lt;/unsafe&gt;' in html and 'GALLERY_RuntimeError' in html
        assert 'SECRET TRACE' not in html and '<unsafe>' not in html
        assert d['state']=='incomplete' and d['answer']=='<unsafe>ACTUAL</unsafe>'
        assert 'chybí' in events[-1]['data']['description']
    asyncio.run(go())

def test_emitter_failure_not_reported_as_browser_success():
    async def go():
        async def emit(e):raise RuntimeError('offline')
        async def solve(**kw):return output()
        f,_,_,fn=await make_router(solve,emitter=emit)
        d=f._job_result(await fn(task='job'))
        assert d['presentation']['state']=='unavailable'
        assert not d['presentation']['delivery_confirmed_by_browser'] and d['answer']=='real result'
    asyncio.run(go())

def test_status_error_does_not_retry_solve():
    async def go():
        calls=[];events=[]
        async def emit(e):events.append(e)
        async def solve(**kw):calls.append(kw);await asyncio.sleep(.45);return output()
        async def status(**kw):raise OSError('test')
        f,_,_,fn=await make_router(solve,status,emitter=emit)
        assert f._job_result(await fn(task='job'))['state']=='completed'
        assert len(calls)==1 and any('detail průběhu není dostupný' in e['data'].get('description','') for e in events)
    asyncio.run(go())

def test_cancel_closes_observer_without_claiming_remote_stop():
    async def go():
        stopped=asyncio.Event();events=[]
        async def emit(e):events.append(e)
        async def solve(**kw):
            try:await asyncio.sleep(100)
            finally:stopped.set()
        _,_,_,fn=await make_router(solve,emitter=emit)
        task=asyncio.create_task(fn(task='job'));await asyncio.sleep(.05);task.cancel()
        with pytest.raises(asyncio.CancelledError):await task
        assert stopped.is_set()
        assert 'není tímto potvrzeno' in events[-1]['data']['description']
    asyncio.run(go())

def test_new_turn_not_shared_result_cache_and_unrelated_choice_preserved():
    async def go():
        calls=[]
        async def solve(**kw):calls.append(kw);return output()
        f,b,m,fn=await make_router(solve)
        await fn(task='job')
        b['tool_choice']={'type':'function','function':{'name':'another_tool'}}
        await f.request(b,__metadata__=m)
        assert b['tool_choice']['function']['name']=='another_tool'
        _,_,_,fn2=await make_router(solve)
        await fn2(task='job');assert len(calls)==2
    asyncio.run(go())

def test_stale_schema_fails_explicitly_without_submitting():
    async def go():
        async def solve(**kw):raise AssertionError('must not submit')
        with pytest.raises(RuntimeError,match='PHYSNEMO_LIFECYCLE_SCHEMA_STALE'):
            await make_router(solve,correlated=False)
    asyncio.run(go())

@pytest.mark.parametrize('envelope',[
    lambda x:x,lambda x:json.dumps(x),lambda x:([{'type':'text','text':json.dumps(x)}],{}),
    lambda x:{'structuredContent':x},lambda x:{'content':[{'type':'text','text':json.dumps(x)}]}])
def test_actual_result_supported_envelopes(envelope):
    payload=envelope(output())
    assert router.Filter._job_result(payload)['answer']=='real result'
    raw=json.dumps(payload).encode()
    assert gateway._physnemo_job_payload_from_tool_response(raw)['job_id']==JOB
    assert gateway._physnemo_completed_job_id_from_tool_response(raw)==JOB

@pytest.mark.parametrize('text,operation',[
    ('Zobraz artefakty '+JOB,'physnemo__render_artifacts'),
    ('PhysicsNeMo ukaž výsledek '+JOB,'physnemo__render_artifacts'),
    ('Stav '+JOB,'physnemo__job_status'),
    ('PhysicsNeMo vytvoř model','physnemo__solve')])
def test_known_job_display_never_forces_new_solve(text,operation):
    routes,forced=router.Filter._route_request(text)
    assert 'physnemo' in routes and forced==operation

def test_small_image_is_inline_and_lifecycle_notice_visible(monkeypatch):
    manifest={'job_id':JOB,'artifacts':[{'name':'result.png','media_type':'image/png','size':len(PNG),'sha256':hashlib.sha256(PNG).hexdigest()}]}
    files={f'/jobs/{JOB}/manifest.json':json.dumps(manifest).encode(),
        f'/jobs/{JOB}/status.json':json.dumps({'state':'incomplete','result_kind':'answer_only',
                         'delivery':{'missing':['expected.csv'],'unchecked_expectations':['quality']}}).encode(),
        f'/jobs/{JOB}/artifacts/result.png':PNG}
    runtime={'artifact_root':'/jobs','artifact_secret':'s'*64,'artifact_base_url':'http://127.0.0.1:8200/physnemo/artifacts'}
    monkeypatch.setattr(gateway,'_physnemo_runtime_storage',lambda:runtime)
    monkeypatch.setattr(gateway,'load_state',lambda:{'mcpo_port':8200,'physnemo_runtime':runtime})
    monkeypatch.setattr(gateway,'_physnemo_wsl_read_file',lambda r,p,**kw:files[p])
    html=gateway._physnemo_render_gallery(JOB)
    assert 'data:image/png;base64,' in html and 'signature=' in html
    assert 'incomplete' in html and 'expected.csv' in html and 'Pouze textová odpověď' in html

def test_auto_middleware_gallery_error_preserves_payload(monkeypatch):
    from fastapi.testclient import TestClient
    app=gateway_harness.build_named_mcpo_app(gateway)
    def failed(job):raise RuntimeError('PRIVATE BACKEND ERROR')
    monkeypatch.setattr(gateway,'_physnemo_render_gallery',failed)
    with TestClient(app) as client:
        r=client.post('/physnemo__solve',json={})
    assert r.status_code==200
    d=router.Filter._job_result(r.json())
    assert d['job_id'] and d['state']=='completed'
    assert d['presentation']['state']=='failed'
    assert 'PRIVATE BACKEND ERROR' not in r.text

@pytest.mark.parametrize('mode',['structured','auto'])
def test_structured_solve_not_swallowed_by_auto_html_middleware(monkeypatch,mode):
    from fastapi.testclient import TestClient
    payload={**output('PRESERVED','incomplete',[{'name':'report.md'}]),'presentation_mode':mode}
    app=gateway_harness.build_named_mcpo_app(gateway,solve_payload=payload)
    calls=[]
    def render(job):calls.append(job);return '<!doctype html><html>PhysicsNeMo gallery</html>'
    monkeypatch.setattr(gateway,'_physnemo_render_gallery',render)
    with TestClient(app) as client:r=client.post('/physnemo__solve',json={})
    if mode=='structured':
        assert not calls and 'application/json' in r.headers['content-type']
        assert router.Filter._job_result(r.json())['answer']=='PRESERVED'
    else:
        assert calls==[JOB] and 'text/html' in r.headers['content-type']

def lifecycle_schema(correlated=True,ref=False):
    defs={};paths={}
    for name in ['physnemo__solve','physnemo__job_status']:
        body={'type':'object','properties':{'client_request_id':{'type':'string'}} if correlated else {}}
        defs[name]=body
        paths['/'+name]={'post':{'operationId':'tool_'+name+'_post','requestBody':{'content':{
            'application/json':{'schema':{'$ref':'#/components/schemas/'+name} if ref else body}}}}}
    return {'paths':paths,'components':{'schemas':defs}}

@pytest.mark.parametrize('ref',[True,False])
def test_live_schema_gate_checks_correlation_and_refs(ref):
    assert gateway._physnemo_lifecycle_schema_report(lifecycle_schema(ref=ref))['ready']
    d=gateway._physnemo_lifecycle_schema_report(lifecycle_schema(False,ref=ref))
    assert not d['ready'] and len(d['missing_correlation_tools'])==2

def test_schema_recursive_ref_fails_closed():
    d=lifecycle_schema(ref=True)
    d['components']['schemas']['physnemo__solve']={'$ref':'#/components/schemas/physnemo__solve'}
    assert not gateway._physnemo_lifecycle_schema_report(d)['ready']

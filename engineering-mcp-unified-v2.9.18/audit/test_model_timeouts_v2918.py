"""Timeout regressions: real file IO, Python processes and HTTPX/TCP.
The model server and NAT/LangChain interfaces are test doubles, not the user's service.
Timings are deliberately scaled down; these tests do not wait 90/300 real seconds.
"""
import asyncio
import json
from pathlib import Path
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import pytest
import httpx
import test_native_dispatch_v2918 as n
import test_model_transport_v2918 as t
import test_native_preflight_v2918 as ins
p=n.p

@pytest.fixture(autouse=True)
def sdk(monkeypatch):
    import sys,types
    module=types.ModuleType('langchain_core.messages')
    for name in ('HumanMessage','SystemMessage','ToolMessage'):setattr(module,name,n.Message)
    monkeypatch.setitem(sys.modules,'langchain_core',types.ModuleType('langchain_core'))
    monkeypatch.setitem(sys.modules,'langchain_core.messages',module)

@pytest.fixture
def source(tmp_path):
    root=tmp_path/'source';root.mkdir();(root/'README.md').write_text('PhysicsNeMo fixture\n')
    return root

class OpenAITimeoutError(RuntimeError):pass

class TimeoutOnWrite(t.JsonProbeModel):
    async def ainvoke(self,messages):
        if self.mode=='json':
            request=json.loads(messages[-1].content)
            if request['tool_choice'].endswith('__workspace_write'):
                self.json_requests+=1
                raise OpenAITimeoutError('DO_NOT_LOG_RESPONSE_OR_API_KEY')
        return await super().ainvoke(messages)


def test_report_shaped_timeout_is_specific_and_preserves_completed_operations(source,tmp_path):
    m=TimeoutOnWrite();events=[]
    r=asyncio.run(p.native_tool_preflight(m,source,tmp_path/'probes',progress_callback=events.append))
    assert not r['success'] and r['error']=='PHYSNEMO_MODEL_REQUEST_TIMEOUT'
    assert r['failed_stage']=='model_probe.workspace_write'
    assert r['origin_exception_type']=='OpenAITimeoutError'
    assert r['model_summary']['requests']==5 and r['model_summary']['responses']==4
    assert r['local_probe']['success'] and r['local_probe']['execution_summary']['succeeded']==1
    assert r['tool_summary']['succeeded']==3 and r['execution_summary']['attempts']==0
    assert r['missing_tools']==['workspace_read','workspace_run_python','workspace_write']
    assert r['timeout_error']['outcome']=='sdk_timeout'
    assert r['timeout_error']['request_timeout_seconds']==300
    assert r['timeout_error']['pending_operation_dispatched'] is False
    assert r['timeout_error']['automatic_retry'] is False
    assert m.native_requests==1 and m.json_requests==4
    root=Path(r['model_probe']['probe_directory'])
    assert not list((root/'workspace').iterdir())
    assert 'DO_NOT_LOG' not in json.dumps(r)+(root/'model-events.jsonl').read_text()+json.dumps(events)
    assert r['model_summary']['last_request']['requested_tool']=='workspace_write'
    assert p._JOB_CONTEXT.get() is None

@pytest.mark.parametrize('exc_type',[TimeoutError,OpenAITimeoutError,httpx.ReadTimeout,httpx.ConnectTimeout,httpx.WriteTimeout,httpx.PoolTimeout])
def test_timeout_types_never_trigger_json_fallback(source,tmp_path,exc_type):
    m=t.JsonProbeModel(native_response=exc_type('private text'))
    r=asyncio.run(p.native_tool_preflight(m,source,tmp_path/'probes'))
    assert r['error']=='PHYSNEMO_MODEL_REQUEST_TIMEOUT'
    assert m.json_requests==0 and m.native_requests==1
    assert r['execution_summary']['attempts']==0
    assert 'private text' not in json.dumps(r)


def test_whole_phase_deadline_differs_from_request_limit_and_no_late_write(source,tmp_path):
    class Slow(t.JsonProbeModel):
        async def ainvoke(self,messages):
            if self.mode=='json' and json.loads(messages[-1].content)['tool_choice'].endswith('__workspace_write'):
                self.json_requests+=1
                await asyncio.sleep(10)
            return await super().ainvoke(messages)
    m=Slow()
    r=asyncio.run(p.native_tool_preflight(m,source,tmp_path/'probes',request_timeout_seconds=.1,total_timeout_seconds=.12))
    assert r['error']=='PHYSNEMO_MODEL_PREFLIGHT_TOTAL_TIMEOUT'
    assert r['timeout_error']['outcome']=='model_phase_deadline'
    assert r['failed_stage']=='model_probe.workspace_write'
    assert r['tool_summary']['succeeded']==3 and r['execution_summary']['attempts']==0
    assert p._JOB_CONTEXT.get() is None


def test_request_watchdog_cancels_unresponsive_model(monkeypatch,source,tmp_path):
    # Patch the request context's loop wait limit via helper policy using a tiny
    # SDK-independent deadline. The +5 second SDK grace remains bounded.
    class Slow(t.JsonProbeModel):
        async def ainvoke(self,messages):
            self.native_requests+=1
            await asyncio.sleep(20)
    m=Slow()
    r=asyncio.run(p.native_tool_preflight(m,source,tmp_path/'probes',request_timeout_seconds=.001,total_timeout_seconds=6))
    assert r['error']=='PHYSNEMO_MODEL_REQUEST_TIMEOUT'
    assert r['timeout_error']['outcome']=='request_deadline'
    assert m.native_requests==1 and m.json_requests==0
    assert r['elapsed_seconds']<7

@pytest.fixture
def model_server():
    requests=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            req=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            requests.append(req.get('tool_choice','native'))
            if req.get('native'):
                message='Text only, no native tool call.'
            else:
                last=req['conversation'][-1]['content'];expected=json.loads(last[last.index('{'):])
                if expected['name'].endswith('__workspace_write'):time.sleep(.18)
                message=json.dumps({'protocol':req['protocol'],'request_id':req['request_id'],
                                   'type':'tool','name':expected['name'],'arguments':expected['arguments']})
            body=json.dumps({'content':message}).encode()
            try:
                self.send_response(200);self.send_header('Content-Type','application/json')
                self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
            except (BrokenPipeError,ConnectionResetError):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    yield f'http://127.0.0.1:{server.server_port}/chat/completions',requests
    server.shutdown();server.server_close();thread.join(2)

class HttpModel(t.JsonProbeModel):
    def __init__(self,url,timeout):super().__init__();self.url=url;self.timeout=timeout
    async def ainvoke(self,messages):
        if self.mode=='native':self.native_requests+=1;request={'native':True}
        else:self.json_requests+=1;request=json.loads(messages[-1].content)
        async with httpx.AsyncClient(timeout=self.timeout,trust_env=False) as client:
            response=await client.post(self.url,json=request);response.raise_for_status()
            return n.AI(response.json()['content'])

@pytest.mark.parametrize('timeout,ok',[(.05,False),(.6,True)])
def test_real_httpx_tcp_delayed_response_fails_short_limit_and_passes_larger_limit(source,tmp_path,model_server,timeout,ok):
    url,requests=model_server;m=HttpModel(url,timeout)
    r=asyncio.run(p.native_tool_preflight(m,source,tmp_path/'probes',request_timeout_seconds=timeout,total_timeout_seconds=4))
    assert r['success'] is ok,r
    assert requests.count('physnemo_internal__workspace_write')==1
    if ok:
        assert r['execution_summary']['succeeded']==1
        assert r['tool_summary']['succeeded']==7 and r['model_tool_execution_verified']
        assert r['model_probe']['script_exact'] and r['exact_content_roundtrip']
    else:
        assert r['error']=='PHYSNEMO_MODEL_REQUEST_TIMEOUT'
        assert r['origin_exception_type']=='ReadTimeout'
        assert r['execution_summary']['attempts']==0 and r['tool_summary']['succeeded']==3


def test_waiting_heartbeats_are_metadata_only(monkeypatch,source,tmp_path,model_server):
    monkeypatch.setattr(p,'MODEL_WAIT_HEARTBEAT_SECONDS',.04)
    url,requests=model_server;events=[]
    r=asyncio.run(p.native_tool_preflight(HttpModel(url,.6),source,tmp_path/'probes',
        request_timeout_seconds=.6,total_timeout_seconds=4,progress_callback=events.append))
    assert r['success']
    waits=[e for e in events if e['phase']=='request_waiting']
    assert len(waits)>=2 and any(e['operation']=='workspace_write' for e in waits)
    assert not any(k in json.dumps(events) for k in ['Kármán','import json','api_key','content'])
    assert r['model_summary']['requests']==r['model_summary']['responses']==8

@pytest.mark.parametrize('a,b',[(0,100),(True,300),(300,10),(float('nan'),100),(300,float('inf')),(901,1800),(300,7201)])
def test_checker_rejects_invalid_budgets(a,b):
    with pytest.raises(RuntimeError,match='TIMEOUT_CONFIG_INVALID'):ins.probe.validate_timeouts(a,b)

@pytest.mark.parametrize('a,b',[(1,1),(300,1800),(900,7200)])
def test_checker_accepts_bounded_budgets(a,b):ins.probe.validate_timeouts(a,b)


def test_main_budget_defaults_and_env_overrides(monkeypatch):
    monkeypatch.delenv('ENGINEERING_MCP_PHYSNEMO_REQUEST_TIMEOUT_SECONDS',raising=False)
    monkeypatch.delenv('ENGINEERING_MCP_PHYSNEMO_PREFLIGHT_TIMEOUT_SECONDS',raising=False)
    assert ins.main._physnemo_model_probe_timeouts()==(300,1800)
    monkeypatch.setenv('ENGINEERING_MCP_PHYSNEMO_REQUEST_TIMEOUT_SECONDS','600')
    monkeypatch.setenv('ENGINEERING_MCP_PHYSNEMO_PREFLIGHT_TIMEOUT_SECONDS','3600')
    assert ins.main._physnemo_model_probe_timeouts()==(600,3600)
    monkeypatch.setenv('ENGINEERING_MCP_PHYSNEMO_REQUEST_TIMEOUT_SECONDS','nan')
    with pytest.raises(ValueError,match='TIMEOUT_CONFIG_INVALID'):ins.main._physnemo_model_probe_timeouts()


def test_checkpoint_report_never_marks_timeout_ready():
    report=ins.good();report.update(success=False,error='PHYSNEMO_MODEL_REQUEST_TIMEOUT')
    assert not ins.main._physnemo_model_execution_verified(report)

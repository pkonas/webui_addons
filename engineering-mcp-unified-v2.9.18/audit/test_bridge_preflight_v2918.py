"""Local HTTP/preflight tests. The optional LangChain shim is NOT the real SDK."""
from __future__ import annotations

import asyncio
import base64
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('probe2912', ROOT.parent / 'check-physnemo-agent-bridge-v2.9.18.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
spec = importlib.util.spec_from_file_location('main2912probe', ROOT / 'engineering_mcp_unified-v2.9.18.py')
main = importlib.util.module_from_spec(spec)
spec.loader.exec_module(main)

MODEL = 'configured-model'
KEY = 'test-bridge-credential-NOT-A-REAL-SECRET'
TEXT = 'ENGINEERING_MCP_BRIDGE_OK'


def completion():
    return {'id':'chatcmpl-test', 'created': 1, 'object':'chat.completion', 'model':MODEL,
            'choices':[{'index':0, 'message':{'role':'assistant','content':TEXT},'finish_reason':'stop'}]}


def wire():
    common={'id':'chatcmpl-test','created':1,'object':'chat.completion.chunk','model':MODEL}
    chunks=[{**common,'choices':[{'index':0,'delta':{'role':'assistant','content':TEXT},'finish_reason':None}]},
            {**common,'choices':[{'index':0,'delta':{},'finish_reason':'stop'}]}]
    return ''.join('data: '+json.dumps(x)+'\n\n' for x in chunks).encode()+b'data: [DONE]\n\n'


@pytest.fixture
def http_server():
    state={'mode':'good','requests':[]}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def send(self, status, raw, media):
            self.send_response(status)
            self.send_header('Content-Type',media)
            if state['mode']!='missing-marker':
                self.send_header('X-Engineering-MCP-Bridge-Protocol','buffered-sse-v1')
            self.send_header('Content-Length',str(len(raw)))
            self.end_headers(); self.wfile.write(raw)
        def do_GET(self):
            if self.headers.get('Authorization')!='Bearer '+KEY:
                self.send(403,b'{}','application/json'); return
            self.send(200,json.dumps({'data':[{'id':MODEL}]}).encode(),'application/json')
        def do_POST(self):
            if self.headers.get('Authorization')!='Bearer '+KEY:
                self.send(403,b'{}','application/json'); return
            payload=json.loads(self.rfile.read(int(self.headers.get('Content-Length',0))))
            state['requests'].append(payload)
            if state['mode']=='error':
                self.send(502,b'{"error":{"code":"openwebui_no_choices","message":"PRIVATE PROVIDER BODY"}}','application/json'); return
            if payload.get('stream'):
                if state['mode']=='json-for-stream':
                    self.send(200,json.dumps(completion()).encode(),'application/json')
                elif state['mode']=='no-done':
                    self.send(200,wire().replace(b'data: [DONE]\n\n',b''),'text/event-stream')
                else:
                    self.send(200,wire(),'text/event-stream')
            else:
                self.send(200,json.dumps(completion()).encode(),'application/json')
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
    base=f'http://127.0.0.1:{server.server_port}/physnemo/openwebui-api'
    try: yield base,state,server
    finally: server.shutdown();server.server_close();thread.join(timeout=2)


def call_probe(base, *extra, env=None):
    e=os.environ.copy();e['PHYSNEMO_AGENT_API_KEY']=KEY
    if env: e.update(env)
    cp=subprocess.run([sys.executable,str(ROOT.parent/'check-physnemo-agent-bridge-v2.9.18.py'),
                       '--base-url',base,'--model',MODEL,'--timeout','5','--non-interactive',*extra],
                      env=e,capture_output=True,text=True,timeout=20)
    assert KEY not in cp.stdout+cp.stderr
    assert TEXT not in cp.stdout+cp.stderr
    return cp,json.loads(cp.stdout.strip().splitlines()[-1])


def test_http_probe_live_json_sse(http_server):
    base,state,_=http_server
    cp,data=call_probe(base)
    assert cp.returncode==0,data
    assert data['success'] is True
    assert data['chat_choice_count']==1 and data['sse_event_count']==2 and data['sse_done'] is True
    assert [p['stream'] for p in state['requests']]==[False,True]


@pytest.mark.parametrize('mode,stage',[('missing-marker','json'),('json-for-stream','sse'),('no-done','sse'),('error','json')])
def test_probe_fail_closed(http_server,mode,stage):
    base,state,_=http_server;state['mode']=mode
    cp,data=call_probe(base)
    assert cp.returncode==2 and data['success'] is False and data['failed_stage']==stage
    assert 'PRIVATE PROVIDER BODY' not in cp.stdout+cp.stderr
    if mode=='error': assert data['bridge_error_code']=='openwebui_no_choices'


def test_models_missing_is_failure(http_server):
    base,_,_=http_server
    with pytest.raises(probe.ProbeError): probe.check_models(base,'absent-model',KEY,5)


@pytest.mark.parametrize('raw',[b'',b'{}',b'data: [DONE]\n\n',b'data: {"error":{}}\n\n',b'data: {"choices":[]}\n\ndata: [DONE]\n\n'])
def test_empty_and_malformed_sse_rejected(raw):
    with pytest.raises((probe.ProbeError,ValueError)): probe.parse_sse(raw)


def test_runtime_env_is_parsed_not_executed(tmp_path):
    sentinel=tmp_path/'must-not-exist'
    p=tmp_path/'runtime.env'
    p.write_text('PHYSNEMO_AGENT_MODEL_B64='+base64.b64encode(MODEL.encode()).decode()+
                 f'\ntouch {shlex.quote(str(sentinel))}\nIGNORED_B64=!!!!\n')
    assert probe.read_runtime_env(p)=={'PHYSNEMO_AGENT_MODEL':MODEL}
    assert not sentinel.exists()


def test_embedded_probe_is_exact_standalone_source():
    assert main.PHYSNEMO_AGENT_BRIDGE_CHECK_SOURCE==(ROOT.parent/'check-physnemo-agent-bridge-v2.9.18.py').read_text()


def test_missing_key_never_prompts(http_server):
    base,_,_=http_server
    cp,data=call_probe(base,env={'PHYSNEMO_AGENT_API_KEY':''})
    assert cp.returncode==2 and data['failed_stage']=='configuration'
    assert 'hidden' not in cp.stdout+cp.stderr


@pytest.mark.parametrize('value',['nan','inf','-1','0'])
def test_invalid_timeout_rejected(value,http_server):
    cp,data=call_probe(http_server[0],'--timeout',value)
    assert cp.returncode==2 and data['failed_stage']=='configuration'


LANGCHAIN_TEST_SHIM = '''# TEST DOUBLE ONLY: exercises installer wiring, not genuine LangChain compatibility.
import json, urllib.request
from types import SimpleNamespace
class ChatOpenAI:
    def __init__(self, **kw):
        assert kw['streaming'] is True and kw['stream_usage'] is True and kw['max_retries']==0
        self.kw=kw
    def query(self, text):
        req=urllib.request.Request(self.kw['base_url']+'/chat/completions',
            data=json.dumps({'model':self.kw['model'],'messages':[{'role':'user','content':text}],'stream':True}).encode(),
            headers={'Authorization':'Bearer '+self.kw['api_key'],'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=self.kw['timeout']) as r:
            assert r.headers.get_content_type()=='text/event-stream'
            content=r.read().decode()
        frames=[json.loads(line[6:]) for line in content.splitlines() if line.startswith('data: {')]
        if not frames: raise ValueError('No generation chunks were returned')
        return SimpleNamespace(content=frames[0]['choices'][0]['delta']['content'],tool_calls=[],additional_kwargs={})
    async def ainvoke(self, text): return self.query(text)
    async def astream(self, text): yield self.query(text)
    async def astream_events(self, text, version):
        assert version=='v2'
        yield {'event':'on_chat_model_stream','data':{'chunk':self.query(text)}}
'''


def test_generated_installer_preflight_live_with_client_test_double(tmp_path,http_server,monkeypatch):
    _,state,server=http_server
    root=tmp_path/'wsl root';(root/'config').mkdir(parents=True);(root/'.venv-nat/bin').mkdir(parents=True)
    (root/'.venv-nat/bin/python').symlink_to(sys.executable)
    values={'PHYSNEMO_AGENT_API_KEY':KEY,'PHYSNEMO_AGENT_MODEL':MODEL,
            'PHYSNEMO_AGENT_TRANSPORT':'openwebui-chat-api','PHYSNEMO_GATEWAY_PORT':str(server.server_port),
            'PHYSNEMO_GATEWAY_ROUTE':'physnemo'}
    (root/'config/runtime.env').write_text(''.join(k+'_B64='+base64.b64encode(v.encode()).decode()+'\n' for k,v in values.items()))
    bindir=tmp_path/'bin';bindir.mkdir();ip=bindir/'ip'
    ip.write_text('#!/bin/sh\necho "default via 127.0.0.1 dev eth0"\n');ip.chmod(0o755)
    lib=tmp_path/'lib';lib.mkdir();(lib/'langchain_openai.py').write_text(LANGCHAIN_TEST_SHIM)
    env=os.environ.copy();env['PATH']=str(bindir)+os.pathsep+env['PATH'];env['PYTHONPATH']=str(lib)
    class Component:
        def shell_path(self,x): return shlex.quote(x)
        def wsl_run(self,distro,script,**kwargs):
            assert distro=='test-distro' and kwargs['stage']=='openwebui-agent-bridge-preflight'
            assert kwargs['timeout']>=30*6+30
            subprocess.run(['bash','-n'],input=script,text=True,check=True,capture_output=True)
            cp=subprocess.run(['bash','-c',script],env=env,text=True,check=True,capture_output=True,timeout=20)
            assert KEY not in script+cp.stdout+cp.stderr
            return cp
    secret=tmp_path/'secret.json';secret.write_text(json.dumps({'agent_transport':'openwebui-chat-api','agent_model':MODEL}))
    monkeypatch.setattr(main,'physnemo_component',lambda:Component())
    monkeypatch.setattr(main,'PHYSNEMO_AGENT_SECRET_FILE',secret)
    monkeypatch.setattr(main,'PHYSNEMO_AGENT_BRIDGE_PREFLIGHT_REPORT',tmp_path/'report.json')
    result=main.probe_physnemo_agent_bridge({'physnemo_runtime':{'configured':True,'distro':'test-distro','linux_install_dir':str(root)}},timeout=5)
    assert result['success'],result
    assert result['langchain']['ainvoke_streaming'] is True
    assert len(state['requests'])==5
    assert (tmp_path/'report.json').exists()


def test_wrapper_rejects_stale_json_only_success_report(tmp_path,monkeypatch):
    class C:
        def shell_path(self,x): return shlex.quote(x)
        def wsl_run(self,*a,**k): return SimpleNamespace(stdout='{"success":true,"chat_choice_count":1}\n')
    secret=tmp_path/'secret';secret.write_text('{"agent_transport":"openwebui-chat-api"}')
    monkeypatch.setattr(main,'physnemo_component',lambda:C())
    monkeypatch.setattr(main,'PHYSNEMO_AGENT_SECRET_FILE',secret)
    monkeypatch.setattr(main,'PHYSNEMO_AGENT_BRIDGE_PREFLIGHT_REPORT',tmp_path/'report')
    report=main.probe_physnemo_agent_bridge({'physnemo_runtime':{'configured':True,'distro':'x','linux_install_dir':'/x'}})
    assert report['success'] is False


def test_direct_provider_still_skips_only_bridge_check(tmp_path,monkeypatch):
    p=tmp_path/'secret';p.write_text('{"agent_transport":"direct-openai"}')
    monkeypatch.setattr(main,'PHYSNEMO_AGENT_SECRET_FILE',p)
    monkeypatch.setattr(main,'PHYSNEMO_AGENT_BRIDGE_PREFLIGHT_REPORT',tmp_path/'report')
    report=main.probe_physnemo_agent_bridge({})
    assert report['success'] and report['skipped'] and not report['attempted']


def test_nat_start_script_bash_syntax_and_dynamic_host():
    script=main._render_integrated_physnemo_run_script('/root/.local/share/engineering-mcp-physnemo',9911)
    subprocess.run(['bash','-n'],input=script,text=True,check=True,capture_output=True)
    assert 'ip route show default' in script and 'PHYSNEMO_GATEWAY_PORT' in script and 'openwebui-api' in script

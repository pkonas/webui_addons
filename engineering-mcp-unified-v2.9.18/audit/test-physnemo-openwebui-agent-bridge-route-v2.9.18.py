from __future__ import annotations
import asyncio, importlib.util, json, sys, tempfile, threading, types
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import httpx

ROOT=Path(__file__).resolve().parent
SOURCE=ROOT/'engineering_mcp_unified-v2.9.18.py'
spec=importlib.util.spec_from_file_location('eng2911', SOURCE)
mod=importlib.util.module_from_spec(spec); assert spec.loader
spec.loader.exec_module(mod)

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def _auth(self): return self.headers.get('Authorization') == 'Bearer real-openwebui-key'
    def do_GET(self):
        if self.path == '/api/models' and self._auth():
            data=json.dumps({'data':[{'id':'e-infra.glm-5.3'}]}).encode()
            self.send_response(200); self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(data))); self.end_headers(); self.wfile.write(data); return
        self.send_response(401 if not self._auth() else 404); self.end_headers()
    def do_POST(self):
        n=int(self.headers.get('Content-Length','0')); raw=self.rfile.read(n)
        if self.path == '/api/chat/completions' and self._auth():
            payload=json.loads(raw)
            assert payload['model']=='e-infra.glm-5.3'
            assert payload['stream'] is False
            data=json.dumps({'id':'x','object':'chat.completion','choices':[{'index':0,'message':{'role':'assistant','content':'OK'},'finish_reason':'stop'}]}).encode()
            self.send_response(200); self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(data))); self.end_headers(); self.wfile.write(data); return
        self.send_response(401 if not self._auth() else 404); self.end_headers()

srv=ThreadingHTTPServer(('127.0.0.1',0), Handler)
thread=threading.Thread(target=srv.serve_forever,daemon=True); thread.start()
with tempfile.TemporaryDirectory() as td:
    secret=Path(td)/'secret.json'
    secret.write_text(json.dumps({'bridge_secret':'bridge-secret','openwebui_base_url':f'http://127.0.0.1:{srv.server_port}','openwebui_api_key':'real-openwebui-key','agent_model':'e-infra.glm-5.3'}))
    mod.PHYSNEMO_AGENT_SECRET_FILE=secret
    captured={}
    pkg=types.ModuleType('mcpo'); pkg.__path__=[]
    mm=types.ModuleType('mcpo.main')
    from fastapi import FastAPI
    mm.FastAPI=FastAPI
    async def run(*args,**kwargs):
        captured['app']=mm.FastAPI(title='physnemo')
    mm.run=run
    pkg.main=mm
    old_mcpo=sys.modules.get('mcpo'); old_main=sys.modules.get('mcpo.main')
    sys.modules['mcpo']=pkg; sys.modules['mcpo.main']=mm
    try:
        rc=mod.run_named_mcpo(['--api-key','gateway','--config',str(Path(td)/'mcpo.json')])
        assert rc==0, rc
    finally:
        if old_mcpo is None: sys.modules.pop('mcpo',None)
        else: sys.modules['mcpo']=old_mcpo
        if old_main is None: sys.modules.pop('mcpo.main',None)
        else: sys.modules['mcpo.main']=old_main
    app=captured['app']
    async def checks():
        tr=httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=tr,base_url='http://test') as c:
            r=await c.get('/openwebui-api/models'); assert r.status_code==403, r.text
            r=await c.get('/openwebui-api/models',headers={'Authorization':'Bearer bridge-secret'}); assert r.status_code==200, r.text; assert r.json()['data'][0]['id']=='e-infra.glm-5.3'
            req={'model':'e-infra.glm-5.3','messages':[{'role':'user','content':'x'}],'stream':True}
            r=await c.post('/openwebui-api/chat/completions',headers={'Authorization':'Bearer bridge-secret'},json=req); assert r.status_code==200, r.text; assert r.headers['content-type'].startswith('text/event-stream')
            assert r.headers['x-engineering-mcp-bridge-protocol']=='buffered-sse-v1'
            assert r.text.endswith('data: [DONE]\n\n')
            frames=[json.loads(line[6:]) for line in r.text.splitlines() if line.startswith('data: {')]
            assert frames[0]['choices'][0]['delta']['content']=='OK'
            assert frames[1]['choices'][0]['finish_reason']=='stop'
            req['stream']=False
            r=await c.post('/openwebui-api/chat/completions',headers={'Authorization':'Bearer bridge-secret'},json=req)
            assert r.status_code==200 and r.headers['content-type']=='application/json'
            assert r.json()['choices'][0]['message']['content']=='OK'
            assert '/openwebui-api/chat/completions' not in app.openapi().get('paths', {})
            bad=dict(req); bad['model']='wrong'
            r=await c.post('/openwebui-api/chat/completions',headers={'Authorization':'Bearer bridge-secret'},json=bad); assert r.status_code==400, r.text
    asyncio.run(checks())
srv.shutdown(); srv.server_close()
print('BRIDGE_ROUTE_TEST_OK')

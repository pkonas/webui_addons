#!/usr/bin/env python3
from __future__ import annotations
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'engineering_mcp_unified-v2.9.18.py'
TMP = tempfile.TemporaryDirectory(prefix='emcp2911-')
os.environ['ENGINEERING_MCP_HOME'] = TMP.name
spec = importlib.util.spec_from_file_location('emcp2911', SOURCE)
assert spec and spec.loader
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

DB = Path(TMP.name) / 'webui.db'
con = sqlite3.connect(DB)
con.executescript('''
CREATE TABLE config (key TEXT PRIMARY KEY, value JSON NOT NULL, updated_at BIGINT);
CREATE TABLE user (id TEXT PRIMARY KEY, email TEXT, role TEXT, created_at BIGINT);
CREATE TABLE api_key (id TEXT PRIMARY KEY, user_id TEXT NOT NULL, key TEXT UNIQUE NOT NULL, data JSON, expires_at BIGINT, last_used_at BIGINT, created_at BIGINT NOT NULL, updated_at BIGINT NOT NULL);
CREATE TABLE tool (id TEXT PRIMARY KEY);
CREATE TABLE function (id TEXT PRIMARY KEY, type TEXT, is_active BOOLEAN, is_global BOOLEAN, updated_at BIGINT);
CREATE TABLE chat (id TEXT PRIMARY KEY, user_id TEXT, chat JSON, updated_at BIGINT);
''')
con.execute("INSERT INTO user(id,email,role,created_at) VALUES('admin-1','admin@example.test','admin',1)")
con.execute("INSERT INTO config(key,value,updated_at) VALUES('auth.enable_api_keys','false',1)")
con.execute("INSERT INTO config(key,value,updated_at) VALUES('auth.api_key.endpoint_restrictions','true',1)")
con.execute("INSERT INTO config(key,value,updated_at) VALUES('auth.api_key.allowed_endpoints','\"/api/usage\"',1)")
con.execute("INSERT INTO tool(id) VALUES('anonymizovat')")
con.execute("INSERT INTO function(id,type,is_active,is_global,updated_at) VALUES('pseudo_anonymization','filter',0,0,1)")
chat = {'models':['e-infra.glm-5.3'], 'history': {'messages': {}}}
con.execute("INSERT INTO chat(id,user_id,chat,updated_at) VALUES('chat-1','admin-1',?,99)", (json.dumps(chat),))
con.commit(); con.close()

state = {'connections': [
    {'type':'openapi','url':'http://127.0.0.1:8200/weknora','path':'weknora-openapi.json','info':{'id':'weknora','name':'old'}},
]}
router_state = {'function': None}
expected_key = {'value': ''}
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def _auth(self): return self.headers.get('Authorization') == 'Bearer ' + expected_key['value']
    def _json(self, code, payload):
        raw=json.dumps(payload).encode(); self.send_response(code); self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw)
    def do_GET(self):
        if not self._auth(): return self._json(401, {'detail':'bad key'})
        if self.path == '/api/models': return self._json(200, {'data':[{'id':'e-infra.glm-5.3'},{'id':'other'}]})
        if self.path == '/api/v1/configs/tool_servers': return self._json(200, {'TOOL_SERVER_CONNECTIONS':state['connections']})
        if self.path == '/api/v1/functions/id/engineering_mcp_tool_router':
            if router_state['function'] is None: return self._json(401, {'detail':'Function not found'})
            return self._json(200, router_state['function'])
        if self.path == '/_app/version.json': return self._json(200, {'version':'0.11.3'})
        return self._json(404, {})
    def do_POST(self):
        if not self._auth(): return self._json(401, {'detail':'bad key'})
        length=int(self.headers.get('Content-Length','0')); payload=json.loads(self.rfile.read(length) or b'{}')
        if self.path == '/api/v1/configs/tool_servers':
            state['connections']=payload['TOOL_SERVER_CONNECTIONS']; return self._json(200, payload)
        if self.path == '/api/v1/configs/tool_servers/verify': return self._json(200, {'ok':True})
        if self.path == '/api/v1/functions/create':
            router_state['function']={**payload,'type':'filter','is_active':False,'is_global':False}
            return self._json(200, router_state['function'])
        if self.path == '/api/v1/functions/id/engineering_mcp_tool_router/update':
            router_state['function'].update(payload); router_state['function']['type']='filter'
            return self._json(200, router_state['function'])
        if self.path == '/api/v1/functions/id/engineering_mcp_tool_router/toggle':
            router_state['function']['is_active']=not bool(router_state['function'].get('is_active'))
            return self._json(200, router_state['function'])
        if self.path == '/api/v1/functions/id/engineering_mcp_tool_router/toggle/global':
            router_state['function']['is_global']=not bool(router_state['function'].get('is_global'))
            return self._json(200, router_state['function'])
        return self._json(404,{})

server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
base=f'http://127.0.0.1:{server.server_port}'

options={
    'openwebui_database':str(DB),
    'openwebui_native_sync':True,
    'openwebui_dlp_repair':True,
    'physnemo_agent_auto_detect':True,
    'physnemo_agent_api_key_file':'',
    'physnemo_openwebui_api_key_file':'',
    'physnemo_openwebui_url':base,
    'physnemo_agent_base_url':'',
    'physnemo_agent_model':'',
}
secret=m._resolve_physnemo_agent_secret(options)
assert secret['configured'] is True, secret
assert secret['agent_transport']=='openwebui-chat-api'
assert secret['agent_model']=='e-infra.glm-5.3'
assert secret['openwebui_database']==str(DB)
expected_key['value']=secret['openwebui_api_key']
assert expected_key['value'].startswith('sk-')

con=sqlite3.connect(DB)
assert json.loads(con.execute("SELECT value FROM config WHERE key='auth.enable_api_keys'").fetchone()[0]) is True
allowed=json.loads(con.execute("SELECT value FROM config WHERE key='auth.api_key.allowed_endpoints'").fetchone()[0])
assert '/api/chat/completions' in allowed and '/api/v1/configs/tool_servers' in allowed and '/api/v1/functions' in allowed
row=con.execute("SELECT is_active,is_global FROM function WHERE id='pseudo_anonymization'").fetchone(); assert tuple(row)==(1,1)
assert con.execute("SELECT COUNT(*) FROM api_key").fetchone()[0]==1
con.close()

m.configured_routes=lambda: ['weknora','matlab','physnemo']
app_state={'mcpo_port':8200,'api_key':'gateway-secret','scan':{'docker':{'openwebui_container':False}},'physnemo_runtime':{'configured':True}}
report=m.sync_physnemo_openwebui_tool_server(app_state,options)
assert report['updated'] and report['verified'] and report['chat_tool_registration_ready'], report
assert report['chat_tool_execution_ready'] is False and report['physnemo_native_tools_verified'] is False
assert 'NOT verified' in report['reason']
# Only the independent local+model probe can turn registration into execution readiness.
phase = {'success':True,'missing_tools':[], 'exact_content_roundtrip':True, 'script_exact':True,
         'execution_summary':{'succeeded':1,'attempts':1,'failed':0},
         'tool_summary':{'succeeded':7,'attempts':7,'failed':0}}
app_state['physnemo_native_tools_preflight'] = {**phase,
    'contract':'PHYSNEMO_NATIVE_TOOL_DISPATCH_V5',
    'preflight_contract':'PHYSNEMO_NATIVE_TOOL_PREFLIGHT_V5',
    'local_probe':dict(phase),'model_probe':dict(phase),'model_summary':{'tool_calls':7},
    'selected_tool_transport':'native','native_tool_calls_verified':True,'model_tool_execution_verified':True}
report=m.sync_physnemo_openwebui_tool_server(app_state,options)
assert report['chat_tool_execution_ready'] and report['physnemo_native_tools_verified'], report
for change in ({'success':False}, {'contract':'PHYSNEMO_NATIVE_TOOL_DISPATCH_V1'},
               {'model_probe':{'success':False}}, {'local_probe':{'success':False}}):
    broken={**app_state, 'physnemo_native_tools_preflight':{**app_state['physnemo_native_tools_preflight'],**change}}
    failed=m.sync_physnemo_openwebui_tool_server(broken,options)
    assert failed['chat_tool_registration_ready'] is True
    assert failed['chat_tool_execution_ready'] is False
# JSON compatibility must not falsely claim native function calling is verified.
json_state = {**app_state, 'physnemo_native_tools_preflight': {
    **app_state['physnemo_native_tools_preflight'], 'selected_tool_transport':'json_actions_v1',
    'native_tool_calls_verified':False, 'model_summary':{'tool_calls':0,'json_actions':7}}}
json_report = m.sync_physnemo_openwebui_tool_server(json_state, options)
assert json_report['chat_tool_execution_ready'] is True
assert json_report['physnemo_model_tools_verified'] is True
assert json_report['physnemo_native_tools_verified'] is False
assert json_report['physnemo_selected_tool_transport'] == 'json_actions_v1'
ids={str((x.get('info') or {}).get('id')) for x in state['connections']}
assert {'weknora','matlab','physnemo'} <= ids, ids
assert report['dlp']['ready'] is True
assert report['tool_router']['ready'] is True
assert router_state['function']['is_active'] and router_state['function']['is_global']

for path in (m.PHYSNEMO_AGENT_DETECTION_REPORT,m.PHYSNEMO_OPENWEBUI_SYNC_REPORT,m.OPENWEBUI_NATIVE_SYNC_REPORT,m.OPENWEBUI_DLP_PREFLIGHT_REPORT,m.OPENWEBUI_ENGINEERING_TOOL_ROUTER_REPORT):
    text=Path(path).read_text(encoding='utf-8')
    assert expected_key['value'] not in text, path

# Idempotent resume reuses the same managed key.
secret2=m._resolve_physnemo_agent_secret(options)
assert secret2['openwebui_api_key']==expected_key['value']
con=sqlite3.connect(DB); assert con.execute("SELECT COUNT(*) FROM api_key").fetchone()[0]==1; con.close()

server.shutdown();server.server_close();TMP.cleanup()
print('OPENWEBUI_NATIVE_SYNC_V2912_OK')

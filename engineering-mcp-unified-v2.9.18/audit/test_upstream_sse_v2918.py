"""Actual bridge routes with mocked upstream byte streams; no external backend."""
import copy
import json
import pytest
import test_bridge_protocol_v2918 as b

TOOL={'type':'function','function':{'name':'physnemo_internal__workspace_write','parameters':{'type':'object'}}}
CHOICE={'type':'function','function':{'name':TOOL['function']['name']}}
ARGS={'relative_path':'workspace/test.py','content':'\n  \'quoted\' "double" \\n Kármán\n','overwrite':False}

def chunk(delta=None,reason=None,index=0,**kwargs):
    return {'id':'chatcmpl-fixture','object':'chat.completion.chunk','created':123,'model':'configured-model',
            'choices':[{'index':index,'delta':delta or {},'finish_reason':reason}],**kwargs}

def wire(frames,done=True):
    return (''.join('data: '+json.dumps(f,ensure_ascii=False)+'\n\n' for f in frames)+('data: [DONE]\n\n' if done else '')).encode()

def frames():
    args=json.dumps(ARGS,ensure_ascii=False)
    return [chunk({'role':'assistant','tool_calls':[{'index':0,'id':'call-1','type':'function','function':{'name':'physnemo_internal__','arguments':''}}]}),
            chunk({'tool_calls':[{'index':0,'function':{'name':'workspace_write','arguments':args[:20]}}]}),
            chunk({'tool_calls':[{'index':0,'function':{'arguments':args[20:]}}]}),chunk(reason='tool_calls')]

@pytest.mark.parametrize('client_stream',[True,False])
def test_tool_request_streams_upstream_but_preserves_client_protocol_and_arguments(client_stream):
    app,calls=b.make_app(raw=wire(frames()),media='text/event-stream')
    r=b.post(app,{'model':'configured-model','stream':client_stream,'tools':[TOOL], 'tool_choice':CHOICE,
                 'params':{'temperature':0.2},'stream_options':{'include_usage':True}})
    assert r.status_code==200,r.text
    assert len(calls)==1
    sent=json.loads(calls[0][3]['body'])
    assert sent['stream'] is True and sent['tools']==[TOOL] and sent['tool_choice']==CHOICE
    assert sent['params']=={'temperature':0.2,'function_calling':'native'}
    assert 'stream_options' not in sent
    assert calls[0][3]['accept']=='text/event-stream'
    assert r.headers['x-engineering-mcp-upstream-transport']=='sse'
    message=b.events(r)[0]['choices'][0]['delta'] if client_stream else r.json()['choices'][0]['message']
    tool=message['tool_calls'][0]
    assert tool['id']=='call-1' and tool['function']['name']==TOOL['function']['name']
    assert json.loads(tool['function']['arguments'])==ARGS
    assert (b.events(r)[1]['choices'][0]['finish_reason'] if client_stream else r.json()['choices'][0]['finish_reason'])=='tool_calls'


def test_tool_bearing_request_can_also_receive_full_json_upstream():
    data=copy.deepcopy(b.GOOD);data['choices'][0]['message']={'role':'assistant','content':None,'tool_calls':[
        {'id':'call-1','type':'function','function':{'name':TOOL['function']['name'],'arguments':json.dumps(ARGS)}}]}
    data['choices'][0]['finish_reason']='tool_calls'
    r=b.post(b.make_app(completion=data)[0],{'tools':[TOOL],'tool_choice':CHOICE,'stream':False})
    assert r.status_code==200 and r.json()==data


def test_pipe_single_complete_completion_event_without_done_is_supported():
    r=b.post(b.make_app(raw=wire([b.GOOD],False),media='text/event-stream')[0],{'stream':False,'tools':[TOOL]})
    assert r.status_code==200 and r.json()==b.GOOD


def test_usage_comments_crlf_and_pipe_trailing_stop_are_handled():
    fs=frames()+[chunk(reason='stop'),{'object':'chat.completion.chunk','choices':[],
         'usage':{'prompt_tokens':2,'completion_tokens':3,'total_tokens':5}}]
    raw=b': keepalive\r\n\r\n'+wire(fs).replace(b'\n',b'\r\n')
    raw+=wire([chunk({'content':'must not be replayed'})])
    r=b.post(b.make_app(raw=raw,media='text/event-stream')[0],{'stream':False,'tools':[TOOL]})
    assert r.status_code==200,r.text
    assert r.json()['choices'][0]['finish_reason']=='tool_calls'
    assert r.json()['usage']['total_tokens']==5
    assert r.json()['choices'][0]['message']['content'] is None


def test_empty_tools_stays_json_no_native_mode_forced():
    app,calls=b.make_app();r=b.post(app,{'tools':[],'stream':False})
    sent=json.loads(calls[0][3]['body'])
    assert r.status_code==200 and sent['tools']==[] and sent['stream'] is False and 'params' not in sent

@pytest.mark.parametrize('raw,code',[
    (wire(frames(),False),'openwebui_stream_incomplete'),
    (wire(frames()[:-1]),'openwebui_stream_incomplete'),
    (b'data: [DONE]\n\n','openwebui_stream_incomplete'),
    (b'data: {bad}\n\n','openwebui_stream_invalid_json'),
    (wire([{'error':{'message':'PRIVATE UPSTREAM ERROR'}}]),'openwebui_stream_error'),
    (wire([{'object':'unknown','choices':[]}]),'openwebui_stream_invalid_object'),
    (wire([chunk({'content':['unsupported']})]),'openwebui_stream_invalid_text'),
    (wire([chunk(index=-1)]),'openwebui_stream_invalid_index'),
    (wire([chunk({'tool_calls':[{'index':0,'function':{'arguments':{}}}]})]),'openwebui_stream_invalid_arguments'),
    (wire([chunk({'role':'system'})]),'openwebui_stream_invalid_role'),
    (b'data: \xff\xfe\n\n','openwebui_stream_invalid_utf8'),
])
def test_incomplete_or_bad_upstream_stream_never_becomes_success(raw,code):
    app,calls=b.make_app(raw=raw,media='text/event-stream');r=b.post(app,{'stream':False,'tools':[TOOL]})
    assert r.status_code==502 and r.json()['error']['code']==code,r.text
    assert len(calls)==1 and 'PRIVATE UPSTREAM ERROR' not in r.text


def test_assistant_prose_containing_sse_is_not_reinterpreted():
    # The old non-streaming Pipe signature is still TEXT, not executable calls.
    data=copy.deepcopy(b.GOOD);data['choices'][0]['message']['content']=wire(frames()).decode()
    r=b.post(b.make_app(completion=data)[0],{'tools':[TOOL],'stream':False})
    assert r.status_code==200 and 'tool_calls' not in r.json()['choices'][0]['message']

@pytest.mark.parametrize('tools',[{},'a',1])
def test_invalid_tools_shape_rejected_before_network(tools):
    app,calls=b.make_app();r=b.post(app,{'tools':tools})
    assert r.status_code==400 and not calls


def test_http_provider_error_preserved_without_repair():
    app,calls=b.make_app(raw=b'{"error":"denied"}',status=403)
    r=b.post(app,{'tools':[TOOL]})
    assert r.status_code==403 and len(calls)==1


def test_real_urllib_upstream_with_a_local_http_sse_server():
    """Real sockets and urllib; model backend is a local test HTTP server."""
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    import threading
    import textwrap
    captured=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            captured.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
            self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers()
            for frame in frames():
                self.wfile.write(wire([frame],False));self.wfile.flush()
            self.wfile.write(b'data: [DONE]\n\n');self.wfile.flush()
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    t=threading.Thread(target=server.serve_forever,daemon=True);t.start()
    try:
        source=b.SOURCE
        start=source.index('                def _physnemo_openwebui_request(')
        end=source.index('                @self.get(',start)
        request_impl=textwrap.dedent(source[start:end])
        source='import urllib.request\nimport urllib.error\n'+request_impl+f'''
def _physnemo_agent_bridge_config(request):
    return "http://127.0.0.1:{server.server_address[1]}","TEST-UPSTREAM-KEY","configured-model","TEST-ONLY"
'''+textwrap.dedent(b.AFTER)
        app,_=b.make_app(source=source)
        r=b.post(app,{'stream':False,'tools':[TOOL],'tool_choice':CHOICE})
        assert r.status_code==200,r.text
        assert len(captured)==1 and captured[0]['stream'] is True
        actual=r.json()['choices'][0]['message']['tool_calls'][0]['function']
        assert json.loads(actual['arguments'])==ARGS
    finally:
        server.shutdown();server.server_close();t.join(timeout=3)

@pytest.mark.parametrize('raw',[
    wire([chunk(reason=['not a string'])]),
    wire([{'object':'chat.completion','choices':123}]),
])
def test_malformed_sse_field_types_return_controlled_failure(raw):
    r=b.post(b.make_app(raw=raw,media='text/event-stream')[0],{'tools':[TOOL]})
    assert r.status_code==502 and r.json()['error']['code'].startswith('openwebui_stream_')

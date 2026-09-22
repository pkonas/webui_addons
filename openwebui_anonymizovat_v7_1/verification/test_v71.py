"""Component tests. WebUI adapters are simulated; no deployed WebUI is used."""
import asyncio
import base64
import contextlib
import copy
import importlib
import inspect
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch, AsyncMock

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import dlp_guard_filter as g
import anonymizovat_tool as t
USER={'id':'user-a','role':'user'}
KEY='synthetic-key-for-component-tests-not-production-987654'
PROMPT='Shrň případ.\nJméno: Jan Novák\nE-mail: jan.novak@example.invalid\nTelefon: +420 000 111 222'

@contextlib.contextmanager
def fake_webui(guard=None, tool_callable=None):
    modules={}
    for name in ['open_webui','open_webui.env','open_webui.models','open_webui.models.functions',
                 'open_webui.models.users','open_webui.utils','open_webui.utils.tools','open_webui.utils.plugin']:
        modules[name]=types.ModuleType(name)
    modules['open_webui.env'].VERSION='0.11.3'
    row=types.SimpleNamespace(id='dlp_guard_v7',is_active=True,is_global=True,type='filter')
    funcs=types.SimpleNamespace(get_function_by_id=AsyncMock(return_value=row),
        get_function_valves_by_id=AsyncMock(return_value=guard.valves.model_dump() if guard else {}))
    modules['open_webui.models.functions'].Functions=funcs
    modules['open_webui.utils.plugin'].get_function_module_from_cache=AsyncMock(return_value=(guard,None,None))
    modules['open_webui.models.users'].Users=types.SimpleNamespace(get_user_by_id=AsyncMock(return_value=types.SimpleNamespace(**USER)))
    modules['open_webui.utils.tools'].get_tools=AsyncMock(return_value={
        'anonymizovat':{'tool_id':'anonymizovat','spec':{'name':'anonymizovat'},'callable':tool_callable}
    } if tool_callable else {})
    with patch.dict(sys.modules,modules):
        yield modules

class Core(unittest.TestCase):
    def setUp(self):
        self.g=g.Filter();self.g.valves.hmac_key=KEY
    def test_all_14_languages(self):
        self.assertEqual(len(g.LANGUAGES),14)
        for lang in g.LANGUAGES:
            with self.subTest(lang=lang):
                label=g.LABELS[lang]['PERSON'][0]
                value='山田花子' if lang=='ja' else '王小明' if lang=='zh' else 'Jan Example'
                result=self.g.anonymize_payload(label+': '+value,[],USER['id'])
                self.assertNotIn(value,result['text'])
                self.assertIn('[[PERSON_',result['text'])
    def test_same_prompt_file_token(self):
        result=self.g.anonymize_payload(PROMPT,[('data.txt',PROMPT.encode())],USER['id'])
        self.assertNotIn('jan.novak@example.invalid',result['text'])
        token=[x for x in result['text'].splitlines() if x.startswith('E-mail:')]
        self.assertEqual(len(set(token)),1)
    def test_determinism(self):
        self.assertEqual(self.g.anonymize_payload(PROMPT,[],USER['id']),self.g.anonymize_payload(PROMPT,[],USER['id']))
    def test_user_separation(self):
        self.assertNotEqual(self.g.anonymize_payload(PROMPT,[],'a')['text'],self.g.anonymize_payload(PROMPT,[],'b')['text'])
    def test_idempotent_recheck(self):
        clean=self.g.anonymize_payload(PROMPT,[],USER['id'])['text']
        self.assertFalse(self.g._analyse([clean],USER['id'])[1])
    def test_missing_key(self):
        self.g.valves.hmac_key=''
        with self.assertRaisesRegex(g.DLPError,'HMAC'):self.g.anonymize_payload(PROMPT,[],USER['id'])
    def test_uninspectable_file(self):
        with self.assertRaises(g.DLPError):self.g.anonymize_payload('Shrň.',[('image.png',b'\x89PNG\r\n\x1a\n')],USER['id'])
    def test_only_one_public_tool_method(self):
        methods=[name for name,fn in inspect.getmembers(t.Tools(),inspect.ismethod) if not name.startswith('_')]
        self.assertEqual(methods,['anonymizovat'])
        self.assertTrue(all(k.startswith('__') for k in inspect.signature(t.Tools().anonymizovat).parameters))
    def test_no_page_automation_in_tool(self):
        code=(ROOT/'anonymizovat_tool.py').read_text()
        for forbidden in ['window.postMessage(',"getElementById('new-chat",'Storage.upload_file','delete_chat_by_id','localStorage.setItem','fetch(']:
            self.assertNotIn(forbidden,code)
    def test_js_serialization(self):
        data='</script>";alert(1);\\'
        self.assertNotIn('<',t.js_data(data))
        self.assertEqual(json.loads(t.js_data(data)),data)

class RequestFlow(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.guard = g.Filter(); self.guard.valves.hmac_key = KEY
        self.req = types.SimpleNamespace(state=types.SimpleNamespace())
        self.emitter = AsyncMock(); self.caller = AsyncMock()
        self.body = {'model':'demo','messages':[{'role':'user','id':'u1','content':PROMPT}], 'tool_ids':['anonymizovat']}
    async def call(self, body=None, metadata=None):
        return await self.guard.inlet(body if body is not None else self.body,USER,self.req,metadata,self.emitter,self.caller)
    async def approved(self):
        pending = getattr(self.req.state,g.DIALOG_INPUT)
        self.assertEqual(getattr(self.req.state,g.DIALOG_CALL),(USER['id'],'anonymizovat'))
        result = self.guard.anonymize_request(pending['messages'], pending['initial_text'] or 'Shrň E-217.', [], USER['id'])
        return {'protocol':t.PROTOCOL,'status':'approved','sanitized_messages':result['messages']}
    async def test_sensitive_enabled_reaches_tool_then_passes_recheck(self):
        original=copy.deepcopy(self.body)
        with fake_webui(self.guard,self.approved):
            out=await self.call(); final=await self.guard.request(out,USER,self.req,{},self.emitter)
        self.assertNotIn('jan.novak@example.invalid',json.dumps(final))
        self.assertIn('[[EMAIL_',json.dumps(final)); self.assertEqual(self.body,original)
        self.assertFalse(hasattr(self.req.state,g.DIALOG_INPUT)); self.assertFalse(hasattr(self.req.state,g.DIALOG_CALL))
    async def test_sensitive_disabled_is_blocked(self):
        self.body.pop('tool_ids')
        with fake_webui(self.guard,self.approved),self.assertRaisesRegex(RuntimeError,'DLP_SENSITIVE_DATA'):
            await self.call()
        self.caller.assert_not_called()
    async def test_sensitive_history_is_sanitized(self):
        self.body['messages'].insert(0,{'role':'assistant','id':'old','content':'E-mail: jan.novak@example.invalid'})
        with fake_webui(self.guard,self.approved):
            out=await self.call();final=await self.guard.request(out,USER,self.req)
        self.assertEqual(len(final['messages']),2)
        self.assertEqual(final['messages'][0]['role'],'assistant')
        self.assertNotIn('jan.novak@example.invalid',json.dumps(final))
    async def test_old_sensitive_history_clean_current(self):
        self.body['messages'].insert(0,{'role':'user','content':PROMPT})
        self.body['messages'][-1]['content']='Shrň E-217.'
        with fake_webui(self.guard,self.approved):
            out=await self.call()
        self.assertNotIn('jan.novak@example.invalid',json.dumps(out))
    async def test_raw_tool_output_is_still_blocked(self):
        fn=AsyncMock(return_value={'protocol':t.PROTOCOL,'status':'approved','sanitized_messages':self.body['messages']})
        with fake_webui(self.guard,fn),self.assertRaisesRegex(RuntimeError,'DLP_SENSITIVE_DATA'):
            await self.call()
        self.assertFalse(hasattr(self.req.state,g.REQUEST_MARKER))
    async def test_cancellation_never_returns_body(self):
        fn=AsyncMock(return_value={'protocol':t.PROTOCOL,'status':'cancelled','code':'DLP_CANCELLED'})
        with fake_webui(self.guard,fn),self.assertRaisesRegex(RuntimeError,'DLP_CANCELLED'):
            await self.call()
        self.assertFalse(hasattr(self.req.state,g.DIALOG_INPUT))
    async def test_wrong_tool_id_does_not_bypass(self):
        self.body['tool_ids']=['another-tool']
        with fake_webui(self.guard,self.approved),self.assertRaisesRegex(RuntimeError,'DLP_SENSITIVE_DATA'):
            await self.call()
    async def test_selected_without_access_blocked(self):
        with fake_webui(self.guard),self.assertRaisesRegex(RuntimeError,'DLP_TOOL_UNAVAILABLE'):
            await self.call()
    async def test_metadata_selection(self):
        self.body.pop('tool_ids')
        meta={'tool_ids':['anonymizovat']}
        with fake_webui(self.guard,self.approved):out=await self.call(metadata=meta)
        self.assertIn('[[PERSON_',out['messages'][-1]['content'])
        self.assertNotIn('tool_ids',meta)
    async def test_old_protocol_rejected(self):
        fn=AsyncMock(return_value={'protocol':'dlp-workspace/7.0','status':'approved','sanitized_prompt':'Clean'})
        with fake_webui(self.guard,fn),self.assertRaisesRegex(RuntimeError,'DLP_TOOL_PROTOCOL'):
            await self.call()
    async def test_role_and_ids_may_not_change(self):
        for row in [{'role':'system','id':'u1','content':'Text'}, {'role':'user','id':'stolen','content':'Text'}]:
            fn=AsyncMock(return_value={'protocol':t.PROTOCOL,'status':'approved','sanitized_messages':[row]})
            with fake_webui(self.guard,fn),self.assertRaisesRegex(RuntimeError,'DLP_TOOL_OUTPUT'):
                await self.call()
    async def test_late_sensitive_injection_blocks(self):
        with fake_webui(self.guard,self.approved):
            out=await self.call();out['messages'].append({'role':'system','content':PROMPT})
            with self.assertRaisesRegex(RuntimeError,'DLP_SENSITIVE_DATA'):
                await self.guard.request(out,USER,self.req)
    async def test_late_file_injection_blocks(self):
        with fake_webui(self.guard,self.approved):
            out=await self.call();out['files']=[{'id':'late'}]
            with self.assertRaisesRegex(RuntimeError,'DLP_LATE_OR_EXCESS_FILES'):
                await self.guard.request(out,USER,self.req)
    async def test_request_without_inlet(self):
        with fake_webui(self.guard),self.assertRaisesRegex(RuntimeError,'DLP_PRECHECK_MISSING'):
            await self.guard.request(self.body,USER,self.req)
    async def test_invalid_backend(self):
        with fake_webui(self.guard) as mods:
            mods['open_webui.env'].VERSION='0.8.0'
            with self.assertRaisesRegex(RuntimeError,'DLP_VERSION'):await self.call()
    async def test_missing_key_stops_before_collecting(self):
        self.guard.valves.hmac_key=''
        fn=AsyncMock()
        with fake_webui(self.guard,fn),self.assertRaisesRegex(RuntimeError,'DLP_HMAC_KEY_REQUIRED'):
            await self.call()
        fn.assert_not_awaited()
    async def test_missing_callback_stops_before_tool(self):
        self.caller=None;fn=AsyncMock()
        with fake_webui(self.guard,fn),self.assertRaisesRegex(RuntimeError,'DLP_BROWSER_CONNECTION_REQUIRED'):
            await self.call()
        fn.assert_not_awaited()
    async def test_raw_file_refs_removed_from_all_carriers(self):
        self.body['files']=[{'id':'abc'}]
        self.body['metadata']={'files':[{'id':'abc'}]}
        self.body['messages'][0]['files']=[{'id':'abc'}]
        meta={'files':[{'id':'abc'}]}
        async def cb():
            pending=getattr(self.req.state,g.DIALOG_INPUT)
            self.assertEqual(pending['file_ids'],['abc'])
            result=self.guard.anonymize_request(pending['messages'],pending['initial_text'],[('data.txt',PROMPT.encode())],USER['id'])
            return {'protocol':t.PROTOCOL,'status':'approved','sanitized_messages':result['messages']}
        with fake_webui(self.guard,cb):
            out=await self.call(metadata=meta)
            final=await self.guard.request(out,USER,self.req,meta)
        self.assertNotIn('"files"',json.dumps(final));self.assertNotIn('jan.novak@example.invalid',json.dumps(final))
    async def test_clean_without_tool_stays_usable(self):
        self.body['messages'][0]['content']='Shrň chybu E-217.';self.body['tool_ids']=[]
        with fake_webui(self.guard):out=await self.call()
        self.assertEqual(out['messages'][0]['content'],'Shrň chybu E-217.')
    async def test_invalid_selection(self):
        self.body['tool_ids']='anonymizovat'
        with fake_webui(self.guard),self.assertRaisesRegex(RuntimeError,'DLP_TOOL_SELECTION'):await self.call()
    async def test_extra_model_control_is_not_auto_sanitized(self):
        self.body['stop']=PROMPT
        with fake_webui(self.guard,self.approved),self.assertRaisesRegex(RuntimeError,'DLP_SENSITIVE_DATA'):
            await self.call()
    async def test_failed_reinvocation_clears_old_marker(self):
        with fake_webui(self.guard,self.approved):await self.call()
        self.body['tool_ids']=[]
        with fake_webui(self.guard),self.assertRaises(RuntimeError):await self.call()
        self.assertFalse(hasattr(self.req.state,g.REQUEST_MARKER))
    async def test_tool_failure_does_not_print_sensitive_trace(self):
        fn=AsyncMock(side_effect=ValueError(PROMPT))
        with fake_webui(self.guard,fn),self.assertRaisesRegex(RuntimeError,'DLP_CHECK_FAILED') as exc:
            await self.call()
        self.assertNotIn('jan.novak@example.invalid',str(exc.exception)+str(self.emitter.call_args_list))

class AddedCore(unittest.TestCase):
    def setUp(self):
        self.guard=g.Filter();self.guard.valves.hmac_key=KEY
    def test_shared_alias_across_history_and_files(self):
        rows=[{'role':'assistant','content':'Jan Novák hlásí E-217.'},{'role':'user','content':'Shrň.'}]
        result=self.guard.anonymize_request(rows,'Shrň.',[('data.txt',PROMPT.encode())],USER['id'])
        self.assertNotIn('Jan Novák',str(result))
        person=g.TOKEN.search(result['messages'][0]['content']).group()
        self.assertIn(person,result['messages'][-1]['content'])
    def test_name_field_is_sanitized(self):
        result=self.guard.anonymize_request([{'role':'user','content':PROMPT,'name':'Jan Novák'}],PROMPT,[],USER['id'])
        self.assertNotIn('Jan Novák',str(result))
    def test_exact_safe_launchers_empty(self):
        for cmd in ['Otevřít anonymizátor.','Otevřít anonymizátor','/anonymizovat']:
            p=self.guard.prepare_dialog_input({'messages':[{'role':'user','content':cmd}]},{},USER['id'])
            self.assertEqual(p['initial_text'],'')
    def test_real_input_never_lost(self):
        p=self.guard.prepare_dialog_input({'messages':[{'role':'user','content':PROMPT}]},{},USER['id'])
        self.assertEqual(p['initial_text'],PROMPT)
    def test_anonymize_request_preserves_input(self):
        rows=[{'role':'user','content':PROMPT}]; before=copy.deepcopy(rows)
        self.guard.anonymize_request(rows,PROMPT,[],USER['id'])
        self.assertEqual(rows,before)
    def test_readonly_core_never_invokes_cleanup(self):
        source=(ROOT/'dlp_guard_filter.py').read_text()+(ROOT/'anonymizovat_tool.py').read_text()
        for fragment in ['Storage.upload_file(', 'Storage.delete_file(', 'Chats.update_', 'delete_chat_by_id(', 'asyncio.create_task(']:
            self.assertNotIn(fragment,source)
    def test_dialog_unknown_binary_blocks(self):
        with self.assertRaises(g.DLPError):
            self.guard.anonymize_request([{'role':'user','content':'Shrň.'}],'Shrň.',[('file.bin',b'\x00\x01')],USER['id'])
    def test_uploaded_file_limit(self):
        cfg=self.guard.valves;cfg.max_file_bytes=1024
        with self.assertRaisesRegex(g.DLPError,'DLP_FILE_LIMIT'):
            self.guard.anonymize_request([{'role':'user','content':'Shrň.'}],'Shrň.',[('x.txt',b'a'*1025)],USER['id'])
    def test_old_hmac_tokens_unchanged(self):
        result=self.guard.anonymize_payload(PROMPT,[],USER['id'])
        current=self.guard.anonymize_request([{'role':'user','content':PROMPT}],PROMPT,[],USER['id'])
        self.assertEqual(result['text'],current['text'])

class ToolErrors(unittest.IsolatedAsyncioTestCase):
    async def test_direct_llm_tool_call_rejected(self):
        tool=t.Tools(); cb=AsyncMock()
        result=await tool.anonymizovat(USER,types.SimpleNamespace(state=types.SimpleNamespace()),cb,None,{},'anonymizovat')
        self.assertEqual(result['code'],'DLP_TOOL_LAUNCHER_REQUIRED');cb.assert_not_awaited()
    async def test_invalid_callback_data_no_leak(self):
        tool=t.Tools()
        with self.assertRaisesRegex(t.DialogError,'DLP_BROWSER_PROTOCOL'):
            await tool._execute(AsyncMock(return_value={'error':PROMPT}),'return {};',2)
    async def test_invalid_base64(self):
        with self.assertRaisesRegex(t.DialogError,'DLP_TRANSFER_INVALID'):
            await t.Tools()._receive(AsyncMock(return_value={'offset':0,'data':'!!'}),'x',0,2,2)
    async def test_short_transfer(self):
        with self.assertRaisesRegex(t.DialogError,'DLP_TRANSFER_TRUNCATED'):
            await t.Tools()._receive(AsyncMock(return_value={'offset':0,'data':'YQ=='}),'x',0,2,2)
    async def test_global_filter_lookup(self):
        guard=g.Filter();guard.valves.hmac_key=KEY
        with fake_webui(guard):
            copyguard=await t.Tools()._guard(types.SimpleNamespace(state=types.SimpleNamespace()))
        self.assertIsNot(copyguard,guard);self.assertEqual(copyguard.valves.hmac_key,KEY)


class UploadedStorage(unittest.IsolatedAsyncioTestCase):
    async def test_actual_file_read_then_mask_and_original_unchanged(self):
        import tempfile
        guard=g.Filter();guard.valves.hmac_key=KEY
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'data.txt';path.write_text(PROMPT,encoding='utf-8')
            original=path.read_bytes()
            filemod=types.ModuleType('open_webui.models.files')
            filemod.Files=types.SimpleNamespace(get_file_by_id=AsyncMock(return_value=types.SimpleNamespace(
                user_id=USER['id'],path=str(path),filename='data.txt')))
            storemod=types.ModuleType('open_webui.storage.provider')
            storemod.Storage=types.SimpleNamespace(get_file=lambda name:name)
            with patch.dict(sys.modules,{'open_webui.models.files':filemod,'open_webui.storage.provider':storemod}):
                name,data=await guard._read_uploaded_file('abc',USER['id'])
                result=guard.anonymize_request([{'role':'user','content':PROMPT}],PROMPT,[(name,data)],USER['id'])
            self.assertNotIn('jan.novak@example.invalid',str(result))
            self.assertEqual(path.read_bytes(),original)
    async def test_ownership_checked_before_storage_read(self):
        guard=g.Filter()
        filemod=types.ModuleType('open_webui.models.files')
        filemod.Files=types.SimpleNamespace(get_file_by_id=AsyncMock(return_value=types.SimpleNamespace(
            user_id='someone-else',path='/private',filename='private.txt')))
        storemod=types.ModuleType('open_webui.storage.provider')
        storemod.Storage=types.SimpleNamespace(get_file=lambda _: self.fail('foreign file read'))
        with patch.dict(sys.modules,{'open_webui.models.files':filemod,'open_webui.storage.provider':storemod}):
            with self.assertRaisesRegex(g.DLPError,'DLP_FILE_ACCESS'):
                await guard._read_uploaded_file('abc',USER['id'])

if __name__=='__main__': unittest.main(verbosity=2)

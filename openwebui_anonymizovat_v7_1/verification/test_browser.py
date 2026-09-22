"""Real Chromium with simulated WebUI resolver/socket/storage; no live WebUI or LLM."""
import asyncio, contextlib, copy, json, sys, types, unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch
from playwright.async_api import async_playwright
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(Path(__file__).parent))
import dlp_guard_filter as g
import anonymizovat_tool as t
from test_v71 import fake_webui, KEY, USER, PROMPT

class Browser(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.pw=await async_playwright().start()
        self.browser=await self.pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
        self.page=await self.browser.new_page(viewport={'width':1080,'height':1000})
        await self.page.set_content('<html><body><h1>Local dialog harness — not Open WebUI</h1><textarea id="chat-input"></textarea></body></html>')
        self.requests=[];self.errors=[];self.codes=[];self.provider_calls=0
        self.page.on('request',lambda r:self.requests.append(r.url));self.page.on('pageerror',lambda e:self.errors.append(str(e)))
        self.guard=g.Filter();self.guard.valves.hmac_key=KEY
        self.tool=t.Tools();self.req=types.SimpleNamespace(state=types.SimpleNamespace());self.emitter=AsyncMock();self.task=None
        async def cb(event):
            self.codes.append(event['data']['code'])
            return await self.page.evaluate('(code)=>{const F=Object.getPrototypeOf(async function(){}).constructor;return new F(code)();}',event['data']['code'])
        self.cb=cb
    async def asyncTearDown(self):
        if self.task and not self.task.done():
            self.task.cancel()
            with contextlib.suppress(BaseException):await self.task
        await self.browser.close();await self.pw.stop()
    async def start(self,text=PROMPT,history=None,uploaded=None,document_files=None):
        self.original=text;await self.page.locator('#chat-input').fill(text)
        self.body={'model':'demo','messages':(history or [])+[{'id':'current','role':'user','content':text}], 'tool_ids':['anonymizovat']}
        if uploaded:self.body['files']=[{'id':fid} for fid in uploaded]
        self.before=copy.deepcopy(self.body)
        async def read(fid,uid):
            if uid!=USER['id'] or fid not in (uploaded or {}):raise g.DLPError('DLP_FILE_ACCESS')
            value=uploaded[fid]
            if isinstance(value,Exception):raise value
            return value
        self.read=AsyncMock(side_effect=read)
        async def call():
            async def wrapper():return await self.tool.anonymizovat(USER,self.req,self.cb,self.emitter,{'chat_id':'demo'},'anonymizovat')
            with fake_webui(self.guard,wrapper),patch.object(g.Filter,'_read_uploaded_file',self.read):
                out=await self.guard.inlet(self.body,USER,self.req,{'chat_id':'demo'},self.emitter,self.cb)
                final=await self.guard.request(out,USER,self.req,{},self.emitter)
                self.provider_calls+=1 # simulated receiver only
                return final
        self.task=asyncio.create_task(call())
        await self.page.wait_for_selector('[data-dlp-v7]')
        await self.page.wait_for_function('!document.querySelector("[data-text]").disabled')
        if document_files:await self.page.locator('[data-files]').set_input_files(document_files)
    async def review(self):
        await self.page.locator('[data-consent]').check();await self.page.locator('[data-process]').click()
        await self.page.wait_for_selector('[data-phase="review"]:visible',timeout=15000)
        self.assertEqual(self.provider_calls,0);self.assertFalse(self.task.done())
    async def approve(self):
        await self.page.locator('[data-reviewed]').check();await self.page.locator('[data-approve]').click()
        final=await asyncio.wait_for(self.task,10)
        self.assertEqual(self.provider_calls,1);self.assertEqual(self.body,self.before)
        self.assertEqual(await self.page.locator('#chat-input').input_value(),self.original)
        self.assertEqual(await self.page.locator('[data-dlp-v7]').count(),0)
        self.assertFalse(self.requests);self.assertFalse(self.errors)
        self.assertFalse(hasattr(self.req.state,g.DIALOG_INPUT));self.assertNotIn('jan.novak@example.invalid',json.dumps(final))
        return final
    async def test_01_sensitive_prefilled_history_and_upload(self):
        await self.start(history=[{'role':'assistant','content':'E-mail: jan.novak@example.invalid'}],uploaded={'abc':('data.txt',PROMPT.encode())})
        self.assertEqual(await self.page.locator('[data-text]').input_value(),PROMPT);self.read.assert_not_awaited()
        await self.page.screenshot(path=str(ROOT/'verification/DIALOG_PREDVYPLNENY.png'))
        await self.review();self.read.assert_awaited_once_with('abc',USER['id'])
        preview=await self.page.locator('[data-preview]').input_value()
        self.assertNotIn('jan.novak@example.invalid',preview);self.assertIn('Zpráva 1',preview);self.assertIn('Zpráva 2',preview)
        final=await self.approve();self.assertEqual(len(final['messages']),2)
        (ROOT/'verification/final_request_example.json').write_text(json.dumps(final,ensure_ascii=False,indent=2))
    async def test_02_cancel_input(self):
        await self.start(uploaded={'abc':('data.txt',PROMPT.encode())})
        await self.page.locator('[data-phase="input"] [data-cancel]').click()
        with self.assertRaisesRegex(RuntimeError,'DLP_CANCELLED'):await asyncio.wait_for(self.task,10)
        self.assertEqual(self.provider_calls,0);self.read.assert_not_awaited()
    async def test_03_cancel_review(self):
        await self.start();await self.review();await self.page.locator('[data-phase="review"] [data-cancel]').click()
        with self.assertRaisesRegex(RuntimeError,'DLP_CANCELLED'):await asyncio.wait_for(self.task,10)
        self.assertEqual(self.provider_calls,0)
    async def test_04_empty_launcher_supported(self):
        await self.start(text='Otevřít anonymizátor.')
        self.assertEqual(await self.page.locator('[data-text]').input_value(),'')
        await self.page.locator('[data-text]').fill(PROMPT);await self.review();await self.approve()
    async def test_05_input_can_be_edited(self):
        await self.start();await self.page.locator('[data-text]').fill('Shrň chybu E-217.')
        await self.review();final=await self.approve();self.assertEqual(final['messages'][-1]['content'],'Shrň chybu E-217.')
    async def test_06_attachment_can_be_excluded(self):
        await self.start(uploaded={'abc':('data.txt',PROMPT.encode())})
        await self.page.locator('[data-include-existing]').uncheck();await self.review();await self.approve();self.read.assert_not_awaited()
    async def test_07_foreign_attachment_blocked(self):
        await self.start(uploaded={'abc':g.DLPError('DLP_FILE_ACCESS')})
        await self.page.locator('[data-consent]').check();await self.page.locator('[data-process]').click()
        with self.assertRaisesRegex(RuntimeError,'DLP_FILE_ACCESS'):await asyncio.wait_for(self.task,10)
        self.assertEqual(self.provider_calls,0)
    async def test_08_large_prefill_and_preview_chunked(self):
        text=('Zařízení GW-07. '*10000)+'\n'+PROMPT
        await self.start(text=text,document_files=[{'name':'data.txt','mimeType':'text/plain','buffer':PROMPT.encode()}])
        self.assertEqual(await self.page.locator('[data-text]').input_value(),text)
        await self.review();await self.approve();self.assertTrue(all(len(c.encode())<100000 for c in self.codes))
    async def test_09_both_consents_required(self):
        await self.start();await self.page.locator('[data-process]').click()
        self.assertIn('souhlas',await self.page.locator('[data-error]').inner_text());self.assertEqual(self.provider_calls,0)
        await self.review();self.assertTrue(await self.page.locator('[data-approve]').is_disabled());await self.approve()
    async def test_10_unsupported_attachment(self):
        await self.start(document_files=[{'name':'image.png','mimeType':'image/png','buffer':b'\x89PNG\r\n\x1a\n'}])
        await self.page.locator('[data-consent]').check();await self.page.locator('[data-process]').click()
        with self.assertRaises(RuntimeError):await asyncio.wait_for(self.task,10)
        self.assertEqual(self.provider_calls,0)
    async def test_11_injected_markup_not_executed(self):
        await self.start(text='Popis: </textarea><img src="https://invalid.invalid/x" onerror="window.PWNED=1">')
        await self.review();await self.approve();self.assertFalse(await self.page.evaluate('!!window.PWNED'))
    async def test_12_policy_changed(self):
        await self.start();await self.review();self.guard.valves.key_id='changed'
        await self.page.locator('[data-reviewed]').check();await self.page.locator('[data-approve]').click()
        with self.assertRaisesRegex(RuntimeError,'DLP_POLICY_CHANGED'):await asyncio.wait_for(self.task,10)
        self.assertEqual(self.provider_calls,0)
if __name__=='__main__':unittest.main(verbosity=2)

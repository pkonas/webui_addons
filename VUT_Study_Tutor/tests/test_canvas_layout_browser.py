"""Browser regressions for the real injected parent-page bridge (no live Open WebUI).

Run: VUT_CHROMIUM=/usr/bin/chromium python tests/test_canvas_layout_browser.py
Requires playwright and a separately installed Chromium. No network is used.
The old bridge is intentionally retained ONLY as a regression fixture.
"""
from __future__ import annotations
import ast
import json
import os
from pathlib import Path
import shutil
import unittest
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
UI = '__VUT_AI_TUTOR_UI_COORDINATOR_V1220__'
DOCK = '__VUT_AI_TUTOR_RIGHT_DOCK_V1220__'
OPENER = '__VUT_AI_TUTOR_PANEL_OPEN_V1265__'
CONFIG = dict(title='VUT AI Tutor Canvas TEST', embedUrl='http://127.0.0.1/study-tutor/canvas?panel=1',
              token='TEST-NOT-A-CREDENTIAL', sessionId='test-session', actionBridge='TEST-BRIDGE',
              sourceId='study-tutor:test-session:test', messageId='', citationIndex=1, payload={'test':True})
STYLE = '''html,body{margin:0;width:100%;height:100%;overflow:hidden}
#chat-container{display:flex;width:100%;height:100%}
#chat-pane{flex:1 1 52%;min-width:0;display:flex;flex-direction:column}
#messages{flex:1}#message-input-container{height:70px;width:100%}
#controls-container{flex:0 0 48%;min-width:0;display:flex;flex-direction:column}
iframe{width:100%;border:0;flex:1;min-height:0}button{height:40px}'''
# srcdoc avoids loading any endpoint. The src attribute is what the parent bridge
# inspects; content and geometric layout are provided entirely by the test.
PANEL = '''<aside id="controls-container"><button aria-label="Close embed">VUT AI Tutor Canvas TEST</button>
<iframe src="http://127.0.0.1/study-tutor/canvas?panel=1#session_id=test-session" srcdoc="<!doctype html><body>Canvas fixture</body>"></iframe></aside>'''
def html(native=False, unknown=False):
    root = 'unknown-chat-root' if unknown else 'chat-container'
    return f'''<!doctype html><style>{STYLE}</style><div id="{root}"><main id="chat-pane"><div id="messages">Chat</div>
<form id="message-input-container"><textarea></textarea></form></main>{PANEL if native else ''}</div>'''

def bridge_source():
    tree = ast.parse(next((ROOT/'runtime').glob('*bootstrap*.py')).read_text())
    method = next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='_canvas_open_panel_code')
    for node in method.body:
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='template' for t in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError('Bridge not found')

class CanvasLayoutBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        path = os.environ.get('VUT_CHROMIUM') or shutil.which('chromium') or shutil.which('google-chrome')
        if not path:
            cls.playwright.stop()
            raise RuntimeError('Set VUT_CHROMIUM to an installed Chromium executable.')
        cls.browser = cls.playwright.chromium.launch(executable_path=path, headless=True, args=['--no-sandbox'])
        cls.source = bridge_source()
        cls.metrics = {'browser':cls.browser.version,'fixture':'reduced nested flex layout; not live Open WebUI/Electron'}

    @classmethod
    def tearDownClass(cls):
        cls.browser.close(); cls.playwright.stop()
        report = os.environ.get('VUT_CANVAS_BROWSER_REPORT')
        if report: Path(report).write_text(json.dumps(cls.metrics,indent=2)+'\n')

    def setUp(self):
        self.page = self.browser.new_page(viewport={'width':1440,'height':900})
        # No navigation: run the complete bridge in a local about:blank document.
        self.page.route('**/*', lambda route:route.abort())

    def tearDown(self):
        self.page.close()

    def setup_page(self,native=False,unknown=False):
        self.page.set_content(html(native,unknown))
        self.page.evaluate('''() => {
            window.loopErrors=[]; window.styleMutations=0;
            addEventListener('error',e=>{if(e.message.includes('ResizeObserver')) loopErrors.push(e.message)});
            const chat=document.getElementById('chat-container');
            if(chat) new MutationObserver(m=>styleMutations+=m.length).observe(chat,{attributes:true,attributeFilter:['style']});
        }''')

    def execute(self,source=None,**changes):
        cfg={**CONFIG,**changes}
        return self.page.evaluate('(code)=>new Function(code)()', (source or self.source).replace('__CONFIG__',json.dumps(cfg)))

    def settle(self,ms=100): self.page.wait_for_timeout(ms)

    def snapshot(self): return self.page.evaluate(f'window.{UI}.snapshot()')

    def open_fallback(self):
        self.execute()
        self.page.wait_for_selector('#study-tutor-right-panel',timeout=4000)
        self.settle()

    def assert_no_loop(self): self.assertEqual(self.page.evaluate('loopErrors.length'),0)

    def test_01_old_bridge_reproduces_self_sustained_native_feedback(self):
        self.setup_page(native=True)
        old=(ROOT/'tests/fixtures/canvas-panel-bridge-before-v1.26.4.js').read_text()
        self.execute(source=old)
        samples=[]
        for _ in range(12):
            self.settle(90)
            samples.append(self.page.eval_on_selector('#chat-container','e=>Math.round(e.getBoundingClientRect().width)'))
        info=self.page.evaluate('({styleMutations,loopErrors:loopErrors.length})')
        self.metrics['before']={**info,'widthSamples':samples}
        self.assertGreater(info['styleMutations'],50)
        self.assertGreater(info['loopErrors'],0)
        self.assertGreater(max(samples)-min(samples),100)

    def test_02_fixed_native_has_no_layout_writes(self):
        self.setup_page(native=True)
        result=self.execute();self.settle(1400)
        info=self.page.evaluate('({styleMutations,loopErrors:loopErrors.length,width:document.getElementById("chat-container").getBoundingClientRect().width})')
        self.metrics['after']={**info,**self.snapshot()}
        self.assertEqual(result['layoutRevision'],'canvas-layout-r1')
        self.assertEqual(info['styleMutations'],0)
        self.assertEqual(info['width'],1440)
        self.assertEqual(self.snapshot()['observedResizeTargets'],0)
        self.assert_no_loop()

    def test_03_native_close_reopen_12_times_remains_stable(self):
        self.setup_page(native=True);self.execute()
        for _ in range(12):
            self.page.eval_on_selector('#controls-container','e=>e.remove()');self.settle(20)
            self.page.eval_on_selector('#chat-container','(e,p)=>e.insertAdjacentHTML("beforeend",p)',PANEL);self.settle(30)
        self.settle(250)
        self.assertEqual(self.page.evaluate('styleMutations'),0)
        self.assertEqual(self.snapshot()['mode'],'native');self.assert_no_loop()
        self.assertEqual(self.page.locator('#study-tutor-right-panel').count(),0)

    def test_04_native_splitter_and_viewport_remain_host_owned(self):
        self.setup_page(native=True);self.execute()
        for width,basis in [(1200,'35%'),(900,'62%'),(1600,'55%'),(1440,'48%')]:
            self.page.set_viewport_size({'width':width,'height':780})
            self.page.eval_on_selector('#controls-container','(e,b)=>e.style.flexBasis=b',basis)
            self.settle(80)
            self.assertEqual(self.page.eval_on_selector('#chat-container','e=>Math.round(e.getBoundingClientRect().width)'),width)
        self.assertEqual(self.page.evaluate('styleMutations'),0);self.assert_no_loop()

    def test_05_fallback_reserves_once_and_never_resizes_composer(self):
        self.setup_page();self.open_fallback()
        self.assertEqual(self.snapshot()['mode'],'fallback-reserved')
        self.assertEqual(self.snapshot()['ownedElements'],1)
        self.assertEqual(self.snapshot()['observedResizeTargets'],1)
        self.assertEqual(self.page.eval_on_selector('#message-input-container','e=>e.getAttribute("style")'),None)
        self.assertEqual(self.page.eval_on_selector('#chat-container','e=>e.style.width'),'')
        self.assertGreater(self.page.eval_on_selector('#chat-container','e=>parseFloat(e.style.paddingRight)'),380)
        self.assert_no_loop()

    def test_06_fallback_idle_is_not_a_layout_poll(self):
        self.setup_page();self.open_fallback();self.settle(200)
        a=self.snapshot();self.settle(1550);b=self.snapshot()
        self.assertEqual(a,b);self.assert_no_loop()

    def test_07_close_preserves_foreign_styles_and_releases_targets(self):
        self.setup_page()
        self.page.eval_on_selector('#chat-container','e=>e.style.cssText="padding-right:11px; color:purple; --foreign:before"')
        self.open_fallback()
        self.page.evaluate(f'''() => {{document.getElementById('chat-container').style.setProperty('--foreign','after');window.{DOCK}.close();}}''')
        self.settle()
        self.assertEqual(self.page.eval_on_selector('#chat-container','e=>e.style.paddingRight'),'11px')
        self.assertEqual(self.page.eval_on_selector('#chat-container','e=>e.style.getPropertyValue("--foreign")'),'after')
        self.assertEqual(self.snapshot()['ownedElements'],0)
        self.assertEqual(self.snapshot()['observedResizeTargets'],0)
        self.settle(1300);self.assertEqual(self.page.locator('#study-tutor-right-panel').count(),0)

    def test_08_close_does_not_overwrite_external_edit_to_owned_property(self):
        self.setup_page();self.open_fallback()
        self.page.evaluate(f'''() => {{document.getElementById('chat-container').style.setProperty('padding-right','17px');window.{DOCK}.close();}}''')
        self.settle();self.assertEqual(self.page.eval_on_selector('#chat-container','e=>e.style.paddingRight'),'17px')

    def test_09_rapid_open_requests_cancel_older_attempts(self):
        self.setup_page();self.execute(sessionId='old-session');self.settle(700)
        self.execute(sessionId='new-session');self.settle(700)
        self.assertEqual(self.page.locator('#study-tutor-right-panel').count(),0)
        self.page.wait_for_selector('#study-tutor-right-panel',timeout=2500);self.settle()
        self.assertIn('new-session',self.page.locator('#study-tutor-right-panel iframe').get_attribute('src'))
        self.assertEqual(self.page.locator('#study-tutor-right-panel').count(),1)
        self.assertFalse(self.page.evaluate(f'Boolean(window.{OPENER})'))

    def test_10_late_native_mount_closes_fallback_and_does_not_resurrect(self):
        self.setup_page();self.open_fallback()
        self.page.eval_on_selector('#chat-container','(e,p)=>e.insertAdjacentHTML("beforeend",p)',PANEL)
        self.page.wait_for_selector('#study-tutor-right-panel',state='detached');self.settle()
        self.assertEqual(self.snapshot()['mode'],'native')
        self.assertEqual(self.snapshot()['ownedElements'],0)
        self.page.eval_on_selector('#controls-container','e=>e.remove()');self.settle(1450)
        self.assertEqual(self.page.locator('#study-tutor-right-panel').count(),0);self.assert_no_loop()

    def test_11_fallback_width_is_clamped_after_window_resize(self):
        self.setup_page();self.open_fallback()
        self.page.set_viewport_size({'width':920,'height':640});self.settle()
        self.assertLessEqual(self.page.locator('#study-tutor-right-panel').bounding_box()['width'],600)
        self.page.set_viewport_size({'width':700,'height':640});self.settle()
        self.assertEqual(self.page.locator('#study-tutor-right-panel').bounding_box()['width'],700)
        self.assertEqual(self.snapshot()['ownedElements'],0)
        self.assertEqual(self.snapshot()['mode'],'fallback-overlay')
        self.page.set_viewport_size({'width':1440,'height':900});self.settle()
        self.assertEqual(self.snapshot()['ownedElements'],1);self.assert_no_loop()

    def test_12_unknown_chat_structure_is_overlay_without_guessing(self):
        self.setup_page(unknown=True);self.open_fallback()
        self.assertEqual(self.snapshot()['mode'],'fallback-overlay')
        self.assertEqual(self.snapshot()['ownedElements'],0)
        self.assertEqual(self.page.eval_on_selector('main','e=>e.getAttribute("style")'),None)

    def test_13_raf_coalesces_repeated_requests(self):
        self.setup_page(native=True);self.execute();self.settle()
        before=self.snapshot()['syncs']
        self.page.evaluate(f'() => {{for(let i=0;i<400;i++) window.{UI}.sync()}}')
        self.settle()
        self.assertEqual(self.snapshot()['syncs']-before,1)
        self.assertEqual(self.snapshot()['styleWrites'],0)

    def test_14_dispose_cancels_pending_open_and_all_owners(self):
        self.setup_page();self.execute();self.settle(100)
        self.page.evaluate(f'window.{UI}.dispose()');self.settle(1600)
        self.assertFalse(self.page.evaluate(f'Boolean(window.{UI} || window.{DOCK} || window.{OPENER})'))
        self.assertEqual(self.page.locator('#study-tutor-right-panel').count(),0)

    def test_15_drag_and_close_cancel_pending_move_and_restore_cursor(self):
        self.setup_page();self.open_fallback()
        self.page.evaluate("document.body.style.cursor='crosshair'")
        box=self.page.locator('#study-tutor-right-panel .resize').bounding_box()
        self.page.mouse.move(box['x']+5,box['y']+100);self.page.mouse.down()
        self.page.mouse.move(box['x']-100,box['y']+100);self.settle()
        self.page.evaluate(f'window.{DOCK}.close()');self.page.mouse.up();self.settle()
        self.assertEqual(self.page.evaluate('document.body.style.cursor'),'crosshair')
        self.assertEqual(self.snapshot()['ownedElements'],0);self.assert_no_loop()

    def test_16_replacing_coordinator_disposes_previous_instance(self):
        self.setup_page();self.open_fallback()
        self.page.evaluate(f'window.oldUI=window.{UI}')
        self.execute();self.settle()
        old=self.page.evaluate('window.oldUI.snapshot()')
        self.assertTrue(old['disposed']);self.assertEqual(old['observedResizeTargets'],0)
        self.assertEqual(old['ownedElements'],0)
        self.page.evaluate('window.oldUI.sync()');self.settle(1300)
        self.assertEqual(self.page.locator('#study-tutor-right-panel').count(),1)
        self.assertEqual(self.page.evaluate('window.oldUI.snapshot()'),old)

    def test_17_action_bridge_deduplicates_and_checks_source_and_key(self):
        self.setup_page(native=True);self.execute();self.settle()
        self.page.evaluate('''() => {window.prompts=[];addEventListener('message',e=>{if(e.data?.source==='vut-ai-tutor') prompts.push(e.data.text)})}''')
        self.page.evaluate('''() => {
          const frame=document.querySelector('iframe');
          const data={type:'study:tutor-action',source:'vut-ai-tutor-canvas',bridge:'TEST-BRIDGE',requestId:'r1',text:'Test teaching',submit:true};
          const send=(d,source)=>window.dispatchEvent(new MessageEvent('message',{data:d,source}));
          send({...data,bridge:'bad'},frame.contentWindow);send(data,window);
          send(data,frame.contentWindow);send(data,frame.contentWindow);
        }''')
        self.settle();self.assertEqual(self.page.evaluate('prompts'),['Test teaching'])

    def test_18_diagnostic_snapshot_is_serializable_and_contains_no_credentials(self):
        self.setup_page(native=True);self.execute();self.settle()
        value=json.dumps(self.snapshot())
        self.assertNotIn(CONFIG['token'],value);self.assertNotIn(CONFIG['actionBridge'],value)
        self.assertIn('canvas-layout-r1',value)

    def test_19_unrelated_pointerup_does_not_clear_foreign_cursor(self):
        self.setup_page();self.open_fallback()
        self.page.evaluate("document.body.style.cursor='col-resize';window.dispatchEvent(new PointerEvent('pointerup'))")
        self.assertEqual(self.page.evaluate('document.body.style.cursor'),'col-resize')

if __name__=='__main__': unittest.main(verbosity=2)

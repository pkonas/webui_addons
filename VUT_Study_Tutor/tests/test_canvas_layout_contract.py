"""No-browser contracts for the parent bridge and explicitly scoped runtime delta."""
from pathlib import Path
import ast,base64,zlib,json,hashlib,unittest
ROOT=Path(__file__).resolve().parents[1]

def sha(b):return hashlib.sha256(b).hexdigest()
class CanvasLayoutContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source=next((ROOT/'runtime').glob('*bootstrap*')).read_text()
        cls.tree=ast.parse(cls.source)
        method=next(n for n in ast.walk(cls.tree) if isinstance(n,ast.FunctionDef) and n.name=='_canvas_open_panel_code')
        cls.bridge=next(ast.literal_eval(n.value) for n in method.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='template' for t in n.targets))
        cls.prov=json.loads((ROOT/'docs/CANVAS-LAYOUT-PROVENANCE.json').read_text())
    def test_template_is_exact_auditable_source(self):
        self.assertEqual(self.bridge,(ROOT/'docs/canvas-panel-bridge.js').read_text())
        self.assertEqual(sha(self.bridge.encode()),self.prov['bridge_after_sha256'])
    def test_old_regression_fixture_is_exact_previous_template(self):
        self.assertEqual(sha((ROOT/'tests/fixtures/canvas-panel-bridge-before-v1.26.4.js').read_bytes()),self.prov['bridge_before_sha256'])
    def test_no_native_geometry_feedback_or_permanent_layout_interval(self):
        self.assertNotIn('setInterval(syncChatLayout',self.bridge)
        self.assertNotIn("setImportant(element, 'width'",self.bridge)
        self.assertNotIn('resizeObserver.observe(target)',self.bridge)
        self.assertIn('new ResizeObserver(scheduleLayout)',self.bridge)
        self.assertIn('observeOnly([dock.host])',self.bridge)
        self.assertIn('requestAnimationFrame(syncChatLayout)',self.bridge)
    def test_only_bridge_and_additive_health_method_changed(self):
        self.assertEqual(set(self.prov['changed_runtime_functions']),{'StudyRuntime._canvas_open_panel_code','StudyRuntime.register_routes'})
        self.assertEqual(sha(self.source.encode()),self.prov['revised_runtime_sha256'])
    def test_lifecycle_and_health_revisions_match(self):
        self.assertIn("'canvas_layout': {'revision': CANVAS_LAYOUT_REVISION",self.source)
        self.assertIn("CANVAS_LAYOUT_REVISION = 'canvas-layout-r1'",self.source)
        self.assertIn("LAYOUT_REVISION = 'canvas-layout-r1'",self.bridge)
        self.assertIn("window.addEventListener('pagehide'",self.bridge)
        self.assertIn("window[OPEN_KEY]?.dispose?.()",self.bridge)
        self.assertIn("window[GLOBAL_KEY] && nativePanelOpen()",self.bridge)
    def test_internal_canvas_assets_unchanged_including_js(self):
        previous={}
        # Old integration baseline records HTML/CSS and the retained JS fixture
        # is checked byte-for-byte by the existing integration suite.
        baseline=json.loads((ROOT/'tests/integration_baseline.json').read_text())
        for n in self.tree.body:
            if isinstance(n,ast.Assign) and isinstance(n.value,ast.Call) and isinstance(n.value.func,ast.Name) and n.value.func.id=='_decode_asset':
                previous[n.targets[0].id]=zlib.decompress(base64.b85decode(ast.literal_eval(n.value.args[0])))
        for name in ['CANVAS_HTML','CANVAS_CSS']:
            self.assertEqual(sha(previous[name]),baseline['preserved_asset_sha256'][name])
        self.assertEqual(previous['CANVAS_JS'],(ROOT/'docs/canvas.pdf-hotfix.js').read_bytes())
if __name__=='__main__': unittest.main(verbosity=2)

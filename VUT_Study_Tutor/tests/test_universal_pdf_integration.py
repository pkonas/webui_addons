"""Offline integration contracts for the complete multi-platform distribution.

Checks every embedded payload layer against canonical sources and compares
unrelated runtime features to an inventory recorded from the supplied 2.3.1 ZIP.
These tests never start a real Desktop, container, service or remote deployment.
"""
from __future__ import annotations
import ast
import base64
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / 'runtime'
BASELINE = json.loads((ROOT / 'tests/integration_baseline.json').read_text())
CONTRACT = json.loads((ROOT / 'RELEASE-CONTRACT.json').read_text())
LAYOUT = json.loads((ROOT / 'docs/CANVAS-LAYOUT-PROVENANCE.json').read_text())
SOURCE_RECOVERY = json.loads((ROOT / 'docs/SOURCE-RECOVERY-PROVENANCE.json').read_text())

def runtime(part: str) -> Path:
    return RUNTIME / f'vut_ai_tutor_{part}_v1.26.5_server_desktop_windows_mock_transport_complete.py'

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def payload(source: str, name: str) -> bytes:
    pattern = r'\$' + re.escape(name) + r" = (?:@'\n(.*?)\n'@|'([^']*)')"
    match = re.search(pattern, source, re.S)
    if match is None:
        raise AssertionError(f'Missing embedded payload {name}')
    return gzip.decompress(base64.b64decode(match[1] or match[2]))

def assignments(source: str) -> dict:
    result = {}
    for node in ast.parse(source).body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            try:
                value = ast.literal_eval(node.value)
            except (ValueError, TypeError):
                continue
            for target in targets:
                if isinstance(target, ast.Name):
                    result[target.id] = value
    return result

def assets() -> dict[str, bytes]:
    result = {}
    for node in ast.parse(runtime('bootstrap').read_text()).body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            if isinstance(node.value.func, ast.Name) and node.value.func.id == '_decode_asset':
                result[node.targets[0].id] = zlib.decompress(base64.b85decode(ast.literal_eval(node.value.args[0])))
    return result

def functions(source: str) -> dict[str, str]:
    result = {}
    def visit(body, prefix=''):
        for node in body:
            if isinstance(node, ast.ClassDef):
                visit(node.body, prefix + node.name + '.')
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                result[prefix + node.name] = sha(ast.dump(node, include_attributes=False).encode())
    visit(ast.parse(source).body)
    return result

class UniversalPdfIntegrationTests(unittest.TestCase):
    def test_release_contract_all_original_platforms(self):
        self.assertEqual(CONTRACT['platforms'], BASELINE['platforms'])
        self.assertEqual(CONTRACT['installer_version'], '2.3.4')
        self.assertEqual(CONTRACT['runtime_version'], '1.26.5')
        self.assertEqual(CONTRACT['api_engine_version'], '2.0.6')
        self.assertEqual(CONTRACT['embedded_api_engine_version'], '2.0.6')
        self.assertEqual(CONTRACT['pdf_delivery_revision'], 'pdf-delivery-r2')
        self.assertFalse(CONTRACT['live_document_verified_by_installer'])

    def test_runtime_and_api_engine_versions_and_markers_agree(self):
        for part in ('bootstrap', 'pipe', 'manager'):
            values = assignments(runtime(part).read_text())
            version_name, marker_name = ('RELEASE_VERSION', 'RELEASE_MARKER') if part == 'manager' else ('PLUGIN_VERSION', 'TUTOR_BUILD_MARKER')
            self.assertEqual(values[version_name], CONTRACT['runtime_version'])
            self.assertEqual(values[marker_name], CONTRACT['runtime_marker'])
        engine = assignments((ROOT/'engine/vut_ai_tutor_universal_installer_v2.0.6.py').read_text())
        self.assertEqual(engine['RUNTIME_VERSION'], CONTRACT['runtime_version'])
        self.assertEqual(engine['RUNTIME_MARKER'], CONTRACT['runtime_marker'])

    def test_all_desktop_payloads_include_recovery_and_verify(self):
        paths = sorted((ROOT/'adapters/desktop').glob('*.ps1'))
        self.assertEqual(len(paths), 3)
        for path in paths:
            source = path.read_text(encoding='utf-8-sig')
            for label in ('Manager', 'Bootstrap', 'Pipe'):
                with self.subTest(adapter=path.name, payload=label):
                    data = payload(source, label + 'Payload')
                    self.assertEqual(data, runtime(label.lower()).read_bytes())
                    expected = re.search(r'\$'+label+r"Sha256 = '([^']*)'", source)[1]
                    self.assertEqual(sha(data), expected)
            self.assertIn("$ReleaseVersion = '1.26.5'", source)

    def test_einfra_all_nested_payloads_identical_to_canonical_sources(self):
        outer = (ROOT/'adapters/einfra/install-vut-ai-tutor-einfra-windows-server-v2.1.8.ps1').read_text(encoding='utf-8-sig')
        data = payload(outer, 'EmbeddedEnginePayload')
        self.assertEqual(data, (ROOT/'adapters/einfra/api-wrapper-v2.0.6.ps1').read_bytes())
        self.assertEqual(sha(data), re.search(r"\$ExpectedEngineSha256 = '([^']*)'", outer)[1])
        inner = data.decode('utf-8-sig').replace('\r\n', '\n')
        targets = {'Manager':ROOT/'engine/vut_ai_tutor_universal_installer_v2.0.6.py', 'Bootstrap':runtime('bootstrap'), 'Pipe':runtime('pipe'), 'DesktopRepair':ROOT/'adapters/desktop/repair-install-vut-ai-tutor-v1.26.5-server-desktop-windows-mock-transport-complete.ps1'}
        for label, path in targets.items():
            with self.subTest(payload=label):
                data = payload(inner, label + 'Payload')
                self.assertEqual(data, path.read_bytes())
                self.assertEqual(sha(data), re.search(r'\$Expected'+label+r"Sha = '([^']*)'", inner)[1])
        self.assertIn("$RuntimeVersion = '1.26.5'", outer)
        self.assertNotIn('VUT-AI-TUTOR-1.26.2-', outer)

    def test_embedded_pipe_and_javascript_fixture_exact(self):
        values = assets()
        self.assertEqual(values['PIPE_SOURCE'], runtime('pipe').read_bytes())
        self.assertEqual(values['CANVAS_JS'], (ROOT/'docs/canvas.pdf-hotfix.js').read_bytes())
        self.assertIn(b'async function diagnosePdfTransport(', values['CANVAS_JS'])

    def test_original_runtime_functions_not_removed(self):
        current = functions(runtime('bootstrap').read_text())
        self.assertFalse(set(BASELINE['original_runtime_functions']) - current.keys())
        for name, expected in BASELINE['unchanged_runtime_function_ast_sha256'].items():
            # Only explicit, hashed source-recovery changes may differ from 1.26.2.
            change = LAYOUT['changed_runtime_functions'].get(name) or SOURCE_RECOVERY['changed_runtime_functions'].get(name)
            self.assertEqual(current[name], change['after_sha256'] if change else expected, name)

    def test_all_preceding_runtime_features_preserved_except_explicit_source_fix(self):
        current = functions(runtime('bootstrap').read_text())
        self.assertFalse(set(SOURCE_RECOVERY['retained_runtime_functions']) - current.keys())
        for name, expected in SOURCE_RECOVERY['unchanged_runtime_function_ast_sha256'].items():
            self.assertEqual(current[name], LAYOUT['changed_runtime_functions'].get(name, {}).get('after_sha256', expected), name)
        for name, change in SOURCE_RECOVERY['changed_runtime_functions'].items():
            self.assertEqual(current[name], LAYOUT['changed_runtime_functions'].get(name, change)['after_sha256'], name)
        for name, expected in SOURCE_RECOVERY['added_runtime_functions'].items():
            self.assertEqual(current[name], expected, name)
        self.assertEqual(sha(runtime('bootstrap').read_bytes()), LAYOUT['revised_runtime_sha256'])
        for name, expected in LAYOUT['unchanged_runtime_function_ast_sha256'].items():
            self.assertEqual(current[name], expected, name)
        self.assertEqual(set(LAYOUT['changed_runtime_functions']), {'StudyRuntime.register_routes', 'StudyRuntime._canvas_open_panel_code'})

    def test_original_canvas_functions_not_removed(self):
        current = set(re.findall(r'\bfunction\s+([\w$]+)\s*\(', assets()['CANVAS_JS'].decode()))
        self.assertFalse(set(BASELINE['original_canvas_function_names']) - current)

    def test_html_css_pdfjs_schema_and_feature_constants_preserved(self):
        for name, expected in BASELINE['preserved_asset_sha256'].items():
            self.assertEqual(sha(assets()[name]), expected, name)
        current = assignments(runtime('bootstrap').read_text())
        for name, expected in BASELINE['preserved_literal_constants'].items():
            self.assertEqual(current[name], expected, name)
        self.assertEqual(current['PDFJS_VERSION'], '6.2.108')
        self.assertEqual(current['SCHEMA_VERSION'], 14)

    def test_dispatcher_keeps_explicit_recovery_and_safe_desktop_default(self):
        source = (ROOT/'install-vut-ai-tutor-universal-v2.3.4.ps1').read_text(encoding='utf-8-sig')
        for action in ('Install','Repair','Verify','Preflight','Uninstall','SelfTest','Detect','BackendRecovery','DesktopDatabaseRepair'):
            self.assertIn("'"+action+"'", source)
        self.assertIn("'TutorOnly'", source)
        self.assertIn('NoAutoStartDesktop', source)
        self.assertIn('StopDesktopProcesses', source)
        self.assertNotIn("'Server'", source)
        adapter = (ROOT/'adapters/desktop/repair-install-vut-ai-tutor-v1.26.5-server-desktop-windows-mock-transport-complete.ps1').read_text(encoding='utf-8-sig')
        for mode in ('RecoverStartup','TutorOnly','Repair','DatabaseRepair','Verify'):
            self.assertIn("'"+mode+"'", adapter)

    def test_every_powershell_file_is_bom_crlf(self):
        for path in ROOT.rglob('*.ps1'):
            raw = path.read_bytes()
            self.assertTrue(raw.startswith(b'\xef\xbb\xbf'), str(path))
            self.assertNotIn(b'\n', raw.replace(b'\r\n', b''), str(path))

    def test_manifest_covers_distribution(self):
        manifest = json.loads((ROOT/'PACKAGE-MANIFEST.json').read_text())
        paths = set()
        for record in manifest['files']:
            self.assertNotIn(record['path'], paths)
            paths.add(record['path'])
            self.assertEqual(sha((ROOT/record['path']).read_bytes()), record['sha256'], record['path'])
        # Local reports and Function backups are not distribution files.
        source_directories = {'adapters', 'runtime', 'engine', 'tests', 'docs'}
        for path in ROOT.rglob('*'):
            if not path.is_file() or '__pycache__' in path.parts or path.suffix == '.pyc':
                continue
            relative = path.relative_to(ROOT)
            if relative.parts[0] in source_directories or (len(relative.parts) == 1 and path.suffix in {'.ps1','.py','.sh'}):
                self.assertIn(relative.as_posix(), paths)
        for required in ('README.md','RELEASE-CONTRACT.json','BUILD-TEST-REPORT.json','TEST-RESULTS.md'):
            self.assertIn(required, paths)

    def test_corrupted_payload_rejected_before_install(self):
        with tempfile.TemporaryDirectory(prefix='vut-corruption-test-') as tmp:
            target = Path(tmp)/'package'
            target.mkdir()
            manifest = json.loads((ROOT/'PACKAGE-MANIFEST.json').read_text())
            for relative in [entry['path'] for entry in manifest['files']] + ['PACKAGE-MANIFEST.json','SHA256SUMS.txt']:
                destination = target/relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT/relative, destination)
            corrupt = target/'runtime'/runtime('pipe').name
            corrupt.write_bytes(corrupt.read_bytes()+b'\n# corruption test\n')
            result = subprocess.run([sys.executable,str(target/'install-vut-ai-tutor-universal-v2.3.4.py'),'--action','self-test','--report-path',str(Path(tmp)/'report.json')], text=True,capture_output=True,timeout=20)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('SHA-256 mismatch',result.stdout+result.stderr)

if __name__ == '__main__':
    unittest.main(verbosity=2)

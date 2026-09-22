from __future__ import annotations
import base64, gzip, hashlib, importlib.util, json, pathlib, re, subprocess, sys, tempfile, unittest
from mock_openwebui_api import start_server
ROOT=pathlib.Path(__file__).resolve().parents[1]
MANAGER=ROOT/'runtime/vut_ai_tutor_manager_v1.26.5_server_desktop_windows_mock_transport_complete.py'
BOOTSTRAP=ROOT/'runtime/vut_ai_tutor_bootstrap_v1.26.5_server_desktop_windows_mock_transport_complete.py'
PIPE=ROOT/'runtime/vut_ai_tutor_pipe_v1.26.5_server_desktop_windows_mock_transport_complete.py'

class InstallerTests(unittest.TestCase):
    def test_embedded_payloads_exact_and_powershell_encoding(self):
        for path in (ROOT/'adapters/desktop').glob('*.ps1'):
            raw=path.read_bytes(); self.assertTrue(raw.startswith(b'\xef\xbb\xbf'))
            self.assertNotIn(b'\n',raw.replace(b'\r\n',b''))
            source=raw.decode('utf-8-sig').replace('\r\n','\n')
            for label,expected in [('Manager',MANAGER),('Bootstrap',BOOTSTRAP),('Pipe',PIPE)]:
                payload=re.search(r'\$'+label+r"Payload = @'\n(.*?)\n'@",source,re.S).group(1)
                data=gzip.decompress(base64.b64decode(payload)); self.assertEqual(data,expected.read_bytes())
                sha=re.search(r'\$'+label+r"Sha256 = '([^']+)'",source).group(1)
                self.assertEqual(hashlib.sha256(data).hexdigest(),sha)

    def test_install_verify_backup_preserve_valves(self):
        server,state,thread,url=start_server()
        old={'id':'study_tutor_gateway_bootstrap','name':'Old tutor','type':'event','content':'class Event: pass','is_active':True,'meta':{}}
        state.functions[old['id']]=dict(old)
        state.valves[old['id']]={'SAFE_PDF_UPLOAD_FALLBACK':False,'TOKEN_LIFETIME_HOURS':1440}
        expected_valves=dict(state.valves[old['id']])
        try:
            with tempfile.TemporaryDirectory() as tmp:
                tmp=pathlib.Path(tmp); token=tmp/'token'; token.write_text(state.token)
                args=[sys.executable,str(MANAGER),'--bootstrap-path',str(BOOTSTRAP),'--pipe-path',str(PIPE),'--target','Desktop','--only-base-url','--base-url',url,'--token-file',str(token),'--route-timeout','2']
                report=tmp/'install.json'
                result=subprocess.run(args+['--mode','TutorOnly','--report-path',str(report)],capture_output=True,text=True,timeout=30)
                self.assertEqual(result.returncode,0,result.stdout+'\n'+result.stderr)
                data=json.loads(report.read_text()); self.assertTrue(data['success'])
                backup=json.loads(pathlib.Path(data['functions_backup_path']).read_text())
                self.assertEqual(backup['functions'][0]['function']['content'],old['content'])
                self.assertEqual(state.valves[old['id']],expected_valves)
                self.assertEqual(state.functions[old['id']]['content'],BOOTSTRAP.read_text())
                result=subprocess.run(args+['--mode','Verify'],capture_output=True,text=True,timeout=30)
                self.assertEqual(result.returncode,0,result.stdout+'\n'+result.stderr)
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=5)

    def test_manager_self_test(self):
        result=subprocess.run([sys.executable,str(MANAGER),'--bootstrap-path',str(BOOTSTRAP),'--pipe-path',str(PIPE),'--self-test'],capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stdout+'\n'+result.stderr)

if __name__=='__main__': unittest.main(verbosity=2)

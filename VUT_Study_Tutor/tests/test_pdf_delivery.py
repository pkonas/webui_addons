"""HTTP-level regression tests: real Tutor gateway, FastAPI, SQLite and token checks.
Only the external Open WebUI Files/Storage adapters are replaced with test doubles.
No installed Desktop, production database or network service is touched.
"""
from __future__ import annotations
import asyncio
import importlib.util
import io
import logging
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

import httpx
from fastapi import FastAPI

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('tutor_pdf_hotfix_test', ROOT / 'runtime/vut_ai_tutor_bootstrap_v1.26.5_server_desktop_windows_mock_transport_complete.py')
TUTOR = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = TUTOR
SPEC.loader.exec_module(TUTOR)
FID = 'd81a3f40-8070-4479-b980-eb37f4e6841a'


def make_pdf() -> bytes:
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>', b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>', b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] >>']
    body = b'%PDF-1.4\n'
    offsets = [0]
    for i, obj in enumerate(objects, 1):
        offsets.append(len(body)); body += f'{i} 0 obj\n'.encode() + obj + b'\nendobj\n'
    xref = len(body)
    body += f'xref\n0 {len(offsets)}\n0000000000 65535 f \n'.encode()
    for offset in offsets[1:]: body += f'{offset:010d} 00000 n \n'.encode()
    return body + f'trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode()


class PdfDeliveryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.uploads = self.root / 'uploads'; self.uploads.mkdir()
        self.pdf = make_pdf()
        self.path = self.root / 'source.pdf'; self.path.write_bytes(self.pdf)
        self.record = types.SimpleNamespace(id=FID, user_id='owner', path=str(self.path), filename='Příliš žluťoučký.pdf', meta={}, data={})
        modules = {name: types.ModuleType(name) for name in ['open_webui', 'open_webui.models', 'open_webui.models.files', 'open_webui.storage', 'open_webui.storage.provider', 'open_webui.config']}
        async def get_record(file_id): return self.record if file_id == FID else None
        self.files = types.SimpleNamespace(get_file_by_id=get_record)
        self.storage_calls = []
        def storage_get(path): self.storage_calls.append(path); return path
        self.storage = types.SimpleNamespace(get_file=storage_get)
        modules['open_webui.models.files'].Files = self.files
        modules['open_webui.storage.provider'].Storage = self.storage
        self.config = modules['open_webui.config']
        self.config.STORAGE_PROVIDER = 'local'; self.config.UPLOAD_DIR = self.uploads
        self.module_patch = patch.dict(sys.modules, modules); self.module_patch.start()
        self.app = FastAPI()
        self.runtime = TUTOR.StudyRuntime(self.app, self.root, TUTOR.Event.Valves())
        self.app.state.STUDY_TUTOR_RUNTIME = self.runtime
        self.app.middleware_stack = self.app.build_middleware_stack()
        TUTOR._install_study_tutor_cors_boundary(self.app)
        await self.runtime.db.initialize(); await self.runtime.register_routes()
        await self.runtime.db.register_book('owner', 'knowledge', FID, 'Test')
        session = await self.runtime.db.create_or_touch_session('owner', 'chat', FID)
        self.token = self.runtime.codec.issue('owner', session['id'])
        self.headers = {'Authorization': 'Bearer '+self.token, 'Origin': 'null'}
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app, raise_app_exceptions=False), base_url='http://127.0.0.1:8080')
        self.url = '/study-tutor/api/pdf/' + FID

    async def asyncTearDown(self):
        await self.client.aclose(); self.module_patch.stop(); self.tmp.cleanup()

    async def get(self, **extra):
        return await self.client.get(self.url, headers={**self.headers, **extra})

    async def test_full_pdf_200_unicode_filename(self):
        r = await self.get()
        self.assertEqual(r.status_code, 200); self.assertEqual(r.content, self.pdf)
        self.assertEqual(int(r.headers['content-length']), len(self.pdf))
        self.assertEqual(r.headers['content-type'], 'application/pdf')
        self.assertIn("filename*=UTF-8''P%C5%99", r.headers['content-disposition'])
        self.assertEqual(r.headers['x-study-tutor-pdf-delivery'], 'pdf-delivery-r2')
        self.assertEqual(r.headers['access-control-allow-origin'], 'null')

    async def test_range_start_end(self):
        r = await self.get(Range='bytes=0-15')
        self.assertEqual(r.status_code, 206); self.assertEqual(r.content, self.pdf[:16])
        self.assertEqual(r.headers['content-range'], f'bytes 0-15/{len(self.pdf)}')

    async def test_range_open_ended(self):
        r = await self.get(Range='bytes=10-'); self.assertEqual(r.status_code,206); self.assertEqual(r.content,self.pdf[10:])

    async def test_range_suffix(self):
        r = await self.get(Range='bytes=-12'); self.assertEqual(r.status_code,206); self.assertEqual(r.content,self.pdf[-12:])

    async def test_range_clamped(self):
        r = await self.get(Range='bytes=0-999999'); self.assertEqual(r.status_code,206); self.assertEqual(r.content,self.pdf)

    async def test_range_suffix_larger_than_file(self):
        r = await self.get(Range='bytes=-99999'); self.assertEqual(r.status_code,206); self.assertEqual(r.content,self.pdf)

    async def test_malformed_ranges_416(self):
        for value in ['bytes=10-1','bytes=-0','bytes=-','bytes=999999-','bytes=0-1,4-5','items=0-1','bytes=abc-def','bytes='+'9'*5000+'-']:
            with self.subTest(value=value[:30]):
                r = await self.get(Range=value)
                self.assertEqual(r.status_code,416); self.assertEqual(r.headers['content-range'],f'bytes */{len(self.pdf)}')

    async def test_head_full(self):
        r = await self.client.head(self.url, headers=self.headers)
        self.assertEqual(r.status_code,200); self.assertEqual(r.content,b''); self.assertEqual(int(r.headers['content-length']),len(self.pdf))

    async def test_head_ignores_range(self):
        r = await self.client.head(self.url,headers={**self.headers,'Range':'bytes=0-5'})
        self.assertEqual(r.status_code,200); self.assertNotIn('content-range',r.headers)
        self.assertEqual(int(r.headers['content-length']),len(self.pdf))

    async def test_preflight_head_allowed(self):
        r=await self.client.options(self.url,headers={'Origin':'null','Access-Control-Request-Method':'HEAD','Access-Control-Request-Headers':'authorization,range'})
        self.assertEqual(r.status_code,204)

    async def test_unauthenticated_no_storage_access(self):
        r=await self.client.get(self.url); self.assertEqual(r.status_code,401); self.assertEqual(self.storage_calls,[])

    async def test_invalid_token(self):
        r=await self.client.get(self.url,headers={'Authorization':'Bearer wrong'}); self.assertEqual(r.status_code,401)

    async def test_other_session_owner_cannot_read(self):
        session=await self.runtime.db.create_or_touch_session('other','other-chat',FID)
        token=self.runtime.codec.issue('other',session['id'])
        r=await self.client.get(self.url,headers={'Authorization':'Bearer '+token})
        self.assertEqual(r.status_code,404); self.assertEqual(self.storage_calls,[])

    async def test_foreign_file_record_cannot_read(self):
        self.record.user_id='other'; r=await self.get(); self.assertEqual(r.status_code,404); self.assertEqual(self.storage_calls,[])

    async def test_missing_file_record(self):
        self.record=None; r=await self.get(); self.assertEqual(r.status_code,404)

    async def test_null_path_is_409_not_500(self):
        self.record.path=None; r=await self.get(); self.assertEqual(r.status_code,409); self.assertEqual(r.json()['detail']['code'],'file_path_missing')

    async def test_blank_path_is_409(self):
        self.record.path=' '; r=await self.get(); self.assertEqual(r.status_code,409)

    async def test_invalid_path_types(self):
        for value in [12,{},b'x','bad\x00path']:
            self.record.path=value; r=await self.get(); self.assertEqual(r.status_code,409)

    async def test_missing_file_404(self):
        self.record.path=str(self.root/'missing.pdf'); r=await self.get(); self.assertEqual(r.status_code,404)

    async def test_null_path_uuid_recovery_database_unchanged(self):
        self.record.path=None; (self.uploads/(FID+'_kniha.pdf')).write_bytes(self.pdf)
        r=await self.get(); self.assertEqual(r.status_code,200); self.assertEqual(r.content,self.pdf); self.assertIsNone(self.record.path)

    async def test_stale_windows_path_uuid_recovery(self):
        self.record.path='D:\\old-install\\data\\uploads\\'+FID+'_kniha.pdf'
        (self.uploads/(FID+'_kniha.pdf')).write_bytes(self.pdf)
        r=await self.get(); self.assertEqual(r.status_code,200); self.assertTrue(self.record.path.startswith('D:'))

    async def test_ambiguous_uuid_rejected(self):
        self.record.path=None
        for suffix in ['_a.pdf','_b.pdf']: (self.uploads/(FID+suffix)).write_bytes(self.pdf)
        r=await self.get(); self.assertEqual(r.status_code,409); self.assertEqual(r.json()['detail']['code'],'file_path_ambiguous')

    async def test_title_only_match_rejected(self):
        self.record.path=None; (self.uploads/self.record.filename).write_bytes(self.pdf)
        r=await self.get(); self.assertEqual(r.status_code,409)

    async def test_uuid_prefix_collision_rejected(self):
        self.record.path=None; (self.uploads/(FID+'extra.pdf')).write_bytes(self.pdf)
        r=await self.get(); self.assertEqual(r.status_code,409)

    async def test_symlink_outside_uploads_rejected(self):
        self.record.path=None
        try: (self.uploads/(FID+'_link.pdf')).symlink_to(self.path)
        except (OSError,NotImplementedError): self.skipTest('symlinks unavailable')
        r=await self.get(); self.assertEqual(r.status_code,409)

    async def test_cloud_no_local_uuid_fallback(self):
        self.config.STORAGE_PROVIDER='s3'; self.record.path=None
        (self.uploads/(FID+'_local.pdf')).write_bytes(self.pdf)
        r=await self.get(); self.assertEqual(r.status_code,409)

    async def test_sync_files_adapter(self):
        self.files.get_file_by_id=lambda file_id:self.record
        r=await self.get(); self.assertEqual(r.status_code,200)

    async def test_sync_wrapper_returning_awaitable(self):
        async def result(): return self.record
        self.files.get_file_by_id=lambda file_id:result()
        r=await self.get(); self.assertEqual(r.status_code,200)

    async def test_async_storage_adapter(self):
        async def get_file(path): return path
        self.storage.get_file=get_file; r=await self.get(); self.assertEqual(r.status_code,200)

    async def test_storage_bad_result(self):
        self.storage.get_file=lambda path:42
        r=await self.get(); self.assertEqual(r.status_code,502); self.assertEqual(r.json()['detail']['code'],'storage_path_invalid')

    async def test_storage_permission_error(self):
        def denied(path): raise PermissionError('private path')
        self.storage.get_file=denied
        with self.assertLogs('study_tutor',level='WARNING'):
            r=await self.get()
        self.assertEqual(r.status_code,503); self.assertNotIn('private path',r.text)

    async def test_storage_exception_safe_diagnostic(self):
        def failure(path): raise RuntimeError('secret-password-and-private-path')
        self.storage.get_file=failure
        with self.assertLogs('study_tutor',level='ERROR') as logs:
            r=await self.get()
        self.assertEqual(r.status_code,502); self.assertNotIn('secret-password',r.text)
        detail=r.json()['detail']; self.assertEqual(detail['error_type'],'RuntimeError')
        self.assertIn(detail['error_id'],'\n'.join(logs.output))

    async def test_empty_file_422(self):
        self.path.write_bytes(b''); r=await self.get(); self.assertEqual(r.status_code,422)

    async def test_non_pdf_422(self):
        self.path.write_bytes(b'<html>error</html>'); r=await self.get(); self.assertEqual(r.status_code,422)

    async def test_open_permission_error_before_headers(self):
        old=Path.open
        def controlled(path,*args,**kwargs):
            if path==self.path and args and args[0]=='rb': raise PermissionError('private path')
            return old(path,*args,**kwargs)
        with patch.object(Path,'open',controlled): r=await self.get()
        self.assertEqual(r.status_code,503); self.assertIn('storage_permission_denied',r.text)

    async def test_generic_error_has_log_id_not_private_details(self):
        async def fail(uid,fid): raise TypeError('private details')
        self.runtime._get_file=fail
        with self.assertLogs('study_tutor',level='ERROR') as logs:
            r=await self.get()
        self.assertEqual(r.status_code,500); payload=r.json(); self.assertEqual(payload['code'],'tutor_route_error')
        self.assertNotIn('private details',r.text); self.assertIn(payload['error_id'],'\n'.join(logs.output))

    async def test_health_identifies_hotfix_not_document_success(self):
        r=await self.client.get('/study-tutor/health'); self.assertEqual(r.status_code,200)
        self.assertEqual(r.json()['pdf_delivery']['revision'],'pdf-delivery-r2')
        self.assertFalse(r.json()['pdf_delivery']['live_document_verified'])

    async def test_sqlite_connection_closed_after_reads_and_writes(self):
        connections=[]
        original=self.runtime.db._connect
        def tracked():
            conn=original(); connections.append(conn); return conn
        self.runtime.db._connect=tracked
        self.runtime.db._execute_sync('CREATE TABLE IF NOT EXISTS close_test (value TEXT)')
        self.runtime.db._one_sync('SELECT 1 AS value')
        self.runtime.db._all_sync('SELECT 1 AS value')
        self.assertEqual(len(connections),3)
        for conn in connections:
            with self.assertRaises(TUTOR.sqlite3.ProgrammingError): conn.execute('SELECT 1')

    async def test_sqlite_connection_closed_on_error(self):
        conn=self.runtime.db._connect()
        self.runtime.db._connect=lambda:conn
        with self.assertRaises(TUTOR.sqlite3.OperationalError):
            self.runtime.db._execute_sync('INSERT INTO absent_table VALUES (1)')
        with self.assertRaises(TUTOR.sqlite3.ProgrammingError): conn.execute('SELECT 1')

    async def test_fd_closed_after_success(self):
        handle=io.BytesIO(self.pdf); response=TUTOR.PdfStreamResponse(handle,len(self.pdf),status_code=200,headers={})
        async def receive(): return {'type':'http.request','body':b'','more_body':False}
        async def send(message): pass
        await response({'type':'http','asgi':{'spec_version':'2.4'},'method':'GET'},receive,send)
        self.assertTrue(handle.closed)

    async def test_fd_closed_after_disconnect(self):
        handle=io.BytesIO(self.pdf); response=TUTOR.PdfStreamResponse(handle,len(self.pdf),status_code=200,headers={})
        async def receive(): return {'type':'http.disconnect'}
        async def send(message): raise OSError('disconnected')
        with self.assertRaises(Exception):
            await response({'type':'http','asgi':{'spec_version':'2.4'},'method':'GET'},receive,send)
        self.assertTrue(handle.closed)


if __name__=='__main__': unittest.main(verbosity=2)

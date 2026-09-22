"""Regression for a missing canonical source + a byte-identical replacement upload.
The ASGI gateway/SQLite/authorization are real; only Open WebUI APIs are doubles.
VUT_CASE_PDF optionally points to a private real PDF. It is never redistributed.
"""
from __future__ import annotations
import asyncio
import hashlib
import io
import os
from pathlib import Path
import sys
import time
import types
import unittest
from contextlib import asynccontextmanager
from unittest.mock import patch
import test_pdf_delivery as fixture

TUTOR = fixture.TUTOR
FID = fixture.FID
NEW = '4a1a7968-eb9a-467d-8041-4f0d54b067e6'
OTHER = 'fa25de9c-6ffe-41c0-86f4-1e43123896b8'

class PdfSourceRecoveryTests(unittest.IsolatedAsyncioTestCase):
    get = fixture.PdfDeliveryTests.get

    async def asyncSetUp(self):
        await fixture.PdfDeliveryTests.asyncSetUp(self)
        if os.environ.get('VUT_CASE_PDF'):
            self.pdf = Path(os.environ['VUT_CASE_PDF']).read_bytes()
            self.path.write_bytes(self.pdf)
        self.digest = hashlib.sha256(self.pdf).hexdigest()
        self.record.meta = {'file_hash': self.digest}
        self.records = {FID: self.record}
        async def get_record(fid): return self.records.get(fid)
        async def get_owned(uid): return [r for r in self.records.values() if r.user_id == uid]
        async def update_data(fid, data):
            record = self.records[fid]
            record.data.update(data)
            return record
        self.files.get_file_by_id = get_record
        self.files.get_files_by_user_id = get_owned
        self.files.update_file_data_by_id = update_data
        self.module_names = ['open_webui.models.knowledge', 'open_webui.routers', 'open_webui.routers.files', 'open_webui.routers.retrieval']
        modules = {name: types.ModuleType(name) for name in self.module_names}
        async def has_file(kid, fid): return True
        async def add_file(**kwargs): return True
        modules['open_webui.models.knowledge'].Knowledges = types.SimpleNamespace(has_file=has_file, add_file_to_knowledge_by_id=add_file)
        self.knowledge = modules['open_webui.models.knowledge'].Knowledges
        self.processed = []
        async def process_file(request, form_data, user, db):
            self.processed.append(form_data.file_id)
            return {'status': True}
        modules['open_webui.routers.retrieval'].ProcessFileForm = lambda **kwargs: types.SimpleNamespace(**kwargs)
        modules['open_webui.routers.retrieval'].process_file = process_file
        self.ow_upload = modules['open_webui.routers.files']
        self.extra_patch = patch.dict(sys.modules, modules); self.extra_patch.start()
        self.user = types.SimpleNamespace(id='owner')
        async def user_from_claims(claims): return self.user
        async def ensure_knowledge(uid): return 'knowledge'
        self.runtime.user_from_claims = user_from_claims
        self.runtime.ensure_knowledge = ensure_knowledge
        self.runtime.schedule_book_analysis = lambda *args, **kwargs: None
        @asynccontextmanager
        async def session(): yield object()
        self.runtime._openwebui_db_session = session
        await self.runtime.db.update_book_file_hash('owner', FID, self.digest)

    async def asyncTearDown(self):
        tasks = list(self.runtime._analysis_tasks.values())
        for task in tasks:
            if not task.done(): task.cancel()
        if tasks: await asyncio.gather(*tasks, return_exceptions=True)
        self.extra_patch.stop()
        await fixture.PdfDeliveryTests.asyncTearDown(self)

    async def add_copy(self, *, register=True, owner='owner', payload=None, raw_meta=True, fid=NEW):
        path = self.uploads / (fid + '.pdf')
        path.write_bytes(self.pdf if payload is None else payload)
        rec = types.SimpleNamespace(id=fid, user_id=owner, path=str(path), filename='numericke_metody_2.pdf',
              meta={'file_hash': self.digest} if raw_meta else {}, data={}, created_at=int(time.time()))
        self.records[fid] = rec
        book = await self.runtime.db.register_book(owner, 'knowledge', fid, 'Numericke metody 2', self.digest) if register else None
        return rec, book

    async def test_regression_reupload_restores_canonical_200_with_identical_bytes(self):
        self.record.path = None
        _, book = await self.add_copy()
        self.assertTrue(book['deduplicated']); self.assertEqual(book['file_id'], FID)
        response = await self.get()
        self.assertEqual(response.status_code, 200); self.assertEqual(response.content, self.pdf)
        self.assertIsNone(self.record.path)
        self.assertEqual(await self.runtime.db.get_setting('owner', 'active_file_id'), FID)

    async def test_study_state_is_not_migrated_or_deleted_during_source_recovery(self):
        session = await self.runtime.db.create_or_touch_session('owner', 'progress-chat', FID)
        await self.runtime.db.add_selection('owner', session['id'], FID, 0, 'selected text', [])
        await self.runtime.db.add_activity('owner', session['id'], FID, 'test', 'Task', 'Topic', {'answer': 42})
        await self.runtime.db.update_mastery('owner', FID, 'Topic', 0.8)
        await self.runtime.db.upsert_learning_path('owner', FID, source_file_id='plan', source_name='plan.md', content_md='Study plan', parsed={'name': 'Plan'}, checksum='abc')
        self.record.path = None; await self.add_copy()
        tables = ['books', 'sessions', 'selections', 'activities', 'mastery', 'learning_paths']
        before = {t: await self.runtime.db.all('SELECT * FROM '+t, ()) for t in tables}
        self.assertEqual((await self.get()).status_code, 200)
        after = {t: await self.runtime.db.all('SELECT * FROM '+t, ()) for t in tables}
        self.assertEqual(before, after)

    async def test_owned_chat_upload_not_yet_registered_is_recovered(self):
        self.record.path = None; await self.add_copy(register=False)
        self.assertEqual((await self.get()).status_code, 200)

    async def test_registered_copy_supported_without_optional_enumeration_api(self):
        self.record.path = None; await self.add_copy(raw_meta=False)
        del self.files.get_files_by_user_id
        self.assertEqual((await self.get()).status_code, 200)

    async def test_sync_owned_copy_api_supported(self):
        self.record.path = None; await self.add_copy(register=False)
        self.files.get_files_by_user_id = lambda uid: list(self.records.values())
        self.assertEqual((await self.get()).status_code, 200)

    async def test_forged_raw_metadata_does_not_replace_byte_hash_check(self):
        self.record.path = None; await self.add_copy(payload=self.pdf+b'\n% different bytes')
        r = await self.get(); self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json()['detail']['recovery'], 'no_verified_owned_copy')

    async def test_copy_mutation_after_success_is_revalidated(self):
        self.record.path = None; copy, _ = await self.add_copy()
        self.assertEqual((await self.get()).status_code, 200)
        Path(copy.path).write_bytes(self.pdf+b'\n% modified')
        self.assertEqual((await self.get()).status_code, 409)

    async def test_foreign_owner_copy_does_not_grant_access(self):
        self.record.path = None; copy, _ = await self.add_copy(owner='foreign', register=False)
        self.files.get_files_by_user_id = lambda uid: list(self.records.values())
        self.assertEqual((await self.get()).status_code, 409)
        self.assertNotIn(copy.path, self.storage_calls)

    async def test_changed_candidate_owner_is_rechecked_after_enumeration(self):
        self.record.path = None; copy, _ = await self.add_copy(register=False)
        claimed = types.SimpleNamespace(**vars(copy)); copy.user_id = 'foreign'
        self.files.get_files_by_user_id = lambda uid: [claimed]
        self.assertEqual((await self.get()).status_code, 409)
        self.assertNotIn(copy.path, self.storage_calls)

    async def test_extracted_text_hash_and_historical_book_hash_are_not_raw_proof(self):
        self.record.path = None; self.record.meta = {}; self.record.hash = self.digest
        await self.add_copy()
        r = await self.get(); self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json()['detail']['recovery'], 'original_raw_hash_missing')

    async def test_same_title_without_raw_identity_is_not_used(self):
        self.record.path = None; await self.add_copy(register=False, raw_meta=False)
        self.assertEqual((await self.get()).status_code, 409)

    async def test_conflicting_candidate_raw_metadata_is_rejected(self):
        self.record.path = None; copy, _ = await self.add_copy()
        copy.meta['file_hash'] = '0'*64
        self.assertEqual((await self.get()).status_code, 409)

    async def test_original_permission_failure_does_not_trigger_copy_fallback(self):
        await self.add_copy()
        def denied(path): raise PermissionError('private details')
        self.storage.get_file = denied
        with self.assertLogs('study_tutor', level='WARNING'):
            r = await self.get()
        self.assertEqual(r.status_code, 503)

    async def test_original_uuid_ambiguity_is_not_bypassed(self):
        self.record.path = None; await self.add_copy()
        for name in ('_one.pdf','_two.pdf'): (self.uploads/(FID+name)).write_bytes(self.pdf)
        r = await self.get(); self.assertEqual(r.status_code,409)
        self.assertEqual(r.json()['detail']['code'], 'file_path_ambiguous')

    async def test_multiple_missing_copies_do_not_recurse(self):
        self.record.path = None; copy, _ = await self.add_copy(); Path(copy.path).unlink(); copy.path = None
        self.assertEqual((await self.get()).status_code, 409)

    async def test_stale_nonempty_path_recovers_from_owned_copy(self):
        self.record.path = str(self.root/'missing.pdf'); await self.add_copy()
        self.assertEqual((await self.get()).status_code, 200)

    async def test_cloud_copy_uses_storage_provider_not_uuid_globbing(self):
        self.config.STORAGE_PROVIDER = 's3'; self.record.path = None
        copy, _ = await self.add_copy(); actual_path = copy.path; copy.path = 's3://example/'+NEW+'.pdf'
        def get(path):
            self.storage_calls.append(path)
            return actual_path if path == copy.path else None
        self.storage.get_file = get
        self.assertEqual((await self.get()).status_code, 200)
        self.assertIn(copy.path, self.storage_calls)

    async def test_recovered_source_range_and_head(self):
        self.record.path = None; await self.add_copy()
        r = await self.get(Range='bytes=10-1023')
        self.assertEqual(r.status_code, 206); self.assertEqual(r.content, self.pdf[10:1024])
        r = await self.client.head(self.url, headers=self.headers)
        self.assertEqual(r.status_code, 200); self.assertEqual(r.content, b'')
        self.assertEqual(int(r.headers['content-length']), len(self.pdf))

    async def test_historical_alias_uses_canonical_identity(self):
        copy, _ = await self.add_copy(); copy.path = None
        # Make alias itself unreadable: canonical source remains valid.
        Path(self.uploads/(NEW+'.pdf')).unlink()
        r = await self.client.get('/study-tutor/api/pdf/'+NEW, headers=self.headers)
        self.assertEqual(r.status_code, 200); self.assertEqual(r.content, self.pdf)

    async def test_raw_hash_helper_never_uses_file_hash_of_extracted_text(self):
        self.record.meta = {}; self.record.hash = 'a'*64
        self.assertEqual(await self.runtime._raw_file_sha256(self.record), self.digest)
        self.record.path = None
        self.assertEqual(await self.runtime._raw_file_sha256(self.record), '')

    async def test_actual_bytes_override_incorrect_raw_metadata(self):
        self.record.meta = {'file_hash':'0'*64}
        self.assertEqual(await self.runtime._raw_file_sha256(self.record), self.digest)

    async def test_new_upload_not_retrapped_by_legacy_unverifiable_canonical(self):
        self.record.path = None; self.record.meta = {}; self.record.hash = self.digest
        await self.add_copy(register=False)
        book = await self.runtime._register_pdf_book('owner', 'knowledge', NEW, 'Book')
        self.assertEqual(book['file_id'], NEW)
        self.assertFalse(book.get('deduplicated', False))
        self.assertIsNotNone(await self.runtime.db.get_book('owner', FID))
        response = await self.client.get('/study-tutor/api/pdf/'+NEW, headers={'Authorization':'Bearer '+self.token})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, self.pdf)

    async def test_strict_hash_validation(self):
        for bad in ['a'*63, 'a'*65, 'a'*32+'-'+ 'a'*32, None, 64, b'a'*64]:
            self.assertEqual(TUTOR._sha256_digest(bad), '')
        self.assertEqual(TUTOR._sha256_digest('  '+'A'*64+'  '), 'a'*64)

    async def test_hash_cache_invalidates_on_changed_bytes(self):
        self.assertEqual(await self.runtime._raw_file_sha256(self.record), self.digest)
        data = self.pdf+b'\n% changed'; self.path.write_bytes(data)
        self.assertEqual(await self.runtime._raw_file_sha256(self.record), hashlib.sha256(data).hexdigest())

    async def test_consolidation_corrects_legacy_text_hash(self):
        self.record.meta = {}; self.record.hash = 'a'*64
        await self.runtime.db.update_book_file_hash('owner', FID, 'a'*64)
        books = await self.runtime.consolidate_user_library('owner')
        self.assertEqual(books[0]['file_sha256'], self.digest)

    async def test_same_text_hash_different_pdf_bytes_do_not_merge(self):
        self.record.hash = 'a'*64; self.record.meta = {}
        copy, _ = await self.add_copy(register=False, payload=self.pdf+b'\n% second PDF', raw_meta=False)
        copy.hash = self.record.hash
        book = await self.runtime._register_pdf_book('owner', 'knowledge', NEW, 'Second book')
        self.assertEqual(book['file_id'], NEW); self.assertFalse(book.get('deduplicated', False))
        self.assertEqual(len(await self.runtime.consolidate_user_library('owner')), 2)

    async def test_deduplicated_failed_index_is_resumed(self):
        self.record.path = None; _, book = await self.add_copy()
        calls = []; self.runtime.schedule_safe_index = lambda *a, **kw: calls.append((a,kw))
        await self.runtime._resume_registered_book_index(None, self.user, book)
        self.assertEqual(len(calls), 1); self.assertEqual(calls[0][0][2]['file_id'], FID)
        self.assertTrue(calls[0][1]['force'])

    async def test_completed_duplicate_does_not_schedule_again(self):
        self.record.data = {'status':'completed','study_text_status':'completed','study_index_status':'completed','content':'test'}
        _, book = await self.add_copy()
        calls = []; self.runtime.schedule_safe_index = lambda *a, **kw: calls.append((a,kw))
        await self.runtime._resume_registered_book_index(None, self.user, book)
        self.assertEqual(calls, [])

    async def test_missing_source_has_cooldown_even_before_extraction(self):
        self.record.path = None
        book = await self.runtime.db.get_book('owner', FID)
        with self.assertLogs('study_tutor', level='WARNING') as logged:
            await self.runtime._safe_index_book(None, self.user, book)
        self.assertGreater(self.runtime._index_retry_after['owner:'+FID], time.monotonic()+290)
        self.assertFalse(any('Traceback' in line for line in logged.output))
        self.runtime.schedule_safe_index(None, self.user, book)
        self.assertEqual(self.runtime._analysis_tasks, {})

    async def test_attachment_adoption_uses_copy_for_missing_canonical(self):
        self.record.path = None; await self.add_copy(register=False)
        calls = []; self.runtime.schedule_safe_index = lambda *a, **kw: calls.append((a,kw))
        book = await self.runtime.adopt_attached_pdf(None, self.user, [{'id':NEW, 'name':'numericke_metody_2.pdf','type':'application/pdf'}], preferred_file_ids={NEW})
        self.assertEqual(book['file_id'], FID); self.assertTrue(book['deduplicated'])
        self.assertEqual((await self.get()).status_code, 200)
        self.assertTrue(calls[0][1]['force'])

    async def test_multipart_reupload_does_not_claim_failed_index_is_cached(self):
        self.record.path = None; await self.add_copy(register=False)
        async def upload(request, **kwargs):
            return dict(vars(self.records[NEW]))
        self.ow_upload.upload_file_handler = upload
        calls = []; self.runtime.schedule_safe_index = lambda *a, **kw: calls.append((a,kw))
        r = await self.client.post('/study-tutor/api/upload', headers=self.headers,
                 files={'file':('numericke_metody_2.pdf', self.pdf,'application/pdf')})
        self.assertEqual(r.status_code,200, r.text)
        self.assertEqual(r.json()['file_id'], FID); self.assertEqual(r.json()['status'],'processing')
        self.assertEqual(r.json()['analysis_status'],'pending'); self.assertTrue(calls[0][1]['force'])
        self.assertEqual((await self.get()).status_code, 200)

    @unittest.skipUnless(os.environ.get('VUT_CASE_PDF'), 'Set VUT_CASE_PDF for the private real-document test')
    async def test_real_pdf_extraction_and_index_via_recovered_source(self):
        self.record.path = None; await self.add_copy()
        book = await self.runtime.db.get_book('owner', FID)
        await self.runtime._safe_index_book(None, self.user, book)
        self.assertEqual(self.record.data.get('study_text_status'), 'completed', self.record.data)
        self.assertEqual(self.record.data.get('study_index_status'), 'completed')
        self.assertGreater(len(self.record.data.get('content','')),10000)
        self.assertEqual(self.processed, [FID, FID])
        self.assertEqual((await self.get()).content,self.pdf)

if __name__ == '__main__': unittest.main(verbosity=2)

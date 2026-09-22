"""
title: Anonymizovat
version: 7.1.0
author: Reference implementation
required_open_webui_version: 0.11.3
description: Workspace Tool for DLP Guard 7.1. Enable then send a prompt; the dialog receives submitted text and owned attachments, sanitises outgoing history and requires preview approval. Previously stored originals are not edited or deleted.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import inspect
import json
import re
import secrets
import time
from pydantic import BaseModel, Field
from typing import Optional, Callable, Any

PROTOCOL = 'dlp-workspace/7.1'


class DialogError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def js_data(value: Any) -> str:
    # No raw string interpolation into code or HTML.
    return json.dumps(value, ensure_ascii=True, separators=(',', ':')).replace('<', '\\u003c')


def guarded_script(code: str) -> str:
    # Never allow browser exceptions to become sensitive error text or an unanswered callback.
    return "try {\n" + code + "\n} catch (_e) {return {error:'DLP_BROWSER_SCRIPT_FAILED'};}"


def fingerprint(config: BaseModel) -> str:
    return hashlib.sha256(config.model_dump_json().encode()).hexdigest()


class Tools:
    class Valves(BaseModel):
        guard_filter_id: str = Field(default='dlp_guard_v7', description='Skutečné ID aktivního globálního filtru DLP Guard v7.1.')
        dialog_timeout_seconds: int = Field(default=600, ge=30, le=1800)
        callback_timeout_seconds: int = Field(default=8, ge=2, le=30)

    def __init__(self):
        self.valves = self.Valves()
        self.citation = False

    async def _guard(self, request):
        try:
            from open_webui.models.functions import Functions
            from open_webui.utils.plugin import get_function_module_from_cache
            row = await Functions.get_function_by_id(self.valves.guard_filter_id)
            if not row or not row.is_active or not row.is_global or row.type != 'filter':
                raise DialogError('DLP_GLOBAL_FILTER_INACTIVE')
            value = get_function_module_from_cache(request, row.id, function=row)
            cached, _, _ = await value if inspect.isawaitable(value) else value
            if getattr(cached, 'api_version', None) != PROTOCOL:
                raise DialogError('DLP_FILTER_VERSION')
            settings = cached.Valves(**(await Functions.get_function_valves_by_id(row.id) or {}))
            local = type(cached)()
            local.valves = settings
            return local
        except DialogError:
            raise
        except Exception:
            raise DialogError('DLP_FILTER_UNAVAILABLE') from None

    async def _execute(self, callback, code: str, timeout: int) -> dict:
        if not callable(callback):
            raise DialogError('DLP_BROWSER_CONNECTION_REQUIRED')
        try:
            reply = await asyncio.wait_for(callback({'type': 'execute', 'data': {'code': guarded_script(code)}}), timeout)
        except asyncio.TimeoutError:
            raise DialogError('DLP_BROWSER_TIMEOUT') from None
        except Exception:
            raise DialogError('DLP_BROWSER_CONNECTION_FAILED') from None
        if not isinstance(reply, dict):
            raise DialogError('DLP_BROWSER_PROTOCOL')
        if reply.get('error'):
            safe = {'DLP_CONTEXT_CHANGED', 'DLP_CANCELLED', 'DLP_DIALOG_ALREADY_OPEN',
                    'DLP_DIALOG_UNSUPPORTED', 'DLP_TRANSFER_STATE', 'DLP_BROWSER_SCRIPT_FAILED',
                    'DLP_DIALOG_CLOSED', 'DLP_DIALOG_TIMEOUT'}
            raise DialogError(reply['error'] if isinstance(reply['error'], str) and reply['error'] in safe else 'DLP_BROWSER_PROTOCOL')
        return reply

    async def _poll(self, callback, key: str, phase: str, deadline: float, timeout: int) -> dict:
        # No individual socket acknowledgement waits for user input. This also works
        # when the server has a short WEBSOCKET_EVENT_CALLER_TIMEOUT.
        while time.monotonic() < deadline:
            response = await self._execute(callback,
                'const s=window[' + js_data(key) + ']; return s ? s.poll() : {error:"DLP_DIALOG_CLOSED"};', timeout)
            if response.get('stage') == phase:
                return response
            if response.get('stage') not in {'input', 'busy', 'review'}:
                raise DialogError('DLP_BROWSER_PROTOCOL')
            await asyncio.sleep(0.7)
        raise DialogError('DLP_DIALOG_TIMEOUT')

    async def _receive(self, callback, key: str, index: int, size: int, timeout: int) -> bytearray:
        output = bytearray()
        try:
            for offset in range(0, size, 49152):
                count = min(49152, size-offset)
                response = await self._execute(callback,
                    'const s=window['+js_data(key)+']; return s ? await s.chunk('+str(index)+','+str(offset)+','+str(count)+') : {error:"DLP_TRANSFER_STATE"};', timeout)
                encoded = response.get('data')
                if response.get('offset') != offset or not isinstance(encoded, str) or len(encoded) > 65536:
                    raise DialogError('DLP_TRANSFER_INVALID')
                try:
                    chunk = base64.b64decode(encoded, validate=True)
                except Exception:
                    raise DialogError('DLP_TRANSFER_INVALID') from None
                if len(chunk) != count:
                    raise DialogError('DLP_TRANSFER_TRUNCATED')
                output.extend(chunk)
            return output
        except BaseException:
            output[:] = b'\0' * len(output)
            raise

    async def anonymizovat(
        self,
        __user__: Optional[dict] = None,
        __request__: Any = None,
        __event_call__: Optional[Callable] = None,
        __event_emitter__: Optional[Callable] = None,
        __metadata__: Optional[dict] = None,
        __id__: Optional[str] = None,
    ) -> dict:
        """Open the private anonymisation dialog via DLP Guard 7.1.

        The user enables this Workspace Tool and sends a prompt. The
        global filter calls it BEFORE any LLM request. Never accept original text
        or files as model-generated arguments. Do not invoke this tool yourself.
        """
        key = '__OWUI_DLP_TOOL_V7_' + secrets.token_hex(16)
        blocks = []
        files = []
        original = ''
        attempted_browser = False
        result = None
        pending = None
        initial = ''
        cfg = self.valves.model_copy(deep=True)
        try:
            if (not isinstance(__user__, dict) or __user__.get('role') not in {'admin', 'user'} or
                not isinstance(__user__.get('id'), str) or not __user__['id'] or __request__ is None):
                raise DialogError('DLP_AUTH')
            uid = __user__['id']
            if getattr(__request__.state, '_dlp_v71_tool_invocation', None) != (uid, __id__):
                raise DialogError('DLP_TOOL_LAUNCHER_REQUIRED')
            guard = await self._guard(__request__)
            if guard.valves.anonymizer_tool_id != __id__:
                raise DialogError('DLP_TOOL_ID_MISMATCH')
            policy_fingerprint = fingerprint(guard.valves)
            guard.valves.engine(uid, masking=True)  # fail BEFORE collecting raw data
            limits = guard.valves
            pending = getattr(__request__.state, '_dlp_v71_input', None)
            if (not isinstance(pending, dict) or pending.get('protocol') != PROTOCOL or
                pending.get('config_fingerprint') != policy_fingerprint or
                not isinstance(pending.get('messages'), list) or not pending['messages'] or
                not isinstance(pending.get('initial_text'), str) or
                not isinstance(pending.get('file_ids'), list)):
                raise DialogError('DLP_TOOL_INPUT')
            initial = pending['initial_text']
            existing_ids = list(pending['file_ids'])
            if len(initial) > limits.max_chars or len(existing_ids) > limits.max_files:
                raise DialogError('DLP_MANIFEST_LIMIT')
            # Probe execute/ack support BEFORE displaying input fields.
            probe = await self._execute(__event_call__,
                'return (typeof document!=="undefined" && typeof HTMLDialogElement!=="undefined") ? {ready:true} : {error:"DLP_DIALOG_UNSUPPORTED"};', cfg.callback_timeout_seconds)
            if probe.get('ready') is not True:
                raise DialogError('DLP_BROWSER_PROTOCOL')
            attempted_browser = True
            opened = await self._execute(__event_call__, 'const cfg='+js_data({
                'key': key, 'ttl': cfg.dialog_timeout_seconds,
                'maxChars': limits.max_chars, 'maxFiles': limits.max_files,
                'maxFileBytes': limits.max_file_bytes, 'maxTotalBytes': limits.max_total_bytes,
                'prefill': bool(initial), 'existingCount': len(existing_ids),
                'historyCount': max(0, len(pending['messages'])-1),
            })+';\n'+DIALOG_JS, cfg.callback_timeout_seconds)
            if opened.get('stage') != 'input':
                raise DialogError('DLP_BROWSER_PROTOCOL')
            # Bounded callback chunks also in the server -> browser direction.
            for offset in range(0, len(initial), 8192):
                part = initial[offset:offset+8192]
                await self._execute(__event_call__,
                    'const s=window['+js_data(key)+']; return s ? s.prefill('+js_data(part)+','+
                    ('true' if offset+8192 >= len(initial) else 'false')+') : {error:"DLP_DIALOG_CLOSED"};',
                    cfg.callback_timeout_seconds)
            initial = ''
            deadline = time.monotonic() + cfg.dialog_timeout_seconds
            manifest = await self._poll(__event_call__, key, 'ready', deadline, cfg.callback_timeout_seconds)
            if manifest.get('consent') is not True:
                raise DialogError('DLP_CONSENT_REQUIRED')
            text_size, rows = manifest.get('text_bytes'), manifest.get('files')
            if type(text_size) is not int or not 0 <= text_size <= limits.max_chars*4 or not isinstance(rows, list) or len(rows) > limits.max_files:
                raise DialogError('DLP_MANIFEST_LIMIT')
            include_existing = manifest.get('include_existing')
            if type(include_existing) is not bool:
                raise DialogError('DLP_MANIFEST_INVALID')
            selected_ids = existing_ids if include_existing else []
            if len(rows) + len(selected_ids) > limits.max_files:
                raise DialogError('DLP_MANIFEST_LIMIT')
            total = 0
            for i, row in enumerate(rows, 1):
                if (not isinstance(row, dict) or type(row.get('index')) is not int or row['index'] != i or
                    type(row.get('size')) is not int or not 0 < row['size'] <= limits.max_file_bytes or
                    not isinstance(row.get('name'), str) or not 1 <= len(row['name']) <= 512):
                    raise DialogError('DLP_MANIFEST_INVALID')
                total += row['size']
            if total > limits.max_total_bytes:
                raise DialogError('DLP_MANIFEST_LIMIT')
            data = await self._receive(__event_call__, key, 0, text_size, cfg.callback_timeout_seconds)
            blocks.append(data)
            try:
                original = data.decode('utf-8', errors='strict')
            except UnicodeError:
                raise DialogError('DLP_TEXT_ENCODING') from None
            for row in rows:
                data = await self._receive(__event_call__, key, row['index'], row['size'], cfg.callback_timeout_seconds)
                blocks.append(data)
                files.append((row['name'], bytes(data)))
            # Re-read actual server-side bytes AFTER consent; ignore client filename,
            # extracted-text and hash hints. Existing originals are not uploaded again.
            for fid in selected_ids:
                name, raw = await asyncio.wait_for(guard._read_uploaded_file(fid, uid), limits.operation_timeout)
                total += len(raw)
                if total > limits.max_total_bytes:
                    raise DialogError('DLP_MANIFEST_LIMIT')
                files.append((name, raw))
                raw = b''
            # In-memory conversion. Parser threads are not a sandbox and cannot be
            # forcibly killed on timeout; size/depth limits remain in the core.
            result = await asyncio.wait_for(asyncio.to_thread(guard.anonymize_request, pending['messages'], original, files, uid), limits.operation_timeout)
            original = ''; files.clear(); manifest.clear()
            for data in blocks:
                data[:] = b'\0' * len(data)
            blocks.clear()
            # Preview uses small socket messages too; do not serialise three copies
            # of a potentially large conversation into one execute event.
            await self._execute(__event_call__,
                'const s=window['+js_data(key)+']; return s ? s.reviewBegin('+js_data({
                    'counts': result['counts'], 'file_count': result['file_count']})+
                ') : {error:"DLP_DIALOG_CLOSED"};', cfg.callback_timeout_seconds)
            preview = result['preview']
            for offset in range(0, len(preview), 8192):
                await self._execute(__event_call__,
                    'const s=window['+js_data(key)+']; return s ? s.reviewChunk('+js_data(preview[offset:offset+8192])+','+
                    ('true' if offset+8192 >= len(preview) else 'false')+') : {error:"DLP_DIALOG_CLOSED"};',
                    cfg.callback_timeout_seconds)
            preview = ''
            approved = await self._poll(__event_call__, key, 'approved', deadline, cfg.callback_timeout_seconds)
            if approved.get('reviewed') is not True:
                raise DialogError('DLP_REVIEW_REQUIRED')
            current = await self._guard(__request__)
            if fingerprint(current.valves) != policy_fingerprint:
                raise DialogError('DLP_POLICY_CHANGED')
            _, findings = guard._analyse([m['content'] for m in result['messages']] + [str(m['name']) for m in result['messages'] if m.get('name')], uid)
            if findings:
                raise DialogError('DLP_RECHECK')
            # No full page navigation, normal upload, input fill, raw message event
            # or LLM call occurs in this Tool. The filter consumes this clean result.
            return {'protocol': PROTOCOL, 'status':'approved',
                    'sanitized_prompt':result['text'], 'sanitized_messages':result['messages'], 'counts':result['counts'],
                    'file_count':result['file_count']}
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            code = getattr(exc, 'code', 'DLP_ANONYMIZER_FAILED')
            if not isinstance(code, str) or not re.fullmatch(r'DLP_[A-Z_]{1,60}', code):
                code = 'DLP_ANONYMIZER_FAILED'
            if __event_emitter__:
                try:
                    await __event_emitter__({'type':'notification', 'data':{'type':'warning',
                        'content':'Anonymizace nebyla dokončena ('+code+'). Tento požadavek nebyl nástrojem schválen pro LLM. Dříve odeslaný text a běžně nahrané soubory mohou zůstat uložené; nic se automaticky nemaže.'}})
                except Exception:
                    pass
            return {'protocol':PROTOCOL, 'status':'cancelled' if code == 'DLP_CANCELLED' else 'blocked', 'code':code}
        finally:
            original = ''; initial = ''; files.clear(); result = None; pending = None
            for data in blocks:
                data[:] = b'\0' * len(data)
            blocks.clear()
            if attempted_browser and callable(__event_call__):
                try:
                    await self._execute(__event_call__,
                        'const s=window['+js_data(key)+']; if(s)s.dispose(); return {disposed:true};', min(4, cfg.callback_timeout_seconds))
                except Exception:
                    pass  # Browser TTL/pagehide separately remove transient state.


DIALOG_JS = r"""
return (() => {
  const active='__OWUI_DLP_TOOL_V7_ACTIVE';
  if(window[active]) return {error:'DLP_DIALOG_ALREADY_OPEN'};
  if(typeof HTMLDialogElement==='undefined') return {error:'DLP_DIALOG_UNSUPPORTED'};
  const originalUrl=location.href;
  let stage='input', blobs=[], manifest=null, timer=null, cancelled=false, prefilling=!!cfg.prefill;
  const d=document.createElement('dialog');
  d.dataset.dlpV7=''; d.setAttribute('aria-label','Anonymizovat');
  d.style.cssText='width:min(860px,94vw);max-height:90vh;padding:24px;background:white;color:#172033;border:1px solid #94a3b8;border-radius:14px;font:15px/1.5 system-ui,sans-serif';
  d.innerHTML=`<style>
  [data-dlp-v7]::backdrop{background:#172033b0} [data-dlp-v7] *{box-sizing:border-box}
  [data-dlp-v7] h2{margin:0 0 10px;font-size:25px} [data-dlp-v7] textarea{display:block;width:100%;min-height:190px;padding:10px;font:14px/1.5 ui-monospace,monospace;background:white;color:#172033;border:1px solid #94a3b8;border-radius:7px}
  [data-dlp-v7] .note{background:#edf5f7;padding:12px;border-radius:7px;margin:12px 0}
  [data-dlp-v7] label{display:block;margin:12px 0} [data-dlp-v7] button{padding:10px 15px;background:white;color:#172033;border:1px solid #94a3b8;border-radius:7px;cursor:pointer;font:inherit}
  [data-dlp-v7] .primary{background:#155e75;color:white} [data-dlp-v7] button:disabled{opacity:.45;cursor:default}
  [data-dlp-v7] .buttons{display:flex;justify-content:flex-end;gap:8px;flex-wrap:wrap;margin-top:14px}
  [data-dlp-v7] .error{color:#9f1239;white-space:pre-wrap}
  </style>
  <h2>Anonymizovat</h2>
  <section data-phase="input">
  <div class="note">Odeslaný text je předvyplněný níže. Můžete jej opravit a přidat další soubory. Očistí se také historie zahrnutá do tohoto modelového požadavku. Údaje vložené nově jen do dialogu nepoužívají běžný upload; originály z editoru a běžného uploadu ale již mohou být uložené. Nic se nemaže.</div>
  <label>Skutečné zadání pro LLM<textarea data-text autocomplete="off" autocorrect="off" autocapitalize="off" spellcheck="false"></textarea></label>
  <p data-history></p>
  <label data-existing-row hidden><input data-include-existing type="checkbox" checked> <span data-existing-label></span></label>
  <label>Další soubory z počítače<input data-files type="file" multiple></label>
  <p data-limits></p>
  <label><input data-consent type="checkbox"> Souhlasím s převodem zvolených souborů na text a očištěním pracovní kopie zadání i historie pro tento požadavek. Originály na počítači se nemění. Obrazové části dokumentů se vynechají, skeny a samostatná média nejsou podporované.</label>
  <div class="buttons"><button data-cancel type="button">Zrušit</button><button data-process class="primary" type="button">Anonymizovat a zobrazit náhled</button></div>
  </section>
  <section data-phase="busy" hidden><p>Probíhá kontrola. Původní obsah se nepředává LLM; starší záznamy v historii se neupravují.</p><button data-cancel type="button">Zrušit</button></section>
  <section data-phase="review" hidden>
  <p data-counts></p><textarea data-preview readonly spellcheck="false"></textarea>
  <div class="note">Detektor nemusí rozpoznat všechna jména ani citlivé souvislosti. Náhled zkontrolujte. Náhled obsahuje všechny zprávy očištěného modelového požadavku včetně předchozího kontextu. Uložené původní zprávy se nepřepisují. Předchozí vlákna a uploady se nemažou.</div>
  <label><input data-reviewed type="checkbox"> Zkontroloval(a) jsem náhled a schvaluji předání tohoto očištěného zadání LLM.</label>
  <div class="buttons"><button data-cancel type="button">Zrušit</button><button data-approve class="primary" type="button" disabled>Předat očištěné zadání LLM</button></div>
  </section><p role="alert" class="error" data-error></p>`;
  const q=s=>d.querySelector(s);
  const phase=name=>d.querySelectorAll('[data-phase]').forEach(e=>{e.hidden=e.dataset.phase!==name;});
  const err=t=>{q('[data-error]').textContent=t;};
  const releaseRaw=()=>{blobs=[]; manifest=null; q('[data-text]').value='';q('[data-files]').value='';};
  const context=()=>location.href===originalUrl;
  function dispose(){
    cancelled=true;clearTimeout(timer);releaseRaw();q('[data-preview]').value='';
    window.removeEventListener('pagehide',dispose);
    if(d.open)d.close();d.remove();
    if(window[active]===cfg.key)delete window[active];delete window[cfg.key];
  }
  function cancel(){
    // Keep only a cancellation acknowledgement until backend polls or TTL expires.
    cancelled=true;stage='cancelled';releaseRaw();q('[data-preview]').value='';
    if(d.open)d.close();d.remove();
  }
  window[cfg.key]={
    prefill(part,last){
      if(cancelled)return {error:'DLP_CANCELLED'};
      if(!context())return {error:'DLP_CONTEXT_CHANGED'};
      if(stage!=='input'||!prefilling||typeof part!=='string'||typeof last!=='boolean'||q('[data-text]').value.length+part.length>cfg.maxChars*2)return {error:'DLP_TRANSFER_STATE'};
      q('[data-text]').value+=part;
      if(last){prefilling=false;q('[data-text]').disabled=false;q('[data-process]').disabled=false;}
      return {stage:'input'};
    },
    poll(){
      if(cancelled)return {error:'DLP_CANCELLED'};
      if(!context()){dispose();return {error:'DLP_CONTEXT_CHANGED'};}
      if(stage==='ready')return {stage,...manifest};
      if(stage==='approved')return {stage,reviewed:true};
      return {stage};
    },
    async chunk(index,offset,length){
      if(cancelled)return {error:'DLP_CANCELLED'};
      if(!context())return {error:'DLP_CONTEXT_CHANGED'};
      if(stage!=='ready'||!Number.isInteger(index)||!Number.isInteger(offset)||!Number.isInteger(length)||offset<0||length<1||length>49152||!blobs[index]||offset+length>blobs[index].size)return {error:'DLP_TRANSFER_STATE'};
      const bytes=new Uint8Array(await blobs[index].slice(offset,offset+length).arrayBuffer());
      if(cancelled||!context()){bytes.fill(0);return {error:'DLP_CANCELLED'};}
      let binary='';for(let i=0;i<bytes.length;i+=8192)binary+=String.fromCharCode(...bytes.subarray(i,i+8192));
      const data=btoa(binary);bytes.fill(0);return {offset,data};
    },
    reviewBegin(payload){
      if(cancelled)return {error:'DLP_CANCELLED'};
      if(!context()){dispose();return {error:'DLP_CONTEXT_CHANGED'};}
      if(stage!=='ready'||!payload||typeof payload.counts!=='object')return {error:'DLP_TRANSFER_STATE'};
      releaseRaw();q('[data-preview]').value='';
      q('[data-counts]').textContent='Přílohy: '+payload.file_count+'. Náhrady: '+Object.values(payload.counts).reduce((a,b)=>a+b,0)+'.';
      stage='review_transfer';return {stage};
    },
    reviewChunk(part,last){
      if(cancelled)return {error:'DLP_CANCELLED'};
      if(!context()){dispose();return {error:'DLP_CONTEXT_CHANGED'};}
      if(stage!=='review_transfer'||typeof part!=='string'||typeof last!=='boolean'||q('[data-preview]').value.length+part.length>cfg.maxChars*3+100000)return {error:'DLP_TRANSFER_STATE'};
      q('[data-preview]').value+=part;
      if(last){stage='review';phase('review');}
      return {stage};
    },
    dispose
  };
  window[active]=cfg.key;
  q('[data-limits]').textContent=`Nejvýše ${cfg.maxFiles} souborů, ${Math.floor(cfg.maxFileBytes/1000000)} MB na soubor, ${Math.floor(cfg.maxTotalBytes/1000000)} MB celkem.`;
  q('[data-text]').disabled=prefilling;q('[data-process]').disabled=prefilling;
  q('[data-history]').textContent=cfg.historyCount ? `Očistí se také ${cfg.historyCount} předchozích zpráv modelového kontextu; budou zahrnuté v náhledu.` : '';
  q('[data-existing-row]').hidden=!cfg.existingCount;
  q('[data-existing-label]').textContent=`Zahrnout již připojené přílohy (${cfg.existingCount}). Budou načteny pod vaším účtem; původní uploady zůstanou nezměněné.`;
  q('[data-process]').onclick=()=>{
    if(cancelled||prefilling||stage!=='input')return;
    err('');const text=q('[data-text]').value;const files=Array.from(q('[data-files]').files||[]);
    if(!q('[data-consent]').checked){err('Nejprve potvrďte souhlas s převodem.');return;}
    const includeExisting=!!cfg.existingCount && q('[data-include-existing]').checked;
    const existingCount=includeExisting ? cfg.existingCount : 0;
    if(!text.trim()&&!files.length&&!existingCount){err('Vložte text nebo zvolte soubor.');return;}
    if(text.length>cfg.maxChars||files.length+existingCount>cfg.maxFiles||files.some(f=>f.size<=0||f.size>cfg.maxFileBytes||f.name.length>512)||files.reduce((n,f)=>n+f.size,0)>cfg.maxTotalBytes){err('Překročen limit nebo prázdný soubor.');return;}
    blobs=[new Blob([text],{type:'text/plain;charset=utf-8'}),...files];
    manifest={consent:true,include_existing:includeExisting,text_bytes:blobs[0].size,files:files.map((f,i)=>({index:i+1,name:f.name,size:f.size}))};
    q('[data-text]').value='';q('[data-files]').value='';stage='ready';phase('busy');
  };
  q('[data-reviewed]').onchange=()=>{q('[data-approve]').disabled=!q('[data-reviewed]').checked;};
  q('[data-approve]').onclick=()=>{
    if(cancelled||!context()||stage!=='review'||!q('[data-reviewed]').checked)return;
    stage='approved';q('[data-approve]').disabled=true;phase('busy');
  };
  d.querySelectorAll('[data-cancel]').forEach(b=>{b.onclick=cancel;});
  d.addEventListener('cancel',e=>{e.preventDefault();cancel();});
  for(const t of ['input','change','paste','drop','dragover','keydown','keyup','compositionstart','compositionend'])
    d.addEventListener(t,e=>{e.stopPropagation();if(t==='drop'||t==='dragover')e.preventDefault();});
  window.addEventListener('pagehide',dispose);
  timer=setTimeout(dispose,cfg.ttl*1000);
  document.body.appendChild(d);d.showModal();q('[data-text]').focus();
  return {stage};
})();
"""

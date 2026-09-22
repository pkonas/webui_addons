import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const source=fs.readFileSync(new URL('../docs/canvas.pdf-hotfix.js',import.meta.url),'utf8');
const fn=source.slice(source.indexOf('async function diagnosePdfTransport('),source.indexOf('function showRendererError('));
function diagnostic(fetch) {
  const context=vm.createContext({fetch,AbortController,TextDecoder,setTimeout,clearTimeout});
  vm.runInContext(fn,context);
  return context.diagnosePdfTransport;
}
test('structured storage error and original bearer authorization',async()=>{
  const run=diagnostic(async(url,options)=>{
    assert.equal(options.headers.Authorization,'Bearer test-token');
    assert.equal(options.headers.Range,'bytes=0-1023');
    assert.equal(options.credentials,'omit');
    assert.equal(url,'/study-tutor/api/pdf/file-id');
    return new Response(JSON.stringify({detail:{code:'file_path_missing',message:'Chybí cesta'}}),{status:409,headers:{'Content-Type':'application/json'}});
  });
  const value=await run('file-id','test-token');
  assert.equal(value.status,409); assert.match(value.text,/file_path_missing/); assert.doesNotMatch(value.text,/test-token/);
});
test('generic route error retains server log correlation ID',async()=>{
  const run=diagnostic(async()=>new Response(JSON.stringify({detail:'Interní chyba',error_id:'abcdef123',error_type:'TypeError'}),{status:500,headers:{'Content-Type':'application/json'}}));
  const value=await run('id','token'); assert.equal(value.status,500); assert.match(value.text,/abcdef123/); assert.match(value.text,/TypeError/);
});
test('successful range response is cancelled without downloading a document',async()=>{
  let cancelled=false;
  const run=diagnostic(async()=>({ok:true,status:206,body:{cancel:async()=>{cancelled=true;}}}));
  const value=await run('id','token'); assert.equal(value.status,206); assert.equal(cancelled,true);
});
test('non-JSON errors are not reflected into the diagnostic',async()=>{
  const run=diagnostic(async()=>new Response('<html>private-details</html>',{status:500,headers:{'Content-Type':'text/html'}}));
  const value=await run('id','token'); assert.equal(value.status,500); assert.doesNotMatch(value.text,/private-details/);
});
test('invalid oversized JSON is bounded and cancelled',async()=>{
  let cancelled=false,reads=0;
  const run=diagnostic(async()=>({ok:false,status:500,headers:new Headers({'Content-Type':'application/json'}),body:{getReader:()=>({read:async()=>{reads++;return {done:false,value:new Uint8Array(100000).fill(65)};},cancel:async()=>{cancelled=true;}})}}));
  const value=await run('id','token'); assert.equal(value.status,500); assert.equal(reads,1); assert.equal(cancelled,true); assert.ok(value.text.length<250);
});
test('network failure remains separate from HTTP and rendering errors',async()=>{
  const run=diagnostic(async()=>{throw new Error('Network unavailable');});
  const value=await run('id','token'); assert.equal(value.status,0); assert.match(value.text,/Network unavailable/);
});

test('missing-source recovery instructions are shown without guessing a source',async()=>{
  const run=diagnostic(async()=>new Response(JSON.stringify({detail:{code:'file_path_missing',message:'Chybi original',recovery:'original_raw_hash_missing',hint:'Nahrajte jako novou knihu; historii nemazte.'}}),{status:409,headers:{'Content-Type':'application/json'}}));
  const value=await run('id','token'); assert.match(value.text,/original_raw_hash_missing/); assert.match(value.text,/historii nemazte/);
});

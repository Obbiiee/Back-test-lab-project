import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {canonicalBytes,intervalText,isLocalReview,MAX_BYTES,nanoseconds,readLocalFile,ReviewLoader,sha256,utcTime,verifyReview} from '../src/tickReview/ReviewImport.js';
const bytes=text=>new TextEncoder().encode(text);
const fixtures=JSON.parse(readFileSync(new URL('./fixtures/tick-review.json',import.meta.url),'utf8'));
const base=fixtures[0];
for(const fixture of fixtures){
  const result=await verifyReview(bytes(fixture.artifact),bytes(fixture.report));
  assert.equal(result.report.status,fixture.status,fixture.name);
  assert(Object.isFrozen(result.artifact.quotes));assert(Object.isFrozen(result.report));
  assert.equal(await sha256(canonicalBytes(result.artifact)),result.report.inputHash);
  assert.equal(result.report.fillPrice,null);assert.equal(result.report.pnl,null);
}
for(const newline of ['\n','\r\n'])assert.equal((await verifyReview(bytes(base.artifact),bytes(base.report+newline))).report.status,base.status);
for(const vector of JSON.parse(readFileSync(new URL('../../backend/tests/fixtures/contract_hash_vectors.json',import.meta.url),'utf8'))){
  const encoded=canonicalBytes(JSON.parse(vector.canonical));assert.equal(new TextDecoder().decode(encoded),vector.canonical);
  assert.equal(await sha256(encoded),vector.sha256);
}
const unicode={schemaVersion:1,'𐀀':'\b\t\n\f\r\u0000','\ue000':'é☃','10':'ten','2':'two'};
assert.equal(new TextDecoder().decode(canonicalBytes(unicode)), '{"10":"ten","2":"two","schemaVersion":1,"":"é☃","𐀀":"\\b\\t\\n\\f\\r\\u0000"}');
const corruptArtifact=async(change,code)=>{
  const a=JSON.parse(base.artifact);change(a);await assert.rejects(async()=>verifyReview(canonicalBytes(a),bytes(base.report)),code);
};
const corruptReport=async change=>{
  const r=JSON.parse(base.report);change(r);
  const {policyHash:discarded,...payload}=r;assert(discarded);
  r.policyHash=await sha256(canonicalBytes(payload));
  await assert.rejects(()=>verifyReview(bytes(base.artifact),canonicalBytes(r)));
};
for(const change of [a=>{a.artifact='v2';},a=>{a.extra=1;},a=>{a.quotes[0].extra=1;},a=>{a.quotes[0].bid=1.2;},
  a=>{a.quotes[0].bid='NaN';},a=>{a.quotes[0].bid='001';},a=>{a.quotes[0].bid='102.0';},a=>{a.quotes[0].timeNs='31';},
  a=>{a.quotes[0].timeNs='01';},a=>{a.quotes[0].timeNs='10000000000000000000001';},a=>{a.quotes[0].sequence=9007199254740992;},
  a=>{a.quotes[0].fresh=1;},a=>{a.quotes=Array(1025).fill(a.quotes[0]);},a=>{a.datasetId='<script>alert(1)</script>';},
  a=>{a.quotes[0].ask=null;},a=>{a.side='SHORT';},a=>{a.sl='102';}])await corruptArtifact(change);
for(const change of [r=>{r.fillPrice='102';},r=>{r.pnl='2';},r=>{r.executionStatus='FILLED';},r=>{r.artifact='v2';},
  r=>{r.inputHash='b'.repeat(64);},r=>{r.status='AMBIGUOUS';},r=>{r.quoteDecision.observed_price='101';},r=>{r.quoteDecision.event_id='absent';},
  r=>{r.quoteDecision.reason='invented';},r=>{r.quoteDecision.evidence_hash='c'.repeat(64);},r=>{r.issues=['<img src=x onerror=alert(1)>'];},
  r=>{r.declaredEvidence.coverage_ref=null;},r=>{r.declaredEvidence.freshness_ref=null;},r=>{r.declaredEvidence.artifact_hash='d'.repeat(64);},
  r=>{r.observedSilences=1;},r=>{r.maxIntervalNs='1';},r=>{r.silenceWarningNs='0';},r=>{r.silenceWarningNs='600000000001';},
  r=>{r.issueScope='GLOBAL_MARKET';},r=>{r.extra=1;}])await corruptReport(change);
for(const raw of [' '+base.artifact,base.artifact+'\n',base.artifact.replace('"schemaVersion":1','"schemaVersion":1,"schemaVersion":1'),base.artifact.slice(0,-1)])
  await assert.rejects(()=>verifyReview(bytes(raw),bytes(base.report)));
for(const raw of [base.report+'\n\n',' '+base.report,base.report.replace('"policyHash":','"unknown":')])await assert.rejects(()=>verifyReview(bytes(base.artifact),bytes(raw)));
await corruptArtifact(a=>{a.quotes[0].timeNs='31';},/HIDDEN_FUTURE/);
await corruptArtifact(a=>{a.quotes[0].bid='102.0';},/INVALID_PRICE/);
await corruptArtifact(a=>{a.quotes[0].extra=true;},/INVALID_SHAPE/);
await corruptArtifact(a=>{a.quotes[0].ask=null;},/UNSUPPORTED_CERTAINTY/);
await corruptArtifact(a=>{a.quotes=Array(1025).fill(a.quotes[0]);},/QUOTE_BOUNDS/);
// Maximum-size wire acceptance: authored incomplete coverage remains ambiguous, not an execution.
const unknown=fixtures.find(item=>item.name==='synthetic-unknown');
const maximum=JSON.parse(unknown.artifact),maximumReport=JSON.parse(unknown.report);
maximum.horizonNs='1100';maximum.coverageEndNs='1100';
maximum.quotes=Array.from({length:1024},(_,i)=>({...maximum.quotes[0],id:'max-'+i,timeNs:String(i+11)}));
const maximumBytes=canonicalBytes(maximum);
maximumReport.inputHash=await sha256(maximumBytes);maximumReport.quoteDecision.evidence_hash=maximumReport.inputHash;maximumReport.maxIntervalNs='1';
const {policyHash:previousHash,...maximumPayload}=maximumReport;assert(previousHash);
maximumReport.policyHash=await sha256(canonicalBytes(maximumPayload));
const maximumResult=await verifyReview(maximumBytes,canonicalBytes(maximumReport));
assert.equal(maximumResult.artifact.quotes.length,1024);assert.equal(maximumResult.report.status,'AMBIGUOUS');
await assert.rejects(()=>verifyReview(new Uint8Array(MAX_BYTES+1),bytes(base.report)));
assert.throws(()=>readLocalFile({size:MAX_BYTES+1},new AbortController().signal),/FILE_SIZE/);
assert.throws(()=>readLocalFile({size:0},new AbortController().signal),/FILE_SIZE/);
await assert.rejects(()=>verifyReview(new Uint8Array([0xff,0xfe]),bytes(base.report)));
assert.throws(()=>canonicalBytes({schemaVersion:1,value:1.2}));
assert.throws(()=>canonicalBytes({schemaVersion:1,value:'\ud800'}));
assert.throws(()=>canonicalBytes({schemaVersion:1,value:'x'.repeat(65537)}));
let deep=0;for(let i=0;i<34;i++)deep={deep};assert.throws(()=>canonicalBytes({schemaVersion:1,deep}));
assert.throws(()=>canonicalBytes({schemaVersion:1,rows:Array.from({length:4096},()=>[1,2,3,4])}));
assert.equal(utcTime('1736514000000000001'),'2025-01-10T13:00:00.000000001Z');
assert.equal(utcTime('0'),'1970-01-01T00:00:00.000000000Z');
assert.equal(utcTime('10000000000000000000000'),'10000000000000000000000 ns sejak epoch UTC (di luar rentang kalender browser)');
assert.equal(intervalText('-1'),'-0.000000001 s');assert.equal(intervalText('70000000000'),'70.000000000 s');
assert.equal(nanoseconds('10000000000000000000000'),10n**22n);
for(const host of ['localhost','127.0.0.1','[::1]','::1'])assert(isLocalReview(host));
for(const host of ['example.com','localhost.example.com','192.168.1.1',''])assert(!isLocalReview(host));
// Resolve delayed reads after cancellation/replacement: no old result may publish.
let resolveFirst;
const delayed=(_file,signal)=>new Promise(resolve=>{if(!resolveFirst)resolveFirst={resolve,signal};else resolve(bytes(base.report));});
const loader=new ReviewLoader(delayed,verifyReview);
const old=loader.load({},{});loader.cancel();assert(resolveFirst.signal.aborted);
resolveFirst.resolve(bytes(base.artifact));await assert.rejects(()=>old,{name:'AbortError'});
let finish;
const late=new ReviewLoader(async file=>bytes(file),()=>new Promise(resolve=>{finish=resolve;}));
const oldHash=late.load(base.artifact,base.report);
await new Promise(resolve=>setTimeout(resolve,0));late.cancel();finish({stale:true});await assert.rejects(()=>oldHash,{name:'AbortError'});
const current=new ReviewLoader(async file=>bytes(file));const result=await current.load(base.artifact,base.report);assert.equal(result.report.status,base.status);
let slowFinish;
const replacing=new ReviewLoader(file=>file==='slow'?new Promise(resolve=>{slowFinish=resolve;}):Promise.resolve(bytes(file)));
const superseded=replacing.load('slow',base.report);
assert.equal((await replacing.load(base.artifact,base.report)).report.status,base.status);
slowFinish(bytes(base.artifact));await assert.rejects(()=>superseded,{name:'AbortError'});
const main=readFileSync(new URL('../src/main.jsx',import.meta.url),'utf8');assert(main.includes("get('tick-review')==='local'"));assert(main.includes('localOrigin?<TickReviewEntry/>'));
assert(main.includes('localOrigin=isLocalReview(window.location.hostname)'));
for(const file of ['ReviewImport.js','LocalTickReview.jsx','TickReviewEntry.jsx']){
  const source=readFileSync(new URL('../src/tickReview/'+file,import.meta.url),'utf8');
  assert(!/from ['"].*(?:trading\/|market\/|drawings\/)/.test(source));
  assert(!/localStorage|indexedDB|fetch\(|XMLHttpRequest|sendBeacon|dangerouslySetInnerHTML|console\./.test(source));
}
console.log(`PASS Local Tick Review: ${fixtures.length} Python-authored vectors, golden canonical parity, exact prices/time, hostile shapes/hash/financial/future refusal, bounds, cancellation, local entry and financial/storage/network separation.`);

// Read-only wire verifier. No TP/SL evaluator, trading writer, storage or network adapter.
export const MAX_BYTES=1048576;
const encoder=new TextEncoder();
const fail=code=>{throw new Error(code);};
const need=(ok,code)=>{if(!ok)fail(code);};
const plain=value=>value!==null&&typeof value==='object'&&!Array.isArray(value)&&Object.getPrototypeOf(value)===Object.prototype;
const shape=(value,keys)=>{const expected=keys.split(' ');need(plain(value)&&Object.keys(value).length===expected.length&&expected.every(key=>Object.hasOwn(value,key)),'INVALID_SHAPE');};
const id=value=>need(typeof value==='string'&&/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/.test(value),'INVALID_ID');
const hash=value=>need(typeof value==='string'&&/^[0-9a-f]{64}$/.test(value),'INVALID_HASH');
const bool=value=>need(typeof value==='boolean','INVALID_FLAG');
const integer=value=>need(Number.isSafeInteger(value)&&value>=0,'INVALID_INTEGER');
export function nanoseconds(value){
  need(typeof value==='string'&&/^(0|[1-9][0-9]{0,22})$/.test(value),'INVALID_TIME');
  const result=BigInt(value);need(result<=10n**22n,'INVALID_TIME');return result;
}
function price(value){
  need(typeof value==='string'&&value.length<=1024&&/^(?:[1-9][0-9]*(?:\.[0-9]*[1-9])?|0\.[0-9]*[1-9])$/.test(value),'INVALID_PRICE');
  const [whole,fraction='']=value.split('.');
  need(fraction.length<=1000&&(whole+fraction).replace(/^0+/,'').length<=1000,'INVALID_PRICE');
}
function comparePrice(a,b){
  const [aw,af='']=a.split('.'),[bw,bf='']=b.split('.');
  if(aw.length!==bw.length)return aw.length-bw.length;
  if(aw!==bw)return aw<bw?-1:1;
  const n=Math.max(af.length,bf.length),aa=af.padEnd(n,'0'),bb=bf.padEnd(n,'0');
  return aa===bb?0:aa<bb?-1:1;
}
function codePointOrder(a,b){
  const aa=Array.from(a,c=>c.codePointAt(0)),bb=Array.from(b,c=>c.codePointAt(0));
  for(let i=0;i<Math.min(aa.length,bb.length);i++)if(aa[i]!==bb[i])return aa[i]-bb[i];
  return aa.length-bb.length;
}
// Match existing Python BTL-CJSON-1 wire values; manual object encoding preserves numeric-key ordering.
export function canonicalBytes(root){
  need(plain(root)&&root.schemaVersion===1,'INVALID_SCHEMA');let budget=16384;
  const text=value=>{
    const chars=Array.from(value);
    need(chars.length<=65536&&!chars.some(c=>c.codePointAt(0)>=0xd800&&c.codePointAt(0)<=0xdfff),'INVALID_UNICODE');
    return JSON.stringify(value);
  };
  const encode=(value,depth=0)=>{
    need(--budget>=0&&depth<=32,'CANONICAL_BOUNDS');
    if(value===null||typeof value==='boolean')return String(value);
    if(typeof value==='string')return text(value);
    if(typeof value==='number'){need(Number.isSafeInteger(value),'INVALID_NUMBER');return String(value);}
    if(Array.isArray(value)){need(value.length<=4096,'CANONICAL_BOUNDS');return '['+value.map(v=>encode(v,depth+1)).join(',')+']';}
    need(plain(value)&&Object.keys(value).length<=4096,'CANONICAL_BOUNDS');
    return '{'+Object.keys(value).sort(codePointOrder).map(k=>text(k)+':'+encode(value[k],depth+1)).join(',')+'}';
  };
  const bytes=encoder.encode(encode(root));need(bytes.length<=MAX_BYTES,'FILE_TOO_LARGE');return bytes;
}
export async function sha256(bytes){
  need(globalThis.crypto?.subtle,'CRYPTO_UNAVAILABLE');
  return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),n=>n.toString(16).padStart(2,'0')).join('');
}
function parse(bytes,report=false){
  need(bytes instanceof Uint8Array&&bytes.length>0&&bytes.length<=MAX_BYTES,'FILE_SIZE');
  let raw;
  try{raw=new TextDecoder('utf-8',{fatal:true,ignoreBOM:true}).decode(bytes);}catch{fail('INVALID_UTF8');}
  // Python CLI stdout can have one platform line ending. No other whitespace normalization.
  if(report)raw=raw.replace(/\r?\n$/,'');
  let value;try{value=JSON.parse(raw);}catch{fail('INVALID_JSON');}
  const normalized=canonicalBytes(value);
  need(new TextDecoder().decode(normalized)===raw,'NON_CANONICAL');return value;
}
function validateArtifact(a){
  shape(a,'schemaVersion artifact datasetId datasetVersion datasetHash profileVersion instrumentId feedId side activationNs horizonNs sl tp coverageStartNs coverageEndNs coverageComplete trustedSequence quotes');
  need(a.artifact==='BTL-TICK-EVIDENCE-1','UNKNOWN_VERSION');
  for(const key of ['datasetId','datasetVersion','profileVersion','instrumentId','feedId'])id(a[key]);
  hash(a.datasetHash);need(['LONG','SHORT'].includes(a.side),'INVALID_SIDE');
  for(const key of ['activationNs','horizonNs','coverageStartNs','coverageEndNs'])nanoseconds(a[key]);
  need(nanoseconds(a.activationNs)<=nanoseconds(a.horizonNs)&&nanoseconds(a.coverageStartNs)<=nanoseconds(a.coverageEndNs),'INVALID_WINDOW');
  price(a.sl);price(a.tp);need(a.side==='LONG'?comparePrice(a.sl,a.tp)<0:comparePrice(a.tp,a.sl)<0,'INVALID_LEVELS');
  bool(a.coverageComplete);bool(a.trustedSequence);need(Array.isArray(a.quotes)&&a.quotes.length<=1024,'QUOTE_BOUNDS');
  for(const q of a.quotes){
    shape(q,'id timeNs bid ask sequence fresh gapBefore');id(q.id);nanoseconds(q.timeNs);
    need(nanoseconds(q.timeNs)<=nanoseconds(a.horizonNs),'HIDDEN_FUTURE');
    if(q.bid!==null)price(q.bid);if(q.ask!==null)price(q.ask);
    if(q.sequence!==null)integer(q.sequence);bool(q.fresh);bool(q.gapBefore);
  }
}
export const explanations=Object.freeze({
  COVERAGE_UNVERIFIED:'Kelengkapan quote pada interval ini belum terbukti.',
  COVERAGE_OUTSIDE_INTERVAL:'Batas coverage tidak mencakup seluruh interval evaluasi.',
  SIDE_FRESHNESS_UNVERIFIED:'Freshness bid/ask belum terbukti; ini bukan bukti harga pasti stale.',
  MISSING_SIDE:'Salah satu sisi bid/ask tidak tersedia.',
  DECLARED_DATA_GAP:'Artifact menyatakan gap; kejadian di dalamnya belum diketahui.',
  ACTIVATION_ORDER_UNKNOWN:'Urutan aktivasi order dan quote pada waktu yang sama belum diketahui.',
  ORDER_WITHIN_TIMESTAMP_UNVERIFIED:'Urutan quote dengan timestamp sama belum terbukti.',
  INSUFFICIENT_COVERAGE:'Bukti coverage belum memenuhi interval evaluasi.',
  INVALID_CHRONOLOGY:'Urutan waktu atau identitas kejadian tidak konsisten.',
  INVALID_SOURCE_SEQUENCE:'Sequence sumber tidak memenuhi deklarasi urutan.',
  TIMESTAMP_TIE:'Timestamp sama tanpa bukti urutan yang memadai.',
  COVERAGE_GAP:'Ada deklarasi gap sebelum quote yang dievaluasi.',
  STALE_QUOTE:'Syarat freshness evaluator tidak terpenuhi; belum membuktikan quote sebenarnya stale.',
  CROSSED_QUOTE:'Bid lebih tinggi dari ask; quote tidak dapat digunakan untuk keputusan.',
  TP:'Crossing TP dilaporkan pada quote yang tersedia, bukan fill broker.',
  SL:'Crossing SL dilaporkan pada quote yang tersedia, bukan fill broker.',
  SUPPLIED_INTERVAL_ONLY:'Tidak ada crossing teramati pada quote yang diberikan; harga tak tercatat tetap unknown.',
});
const unresolved=new Set(['INSUFFICIENT_COVERAGE','INVALID_CHRONOLOGY','INVALID_SOURCE_SEQUENCE','ACTIVATION_ORDER_UNKNOWN','TIMESTAMP_TIE','COVERAGE_GAP','MISSING_SIDE','STALE_QUOTE','CROSSED_QUOTE']);
function validateReport(r,a){
  shape(r,'schemaVersion artifact status issues quoteDecision inputHash declaredEvidence observedSilences maxIntervalNs silenceWarningNs executionStatus fillPrice pnl issueScope policyHash');
  need(r.artifact==='BTL-PRECISION-POLICY-1','UNKNOWN_VERSION');hash(r.inputHash);hash(r.policyHash);
  need(r.executionStatus==='NOT_SIMULATED'&&r.fillPrice===null&&r.pnl===null,'FINANCIAL_CLAIM');
  need(r.issueScope==='SUPPLIED_REVEALED_INTERVAL','INVALID_ISSUE_SCOPE');
  need(Array.isArray(r.issues)&&r.issues.length<=32&&r.issues.every(v=>Object.hasOwn(explanations,v))&&new Set(r.issues).size===r.issues.length,'INVALID_ISSUES');
  integer(r.observedSilences);nanoseconds(r.maxIntervalNs);
  const threshold=nanoseconds(r.silenceWarningNs);need(threshold>0n&&threshold<=600_000_000_000n,'INVALID_THRESHOLD');
  if(r.declaredEvidence!==null){
    shape(r.declaredEvidence,'artifact_hash coverage_ref freshness_ref sequence_ref');hash(r.declaredEvidence.artifact_hash);
    need(r.declaredEvidence.artifact_hash===r.inputHash,'EVIDENCE_MISMATCH');
    for(const key of ['coverage_ref','freshness_ref','sequence_ref'])if(r.declaredEvidence[key]!==null)id(r.declaredEvidence[key]);
  }
  const d=r.quoteDecision;shape(d,'classification reason event_id observed_price evidence_hash evaluator_version');
  hash(d.evidence_hash);need(d.evaluator_version==='BTL-TICK-EVIDENCE-1','UNKNOWN_VERSION');
  const statuses={UNRESOLVED:'AMBIGUOUS',OBSERVED_CROSSING:'OBSERVED_QUOTE_CROSSING',NO_OBSERVED_CROSSING:'NO_OBSERVED_CROSSING'};
  need(Object.hasOwn(statuses,d.classification)&&r.status===statuses[d.classification],'INCONSISTENT_STATUS');
  if(d.classification==='OBSERVED_CROSSING'){
    id(d.event_id);price(d.observed_price);need(['TP','SL'].includes(d.reason),'INVALID_REASON');
    const matches=a.quotes.filter(q=>q.id===d.event_id);
    need(matches.length===1&&nanoseconds(matches[0].timeNs)>nanoseconds(a.activationNs)&&
      d.observed_price===(a.side==='LONG'?matches[0].bid:matches[0].ask),'INCONSISTENT_EVENT');
    const quote=matches[0];
    need(a.coverageComplete&&r.declaredEvidence?.coverage_ref&&r.declaredEvidence?.freshness_ref&&quote.fresh&&
      quote.bid!==null&&quote.ask!==null&&!quote.gapBefore&&comparePrice(quote.bid,quote.ask)<=0&&
      nanoseconds(a.coverageStartNs)<=nanoseconds(a.activationNs)&&nanoseconds(a.coverageEndNs)>=nanoseconds(a.horizonNs),'UNSUPPORTED_CERTAINTY');
  }else{
    need(d.event_id===null&&d.observed_price===null,'INCONSISTENT_EVENT');
    need(d.classification==='UNRESOLVED'?unresolved.has(d.reason)&&r.issues.includes(d.reason):d.reason==='SUPPLIED_INTERVAL_ONLY','INVALID_REASON');
    if(d.classification==='NO_OBSERVED_CROSSING')need(a.coverageComplete&&r.declaredEvidence?.coverage_ref,'UNSUPPORTED_CERTAINTY');
  }
  const relevant=a.quotes.filter(q=>nanoseconds(q.timeNs)>=nanoseconds(a.activationNs));let silences=0,max=0n;
  for(let i=1;i<relevant.length;i++){
    const interval=nanoseconds(relevant[i].timeNs)-nanoseconds(relevant[i-1].timeNs);
    if(interval>threshold)silences++;if(interval>max)max=interval;
  }
  need(r.observedSilences===silences&&nanoseconds(r.maxIntervalNs)===max,'INCONSISTENT_DIAGNOSTICS');
}
function frozen(value){if(value&&typeof value==='object'){Object.values(value).forEach(frozen);Object.freeze(value);}return value;}
export async function verifyReview(artifactBytes,reportBytes){
  const artifact=parse(artifactBytes),report=parse(reportBytes,true);validateArtifact(artifact);validateReport(report,artifact);
  need(await sha256(artifactBytes)===report.inputHash,'ARTIFACT_HASH_MISMATCH');
  const {policyHash,...payload}=report;need(await sha256(canonicalBytes(payload))===policyHash,'REPORT_HASH_MISMATCH');
  // Verifies the effective input identity only; does not evaluate crossings or certify declarations.
  const refs=report.declaredEvidence;
  const effective={...artifact,coverageComplete:Boolean(refs?.coverage_ref&&artifact.coverageComplete),trustedSequence:Boolean(refs?.sequence_ref&&artifact.trustedSequence),
    quotes:artifact.quotes.map(q=>({...q,fresh:Boolean(q.fresh&&refs?.freshness_ref)}))};
  need(await sha256(canonicalBytes(effective))===report.quoteDecision.evidence_hash,'EFFECTIVE_HASH_MISMATCH');
  return frozen({artifact,report});
}
export function utcTime(value){
  const ns=nanoseconds(value),seconds=ns/1_000_000_000n;
  if(seconds*1000n>8_640_000_000_000_000n)return value+' ns sejak epoch UTC (di luar rentang kalender browser)';
  return new Date(Number(seconds*1000n)).toISOString().replace('.000Z','.'+(ns%1_000_000_000n).toString().padStart(9,'0')+'Z');
}
export function intervalText(value){
  const n=BigInt(value),abs=n<0n?-n:n;return (n<0n?'-':'')+(abs/1_000_000_000n)+'.'+(abs%1_000_000_000n).toString().padStart(9,'0')+' s';
}
export {isLocalReview} from './LocalOrigin.js';
export function readLocalFile(file,signal){
  need(file&&Number.isSafeInteger(file.size)&&file.size>0&&file.size<=MAX_BYTES,'FILE_SIZE');
  return new Promise((resolve,reject)=>{
    const reader=new FileReader();
    const abort=()=>{reader.abort();reject(new DOMException('Cancelled','AbortError'));};
    if(signal.aborted){abort();return;}
    signal.addEventListener('abort',abort,{once:true});
    const cleanup=()=>signal.removeEventListener('abort',abort);
    reader.onload=()=>{cleanup();resolve(new Uint8Array(reader.result));};
    reader.onerror=()=>{cleanup();reject(new Error('FILE_READ_FAILED'));};
    reader.onabort=()=>{cleanup();reject(new DOMException('Cancelled','AbortError'));};
    reader.readAsArrayBuffer(file);
  });
}
export class ReviewLoader{
  constructor(read=readLocalFile,verify=verifyReview){this.read=read;this.verify=verify;}
  cancel(){this.controller?.abort();this.controller=null;}
  async load(artifact,report){
    this.cancel();const controller=new AbortController();this.controller=controller;
    const bytes=await Promise.all([this.read(artifact,controller.signal),this.read(report,controller.signal)]);
    if(controller.signal.aborted)throw new DOMException('Cancelled','AbortError');
    const result=await this.verify(...bytes);
    if(controller.signal.aborted)throw new DOMException('Cancelled','AbortError');
    return result;
  }
}

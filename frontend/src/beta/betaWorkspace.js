import {canonicalBytes,sha256} from '../tickReview/ReviewImport.js';

export const newId=prefix=>`${prefix}:${crypto.randomUUID()}`;
// Start months the catalog says this instrument can replay. Optional `periods`
// lists only months that passed data checks; refused months are simply absent.
// Without it the single catalog `startPeriod` is the only choice.
const PERIOD=/^\d{4}-(0[1-9]|1[0-2])$/;
export function startPeriods(instrument){
  const listed=Array.isArray(instrument?.periods)?instrument.periods.filter(p=>typeof p==='string'&&PERIOD.test(p)):[];
  if(listed.length)return [...new Set(listed)].sort();
  return typeof instrument?.startPeriod==='string'&&PERIOD.test(instrument.startPeriod)?[instrument.startPeriod]:[];
}
export function periodLabel(period){
  const [y,m]=period.split('-');
  return ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][Number(m)-1]+' '+y;
}
export function methodFromForm(fields,id){
  const protocol=fields.get('kind')==='PROTOCOL';
  return {schemaVersion:1,artifact:'BTL-LOCAL-METHOD-1',id,name:fields.get('name'),kind:protocol?'PROTOCOL':'FREE_STYLE',
    checklistOn:protocol&&fields.get('checklist')==='ON',conditions:protocol?String(fields.get('conditions')??'').split('\n').map(s=>s.trim()).filter(Boolean).map((label,i)=>({id:`condition:${i}`,label})):[],
    riskPercent:protocol?fields.get('risk'):null,rr:protocol?fields.get('rr'):null};
}
export function orderFromForm(fields,view){
  const protocol=view.method.kind==='PROTOCOL',planned=protocol||fields.get('workflow')==='PLANNED';
  const side=fields.get('side');
  return {side,workflow:planned?'PLANNED':'QUICK',orderType:planned?fields.get('orderType'):'MARKET',
    entry:planned?fields.get('entry'):side==='LONG'?view.quote?.ask:view.quote?.bid,
    quantity:protocol?null:fields.get('quantity'),sl:fields.get('sl')||null,tp:protocol?null:fields.get('tp')||null,
    riskPercent:protocol?null:'1',observations:protocol?view.method.conditions.map(c=>({conditionId:c.id,outcome:fields.get('condition:'+c.id)||'NOT_ASSESSED'})):[]};
}
// One in-flight command; pausing prevents any subsequent scheduled command.
export function createReplayLoop({step,onStop,schedule=setTimeout,cancel=clearTimeout}){
  let running=false,timer=null,epoch=0,pending=false;
  function stop(){running=false;epoch++;if(timer!==null)cancel(timer);timer=null;onStop();}
  async function pump(version){
    if(!running||version!==epoch||pending)return;
    pending=true;let more;
    try{more=await step();}catch{more=false;}finally{pending=false;}
    if(!running||version!==epoch)return;
    if(!more){stop();return;}timer=schedule(()=>{timer=null;void pump(version);},500);
  }
  return {start(){if(running||pending)return false;running=true;const version=++epoch;void pump(version);return true;},stop};
}
export function executionCommand(view,kind,payload){
  if(view?.artifact!=='BTL-RESEARCH-SESSION-VIEW-2')throw Error('Unsupported Beta Session.');
  return {schemaVersion:1,artifact:'BTL-TICK-EXECUTION-COMMAND-2',sessionId:view.metadata.id,
    commandId:newId('command'),expectedRevision:view.state.revision,kind,payload};
}
export async function confirmation(review){
  if(review?.artifact!=='BTL-ORDER-REVIEW-2')throw Error('Unsupported review.');
  return {reviewId:review.id,reviewHash:await sha256(canonicalBytes(review))};
}
export function accessMessage(access){
  if(access?.artifact!=='BTL-SANDBOX-ACCESS-1'||access.mode!=='SANDBOX'||access.fundsCollected!==false)throw Error('Unsupported access policy.');
  return `${access.tier} · ${access.savedSessions}/${access.savedLimit} saved Sessions · reset 00:00 ${access.resetTimezone}`;
}
export function betaNotice(error){
  if(error.reconciliationRequired)return 'The request outcome is uncertain. Reload saved evidence before submitting another change.';
  const messages={DAILY_WINDOW_LIMIT:'Today’s Free activation is used. Continue your activated Session, or return after 00:00 UTC.',
    PROTOCOL_BLOCKED:'Protocol rules refused this order. Assess required conditions and preserve the strategy risk, target and order type.',
    SAVED_SESSION_LIMIT:'Your saved Session limit is reached. Move an unused Session to Trash before creating another.',
    WINDOW_ACTIVATION_REQUIRED:'Activate this Session before replay or trading. Free can activate one monthly window per UTC day.',
    SESSION_TRASHED:'Restore this Session from Trash before continuing.',TRASH_EXPIRED:'The 30-day restore period has expired.',
    WINDOW_CONTINUATION_UNAVAILABLE:'This replay target is outside the activated window.',
    SIGN_IN_REQUIRED:'Your sign-in has expired. Sign in again.',UNAVAILABLE:'Beta sandbox is unavailable here. The operator must enable it; no local feed is substituted.',
    HTTPS_REQUIRED:'Sign-in requires the secure application address.',RELOAD_REQUIRED:'The saved state changed or the request was refused. Reload before trying again.',
    SERVICE_BUSY:'The service is busy. Wait, then reload.',SERVICE_UNAVAILABLE:'The service is unavailable. Reload when it is ready.'};
  return messages[error.code]||'The request was refused. Reload saved evidence and check your inputs.';
}

export function checkoutAddress(value){
  if(typeof value!=='string'||value.length>1024)throw Error('Invalid checkout address');
  const url=new URL(value);
  if(url.protocol!=='https:'||url.host!=='app.sandbox.midtrans.com'||url.username||url.password||url.search||url.hash||!/^\/snap\/v[0-9]+\/redir\/[A-Za-z0-9_-]+$/.test(url.pathname))throw Error('Invalid checkout address');
  return url.href;
}

export function billingDuration(value){
  if(typeof value!=='string'||!/^\d{1,8}$/.test(value))return 'Unavailable';
  const seconds=BigInt(value);
  return seconds%86400n===0n?`${seconds/86400n} days`:seconds%3600n===0n?`${seconds/3600n} hours`:`${seconds} seconds`;
}
export function billingExpiry(value){
  if(typeof value!=='string'||!/^\d{1,12}$/.test(value))return 'Unavailable';
  const date=new Date(Number(value)*1000);
  return Number.isFinite(date.getTime())?date.toISOString().replace('T',' ').replace('.000Z',' UTC'):'Unavailable';
}

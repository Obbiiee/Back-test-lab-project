// Optional local observations only. Never an execution or abandonment authority.
export const KEY='btl.alpha.measurement.v1',RETENTION=30*86400000,MAX_BYTES=32768;
export const EVENTS=['workspace_opened','session_restored','replay_started','replay_paused','replay_advanced','replay_seeked','order_command_submitted','order_command_refused','order_outcome_committed','order_outcome_unresolved','analysis_opened','research_metric_requested','recovery_completed','feature_drawing','feature_indicator','feature_journal','feature_source'];
export const FEATURES=['chart','replay','order','drawing','indicator','journal','analysis','source','none'];
export const QUESTIONS=[
  ['usefulness','Does Backtest Lab help your research?',['1','2','3','4','5']],
  ['useful','Most useful feature',FEATURES],['confusing','Most confusing feature',FEATURES],
  ['need','Most wanted next capability',['better-data','clearer-workflow','research','performance','education','other','none']],
  ['pay','Would you consider paying?',['yes','maybe','no']],
  ['price','Optional monthly price band (USD)',['skip','under-5','5-10','10-20','over-20']],
  ['disappointment','If this product were unavailable',['very','somewhat','not','unsure']],
];
const empty=()=>({schemaVersion:1,enabled:false,cohort:'INTERNAL',events:[],responses:[],dropped:0});
export function validateRecord(value,now){
  if(!value||Object.keys(value).sort().join()!=='cohort,dropped,enabled,events,responses,schemaVersion'||value.schemaVersion!==1||typeof value.enabled!=='boolean'||value.cohort!=='INTERNAL'||
     !Array.isArray(value.events)||value.events.length>256||!Array.isArray(value.responses)||value.responses.length>8||
     !Number.isSafeInteger(value.dropped)||value.dropped<0)throw Error('Unsupported measurement record; existing data preserved.');
  for(const e of value.events){if(Object.keys(e).sort().join()!=='at,id,name'||!EVENTS.includes(e.name)||
    typeof e.id!=='string'||!/^[a-z0-9:-]{1,80}$/.test(e.id)||!Number.isSafeInteger(e.at)||e.at>now+60000)throw Error('Invalid local event; existing data preserved.');}
  for(const r of value.responses){if(Object.keys(r).sort().join()!=='answers,at,id,surveyVersion'||r.surveyVersion!=='BTL-ALPHA-FEEDBACK-1'||
    typeof r.id!=='string'||!/^[a-z0-9:-]{1,80}$/.test(r.id)||!Number.isSafeInteger(r.at)||r.at>now+60000||
    Object.keys(r.answers).sort().join()!==QUESTIONS.map(([key])=>key).sort().join()||
    QUESTIONS.some(([key,,options])=>!options.includes(r.answers[key])))throw Error('Invalid feedback; existing data preserved.');}
  return {...value,events:value.events.filter(e=>e.at>=now-RETENTION),responses:value.responses.filter(r=>r.at>=now-RETENTION)};
}
export function readMeasurement(storage,now=Date.now()){
  const raw=storage.getItem(KEY);if(raw===null)return empty();
  if(raw.length>MAX_BYTES)throw Error('Measurement storage limit; existing data preserved.');
  const parsed=JSON.parse(raw),checked=validateRecord(parsed,now);
  if(checked.events.length!==parsed.events.length||checked.responses.length!==parsed.responses.length)
    storage.setItem(KEY,JSON.stringify(checked)); // Purge expired observations on next successful access.
  return checked;
}
export function writeMeasurement(storage,value,now=Date.now()){
  const checked=validateRecord(value,now),raw=JSON.stringify(checked);
  if(raw.length>MAX_BYTES)throw Error('Measurement storage limit.');
  storage.setItem(KEY,raw);return checked;
}
export function eventTo(storage,event,now=Date.now()){
  try{
    const value=readMeasurement(storage,now);if(!value.enabled)return false;
    if(!EVENTS.includes(event.name)||Object.keys(event).sort().join()!=='id,name')return false;
    if(value.events.some(e=>e.id===event.id))return true;
    if(value.events.length===256){value.dropped++;writeMeasurement(storage,value,now);return false;}
    writeMeasurement(storage,{...value,events:[...value.events,{...event,at:now}]},now);return true;
  }catch{return false;} // Optional observation never propagates into finance.
}
export function emitLocal(name){
  // Invoked only after UI acknowledgement/render; no awaited analytics dependency.
  try{eventTo(window.localStorage,{id:'event:'+crypto.randomUUID(),name});}catch{/* disabled/unavailable */}
}
export function saveFeedback(storage,answers,id,now=Date.now()){
  const value=readMeasurement(storage,now);
  if(!value.enabled)throw Error('Enable optional local measurement first.');
  const response={id,at:now,surveyVersion:'BTL-ALPHA-FEEDBACK-1',answers};
  const existing=value.responses.find(r=>r.id===id);
  if(existing){if(JSON.stringify(existing.answers)!==JSON.stringify(answers))throw Error('Feedback retry differs.');return value;}
  if(value.responses.length)throw Error('One response per 30-day local observation window.');
  return writeMeasurement(storage,{...value,responses:[response]},now);
}
export function measurementExport(value,now=Date.now()){
  const record=validateRecord(value,now),counts=Object.fromEntries(EVENTS.map(name=>[name,record.events.filter(e=>e.name===name).length]));
  return {schemaVersion:1,artifact:'BTL-INTERNAL-MEASUREMENT-1',exportedAt:new Date(now).toISOString(),
    observationWindowDays:30,appRelease:'V2.2-INTERNAL-ALPHA',timestampBasis:'UTC_EPOCH_MILLISECONDS_BROWSER_CLOCK_UNTRUSTED',cohort:'INTERNAL',externalCohortSize:0,excludedFromPublicMetrics:true,
    completeness:record.enabled&&record.dropped===0?'LOCAL_OBSERVATIONS_ONLY':'DISABLED_OR_INCOMPLETE',
    counts,dropped:record.dropped,responses:record.responses,
    definitions:{meaningfulUse:'Canonical replay advance and reviewed order, followed by Analysis; survey gate is local UI only.',
      returnUse:'Two workspace observations on separate UTC dates; not verified unique-user retention.',
      abandonment:'UNKNOWN: missing events never prove abandonment',pay:'Stated interest, not paid conversion',
      features:'Feature surface/tool selected, not proof of completing a drawing or study'},
    costWorksheet:{datedAt:new Date(now).toISOString().slice(0,10),currency:'USD',host:'LOCAL_LAPTOP_NOT_HOSTED_INVOICE',
      sharedFixedMonthly:null,computeUnitTariff:null,storageUnitTariff:null,databaseBackupMonthly:null,
      bandwidthUnitTariff:null,dataLicensingMonthly:null,operationalServicesMonthly:null,
      marginalUserCost:null,activeUserAverage:null,workloadClasses:['light','heavy'],
      assumptions:'Tariffs, resource attribution and active-user denominator unknown; local observations cannot estimate SaaS cost.'}};
}

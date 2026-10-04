// UX-only contracts. No account, storage, replay, settlement or financial ledger writes.
import { validateOrder } from '../trading/simulator.js';
export const DEMO_CANDLES=Object.freeze(Array.from({length:100},(_,i)=>{const close=2330+Math.sin(i/8)*3;return {time:1704067200+i*900,open:close-.2,high:close+.7,low:close-.8,close};}));
export const DEMO_PROFILE = Object.freeze({ instrumentId:'DEMO:XAUUSD', feedId:'DEMO_SYNTHETIC', currency:'USD', decimals:3, tick:.001, contractSize:100, step:.0001, min:.0001, max:1000, basis:100000, costs:'Explicit zero-cost UX assumption' });
export const SAMPLE_METHODS = Object.freeze([
  Object.freeze({id:'free',name:'Discretionary research',type:'FREE_STYLE'}),
  Object.freeze({id:'on',name:'Fixed RR · checklist ON',type:'PROTOCOL',rr:2,riskMode:'PERCENT',risk:1,enforcement:true,conditions:Object.freeze(['Setup identified','Stop defined'])}),
  Object.freeze({id:'off',name:'Fixed RR · checklist OFF',type:'PROTOCOL',rr:2,riskMode:'PERCENT',risk:1,enforcement:false,conditions:Object.freeze(['Setup identified','Stop defined'])}),
]);
export function createMethod({name,rr,risk,conditions,enforcement}) {
  if(!name?.trim() || !Number.isFinite(rr) || rr<=0 || !Number.isFinite(risk) || risk<=0 || !conditions?.length || conditions.some(c=>!c.trim())) throw new Error('Name, positive risk/RR and at least one condition are required.');
  if(new Set(conditions.map(c=>c.trim())).size!==conditions.length)throw new Error('Checklist condition names must be unique in this demo.');
  return Object.freeze({id:'custom:'+name.trim(),name:name.trim(),type:'PROTOCOL',rr,riskMode:'PERCENT',risk,enforcement:Boolean(enforcement),conditions:Object.freeze(conditions.map(c=>c.trim()))});
}
export const roundPrice=value=>Math.round(value/DEMO_PROFILE.tick)*DEMO_PROFILE.tick;
export function constrainPlan(method,plan) {
  const next={...plan};
  if(method.type==='PROTOCOL') {next.riskMode=method.riskMode;next.risk=method.risk;next.tp=next.entry+(next.side==='Buy'?1:-1)*Math.abs(next.entry-next.sl)*method.rr;}
  return next;
}
export function preview(method,plan) {
  const p=constrainPlan(method,plan),direction=p.side==='Buy'?1:-1;
  const distance=(p.entry-p.sl)*direction,reward=(p.tp-p.entry)*direction;
  const budget=p.riskMode==='CASH'?p.risk:DEMO_PROFILE.basis*p.risk/100;
  const size=distance>0?Math.floor((budget/(distance*DEMO_PROFILE.contractSize)+1e-10)/DEMO_PROFILE.step)*DEMO_PROFILE.step:0;
  return {plan:p,distance,reward,budget,size,rr:distance>0?reward/distance:null,loss:distance*size*DEMO_PROFILE.contractSize};
}
const tickAligned=n=>Number.isFinite(n)&&Math.abs(n/DEMO_PROFILE.tick-Math.round(n/DEMO_PROFILE.tick))<1e-7;
const close=(a,b)=>Math.abs(a-b)<=1e-7*Math.max(1,Math.abs(a),Math.abs(b));
export function validateRequest(method,request,quote,revision) {
  const reasons=[];
  if(!['FREE_STYLE','PROTOCOL'].includes(method.type))reasons.push('METHOD: Unsupported Method type.');
  if(request.methodId!==method.id || request.sessionId!=='demo-session:'+method.id || request.instrumentId!==DEMO_PROFILE.instrumentId || request.feedId!==DEMO_PROFILE.feedId) reasons.push('IDENTITY: Method/Session/instrument/feed mismatch.');
  if(request.revision!==revision || request.quoteRevision!==quote.revision) reasons.push('STALE: Review no longer matches the plan or quote revision.');
  if(!['QUICK','PLANNED'].includes(request.workflow)) reasons.push('WORKFLOW: Unsupported journey.');
  if(!Number.isFinite(quote.price)||quote.price<=0) reasons.push('QUOTE: Revealed price unavailable.');
  const order={side:request.side,type:request.type,size:request.size,entry:request.entry,sl:request.sl,tp:request.tp};
  const numeric=validateOrder(order,quote.price);if(numeric) reasons.push('ORDER: '+numeric);
  if(request.type==='Market'&&!close(request.entry,quote.price)) reasons.push('QUOTE: Market entry must match reviewed quote.');
  for(const key of ['entry','sl','tp']) if(request[key]!=null&&!tickAligned(request[key])) reasons.push('PRECISION: '+key+' must align to demo tick 0.001.');
  if(request.size<DEMO_PROFILE.min || request.size>DEMO_PROFILE.max || !close(request.size/DEMO_PROFILE.step,Math.round(request.size/DEMO_PROFILE.step))) reasons.push('SIZE: Outside demo lot bounds/step.');
  if(request.workflow==='PLANNED'&&(!Number.isFinite(request.sl)||!Number.isFinite(request.tp)||!Number.isFinite(request.risk)||request.risk<=0||!['PERCENT','CASH'].includes(request.riskMode))) reasons.push('PLAN: Entry, SL, TP and positive risk required.');
  if(request.workflow==='PLANNED'&&!close(request.size,preview(method,request).size)) reasons.push('PLAN: Size must match rounded risk-derived preview.');
  if(method.type==='PROTOCOL') {
    if(request.workflow!=='PLANNED') reasons.push('PROTOCOL: Quick execution is prohibited.');
    if(!['Limit','Stop'].includes(request.type)) reasons.push('PROTOCOL: Pending Limit/Stop only; Market prohibited.');
    if(request.riskMode!==method.riskMode || request.risk!==method.risk) reasons.push('PROTOCOL: Risk is locked by Method.');
    const expected=preview(method,request);
    if(!close(request.tp,expected.plan.tp)||!close(request.size,expected.size)) reasons.push('PROTOCOL: Locked RR/derived size mismatch.');
    if(!method.conditions?.length) reasons.push('PROTOCOL: At least one condition required.');
    if(method.enforcement) for(const condition of method.conditions??[]) if(request.checklist?.[condition]!=='PASS') reasons.push('CHECKLIST: '+condition+' is not PASS.');
  }
  return reasons;
}
export function makeRequest(method,plan,quote,revision,id) {
  const stats=preview(method,plan),p=stats.plan;
  return Object.freeze({id,methodId:method.id,sessionId:'demo-session:'+method.id,instrumentId:DEMO_PROFILE.instrumentId,feedId:DEMO_PROFILE.feedId,revision,quoteRevision:quote.revision,workflow:p.workflow,side:p.side,type:p.type,entry:p.type==='Market'?quote.price:p.entry,sl:p.sl,tp:p.tp,size:p.workflow==='QUICK'?p.size:stats.size,risk:p.risk,riskMode:p.riskMode,checklist:Object.freeze(Object.fromEntries((method.conditions??[]).map(c=>[c,p.checklist?.[c]??'NOT_ASSESSED']))),enforcement:method.type==='PROTOCOL'?method.enforcement:null,source:'PROTOTYPE'});
}
export function confirmRequest(registry,method,request,quote,revision) {
  const payload=JSON.stringify(request),prior=registry[request.id];
  if(prior) return prior.payload===payload?{registry,result:prior.result,duplicate:true,reasons:[]}:{registry,reasons:['IDEMPOTENCY_CONFLICT: Request identity reused with changed payload.']};
  const reasons=validateRequest(method,request,quote,revision);if(reasons.length)return {registry,reasons};
  const result={request,state:request.type==='Market'?'active_position':'pending',remaining:1};
  return {registry:{...registry,[request.id]:{payload,result}},result,reasons:[],duplicate:false};
}
export function manage(method,item,action) {
  if(!item)return {reason:'No simulated order/position selected.'};
  if(action==='cancel' && item.state==='pending')return {item:{...item,state:'cancelled'}};
  if(action==='trigger' && item.state==='pending')return {item:{...item,state:'active_position'}};
  if(!['active_position','partially_exited'].includes(item.state))return {reason:'Action requires an active position.'};
  if(method.type==='PROTOCOL'&&['close','partial','amend'].includes(action))return {reason:'PROTOCOL: No discretionary manual/partial close or exit amendment after trigger.'};
  if(action==='partial')return {item:{...item,state:'partially_exited',remaining:item.remaining*.5}};
  if(['close','plannedExit'].includes(action))return {item:{...item,state:'closed',remaining:0}};
  if(action==='amend')return {item,amend:true};
  return {reason:'Unsupported action.'};
}
export function amendExits(method,item,sl,tp) {
  const permission=manage(method,item,'amend');if(permission.reason)return permission;
  const reason=validateOrder({...item.request,type:'Market',sl,tp},item.request.entry);
  if(reason||![sl,tp].every(tickAligned))return {reason:reason||'Exit prices must align to demo tick.'};
  return {item:{...item,currentExits:{sl,tp}}};
}

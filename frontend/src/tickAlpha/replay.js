// Pure replay-navigation helpers. Targets are canonical UTC nanosecond strings sent to the
// backend ADVANCE/SEEK commands; the backend reveals ticks and settles orders. Nothing here
// derives a fill, a price or an outcome (never settle from candles).
export const SPEEDS=[0.5,1,2,5,10,20];
// Playback rate: market seconds revealed per wall-clock second. One request is issued per
// PLAY_INTERVAL_MS, so the batch revealed per request is rate*PLAY_INTERVAL_MS (ms of market time).
export const PLAY_INTERVAL_MS=500;
const TF_SECONDS={'1m':60,'3m':180,'5m':300,'15m':900,'30m':1800,'1h':3600,'2h':7200,'4h':14400,D:86400};
const TF_LABEL={'1m':'M1','3m':'M3','5m':'M5','15m':'M15','30m':'M30','1h':'H1','2h':'H2','4h':'H4',D:'D1'};
const NS=1000000000n;
export const timeframeSeconds=timeframe=>{
  const value=TF_SECONDS[timeframe];
  if(!value)throw Error('Unsupported timeframe');
  return BigInt(value);
};
export const timeframeLabel=timeframe=>TF_LABEL[timeframe]??timeframe;
const through=value=>{
  if(typeof value!=='string'||!/^\d{1,20}$/.test(value))throw Error('Invalid replay cursor');
  return BigInt(value);
};
// The first nanosecond AFTER the bucket that contains `throughNs` is its end; the candle is
// complete once every tick strictly before that end has been revealed, i.e. through==end-1ns.
// If the cursor already sits on that last nanosecond, the next bucket is targeted. Weekend and
// market gaps need no special case: the target is calendar time (UTC), not tick count.
export function candleTarget(throughNs,timeframe){
  const cursor=through(throughNs),size=timeframeSeconds(timeframe)*NS;
  const end=(cursor/size+1n)*size-1n;
  return String(end>cursor?end:end+size);
}
export function playbackTarget(throughNs,rate,scale=1n){
  if(!SPEEDS.includes(rate))throw Error('Unsupported replay speed');
  return String(through(throughNs)+BigInt(rate*PLAY_INTERVAL_MS)*1000000n*scale);
}
// When a Play request reveals nothing (market gap) the next request widens 4x, up to one candle.
export function widenScale(scale,revealed,timeframe,rate){
  if(revealed)return 1n;
  const cap=timeframeSeconds(timeframe)*NS/(BigInt(rate*PLAY_INTERVAL_MS)*1000000n)||1n;
  const next=scale*4n;
  return next>cap?(cap<1n?1n:cap):next;
}
export const utcLabel=ns=>new Date(Number(BigInt(ns)/1000000n)).toISOString().replace('T',' ').replace(/\.\d{3}Z$/,' UTC');
// Display-only trade announcements. Everything shown comes from the server's committed
// projection (fill price, exit price, net, reason); nothing is recomputed here.
export function tradeEvents(before,after){
  const a=before?.analysis,b=after?.analysis;
  if(!a||!b||a.status!=='COMPLETE'||b.status!=='COMPLETE')return [];
  const knownActive=new Set(a.orders.filter(o=>o.status==='ACTIVE').map(o=>o.id));
  const knownClosed=new Set(a.completed.map(o=>o.id));
  const events=[];
  for(const order of b.orders)if(order.status==='ACTIVE'&&!knownActive.has(order.id)&&!knownClosed.has(order.id))events.push({kind:'FILL',order});
  for(const order of b.completed)if(!knownClosed.has(order.id))events.push({kind:'EXIT',order});
  return events;
}
export function durationLabel(ns){
  if(typeof ns!=='string'||!/^\d{1,20}$/.test(ns))return null;
  let seconds=Number(BigInt(ns)/1000000000n);
  const days=Math.floor(seconds/86400);seconds%=86400;
  const hours=Math.floor(seconds/3600);seconds%=3600;
  const minutes=Math.floor(seconds/60);seconds%=60;
  return days?`${days}d ${hours}h`:hours?`${hours}h ${minutes}m`:minutes?`${minutes}m ${String(seconds).padStart(2,'0')}s`:`${seconds}s`;
}
// ---- Scrubber geometry (presentation + target selection only) ----
// The track spans the Session's calendar month. Left of the cursor is revealed history (pans the
// chart only); right of it is future time that can only be reached through a confirmed forward
// SEEK. No future candle is ever drawn by the scrubber.
export function scrubRange(view){
  const match=/^(\d{4})-(\d{2})$/.exec(view?.metadata?.startPeriod??'');
  if(!match)return null;
  const year=Number(match[1]),month=Number(match[2]);
  if(month<1||month>12)return null;
  return {startNs:BigInt(Date.UTC(year,month-1,1))*1000000n,endNs:BigInt(Date.UTC(year,month,1))*1000000n};
}
export function scrubFraction(ns,range){
  const span=range.endNs-range.startNs;
  if(span<=0n)return 0;
  const value=Number((BigInt(ns)-range.startNs)*1000000n/span)/1000000;
  return Math.min(1,Math.max(0,value));
}
export function scrubTarget(fraction,range){
  const clamped=Math.min(1,Math.max(0,fraction));
  const span=range.endNs-range.startNs;
  const ns=range.startNs+span*BigInt(Math.round(clamped*1000000))/1000000n;
  return String(ns/NS*NS); // whole seconds
}
export const scrubKind=(targetNs,throughNs)=>BigInt(targetNs)<=BigInt(throughNs)?'REVEALED':'FUTURE';
export function scrubStep(targetNs,timeframe,direction,range){
  const size=timeframeSeconds(timeframe)*NS;
  const moved=BigInt(targetNs)+(direction<0?-size:size);
  return String(moved<range.startNs?range.startNs:moved>range.endNs?range.endNs:moved);
}
// Unfinished ADVANCE target reported by the service (the server is the authority; nothing is stored in
// the browser). Older transports may omit the canonical field.
export function pendingTarget(view){
  const target=view&&Object.hasOwn(view,'pendingReplayTargetNs')?view.pendingReplayTargetNs:view?.state?.pendingTargetNs;
  if(typeof target!=='string'||!/^(0|[1-9][0-9]{0,19})$/.test(target))return null;
  return BigInt(target)>BigInt(view.state.throughNs)?{kind:'ADVANCE',target}:null;
}

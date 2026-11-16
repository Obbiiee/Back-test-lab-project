// Pure replay-navigation helpers. Targets are canonical UTC nanosecond strings sent to the
// backend ADVANCE/SEEK commands; the backend reveals ticks and settles orders. Nothing here
// derives a fill, a price or an outcome (never settle from candles).
export const SPEEDS=[1,2,5,10,20];
// Playback rate: market seconds revealed per wall-clock second. One request is issued per
// PLAY_INTERVAL_MS, so the batch revealed per request is rate*PLAY_INTERVAL_MS (ms of market time).
export const PLAY_INTERVAL_MS=500;
export const JUMP_MAX_CHUNKS=240;
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
// Signature of order-relevant committed state, used to detect a trading event during a jump.
export function eventSignature(view){
  const a=view.analysis;
  if(!a||a.status!=='COMPLETE')return `${view.state.revision}`;
  return `${a.orders.map(o=>`${o.id}:${o.status}:${o.remaining??''}:${o.exitRequested?1:0}`).join(',')}|${a.completed.length}`;
}
export const hasWatchedOrders=view=>Boolean(view.analysis?.status==='COMPLETE'&&view.analysis.orders.some(o=>['PENDING','ACTIVE'].includes(o.status)));
export const utcLabel=ns=>new Date(Number(BigInt(ns)/1000000n)).toISOString().replace('T',' ').replace(/\.\d{3}Z$/,' UTC');

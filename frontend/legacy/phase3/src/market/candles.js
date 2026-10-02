export const TIMEFRAMES = { '1m':60,'3m':180,'5m':300,'15m':900,'30m':1800,'1h':3600,'2h':7200,'4h':14400,D:86400,W:604800,M:null };
export function bucketTime(time, timeframe) {
  if (!(timeframe in TIMEFRAMES)) throw new Error('Unsupported timeframe');
  const date = new Date(time * 1000);
  if (timeframe === 'M') return Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), 1) / 1000;
  if (timeframe === 'W') { date.setUTCHours(0,0,0,0); date.setUTCDate(date.getUTCDate() - (date.getUTCDay()+6)%7); return date.getTime()/1000; }
  return Math.floor(time / TIMEFRAMES[timeframe]) * TIMEFRAMES[timeframe];
}
export function aggregateCandles(bars, timeframe) {
  const result=[];
  for(const bar of [...bars].sort((a,b)=>a.time-b.time)) {
    const time=bucketTime(bar.time,timeframe), last=result.at(-1);
    if(last?.time===time) { last.high=Math.max(last.high,bar.high); last.low=Math.min(last.low,bar.low); last.close=bar.close; last.volume+=(bar.volume??0); }
    else result.push({...bar,time,volume:bar.volume??0});
  }
  const date = new Date((result.at(-1)?.time ?? Date.now()/1000)*1000);
  Object.defineProperty(result,"intervalSeconds",{value:TIMEFRAMES[timeframe] ?? (Date.UTC(date.getUTCFullYear(),date.getUTCMonth()+1,1)/1000-bucketTime(date.getTime()/1000,"M"))});
  return result;
}
export function addQuote(bars, quote) {
  const time=bucketTime(quote.time,'1m');
  const index=bars.findIndex(bar=>bar.time===time);
  if(index<0) return [...bars,{time,open:quote.price,high:quote.price,low:quote.price,close:quote.price,volume:0}].sort((a,b)=>a.time-b.time).slice(-30000);
  return bars.map((bar,i)=>i===index?{...bar,high:Math.max(bar.high,quote.price),low:Math.min(bar.low,quote.price),close:quote.price}:bar);
}
export function parseQuote(data) {
  const price=Number(data.price), time=Date.parse(data.updatedAt)/1000;
  if(data.symbol!=='XAU'||!Number.isFinite(price)||price<=0||!Number.isFinite(time)) throw new Error('Format harga XAU/USD tidak valid');
  return {price,time};
}

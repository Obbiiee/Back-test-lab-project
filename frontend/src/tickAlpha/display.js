// Number conversion is confined to chart/indicator presentation, never settlement.
export const TIMEFRAMES=['1m','3m','5m','15m','30m','1h','2h','4h','D'];
export const TICK_STEP_NS=15000000000n;
const MAX_NS=10n**22n;
export const stamp=value=>value===null?'—':new Date(Number(BigInt(value)/1000000n)).toISOString();
export function historyPage(view,page,timeframe,offset){
  const fields='schemaVersion artifact datasetId datasetVersion startTime endTime timeframe priceBasis volumeAvailable coverage executionAuthority status candles nextOffset'.split(' ');
  if(!page||Object.keys(page).length!==fields.length||fields.some(key=>!Object.hasOwn(page,key))||page.schemaVersion!==1)throw Error('Invalid past candle context');
  const end=Date.parse(`${view.metadata.startPeriod}-01T00:00:00Z`)/1000;
  const date=new Date(end*1000);date.setUTCMonth(date.getUTCMonth()-1);
  const start=date.getTime()/1000;
  if(page?.artifact!=='BTL-PAST-CHART-CONTEXT-1'||page.datasetId!==view.state.datasetId
    ||page.datasetVersion!==view.state.datasetVersion||page.timeframe!==timeframe
    ||page.startTime!==start||page.endTime!==end||page.executionAuthority!==false
    ||page.coverage!=='UNKNOWN'||page.priceBasis!=='EXACT_REVEALED_MID_DISPLAY_ONLY'||page.volumeAvailable!==false
    ||!['BUILDING','READY'].includes(page.status)||!Array.isArray(page.candles)||page.candles.length>512
    ||(page.status==='BUILDING'&&(page.candles.length||page.nextOffset!==null))
    ||(page.nextOffset!==null&&(page.nextOffset!==offset+512||page.candles.length!==512||page.nextOffset>50000)))throw Error('Invalid past candle context');
  const bars=displayBars({...view,chart:{...page,candles:page.candles}});
  const duration=timeframe==='D'?86400:parseInt(timeframe,10)*(timeframe.endsWith('h')?3600:60);
  if(bars.some(bar=>bar.time<start||bar.time%duration!==0||bar.time+duration>end))throw Error('Past candle context crosses the Session boundary');
  return bars;
}
export function referencePage(view,page,timeframe,offset){
  const fields='schemaVersion artifact datasetId datasetVersion reference timeframe period startTime endTime trustedStartNs priceBasis volumeAvailable coverage executionAuthority status candles nextOffset'.split(' ');
  if(!page||Object.keys(page).length!==fields.length||fields.some(key=>!Object.hasOwn(page,key))||page.schemaVersion!==1)throw Error('Invalid reference OHLC context');
  const start=BigInt(view.state.startNs),startDate=new Date(Number(start/1000000n));
  const monthStart=Date.UTC(startDate.getUTCFullYear(),startDate.getUTCMonth(),1)/1000;
  const prior=new Date((monthStart-1)*1000),period=`${prior.getUTCFullYear()}-${String(prior.getUTCMonth()+1).padStart(2,'0')}`;
  const priorStart=Date.UTC(prior.getUTCFullYear(),prior.getUTCMonth(),1)/1000;
  const refFields='providerId priceType timezone sourceTimezone manifestSha256 executionAuthority coverage rights fileName fileSha256'.split(' ');
  const unavailableReference=page.reference===null&&['UNAVAILABLE','WARMUP_INCOMPLETE'].includes(page.status)&&page.candles?.length===0&&page.nextOffset===null;
  if(page.artifact!=='BTL-OBSERVED-REFERENCE-OHLC-1'||page.datasetId!==view.state.datasetId||page.datasetVersion!==view.state.datasetVersion
    ||(page.reference===null&&!unavailableReference)
    ||(page.reference!==null&&(!page.reference||Object.keys(page.reference).length!==refFields.length||refFields.some(key=>!Object.hasOwn(page.reference,key))
      ||page.reference.providerId!=='HistData.com'||page.reference.priceType!=='BID'||page.reference.timezone!=='UTC'||page.reference.sourceTimezone!=='EST_FIXED_UTC-5'
      ||!/^\d{4}-\d\d-/.test(page.reference.fileName)||!/^[a-f0-9]{64}$/.test(page.reference.fileSha256)||!/^[a-f0-9]{64}$/.test(page.reference.manifestSha256)
      ||page.reference.executionAuthority!==false||page.reference.coverage!=='UNKNOWN'||page.reference.rights!=='UNKNOWN'))
    ||page.timeframe!==timeframe||page.period!==period||page.startTime!==priorStart||page.endTime!==monthStart
    ||page.trustedStartNs!==view.state.startNs||page.priceBasis!=='HISTDATA_BID_REFERENCE_ONLY'||page.volumeAvailable!==false
    ||page.coverage!=='UNKNOWN'||page.executionAuthority!==false||!['READY','WARMUP_INCOMPLETE','UNAVAILABLE'].includes(page.status)
    ||!Array.isArray(page.candles)||page.candles.length>512||(page.nextOffset!==null&&(page.nextOffset!==offset+page.candles.length||page.candles.length!==512)))throw Error('Invalid reference OHLC context');
  const duration=timeframe==='D'?86400:parseInt(timeframe,10)*(timeframe.endsWith('h')?3600:60);
  let previous=-1;
  const bars=page.candles.map(bar=>{
    if(!Number.isSafeInteger(bar.time)||bar.time<=previous||bar.time%duration||bar.time<page.startTime||bar.time+duration>page.endTime
      ||BigInt(bar.time+duration)*1000000000n>start)throw Error('Reference OHLC crosses the observed Session boundary');
    previous=bar.time;const prices=Object.fromEntries(['open','high','low','close'].map(key=>{
      if(typeof bar[key]!=='string'||!/^[0-9]+(?:\.[0-9]+)?$/.test(bar[key]))throw Error('Invalid reference price');
      const value=Number(bar[key]);if(!Number.isFinite(value))throw Error('Invalid reference price');return[key,value];
    }));
    if(prices.low<=0||prices.low>Math.min(prices.open,prices.close)||prices.high<Math.max(prices.open,prices.close))throw Error('Invalid reference OHLC envelope');
    return{time:bar.time,...prices};
  });
  return bars;
}
export function displayBars(view){
  const chart=view.chart;
  if(!chart||chart.priceBasis!=='EXACT_REVEALED_MID_DISPLAY_ONLY'||chart.volumeAvailable!==false
    ||!TIMEFRAMES.includes(chart.timeframe)||!Array.isArray(chart.candles)||chart.candles.length>512)throw Error('Invalid revealed chart');
  const through=BigInt(view.state.throughNs);let previous=-1;
  return chart.candles.map(bar=>{
    if(!Number.isSafeInteger(bar.time)||bar.time<=previous||BigInt(bar.time)*1000000000n>through)throw Error('Unrevealed chart time');
    previous=bar.time;
    const prices=Object.fromEntries(['open','high','low','close'].map(key=>{
      if(typeof bar[key]!=='string'||!/^\d+(?:\.\d+)?$/.test(bar[key]))throw Error('Invalid display price');
      const value=Number(bar[key]);if(!Number.isFinite(value))throw Error('Invalid display price');
      return [key,value];
    }));
    if(prices.low>Math.min(prices.open,prices.close)||prices.high<Math.max(prices.open,prices.close)||prices.low>prices.high)throw Error('Invalid candle geometry');
    return {time:bar.time,...prices};
  });
}
export function replayTarget(view,steps){
  if(![1,4,16].includes(steps))throw Error('Unsupported replay batch');
  const step=view.replayStepNs===undefined?TICK_STEP_NS:BigInt(view.replayStepNs);
  if(typeof view.replayStepNs!=="undefined"&&(typeof view.replayStepNs!=="string"||!/^[1-9][0-9]{0,10}$/.test(view.replayStepNs)||step>60000000000n))throw Error('Invalid replay interval');
  const target=BigInt(view.state.throughNs)+BigInt(steps)*step;
  if(target>MAX_NS)throw Error('Replay target is outside the supported timestamp range');
  return String(target);
}
export function nextReplayTarget(view,steps,pending=null){
  const through=BigInt(view.state.throughNs);
  if(pending!==null){
    if(typeof pending!=='string'||!/^[0-9]{1,23}$/.test(pending)||BigInt(pending)>MAX_NS)throw Error('Invalid pending replay target');
    if(BigInt(pending)>through)return pending;
  }
  return replayTarget(view,steps);
}
export function seekTarget(value){
  if(!/^\d{4}-\d\d-\d\dT\d\d:\d\d(?::\d\d)?$/.test(value))throw Error('Enter a UTC date and time');
  const milliseconds=Date.parse(value+'Z');
  if(!Number.isSafeInteger(milliseconds)||milliseconds<0)throw Error('Enter a valid UTC date and time');
  const canonical=new Date(milliseconds).toISOString().slice(0,19);
  if(canonical!==(value.length===16?value+':00':value))throw Error('Enter a valid UTC date and time');
  return String(BigInt(milliseconds)*1000000n);
}

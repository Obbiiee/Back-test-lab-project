// Geometry is a proposed intent, never a reviewed command, fill or account value.
function gridIntent(value,tickSize){
  if(tickSize===undefined)return String(value);
  const price=String(value);
  if(!/^\d+(\.\d+)?$/.test(price)||!/^\d+(\.\d+)?$/.test(tickSize))throw Error('Enter planning levels manually for this price format.');
  const digits=Math.max(price.split('.')[1]?.length??0,tickSize.split('.')[1]?.length??0);
  const scaled=s=>BigInt(s.replace('.',''))*10n**BigInt(digits-(s.split('.')[1]?.length??0));
  const step=scaled(tickSize);if(step<=0n)throw Error('Planning needs the Session price grid.');
  const input=scaled(price),valueOnGrid=((input*2n+step)/(2n*step))*step;
  const scale=10n**BigInt(digits),fraction=String(valueOnGrid%scale).padStart(digits,'0').replace(/0+$/,'');
  return String(valueOnGrid/scale)+(fraction?'.'+fraction:'');
}
export function planningIntent(drawing,{protocol=false,tickSize}={}){
  // The fourth canonical anchor controls rectangle width, not an order price.
  if(!drawing||!['long-position','short-position'].includes(drawing.type)||![3,4].includes(drawing.points?.length))throw Error('Select a Long or Short planning drawing.');
  const [entry,sl,tp]=drawing.points.map(p=>p.price),long=drawing.type==='long-position';
  if(![entry,sl,tp].every(p=>Number.isFinite(p)&&p>0)||(long?!(sl<entry&&entry<tp):!(tp<entry&&entry<sl)))throw Error('Planning levels need a valid entry, stop and target.');
  // Do not reuse donor/simulator quantity, R/R or floating-point PnL estimates.
  const values=[entry,sl,tp].map(p=>gridIntent(p,tickSize));
  const rounded=values.map(Number);
  if(rounded.some(p=>p<=0)||(long?!(rounded[1]<rounded[0]&&rounded[0]<rounded[2]):!(rounded[2]<rounded[0]&&rounded[0]<rounded[1])))throw Error('Planning levels collapse on the Session price grid; move the stop or target.');
  return {side:long?'LONG':'SHORT',workflow:'PLANNED',orderType:'LIMIT',entry:values[0],sl:values[1],...(protocol?{}:{tp:values[2]})};
}

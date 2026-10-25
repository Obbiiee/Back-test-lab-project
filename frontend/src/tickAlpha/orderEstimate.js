// Display-only planning estimates for the order ticket. Exact decimal (BigInt) arithmetic,
// mirroring the server's risk_quantity rule so the preview matches the review; the server
// review remains the only authority for quantity, risk basis and every financial value.
const DECIMAL=/^\d+(\.\d+)?$/;
function parse(text){
  if(typeof text!=='string'||!DECIMAL.test(text.trim()))return null;
  const [whole,fraction='']=text.trim().split('.');
  return {n:BigInt(whole+fraction),d:10n**BigInt(fraction.length)};
}
const gcd=(a,b)=>{a=a<0n?-a:a;b=b<0n?-b:b;while(b){[a,b]=[b,a%b];}return a||1n;};
const norm=({n,d})=>{if(d<0n){n=-n;d=-d;}const g=gcd(n,d);return {n:n/g,d:d/g};};
const sub=(a,b)=>norm({n:a.n*b.d-b.n*a.d,d:a.d*b.d});
const add=(a,b)=>norm({n:a.n*b.d+b.n*a.d,d:a.d*b.d});
const mul=(a,b)=>norm({n:a.n*b.n,d:a.d*b.d});
const div=(a,b)=>norm({n:a.n*b.d,d:a.d*b.n});
const abs=a=>({n:a.n<0n?-a.n:a.n,d:a.d});
const sign=a=>a.n===0n?0:(a.n>0n?1:-1);
const floorDiv=(a,b)=>{const q=div(a,b);let f=q.n/q.d;if(q.n<0n&&f*q.d!==q.n)f-=1n;return f;};
function format(a,places){
  const neg=a.n<0n,scale=10n**BigInt(places),v=(neg?-a.n:a.n)*scale;
  let r=v/a.d;if((v%a.d)*2n>=a.d)r+=1n;
  const whole=r/scale,fraction=places?'.'+String(r%scale).padStart(places,'0'):'';
  return (neg&&r!==0n?'-':'')+String(whole)+fraction;
}
const placesOf=text=>(text.split('.')[1]||'').length;

export function decimalText(value,places=2){const v=parse(String(value));return v?format(v,places):null;}

// Proposed order type only. Exact quote comparison; the server still reviews it.
export function orderTypeForEntry({side,entry,quote}){
  if(!['LONG','SHORT'].includes(side))return null;
  const e=parse(entry),q=parse(side==='LONG'?quote?.ask:quote?.bid);
  if(!e||!q||sign(e)<=0||sign(q)<=0)return null;
  const compared=sign(sub(e,q));
  return compared===0?'MARKET':(side==='LONG'?compared<0:compared>0)?'LIMIT':'STOP';
}

// Price on the Session tick grid that sits rr × stop-distance away from entry.
export function targetForRR({side,entry,sl,rr,tickSize}){
  const e=parse(entry),s=parse(sl),r=parse(rr),t=parse(tickSize);
  if(!e||!s||!r||!t||sign(t)<=0||sign(r)<=0)return null;
  const distance=abs(sub(e,s));if(sign(distance)===0)return null;
  if(side==='LONG'?!(sign(sub(e,s))>0):!(sign(sub(s,e))>0))return null;
  const move=mul(distance,r),raw=side==='LONG'?add(e,move):sub(e,move);
  const ticks=div(raw,t),rounded=(ticks.n*2n+ticks.d)/(2n*ticks.d);
  const price=mul({n:rounded,d:1n},t);
  return sign(price)>0?format(price,placesOf(tickSize)):null;
}

// Preview for a Planned Free Style order: risk money, implied lots (floored to the lot step,
// as the server does), reward money at TP and R:R. Returns null fields when inputs are invalid.
export function plannedEstimate({side,entry,sl,tp,riskPercent,balance,profile}){
  const e=parse(entry),s=parse(sl),t=tp?parse(tp):null,risk=parse(riskPercent),bal=parse(balance);
  const contract=parse(profile?.contractSize),step=parse(profile?.lotStep),tick=parse(profile?.tickSize);
  const commission=parse(profile?.commissionPerLotSide??'0')||{n:0n,d:1n};
  const out={valid:false,riskMoney:null,rewardMoney:null,rr:null,lots:null,stopTicks:null,targetTicks:null,reason:null};
  if(profile?.quoteCurrency&&profile.quoteCurrency!=='USD'){out.reason='Conversion preview unavailable; use the server review for exact USD risk and lots.';return out;}
  if(!e||!s||!risk||!bal||!contract||!step||!tick){out.reason='Enter entry, stop and risk %.';return out;}
  const stopMove=side==='LONG'?sub(e,s):sub(s,e);
  if(sign(stopMove)<=0){out.reason=side==='LONG'?'Stop must be below entry for a Buy.':'Stop must be above entry for a Sell.';return out;}
  out.stopTicks=format(div(stopMove,tick),0);
  const budget=div(mul(bal,risk),{n:100n,d:1n});
  const perLot=add(mul(stopMove,contract),mul({n:2n,d:1n},commission));
  const steps=floorDiv(div(budget,perLot),step);
  const lots=mul({n:steps,d:1n},step);
  out.lots=format(lots,placesOf(profile.lotStep));
  out.riskMoney=format(mul(lots,perLot),2);
  if(steps<=0n){out.reason='Risk budget is smaller than one lot step at this stop distance.';return out;}
  if(t){
    const targetMove=side==='LONG'?sub(t,e):sub(e,t);
    if(sign(targetMove)<=0){out.reason=side==='LONG'?'Target must be above entry for a Buy.':'Target must be below entry for a Sell.';return out;}
    out.targetTicks=format(div(targetMove,tick),0);
    out.rewardMoney=format(sub(mul(lots,mul(targetMove,contract)),mul(lots,mul({n:2n,d:1n},commission))),2);
    out.rr=format(div(targetMove,stopMove),2);
  }
  out.valid=true;return out;
}

// S-3 evaluates calculators separately from hosts; never installs a donor.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import {resolve,join} from 'node:path';
import {pathToFileURL} from 'node:url';
import {gzipSync} from 'node:zlib';
import {sma,ema,bollinger} from '../src/indicators/overlayCalculations.js';
import {rsi,macd,atr,stochastic} from '../src/indicators/paneCalculations.js';
const bars=closes=>closes.map((close,i)=>({time:100+i*60,open:close,high:close+1,low:close-1,close}));
const clean=value=>Array.isArray(value)?value.map(({time,value})=>({time,value})):Object.fromEntries(Object.entries(value).map(([k,v])=>[k,clean(v)]));
const btl={SMA:b=>sma(b,{period:2}),EMA:b=>ema(b,{period:2}),BB:b=>bollinger(b,{period:2,multiplier:2}),RSI:b=>rsi(b,{period:2}),MACD:b=>macd(b,{fastPeriod:2,slowPeriod:3,signalPeriod:2}),ATR:b=>atr(b,{period:2}),STOCH:b=>stochastic(b,{kPeriod:2,dPeriod:2})};
const near=(actual,expected)=>{
  if(typeof expected==='number'){assert.ok(Number.isFinite(actual)&&Math.abs(actual-expected)<=1e-9,`${actual} != ${expected}`);return;}
  assert.deepEqual(Object.keys(actual),Object.keys(expected));
  for(const k of Object.keys(expected))near(actual[k],expected[k]);
};
const points=(values,first=1)=>values.map((value,i)=>({time:100+(first+i)*60,value}));
// Materialized hand-computed goldens, not another calculator as the oracle.
near(clean(btl.SMA(bars([1,2,3,10,4]))),points([1.5,2.5,6.5,7]));
near(clean(btl.EMA(bars([1,2,3,10,4]))),points([1.5,2.5,7.5,31/6]));
near(clean(btl.BB(bars([1,3,3]))),{basis:points([2,3]),upper:points([4,3]),lower:points([0,3])});
near(clean(btl.RSI(bars([1,2,3,2,2,5]))),points([100,50,50,650/7],2));
near(clean(btl.MACD(bars([1,2,3,10,4]))),{macd:points([.5,1.5,1/6],2),signal:points([1,4/9],3),histogram:points([.5,-5/18],3)});
const ranges=[{high:10,low:8,close:9},{high:13,low:11,close:12},{high:12,low:9,close:10},{high:15,low:14,close:14.5}].map((b,i)=>({...b,time:100+i*60,open:b.close}));
near(clean(btl.ATR(ranges)),points([3,3,4]));
near(clean(btl.STOCH(bars([1,2,3,2,2,5]))),{k:points([200/3,200/3,100/3,50,80]),d:points([200/3,50,125/3,65],2)});
const flat=bars([2,2,2,2,2]).map(b=>({...b,high:2,low:2}));
near(clean(btl.RSI(flat)),points([50,50,50],2));
near(clean(btl.STOCH(flat)),{k:points([50,50,50,50]),d:points([50,50,50],2)});
const trend=bars(Array.from({length:60},(_,i)=>20+Math.sin(i)*4+i/10));
const cases=[[],bars([1]),bars([1,2]),bars([1,2,3,10,4]),ranges,flat,trend,trend.filter((_,i)=>i%5===0)];
function causality(calculators){
  for(const [type,fn] of Object.entries(calculators))for(const source of cases){
    const input=structuredClone(source), before=JSON.stringify(input), full=clean(fn(input));
    assert.equal(JSON.stringify(input),before,'immutable '+type);
    for(let n=0;n<=input.length;n++){
      const prefix=clean(fn(input.slice(0,n)));
      const clip=value=>Array.isArray(value)?value.filter(p=>n&&p.time<=input[n-1].time):Object.fromEntries(Object.entries(value).map(([k,v])=>[k,clip(v)]));
      near(prefix,clip(full));
      const mutated=input.map((b,i)=>i<n?b:{...b,close:1e9,high:1e10,low:-1e9});
      near(clean(fn(mutated.slice(0,n))),prefix);
    }
  }
}
causality(btl);
console.log('PASS S-3 seven BTL authored goldens, empty/warmup/flat/replay/timeframe and mutated-future prefix vectors.');
if(process.env.BTL_SPIKE_DONOR_ROOT){
  const {rolldown}=await import('rolldown'),root=process.env.BTL_SPIKE_DONOR_ROOT;
  const pins={'openalgo-charts':'8b4cffe41a8e8fda96c286d608625dac1ec36e53',OpenCharts:'785d1f18cc1ca67b0246031b2b9a08cb5cb60264'};
  mkdirSync(resolve('tests/artifacts'),{recursive:true});
  for(const [name,pin] of Object.entries(pins)){
    assert.equal(execFileSync('git',['-C',join(root,name),'rev-parse','HEAD'],{encoding:'utf8'}).trim(),pin);
    assert.equal(execFileSync('git',['-C',join(root,name),'status','--porcelain'],{encoding:'utf8'}).trim(),'');
  }
  async function bundle(name,code,alias={}){
    const input=resolve('tests/artifacts/stitch-indicator-'+name+'-entry.mjs');writeFileSync(input,code);
    const b=await rolldown({input,resolve:{alias}});
    try{
      const output=await b.write({file:resolve('tests/artifacts/stitch-indicator-'+name+'.mjs'),format:'esm',minify:true});
      const c=output.output.find(x=>x.type==='chunk');
      return {minifiedBytes:Buffer.byteLength(c.code),gzipBytes:gzipSync(c.code).length,modules:Object.keys(c.modules).length};
    }finally{await b.close();}
  }
  const url=p=>pathToFileURL(p).href;
  // Absolute paths are generated only in ignored artifacts, never in shipped code.
  const path=p=>JSON.stringify(p.replaceAll('\\','/'));
  const metrics={BTL:await bundle('BTL',`export * from '../../src/indicators/overlayCalculations.js';export * from '../../src/indicators/paneCalculations.js';`)};
  metrics.OpenAlgo=await bundle('OpenAlgo',`export {SMA,EMA,BOLLINGER} from ${path(join(root,'openalgo-charts/src/indicators/trend.ts'))};export {RSI,MACD,ATR,STOCHASTIC} from ${path(join(root,'openalgo-charts/src/indicators/momentum.ts'))};`,{'openalgo-charts':join(root,'openalgo-charts/src/index.ts')});
  metrics.OpenCharts=await bundle('OpenCharts',`export * from ${path(join(root,'OpenCharts/src/lib/indicators.ts'))};`);
  const a=await import(url(resolve('tests/artifacts/stitch-indicator-OpenAlgo.mjs'))),o=await import(url(resolve('tests/artifacts/stitch-indicator-OpenCharts.mjs')));
  const arrayPoints=(v,b)=>v.flatMap((value,i)=>Number.isFinite(value)?[{time:b[i].time,value}]:[]);
  const descriptor=(d,s,key)=>b=>{const result=d.calc(b,s);return key?arrayPoints(result[key],b):Object.fromEntries(Object.entries(result).filter(([k])=>!['upperLevel','lowerLevel'].includes(k)).map(([k,v])=>[k,arrayPoints(v,b)]));};
  const algo={SMA:descriptor(a.SMA,{length:2,source:'close'},'ma'),EMA:descriptor(a.EMA,{length:2,source:'close'},'ma'),BB:descriptor(a.BOLLINGER,{length:2,stdDev:2,source:'close'}),RSI:descriptor(a.RSI,{length:2,source:'close'},'rsi'),MACD:descriptor(a.MACD,{fastPeriod:2,slowPeriod:3,signalPeriod:2,source:'close'}),ATR:descriptor(a.ATR,{period:2},'atr'),STOCH:descriptor(a.STOCHASTIC,{kPeriod:2,kSmoothing:1,dPeriod:2})};
  const open={SMA:b=>o.sma(b,2),EMA:b=>o.ema(b,2),BB:b=>{const x=o.bollingerBands(b,2,2);return {basis:x.middle,upper:x.upper,lower:x.lower};},RSI:b=>o.rsi(b,2),MACD:b=>o.macd(b,2,3,2),ATR:b=>o.atr(b,2),STOCH:b=>o.stochastic(b,2,2)};
  // Key order is representation-only, not a semantic discrepancy.
  const canonical=v=>Array.isArray(v)?clean(v):Object.fromEntries(Object.keys(v).sort().map(k=>[k,clean(v[k])]));
  const report={metrics,pins,comparisons:{}};
  for(const [name,calc] of [['OpenAlgo',algo],['OpenCharts',open]]){
    causality(calc);const mismatches={};
    for(const type of Object.keys(btl)){
      const failures=[];cases.forEach((c,i)=>{try{near(canonical(calc[type](c)),canonical(btl[type](c)));}catch{failures.push(i);}});
      mismatches[type]=failures;
    }
    report.comparisons[name]={causality:true,mismatches,flatRSI:calc.RSI(flat),flatStochastic:calc.STOCH(flat),atrRange:calc.ATR(ranges)};
  }
  assert.deepEqual(Object.entries(report.comparisons.OpenAlgo.mismatches).filter(([,v])=>v.length).map(([k])=>k),['RSI','STOCH']);
  assert.deepEqual(Object.entries(report.comparisons.OpenCharts.mismatches).filter(([,v])=>v.length).map(([k])=>k),['RSI','ATR']);
  // Actual BTL host and native OpenCharts React host on installed LC5.
  await bundle('host',`export {IndicatorEngine} from '../../src/indicators/IndicatorEngine.js';export {productionRegistry} from '../../src/indicators/productionRegistry.js';export {createElement,Component} from 'react';export {createRoot} from 'react-dom/client';export {useIndicators} from ${path(join(root,'OpenCharts/src/pages/trading/useIndicators.ts'))};`,{react:resolve('node_modules/react'),'react-dom/client':resolve('node_modules/react-dom/client.js'),'lightweight-charts':resolve('tests/browser/stitch-lc-global.mjs')});
  writeFileSync(resolve('tests/artifacts/stitch-indicator-report.json'),JSON.stringify(report,null,2));
  console.log(JSON.stringify(report));
  console.log('PASS pinned descriptor comparison: semantic gaps explicitly reproduced; calculators remain separate from host compatibility.');
}

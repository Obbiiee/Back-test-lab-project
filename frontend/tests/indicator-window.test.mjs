// Rendered-series window (PR #36 memory gate): the chart receives a bounded slice of
// each long indicator series; values are identical to the full series, nothing
// beyond the full series appears, short series and charts without a time scale get
// full data, and moving the view re-slices.
import assert from 'node:assert/strict';
import {IndicatorSeriesAdapter,windowSlice,WINDOW_MIN_POINTS,WINDOW_FROM_POINTS} from '../src/indicators/IndicatorSeriesAdapter.js';
import {productionRegistry as defaultIndicatorRegistry} from '../src/indicators/productionRegistry.js';
import {IndicatorEngine} from '../src/indicators/IndicatorEngine.js';

globalThis.requestAnimationFrame=callback=>{callback();return 1;};
const N=45000,T0=1733011200;
const full=Array.from({length:N},(_,i)=>({time:T0+i*60,value:i}));

// windowSlice
assert.equal(windowSlice(full,null),full);
assert.equal(windowSlice(full.slice(0,WINDOW_FROM_POINTS),{from:T0,to:T0+60}).length,WINDOW_FROM_POINTS,'series up to the threshold untouched');
const mid=windowSlice(full,{from:T0+20000*60,to:T0+30000*60});
assert.equal(mid[0].time,T0+20000*60);assert.equal(mid.at(-1).time,T0+30000*60);
assert.ok(mid.every(p=>p===full[(p.time-T0)/60]),'same point objects, same values');
const narrow=windowSlice(full,{from:T0+100*60,to:T0+110*60});
assert.equal(narrow.length,WINDOW_MIN_POINTS,'widened to the minimum');assert.equal(narrow[0].time,T0,'clamped at the start');
const tail=windowSlice(full,{from:T0+(N-5)*60,to:T0+(N+500)*60});
assert.equal(tail.at(-1),full.at(-1),'never past the last point');assert.equal(tail.length,WINDOW_MIN_POINTS);
assert.equal(windowSlice([{time:'2024-01-01',value:1},...full].slice(0,N),{from:0,to:1}).length,N,'non-numeric time is not windowed');

// Adapter against a fake chart with a time scale.
const fakeChart=()=>{
  let range=null,listener=null;const series=[];
  return {series,setRange(r){range=r;listener?.();},
    timeScale:()=>({getVisibleRange:()=>range,subscribeVisibleTimeRangeChange(l){listener=l;},unsubscribeVisibleTimeRangeChange(){listener=null;}}),
    applyOptions(){},addPane(){return {paneIndex:()=>1,setStretchFactor(){},getStretchFactor:()=>0.35};},
    addSeries(type,options){const s={options,points:[],applyOptions(){},setData(p){this.points=p;},createPriceLine:()=>({applyOptions(){}}),removePriceLine(){}};series.push(s);return s;},
    removeSeries(){},removePane(){}};
};
const chart=fakeChart();
const engine=new IndicatorEngine(defaultIndicatorRegistry,new IndicatorSeriesAdapter());
engine.attach(chart);
const candles=Array.from({length:N},(_,i)=>{const c=2600+Math.sin(i/50)*10;return {time:T0+i*60,open:c,high:c+1,low:c-1,close:c};});
engine.setCandles(candles);
const sma=engine.create({id:'w-sma',type:'SMA',parameters:{},visible:true});
const output=engine.output(sma.id);
const line=chart.series.at(-1);
assert.equal(line.points.length,WINDOW_MIN_POINTS,'no visible range yet: latest points only');
assert.equal(line.points.at(-1),output.at(-1));
chart.setRange({from:T0+10000*60,to:T0+10500*60});
assert.equal(line.points.length,WINDOW_MIN_POINTS,'500 visible bars ± one span, widened to the minimum');
const first=line.points[0].time,last=line.points.at(-1).time;
assert.ok(first<=T0+10000*60&&last>=T0+10500*60,'visible range covered');
const byTime=new Map(output.map(p=>[p.time,p]));
assert.ok(line.points.every(p=>byTime.get(p.time)===p),'rendered values equal the full calculation');
chart.setRange({from:T0+40000*60,to:T0+44000*60});
assert.ok(line.points[0].time<=T0+40000*60&&line.points.at(-1).time>=T0+44000*60,'re-sliced after the view moved');
assert.ok(line.points.length<=9001&&line.points.length>=8000,'4000 visible bars + one span to the left, clipped at the last bar: '+line.points.length);
// Charts without a time scale (and short series) receive everything.
const plain={...fakeChart(),timeScale:undefined};
const e2=new IndicatorEngine(defaultIndicatorRegistry,new IndicatorSeriesAdapter());e2.attach(plain);e2.setCandles(candles);e2.create({id:'p',type:'SMA',parameters:{},visible:true});
assert.equal(plain.series.at(-1).points.length,e2.output('p').length);
console.log('indicator window: ok');

// S-1 authored parity vectors. This test never installs or migrates a donor.
import assert from 'node:assert/strict';
import {DrawingManager} from '../src/drawings/DrawingManager.js';
import {DrawingHistory} from '../src/drawings/DrawingHistory.js';
import {DrawingPersistence} from '../src/drawings/DrawingPersistence.js';
import {DrawingInteractionController} from '../src/drawings/interaction/DrawingInteractionController.js';
import {HIT} from '../src/drawings/interaction/hitTesting.js';
import {DRAWING_SPECS} from '../src/drawings/DrawingTypes.js';
import {performance} from 'node:perf_hooks';
import {execFileSync} from 'node:child_process';
import {readFileSync,writeFileSync,readdirSync} from 'node:fs';
import {resolve,join} from 'node:path';
import {pathToFileURL} from 'node:url';
import {gzipSync} from 'node:zlib';
import {createHash} from 'node:crypto';

const records=new Map(), storage={getItem:k=>records.get(k)??null,setItem:(k,v)=>records.set(k,v)};
const manager=new DrawingManager(), history=new DrawingHistory(manager);
const persistence=new DrawingPersistence(storage,'stitch-authored');
history.reset(persistence.load(manager.registry));
manager.subscribeCommitted((before,after)=>persistence.save(after));
// Irregular spacing and off-grid, fractional timestamps forbid bar-index storage.
const bars=[{time:100},{time:200},{time:500}]; manager.setTimePoints(bars);
const chart={timeScale:()=>({timeToCoordinate:t=>({100:10,200:30,500:50})[t]??null})};
const series={coordinateToPrice:y=>100-y,priceToCoordinate:p=>100-p};
const interactions=new DrawingInteractionController(manager,chart,series,history);
const samples=[];
// Preserve the original eight-candidate comparison; supplemental Ray gates
// live in phase9 and the separate pinned Alpha fixture.
const originalSpecs=Object.fromEntries(Object.entries(DRAWING_SPECS).filter(([type])=>type!=='ray'));
for(const [type,spec] of Object.entries(originalSpecs)){
  const points=[{time:150.25,price:80.125},{time:350.75,price:60.875}].slice(0,spec.points);
  const input={id:type,type,points,...(type==='text'?{text:'Authored Ω'}:{})};
  const start=performance.now(); manager.add(input);
  points[0].price=9999; assert.equal(manager.get(type).points[0].price,80.125);
  manager.select(type); assert.equal(manager.selectedId,type);
  const initial=JSON.stringify(manager.get(type));
  manager.setProperties(type,{locked:true});
  assert.equal(interactions.begin({id:type,type:HIT.BODY},{x:30,y:30}),false);
  manager.setProperties(type,{locked:false,visible:false}); assert.equal(manager.selectedId,null);
  manager.setProperties(type,{visible:true}); manager.select(type);
  const before=manager.get(type).points;
  assert.equal(interactions.begin({id:type,type:HIT.BODY},{x:30,y:30}),true);
  interactions.move({x:32,y:28}); interactions.finish();
  assert.notDeepEqual(manager.get(type).points,before);
  assert.ok(history.undo()); assert.deepEqual(manager.get(type).points,before);
  assert.ok(history.redo());
  manager.remove(type); assert.equal(manager.get(type),undefined);
  assert.ok(history.undo()); assert.ok(manager.get(type));
  history.undo(); // reverse redo drag
  assert.equal(JSON.stringify(manager.get(type)),initial);
  samples.push(performance.now()-start);
}
const snapshot=JSON.stringify(manager.getAll());
for(const prefix of [[],bars.slice(0,1),bars,bars.filter((b,i)=>i%2===0)]){
  manager.setTimePoints(prefix); assert.equal(JSON.stringify(manager.getAll()),snapshot);
}
const restored=new DrawingManager(); restored.replaceAll(new DrawingPersistence(storage,'stitch-authored').load(restored.registry));
assert.equal(JSON.stringify(restored.getAll()),snapshot);
// A future schema remains byte-identical and read-only; no optimistic migration.
const future=JSON.stringify({version:42,workspace:'stitch-authored',drawings:[]});records.set(persistence.key,future);
assert.deepEqual(persistence.load(manager.registry),[]);assert.equal(persistence.save(manager.getAll()),false);
assert.equal(records.get(persistence.key),future);
samples.sort((a,b)=>a-b);
console.log(JSON.stringify({candidate:'BTL',eightTypes:Object.keys(originalSpecs),lifecycle:true,canonicalReload:true,irregularTime:true,replayTimeframeAnchorStability:true,unsupportedSchemaPreserved:true,fixtureLifecycleMedianMs:samples[4],fixtureLifecycleMaxMs:samples.at(-1),productionSemanticRewrites:0,newRuntimeDependencies:0}));
console.log('PASS S-1 BTL authored lifecycle, canonical preservation and rollback vectors; browser evidence is a separate gate.');

// Optional repeatable donor evaluation. Exact source is supplied locally; no
// network acquisition, automatic upgrades or package installs occur here.
if(process.env.BTL_SPIKE_DONOR_ROOT){
  const {rolldown}=await import('rolldown');
  const donorRoot=process.env.BTL_SPIKE_DONOR_ROOT;
  const pins={'openalgo-charts':'8b4cffe41a8e8fda96c286d608625dac1ec36e53',OpenCharts:'785d1f18cc1ca67b0246031b2b9a08cb5cb60264'};
  const metrics={};
  const entries={BTL:resolve('src/drawings/useDrawingTools.js'),'openalgo-charts':join(donorRoot,'openalgo-charts/src/draw/index.ts'),OpenCharts:join(donorRoot,'OpenCharts/src/lib/chart-plugins/drawing-tools/manager.ts')};
  for(const [name,input] of Object.entries(entries)){
    if(pins[name]){
      assert.equal(execFileSync('git',['-C',join(donorRoot,name),'rev-parse','HEAD'],{encoding:'utf8'}).trim(),pins[name]);
      assert.equal(execFileSync('git',['-C',join(donorRoot,name),'status','--porcelain'],{encoding:'utf8'}).trim(),'');
    }
    const b=await rolldown({input,external:['react'],resolve:{alias:name==='openalgo-charts'?{'openalgo-charts':join(donorRoot,name,'src/index.ts')}:{}}});
    try{
      const result=await b.write({file:resolve('tests/artifacts/stitch-'+name+'.mjs'),format:'esm',minify:true});
      const chunk=result.output.find(x=>x.type==='chunk');
      metrics[name]={pin:pins[name]??'repository baseline',modules:Object.keys(chunk.modules).length,minifiedBytes:Buffer.byteLength(chunk.code),gzipBytes:gzipSync(chunk.code).length,sourceNonblankLines:Object.keys(chunk.modules).reduce((sum,p)=>sum+readFileSync(p,'utf8').split(/\r?\n/).filter(x=>x.trim()).length,0)};
      if(pins[name])metrics[name].licenseSha256=createHash('sha256').update(readFileSync(join(donorRoot,name,'LICENSE'))).digest('hex');
    }finally{await b.close();}
  }
  // Model/lifecycle check with identical authored anchors, external save/load.
  const algo=await import(pathToFileURL(resolve('tests/artifacts/stitch-openalgo-charts.mjs')));
  const host=()=>{const listeners=new Map();return {on(e,f){const fs=listeners.get(e)??[];fs.push(f);listeners.set(e,fs);return()=>{};},emit(e,p){for(const f of listeners.get(e)??[])f(p);},addPrimitive(){},removePrimitive(){},dataLayer:{},getVisibleLogicalRange:()=>({from:0,to:80}),drawingState:()=>null,setDrawingState(){}};};
  const a=new algo.DrawingController(host(),{magnet:false,inputAnchors:false});
  const mapping={'fibonacci-retracement':'fib-retracement'};
  const times=[];
  for(const [type,spec] of Object.entries(originalSpecs)){
    const points=[{time:150.25,price:80.125},{time:350.75,price:60.875}].slice(0,spec.points);
    const start=performance.now();
    a.add({id:type,tool:mapping[type]??type,points:structuredClone(points),paneIndex:0,createdAt:1,...(type==='text'?{text:{value:'Authored Ω'}}:{})});
    a.select(type);assert.equal(a.selected(),type);a.update(type,{locked:true,visible:false});assert.equal(a.get(type).locked,true);assert.equal(a.get(type).visible,false);assert.ok(a.undo());assert.ok(a.redo());a.update(type,{locked:false,visible:true});
    a.remove(type);assert.ok(a.undo());assert.deepEqual(a.get(type).points,points);
    times.push(performance.now()-start);
  }
  const restoredAlgo=new algo.DrawingController(host(),{magnet:false,inputAnchors:false});restoredAlgo.fromJSON(JSON.parse(JSON.stringify(a.toJSON())));
  for(const [type] of Object.entries(originalSpecs))assert.deepEqual(restoredAlgo.get(type).points,a.get(type).points);
  assert.equal(restoredAlgo.get('text').text.value,'Authored Ω');
  times.sort((a,b)=>a-b);metrics['openalgo-charts'].fixtureLifecycleMedianMs=times[4];metrics['openalgo-charts'].fixtureLifecycleMaxMs=times.at(-1);
  a.destroy();restoredAlgo.destroy();
  const open=await import(pathToFileURL(resolve('tests/artifacts/stitch-OpenCharts.mjs')));
  const oldWindow=globalThis.window;globalThis.window=new EventTarget();
  const container=new EventTarget();container.style={};
  const scale={timeToCoordinate:x=>x,logicalToCoordinate:x=>x,coordinateToTime:x=>x,coordinateToLogical:x=>x,getVisibleLogicalRange:()=>({from:0,to:80})};
  const chart={timeScale:()=>scale,applyOptions(){}};
  const series={priceToCoordinate:x=>x,coordinateToPrice:x=>x,subscribeDataChanged(){},unsubscribeDataChanged(){},attachPrimitive:p=>p.attached({chart,series,requestUpdate(){}}),detachPrimitive:p=>p.detached(),priceFormatter:()=>({format:String})};
  const added=[];
  try{
    const m=new open.DrawingToolsManager({chart,series,container,intervalSec:60,timeframe:'1m',callbacks:{onAdd:d=>added.push(d),onUpdate(){},onRemove(){},onToolFinished(){}}});
    const tools=['trendline','horizontal','vertical','rectangle','fibonacci','arrow','text','measure'];
    const timing=[];
    for(const tool of tools){const start=performance.now();m.setTool(tool);m.commitPlacement({time:150.25,price:80.125},{time:350.75,price:60.875});timing.push(performance.now()-start);}
    assert.equal(added.length,7,'Native Measure must remain recorded as transient, not a persisted drawing');
    assert.ok(!Object.hasOwn(added.find(d=>d.type==='horizontal'),'time'),'Native horizontal schema loses canonical anchor time');
    assert.equal(m.measureResult.id,'measure');
    timing.sort((a,b)=>a-b);metrics.OpenCharts.fixturePlacementMedianMs=timing[4];metrics.OpenCharts.fixturePlacementMaxMs=timing.at(-1);metrics.OpenCharts.nativePersistedTypes=7;metrics.OpenCharts.nativeHorizontalAnchorTime=false;
    m.destroy();
  }finally{globalThis.window=oldWindow;}
  // Count all retained drawing source, not just the tree-shaken selected entry.
  const sourceFiles=dir=>readdirSync(dir,{withFileTypes:true}).flatMap(e=>e.isDirectory()?sourceFiles(join(dir,e.name)):/\.(js|jsx)$/.test(e.name)?[join(dir,e.name)]:[]);
  metrics.BTL.retainedDrawingNonblankLines=sourceFiles(resolve('src/drawings')).reduce((sum,p)=>sum+readFileSync(p,'utf8').split(/\r?\n/).filter(x=>x.trim()).length,0);
  const fixture=readFileSync(resolve('tests/browser/stitch-drawing.html'),'utf8').replace(/\r\n/g,'\n');
  const algoStart=fixture.indexOf("}else if(candidate==='OpenAlgo'){");
  const openStart=fixture.indexOf("}else{\n  const {DrawingToolsManager}",algoStart);
  const end=fixture.indexOf("button('#tools','Cursor'",openStart);
  assert.ok(algoStart>0&&openStart>algoStart&&end>openStart);
  for(const [name,code] of [['openalgo-charts',fixture.slice(algoStart,openStart)],['OpenCharts',fixture.slice(openStart,end)]]){
    metrics[name].spikeGlueNonblankLines=code.split(/\r?\n/).filter(x=>x.trim()).length;
    metrics[name].spikeGlueBytes=Buffer.byteLength(code);
  }
  writeFileSync(resolve('tests/artifacts/stitch-drawing-metrics.json'),JSON.stringify(metrics,null,2));
  console.log(JSON.stringify(metrics));
  console.log('PASS pinned donor lifecycle evaluation; OpenCharts native persistence gaps are reproduced, not hidden.');
}

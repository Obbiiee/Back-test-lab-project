import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { DrawingManager } from '../src/drawings/DrawingManager.js';
import { DrawingHistory } from '../src/drawings/DrawingHistory.js';
import { DrawingPersistence, DRAWING_STORAGE_PREFIX } from '../src/drawings/DrawingPersistence.js';
import { DrawingInteractionController } from '../src/drawings/interaction/DrawingInteractionController.js';
import { HIT } from '../src/drawings/interaction/hitTesting.js';

const legacy = new Map([
  ['backtest-drawings-v2:valid',' [{"id":"old","type":"trendline"}] '],
  ['backtest-drawings-v2:mixed','[{"type":"long-position"},{"type":"future","extra":1}]'],
  ['backtest-drawings-v2:malformed','{broken'],
  ['backtest-drawings-v2:backup','opaque bytes'],
]);
const records=new Map(legacy); let writes=0;
const storage={getItem:key=>records.get(key)??null,setItem:(key,value)=>{assert.ok(key.startsWith(DRAWING_STORAGE_PREFIX));writes++;records.set(key,value);}};
const manager=new DrawingManager(),history=new DrawingHistory(manager,3),persistence=new DrawingPersistence(storage,'main:XAUUSD');
history.reset(persistence.load(manager.registry)); manager.subscribeCommitted((before,after)=>persistence.save(after));
const input={id:'line',type:'trend-line',points:[{time:150,price:80},{time:350,price:60}],metadata:{createdOnTimeframe:'15m'}};
const model=manager.add(input);
function invariant() {
  assert.deepEqual(JSON.parse(records.get(persistence.key)).drawings,JSON.parse(JSON.stringify(manager.getAll())));
  for (const [id,primitive] of manager.primitives) assert.equal(primitive.model,manager.get(id));
  const raw=records.get(persistence.key);
  for(const field of ['selectedId','hover','draft','clientX','clientY','logical','primitive','chart']) assert.ok(!raw.includes('"'+field+'"'));
}
invariant(); manager.select('line'); history.undo(); invariant(); assert.equal(manager.selectedId,null); assert.equal(manager.getAll().length,0);
history.redo(); invariant(); assert.deepEqual(manager.get('line'),model);
manager.remove('line'); invariant(); history.undo(); invariant(); assert.ok(manager.get('line')); history.redo(); invariant(); assert.equal(manager.get('line'),undefined); history.undo();
const chart={timeScale:()=>({timeToCoordinate:t=>({100:10,200:30,500:50})[t]??null})};
const series={coordinateToPrice:y=>100-y,priceToCoordinate:p=>100-p}; manager.setTimePoints([{time:100},{time:200},{time:500}]);
const controller=new DrawingInteractionController(manager,chart,series,history);
for (const type of [HIT.A,HIT.B,HIT.BODY]) {
  const before=manager.get('line').points, start={x:30,y:30}, count=writes, length=history.undoStack.length;
  assert.equal(controller.begin({id:'line',type},start),true);
  for(let i=1;i<=20;i++) controller.move({x:30+i*.1,y:30-i*.1});
  assert.equal(writes,count,'No pointermove storage writes'); assert.equal(history.undoStack.length,length,'No pointermove history');
  controller.finish(); invariant(); const after=manager.get('line').points;
  assert.notDeepEqual(after,before); assert.equal(writes,count+1,'One drag save');
  if(type===HIT.A) assert.deepEqual(after[1],before[1]);
  if(type===HIT.B) assert.deepEqual(after[0],before[0]);
  if(type===HIT.BODY) {assert.equal(after[1].time-after[0].time,before[1].time-before[0].time);assert.equal(after[1].price-after[0].price,before[1].price-before[0].price);}
  history.undo(); invariant(); assert.deepEqual(manager.get('line').points,before); history.redo(); invariant(); assert.deepEqual(manager.get('line').points,after);
}
for(const cancelled of [true,false]) {
  const before=manager.get('line').points,count=writes,length=history.undoStack.length;
  controller.begin({id:'line',type:HIT.A},{x:30,y:30});
  controller.move(cancelled?{x:35,y:35}:{x:30,y:30}); controller.finish(cancelled);
  assert.deepEqual(manager.get('line').points,before); assert.equal(writes,count); assert.equal(history.undoStack.length,length); invariant();
}
history.undo(); assert.equal(history.canRedo,true); manager.setProperties('line',{locked:true}); invariant(); assert.equal(history.canRedo,false);
assert.equal(controller.begin({id:'line',type:HIT.A},{x:30,y:30}),false);
const lockedPoints=manager.get('line').points; manager.update('line',[{time:9,price:9},{time:10,price:10}]); assert.deepEqual(manager.get('line').points,lockedPoints);
history.undo(); assert.equal(manager.get('line').locked,false); history.redo(); assert.equal(manager.get('line').locked,true);
manager.select('line'); manager.setProperties('line',{visible:false}); invariant(); assert.equal(manager.selectedId,null);
assert.equal(controller.hit({x:30,y:30}).type,HIT.NONE);
manager.primitives.get('line').attached({chart,series,requestUpdate(){}});
assert.equal(manager.primitives.get('line').paneViews()[0].projected.filter(Boolean).length,2,'Hidden render test has valid projection');
let rendered=false; manager.primitives.get('line').paneViews()[0].renderer().draw({useMediaCoordinateSpace:()=>{rendered=true;}}); assert.equal(rendered,false);
history.undo(); assert.equal(manager.get('line').visible,true); history.redo(); assert.equal(manager.get('line').visible,false);
const restored=new DrawingManager(),restoredHistory=new DrawingHistory(restored),reloaded=new DrawingPersistence(storage,'main:XAUUSD');
restoredHistory.reset(reloaded.load(restored.registry)); assert.deepEqual(restored.getAll(),manager.getAll()); assert.equal(restoredHistory.canUndo,false,'History reset on reload');
assert.equal(restored.get('line').locked,true); assert.equal(restored.get('line').visible,false);
manager.setProperties('line',{visible:true}); invariant(); assert.equal(manager.get('line').visible,true);
const exact=JSON.stringify(manager.getAll()), rawBefore=records.get(persistence.key), writeBefore=writes;
manager.setTimePoints([{time:100},{time:500}]); manager.setTimePoints([{time:100},{time:200},{time:500}]); manager.setTimePoints([{time:100},{time:200},{time:500},{time:600}]);
assert.equal(JSON.stringify(manager.getAll()),exact); assert.equal(records.get(persistence.key),rawBefore); assert.equal(writes,writeBefore);
for(let i=0;i<10;i++) manager.setProperties('line',{locked:i%2===0}); assert.equal(history.undoStack.length,3);
for(const [key,value] of legacy) assert.equal(records.get(key),value,'Legacy raw bytes unchanged');
const valid=JSON.parse(JSON.stringify(model)), envelope=drawings=>JSON.stringify({version:1,workspace:'main:XAUUSD',drawings});
for(const raw of ['', '{bad','null',JSON.stringify({version:2,workspace:'main:XAUUSD',drawings:[valid]}),JSON.stringify({version:1,workspace:'other',drawings:[valid]})]) {
  records.set(persistence.key,raw); const p=new DrawingPersistence(storage,'main:XAUUSD'); assert.deepEqual(p.load(manager.registry),[]); assert.equal(p.writable,false); assert.equal(p.save([valid]),false); assert.equal(records.get(persistence.key),raw);
}
for(const invalid of [{...valid,type:'future'}, {...valid,points:[valid.points[0]]}, {...valid,futureField:true}, {...valid,points:[{time:NaN,price:1},valid.points[1]]}]) {
  const raw=envelope([valid,invalid]); records.set(persistence.key,raw); const p=new DrawingPersistence(storage,'main:XAUUSD'); assert.equal(p.load(manager.registry).length,1); assert.equal(p.writable,false); p.save([]); assert.equal(records.get(persistence.key),raw);
}
records.set(persistence.key,envelope([valid,valid])); assert.equal(new DrawingPersistence(storage,'main:XAUUSD').load(manager.registry).length,1);
records.set(persistence.key,envelope([])); const empty=new DrawingPersistence(storage,'main:XAUUSD'); assert.deepEqual(empty.load(manager.registry),[]); assert.equal(empty.writable,true);
const unavailable=new DrawingPersistence(()=>{throw Error('denied');},'main:XAUUSD'); assert.deepEqual(unavailable.load(manager.registry),[]); assert.equal(unavailable.save([]),false);
const quota=new DrawingPersistence({getItem:()=>null,setItem:()=>{throw Error('quota');}},'main:XAUUSD');quota.load(manager.registry);assert.equal(quota.save([valid]),false);assert.ok(quota.status);
const clean=new DrawingPersistence(storage,'clean');clean.load(manager.registry);clean.save([{...valid,selectedId:'bad',clientX:123}]);assert.ok(!records.get(clean.key).includes('selectedId'));assert.ok(!records.get(clean.key).includes('clientX'));
assert.throws(()=>manager.add({...input,id:'risk',type:'long-position'}));
for(const name of ['DrawingManager.js','DrawingHistory.js']) assert.ok(!/localStorage|from ['"][^'"]*(trading|react)/.test(readFileSync(new URL('../src/drawings/'+name,import.meta.url),'utf8')));
const keyboardManager=new DrawingManager(),keyboardHistory=new DrawingHistory(keyboardManager);
keyboardManager.add(input); const keys=new Map(),events=new Map();
globalThis.window={addEventListener:(name,fn)=>keys.set(name,fn),removeEventListener:name=>keys.delete(name)};
const root={addEventListener:(name,fn)=>events.set(name,fn),removeEventListener:name=>events.delete(name),hasPointerCapture:()=>false};
const element={parentElement:root,style:{},contains:target=>target.tagName==='DIV',getBoundingClientRect:()=>({left:0,top:0}),focus(){}};
const keyboardChart={...chart,options:()=>({handleScroll:{pressedMouseMove:true}}),applyOptions(){},paneSize:()=>({height:100})};
keyboardChart.timeScale().width=()=>100;
const keyboardController=new DrawingInteractionController(keyboardManager,keyboardChart,series,keyboardHistory);
const unbind=keyboardController.bind(element);
const key=(name,target={tagName:'BODY',closest:()=>null})=>({key:name,ctrlKey:true,shiftKey:false,target,preventDefault(){},stopImmediatePropagation(){}});
keys.get('keydown')(key('z')); assert.equal(keyboardManager.getAll().length,0);
keys.get('keydown')(key('y')); assert.equal(keyboardManager.getAll().length,1);
keys.get('keydown')(key('z',{tagName:'INPUT',closest:()=>({})})); assert.equal(keyboardManager.getAll().length,1,'Editable shortcut protected');
events.get('pointerdown')({target:{closest:()=>({})}}); keys.get('keydown')(key('z')); assert.equal(keyboardManager.getAll().length,1,'Trading owns its history shortcuts');
unbind(); delete globalThis.window;
console.log('PASS Phase 7 canonical persistence/restore, one-action drag history, undo/redo/bounds, lock/hide, corruption/future preservation, selection, timeframe/replay and legacy isolation.');

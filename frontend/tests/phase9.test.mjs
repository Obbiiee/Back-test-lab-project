import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { DrawingManager } from '../src/drawings/DrawingManager.js';
import { DrawingHistory } from '../src/drawings/DrawingHistory.js';
import { DrawingPersistence } from '../src/drawings/DrawingPersistence.js';
import { TrendLineCreation } from '../src/drawings/TrendLineCreation.js';
import { DrawingInteractionController } from '../src/drawings/interaction/DrawingInteractionController.js';
import { HIT } from '../src/drawings/interaction/hitTesting.js';
import { projectGeometry } from '../src/drawings/projectGeometry.js';
import { FIBONACCI as F, ARROW as A, TEXT as T, MEASURE as M, RAY } from '../src/drawings/DrawingTypes.js';
import {rayEnd} from '../src/drawings/rayGeometry.js';
import { FIB_LEVELS, fibonacciLevels, arrowHead, measurement, measurementLines, labelBounds } from '../src/drawings/advancedGeometry.js';
const bars=[{time:100},{time:200},{time:500}];let zoom=1,pan=0;
const scale={width:()=>100,timeToCoordinate:t=>({100:10,200:30,500:70})[t]==null?null:({100:10,200:30,500:70})[t]*zoom+pan,coordinateToTime:x=>100+(x-10)*5};
const chart={timeScale:()=>scale,paneSize:()=>({height:100})};
const series={priceToCoordinate:p=>100-p,coordinateToPrice:y=>100-y,attachPrimitive:p=>p.attached({chart,series,requestUpdate(){}}),detachPrimitive:p=>p.detached()};
const anchors=[{time:150,price:80},{time:350,price:40}];
const manager=new DrawingManager(),history=new DrawingHistory(manager);manager.setTimePoints(bars);manager.attach(series);
const legacy=new Map([['backtest-drawings-v2:old','  opaque legacy bytes  ']]),records=new Map(legacy);let writes=0;
const storage={getItem:k=>records.get(k)??null,setItem:(k,v)=>{writes++;records.set(k,v);}};
const persistence=new DrawingPersistence(storage,'main:XAUUSD');persistence.load(manager.registry);manager.subscribeCommitted((before,after)=>persistence.save(after));
for(const type of [F,A,T,M,RAY]){
 const count=type===T?1:2,input={id:type,type,points:anchors.slice(0,count),...(type===T?{text:'Research\nSession A'}:{})};
 for(const points of [[],[...input.points,{time:1,price:2}],input.points.map(p=>({...p,time:NaN})),input.points.map(p=>({...p,price:Infinity}))])assert.throws(()=>manager.add({...input,points}));
 if(type===T)for(const text of [undefined,42,'','  ','a'.repeat(2001)])assert.throws(()=>manager.add({...input,text}));
 let pending=null;const creation=new TrendLineCreation(manager,chart,series,bars,'15m',()=>{},type,point=>{pending=point;});
 const start={point:{x:20,y:20},time:150},end={point:{x:50,y:60},time:350};const beforeCreate=history.undoStack.length, beforeWrites=writes;
 creation.click(start);
 if(type===T){assert.deepEqual(pending,anchors[0]);assert.equal(manager.getAll().some(m=>m.type===T),false);assert.equal(history.undoStack.length,beforeCreate);creation.cancel();assert.equal(writes,beforeWrites);manager.add(input);}
 else{assert.ok(manager.draft);creation.move(end);assert.deepEqual(manager.draft.model.points,anchors);assert.equal(history.undoStack.length,beforeCreate);creation.cancel();assert.equal(manager.draft,null);assert.equal(writes,beforeWrites);creation.click(start);creation.move(end);creation.click(end);}
 const model=manager.getAll().find(m=>m.type===type),id=model.id;assert.equal(model.points.length,count);assert.equal(history.undoStack.length,beforeCreate+1);assert.ok(Object.isFrozen(model.points));
 // Test each shape in isolation to avoid intentional overlap/selection priority.
 const isolated=new DrawingManager();isolated.setTimePoints(bars);isolated.add({...model,id});const controller=new DrawingInteractionController(isolated,chart,series);
 const projected=projectGeometry(model,chart,series,bars),pointer=type===T?{x:40,y:30}:{x:35,y:40};
 assert.equal(controller.hit(pointer).id,id);isolated.select(id);assert.equal(controller.hit(projected[0]).type,HIT.A);
 if(type!==T)assert.equal(controller.hit(projected[1]).type,HIT.B);
 const editModes=type===T?[HIT.A,HIT.BODY]:[HIT.A,HIT.B,HIT.BODY];
 for(const hit of editModes){isolated.update(id,model.points);controller.begin({id,type:hit},{x:30,y:30});controller.move({x:35,y:35});controller.finish();const points=isolated.get(id).points;assert.notDeepEqual(points,model.points);if(hit===HIT.BODY&&count===2){assert.equal(points[0].time-model.points[0].time,points[1].time-model.points[1].time);assert.equal(points[0].price-model.points[0].price,points[1].price-model.points[1].price);}else if(count===2)assert.deepEqual(points[hit===HIT.A?1:0],model.points[hit===HIT.A?1:0]);}
 const mainController=new DrawingInteractionController(manager,chart,series,history), original=manager.get(id).points,undoBefore=history.undoStack.length,writeBefore=writes;
 mainController.begin({id,type:HIT.BODY},{x:30,y:30});for(let i=1;i<=8;i++)mainController.move({x:30+i,y:30+i});assert.equal(history.undoStack.length,undoBefore);assert.equal(writes,writeBefore);mainController.finish();assert.equal(history.undoStack.length,undoBefore+1);assert.equal(writes,writeBefore+1);const after=manager.get(id).points;
 history.undo();assert.deepEqual(manager.get(id).points,original);history.redo();assert.deepEqual(manager.get(id).points,after);
 const cancelCount=history.undoStack.length;mainController.begin({id,type:HIT.A},{x:30,y:30});mainController.move({x:40,y:40});mainController.escape();assert.deepEqual(manager.get(id).points,after);assert.equal(history.undoStack.length,cancelCount);
 manager.setProperties(id,{locked:true});assert.equal(mainController.begin({id,type:HIT.BODY},{x:30,y:30}),false);manager.update(id,original);assert.deepEqual(manager.get(id).points,after);
 if(type===T){assert.equal(manager.setText(id,'Locked edit'),false);assert.equal(manager.get(id).text,input.text);}
 isolated.setProperties(id,{visible:false});assert.equal(controller.hit(pointer).type,HIT.NONE);
 const primitive=manager.primitives.get(id);let strokes=0;const calls=[];const context=new Proxy({stroke(){strokes++;},moveTo:(x,y)=>calls.push(['move',x,y]),lineTo:(x,y)=>calls.push(['line',x,y]),fillText:(text,x,y)=>calls.push(['text',text,x,y])},{get:(o,k)=>o[k]??(()=>{})});
 primitive.updateAllViews();primitive.paneViews()[0].renderer().draw({useMediaCoordinateSpace:fn=>fn({context})});assert.equal(primitive.autoscaleInfo,undefined);
 if(type===T){assert.deepEqual(calls.filter(c=>c[0]==='text').map(c=>c[1]),['Research','Session A']);const editCount=history.undoStack.length;manager.setProperties(id,{locked:false});const unlockedCount=history.undoStack.length;manager.setText(id,'Edited content');assert.equal(history.undoStack.length,unlockedCount+1);history.undo();assert.equal(manager.get(id).text,input.text);history.redo();assert.equal(manager.get(id).text,'Edited content');manager.setText(id,'Edited content');assert.equal(history.undoStack.length,unlockedCount+1);assert.ok(editCount<=unlockedCount);}
 if(type===A){assert.equal(calls.filter(c=>c[0]==='line').length,3,'Shaft plus two arrowhead wings');assert.ok(strokes>0);}
 if(type===F){assert.equal(calls.filter(c=>c[0]==='text').length,7);assert.ok(strokes>=8);}
 if(type===M){assert.equal(calls.filter(c=>c[0]==='text').length,2);const first=measurementLines(manager.get(id).points,bars);manager.setProperties(id,{locked:false});manager.update(id,[after[0],{...after[1],price:after[1].price+5}]);assert.notDeepEqual(measurementLines(manager.get(id).points,bars),first);}
 manager.setProperties(id,{visible:false});primitive.updateAllViews();const paintCount=calls.length;primitive.paneViews()[0].renderer().draw({useMediaCoordinateSpace:fn=>fn({context})});assert.equal(calls.length,paintCount);manager.setProperties(id,{visible:true});
 const canonical=JSON.stringify(manager.getAll());zoom=2;pan=-30;manager.setTimePoints([{time:100},{time:500}]);primitive.updateAllViews();assert.equal(JSON.stringify(manager.getAll()),canonical);manager.setTimePoints(bars);zoom=1;pan=0;
 manager.select(id);mainController.deleteSelected();assert.equal(manager.get(id),undefined);history.undo();assert.ok(manager.get(id));history.redo();assert.equal(manager.get(id),undefined);history.undo();
}
assert.deepEqual(FIB_LEVELS,[0,.236,.382,.5,.618,.786,1]);
for(const points of [anchors,[...anchors].reverse()]){const levels=fibonacciLevels(points);assert.equal(levels[0].price,points[1].price);assert.equal(levels[6].price,points[0].price);assert.equal(levels[3].price,(points[0].price+points[1].price)/2);}
assert.deepEqual(arrowHead({x:1,y:1},{x:1,y:1}),[]);assert.deepEqual(arrowHead({x:0,y:0},{x:20,y:0}),[{x:8,y:-6},{x:8,y:6}]);
assert.deepEqual(measurement(anchors,bars),{priceDelta:-40,percentage:-50,seconds:200,bars:1});assert.equal(measurement([{time:150,price:0},{time:350,price:5}],[]).percentage,null);assert.equal(measurement(anchors,[]).bars,null);
// Derived-level and arrowhead/text-label hits, rather than only baseline hits.
const fibManager=new DrawingManager();fibManager.setTimePoints(bars);fibManager.add({id:'fib',type:F,points:anchors});const fibController=new DrawingInteractionController(fibManager,chart,series);assert.equal(fibController.hit({x:30,y:60}).id,'fib');
const arrowManager=new DrawingManager();arrowManager.setTimePoints(bars);arrowManager.add({id:'arrow',type:A,points:[{time:100,price:80},{time:500,price:80}]});assert.equal(new DrawingInteractionController(arrowManager,chart,series).hit({x:58,y:26}).id,'arrow');
const label=labelBounds({x:20,y:20},['Research','Session A']);assert.ok(label.width>60&&label.height===40);
// Mixed v1 storage restores old models alongside every new type, without geometry migration.
manager.add({id:'old-trend',type:'trend-line',points:anchors});manager.add({id:'old-horizontal',type:'horizontal-line',points:[anchors[0]]});manager.add({id:'old-vertical',type:'vertical-line',points:[anchors[0]]});manager.add({id:'old-rectangle',type:'rectangle',points:anchors});
const loaded=new DrawingManager();loaded.replaceAll(new DrawingPersistence(storage,'main:XAUUSD').load(loaded.registry));assert.deepEqual(loaded.getAll(),manager.getAll());const raw=records.get(persistence.key);assert.equal(JSON.parse(raw).version,1);for(const field of ['selectedId','draft','hover','arrowhead','levels','percentage','pixels','barDistance'])assert.ok(!raw.includes('"'+field+'"'));for(const [key,value] of legacy)assert.equal(records.get(key),value);
const valid=JSON.parse(raw);const bad={...valid.drawings.find(m=>m.type===T),text:''};records.set(persistence.key,JSON.stringify({...valid,drawings:[...valid.drawings,bad]}));const damaged=new DrawingPersistence(storage,'main:XAUUSD');assert.equal(damaged.load(manager.registry).length,valid.drawings.length);assert.equal(damaged.writable,false);const damagedRaw=records.get(persistence.key);assert.equal(damaged.save([]),false);assert.equal(records.get(persistence.key),damagedRaw);
for(const source of ['advancedGeometry.js','models/CoreDrawing.js']){const text=readFileSync(new URL('../src/drawings/'+source,import.meta.url),'utf8');assert.ok(!/trading|createOrder|localStorage|setData\(/.test(text));}
const mixedBefore = JSON.stringify(manager.getAll());
manager.setProperties('old-trend',{visible:false});manager.setText(manager.getAll().find(model=>model.type===T).id,'Mixed text edit');manager.remove('old-rectangle');
const mixedAfter=JSON.stringify(manager.getAll());for(let i=0;i<3;i++)history.undo();assert.equal(JSON.stringify(manager.getAll()),mixedBefore);for(let i=0;i<3;i++)history.redo();assert.equal(JSON.stringify(manager.getAll()),mixedAfter);
for(const type of ['fibonacci-extension','brush','ellipse','indicator'])assert.throws(()=>manager.registry.get(type),/Unknown drawing type/);
// Ray extension is selectable in both screen directions, but never behind
// the origin. Handles always refer to the real two anchors, not the far end.
for(const [points,inside,outside] of [
 [[{time:100,price:80},{time:200,price:80}],{x:90,y:20},{x:0,y:20}],
 [[{time:200,price:80},{time:100,price:80}],{x:0,y:20},{x:90,y:20}],
 [[{time:100,price:80},{time:100,price:60}],{x:10,y:90},{x:10,y:0}],
]){
 const m=new DrawingManager();m.setTimePoints(bars);m.add({id:'r',type:RAY,points});
 const c=new DrawingInteractionController(m,chart,series);
 assert.equal(c.hit(inside).id,'r');assert.equal(c.hit(outside).type,HIT.NONE);
 m.select('r');assert.equal(c.hit(projectGeometry(m.get('r'),chart,series,bars)[1]).type,HIT.B);
 m.setProperties('r',{locked:true});assert.equal(c.begin(c.hit(inside),inside),false);
 m.setProperties('r',{visible:false});assert.equal(c.hit(inside).type,HIT.NONE);
}
const offscreen=rayEnd({x:-10000,y:20},{x:-9990,y:20},100,100);
assert.ok(offscreen.x>100);assert.equal(offscreen.y,20);
assert.deepEqual(rayEnd({x:1,y:1},{x:1,y:1},100,100),{x:1,y:1});
console.log('PASS Phase 9: exact Fib levels/reversal, arrow shaft/head, text validation/content/edit/cancel, deterministic measurement, creation/draft, handles/body/commit history, lock/hide/delete, mixed v1 restore, corruption safety and domain isolation.');

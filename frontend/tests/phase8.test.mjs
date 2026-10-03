import assert from 'node:assert/strict';
import { DrawingManager } from '../src/drawings/DrawingManager.js';
import { DrawingHistory } from '../src/drawings/DrawingHistory.js';
import { DrawingPersistence } from '../src/drawings/DrawingPersistence.js';
import { TrendLineCreation } from '../src/drawings/TrendLineCreation.js';
import { DrawingInteractionController } from '../src/drawings/interaction/DrawingInteractionController.js';
import { HIT } from '../src/drawings/interaction/hitTesting.js';
import { projectGeometry } from '../src/drawings/projectGeometry.js';
import { HORIZONTAL_LINE as H, VERTICAL_LINE as V, RECTANGLE as R } from '../src/drawings/DrawingTypes.js';
const bars = [{time:100},{time:200},{time:500}];
let zoom=1, pan=0, width=100, height=100;
const scale={timeToCoordinate:t=>({100:10,200:30,500:50})[t] == null ? null : ({100:10,200:30,500:50})[t]*zoom+pan, width:()=>width,coordinateToTime:x=>100+(x-10)*5};
const chart={timeScale:()=>scale,paneSize:()=>({height})};
const series={coordinateToPrice:y=>100-y, priceToCoordinate:p=>100-p,attachPrimitive:p=>p.attached({chart,series,requestUpdate(){}}),detachPrimitive:p=>p.detached()};
for(const type of [H,V,R]) {
 const manager=new DrawingManager(),history=new DrawingHistory(manager);manager.setTimePoints(bars);manager.attach(series);
 const count=type===R?2:1, points=[{time:150,price:80},{time:350,price:60}].slice(0,count);
 for(const invalid of [[],[...points,{time:1,price:2}],points.map(p=>({...p,time:NaN})),points.map(p=>({...p,price:Infinity}))])assert.throws(()=>manager.add({id:'invalid',type,points:invalid}));
 assert.throws(()=>manager.add({id:'invalid',type,points,options:{lineWidth:0}}));
 const creation=new TrendLineCreation(manager,chart,series,bars,'15m',()=>{},type);
 const param={point:{x:20,y:20},time:150};creation.click(param);
 if(type===R){assert.equal(manager.getAll().length,0);assert.ok(manager.draft);creation.move({point:{x:40,y:40},time:350});assert.equal(history.undoStack.length,0);creation.cancel();assert.equal(manager.draft,null);assert.equal(history.undoStack.length,0);creation.click(param);creation.move({point:{x:40,y:40},time:350});creation.click({point:{x:40,y:40},time:350});}
 assert.equal(manager.getAll().length,1);assert.equal(history.undoStack.length,1);
 const model=manager.getAll()[0],id=model.id, original=model.points;
 assert.equal(model.points.length,count);assert.ok(Object.isFrozen(model.points[0]));
 const controller=new DrawingInteractionController(manager,chart,series,history);
 const pointer=type===H?{x:60,y:20}:type===V?{x:20,y:70}:{x:30,y:30};
 assert.equal(controller.hit(pointer).id,id);assert.equal(controller.hit(pointer).type,HIT.BODY);
 controller.begin({id,type:HIT.BODY},pointer);for(let i=1;i<=10;i++)controller.move({x:pointer.x+i,y:pointer.y+i});assert.equal(history.undoStack.length,1);controller.finish();assert.equal(history.undoStack.length,2);
 const after=manager.get(id).points;
 if(type===H){assert.equal(after[0].time,original[0].time);assert.equal(after[0].price,original[0].price-10);}
 if(type===V){assert.equal(after[0].price,original[0].price);assert.notEqual(after[0].time,original[0].time);}
 if(type===R){assert.equal(after[0].time-original[0].time,after[1].time-original[1].time);assert.equal(after[0].price-original[0].price,after[1].price-original[1].price);}
 history.undo();assert.deepEqual(manager.get(id).points,original);history.redo();assert.deepEqual(manager.get(id).points,after);
 const historyCount=history.undoStack.length;controller.begin({id,type:HIT.BODY},pointer);controller.move({x:pointer.x+8,y:pointer.y+8});controller.finish(true);assert.equal(history.undoStack.length,historyCount);assert.deepEqual(manager.get(id).points,after);
 if(type!==R){controller.begin({id,type:HIT.BODY},pointer);controller.move(type===H?{x:pointer.x+5,y:pointer.y}:{x:pointer.x,y:pointer.y+5});controller.finish();assert.equal(history.undoStack.length,historyCount,'Irrelevant axis does not create an action');}
 manager.setProperties(id,{locked:true});assert.equal(controller.begin({id,type:HIT.BODY},pointer),false);manager.update(id,original);assert.deepEqual(manager.get(id).points,after);
 manager.setProperties(id,{visible:false});assert.equal(manager.selectedId,null);assert.equal(controller.hit(pointer).type,HIT.NONE);
 let strokes=0;const ctx=new Proxy({stroke(){strokes++;}},{get:(o,k)=>o[k]??(()=>{})});const primitive=manager.primitives.get(id);primitive.updateAllViews();primitive.paneViews()[0].renderer().draw({useMediaCoordinateSpace:fn=>fn({context:ctx})});assert.equal(strokes,0);
 manager.setProperties(id,{visible:true,locked:false});primitive.updateAllViews();primitive.paneViews()[0].renderer().draw({useMediaCoordinateSpace:fn=>fn({context:ctx})});assert.ok(strokes>0);assert.equal(primitive.autoscaleInfo,undefined);
 const canonical=JSON.stringify(manager.getAll());zoom=2;pan=-10;width=200;height=160;primitive.updateAllViews();const projected=primitive.paneViews()[0].projected;
 if(type===H){assert.equal(projected[0].x,0);assert.equal(projected[1].x,200);assert.equal(projected[0].y,projected[1].y);}
 if(type===V){assert.equal(projected[0].y,0);assert.equal(projected[1].y,160);assert.equal(projected[0].x,projected[1].x);}
 manager.setTimePoints([{time:100},{time:500}]);manager.setTimePoints(bars);assert.equal(JSON.stringify(manager.getAll()),canonical);zoom=1;pan=0;width=100;height=100;
 const records=new Map([['backtest-drawings-v2:old','opaque']]);const storage={getItem:k=>records.get(k)??null,setItem:(k,v)=>records.set(k,v)};
 const persistence=new DrawingPersistence(storage,'main:XAUUSD');persistence.load(manager.registry);assert.equal(persistence.save(manager.getAll()),true);
 const restored=new DrawingManager();restored.replaceAll(new DrawingPersistence(storage,'main:XAUUSD').load(restored.registry));assert.deepEqual(restored.getAll(),manager.getAll());assert.equal(records.get('backtest-drawings-v2:old'),'opaque');
 const raw=records.get(persistence.key);for(const field of ['selected','draft','hover','pixel','logical','clientX'])assert.ok(!raw.includes('"'+field+'"'));assert.equal(JSON.parse(raw).version,1);
 manager.setProperties(id,{locked:true});manager.select(id);controller.deleteSelected();assert.equal(manager.get(id),undefined);history.undo();assert.ok(manager.get(id));history.redo();assert.equal(manager.get(id),undefined);
}
// All rectangle orientations expose exactly four virtual handles, backed by two anchors.
for(const points of [[{time:150,price:80},{time:350,price:60}],[{time:350,price:60},{time:150,price:80}],[{time:150,price:60},{time:350,price:80}],[{time:350,price:80},{time:150,price:60}]]){
 const manager=new DrawingManager();manager.setTimePoints(bars);manager.add({id:'r',type:R,points});manager.select('r');const controller=new DrawingInteractionController(manager,chart,series);
 const projected=projectGeometry(manager.get('r'),chart,series,bars);assert.equal(projected.length,4);
 for(const [index,hit] of [HIT.A,HIT.B,HIT.C,HIT.D].entries()){
  manager.update('r',points);const p=projected[index];assert.equal(controller.hit(p).type,hit);controller.begin({id:'r',type:hit},p);controller.move({x:p.x+2,y:p.y+3});controller.finish();const result=manager.get('r').points;assert.equal(result.length,2);assert.notDeepEqual(result,points);
  if(index<2)assert.deepEqual(result[1-index],points[1-index]);
  if(index===2){assert.equal(result[0].time,points[0].time);assert.equal(result[1].price,points[1].price);}
  if(index===3){assert.equal(result[0].price,points[0].price);assert.equal(result[1].time,points[1].time);}
 }
}
for(const type of [H,V,R,'trend-line']) {
 const manager=new DrawingManager();const points=[{time:150,price:80},{time:350,price:60}].slice(0,[H,V].includes(type)?1:2);const model=manager.add({id:'finite',type,points});
 const badChart={timeScale:()=>({...scale,timeToCoordinate:()=>NaN}),paneSize:()=>({height})};
 const badSeries={priceToCoordinate:()=>NaN};
 assert.ok(projectGeometry(model,badChart,badSeries,bars).every(p=>p===null),'Invalid projection is never sent to canvas');
}
console.log('PASS Phase 8: models, single/two-click creation, draft cancel, primitive geometry, four rectangle orientations/handles, hit/drag/axis constraints, one-action history, lock/hide/delete, v1 save/restore, projection and legacy isolation.');

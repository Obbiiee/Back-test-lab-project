// Explicit, pinned supplemental evaluation. No install, production cutover,
// storage migration, or network request. Failure observations are not fixed here.
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {readFileSync, writeFileSync} from 'node:fs';
import {resolve, join} from 'node:path';
import {pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
import {gzipSync} from 'node:zlib';
import {rolldown} from 'rolldown';
import {projectTimestamp, continuousPointFromPointer} from '../src/drawings/timeCoordinates.js';

const root = process.env.BTL_SUPPLEMENTAL_DRAWING_ROOT;
assert.ok(root, 'Explicit inspected donor root required');
const pin = '72290d3165682ec7bd28f96af7f9354184982dda';
assert.equal(execFileSync('git', ['-C', root, 'rev-parse', 'HEAD'], {encoding:'utf8'}).trim(), pin);
assert.equal(execFileSync('git', ['-C', root, 'status', '--porcelain'], {encoding:'utf8'}).trim(), '');
const pkg = JSON.parse(readFileSync(join(root, 'package.json'), 'utf8'));
assert.equal(pkg.version, '0.5.1');
assert.equal(pkg.license, 'MIT');
const output = resolve('tests/artifacts/alpha-drawing-051.mjs');
const build = await rolldown({input:join(root, 'src/index.ts'), transform:{define:{__VERSION__:JSON.stringify(pkg.version)}}});
let metrics;
try {
  const result = await build.write({file:output, format:'esm', minify:true});
  const chunk = result.output.find(item=>item.type==='chunk');
  metrics = {pin, version:pkg.version, peer:pkg.peerDependencies['lightweight-charts'], modules:Object.keys(chunk.modules).length,
    minifiedBytes:Buffer.byteLength(chunk.code), gzipBytes:gzipSync(chunk.code).length,
    licenseSha256:createHash('sha256').update(readFileSync(join(root, 'LICENSE'))).digest('hex')};
} finally { await build.close(); }
const donor = await import(pathToFileURL(output));
assert.equal(donor.VERSION, '0.5.1');
const bars = [{time:100}, {time:200}, {time:500}];
const scale = {timeToCoordinate:t=>({100:10, 200:30, 500:50})[t]??null,
  coordinateToTime:()=>null, coordinateToLogical:x=>(x-10)/20, logicalToCoordinate:i=>10+i*20};
const chart = {timeScale:()=>scale};
const series = {priceToCoordinate:p=>100-p, coordinateToPrice:y=>100-y};
const coords = donor.makeCoords(chart, series, ()=>bars);
const time = 150.25, x = coords.timeToX(time);
assert.equal(x, projectTimestamp(scale, bars, time));
const nativeInverse = coords.xToTime(x);
assert.notEqual(nativeInverse, time, 'Re-evaluate if donor inverse is repaired');
const preservedInverse = continuousPointFromPointer(chart, series, {x,y:20}, bars).time;
assert.ok(Math.abs(preservedInverse-time)<1e-10);
// Chart global indices can differ from the series-local array (other series).
const shifted = {...scale, logicalToCoordinate:i=>100+i*20};
const nativeGlobal = donor.makeCoords({timeScale:()=>shifted}, series, ()=>bars).timeToX(time);
assert.notEqual(nativeGlobal, projectTimestamp(shifted, bars, time));
const invalid = [{id:'bad', kind:'future-kind', points:[{time:'not-a-time', price:Infinity}]}];
const parsed = donor.parseDrawings(invalid);
assert.equal(parsed.length, 1);
assert.equal(parsed[0].points[0].price, Infinity);
assert.ok(invalid[0].style, 'Native parser mutates input through style backfill');
assert.deepEqual(donor.parseDrawings({version:1, workspace:'btl', drawings:[]}), []);
// Core is explicitly separable: host-owned coordinates can render a Ray
// without native runtime/storage. Verify this bounded alternative as well.
const ray = {id:'ray', kind:'ray', points:[{time,price:80},{time:350.75,price:60}], style:donor.defaultStyleFor('ray')};
const pts = [{x:20.05,y:20},{x:40.05,y:40}];
const scene = donor.sceneOf(ray, pts, {w:300,h:200,coords:null,selected:false});
assert.ok(scene.some(item=>item.t==='line'), 'Ray core scene available');
const observations = {metrics, coordinate:{time,x,nativeInverse,preservedInverse,nativeGlobal},
  nativeParser:{acceptsInvalid:true,mutatesInput:true,dropsBTLEnvelope:true}, coreRayScene:true,
  interpretation:'Native runtime needs coordinate and strict-storage adapters; core scene can use the existing host bridge. No production eligibility claimed.'};
writeFileSync(resolve('tests/artifacts/alpha-drawing-051-evidence.json'), JSON.stringify(observations,null,2)+'\n');
console.log(JSON.stringify(observations));
console.log('PASS authored supplemental observations; native mismatch is recorded, not adopted. Browser is a separate gate.');

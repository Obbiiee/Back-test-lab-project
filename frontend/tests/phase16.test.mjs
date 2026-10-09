import assert from 'node:assert/strict';
import { AccountPersistence, ACCOUNT_KEY, validateStoredAccount } from '../src/trading/AccountPersistence.js';
import { initialAccount, placeOrder, processCandle, closePosition } from '../src/trading/simulator.js';
import { readFavorites, FAVORITES_KEY, DEFAULT_FAVORITES } from '../src/workspacePreferences.js';
import { markerGroups } from '../src/news/NewsMarkerAdapter.js';
import { EventIndex, projectOccurrence, matchesFilters } from '../src/news/eventIndex.js';
import { validateDataset } from '../src/news/eventValidation.js';
import { pilot, fact, iso, START } from './phase14-5-fixtures.mjs';
import { readFileSync, readdirSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const quote = { time: 60, open: 2000, high: 2001, low: 1999, close: 2000 };
let account = placeOrder(initialAccount(), { id: 'test-active', side: 'Buy', type: 'Market', size: 1, sl: 1980, tp: 2020 }, quote);
account = closePosition(account, 'test-active', 2010, 120, 'Manual close', .5);
account.trades[0].notes = 'Preserved Unicode العربية 日本語';
account.customMetadata = { source: 'legacy' };
const bytes = JSON.stringify(account), values = new Map([[ACCOUNT_KEY, bytes]]);
const storage = { getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, value) };
const persistence = new AccountPersistence(storage);
assert.deepEqual(persistence.load(), account);assert.equal(persistence.save(account), true);assert.equal(values.get(ACCOUNT_KEY), bytes);
const legacy = { balance: 123, orders: [], positions: [], trades: [{ size: .1, notes: 'Old record' }] };
assert.equal(validateStoredAccount(legacy), legacy, 'Do not fabricate legacy evidence or normalize valid metadata.');
const numericIdentity={...account,positions:[{...account.positions[0],id:123}]};assert.equal(validateStoredAccount(numericIdentity),numericIdentity,'Legacy numeric identities accepted by the existing simulator must not be migrated or dropped.');
for (const invalid of ['{bad', 'null', JSON.stringify({ ...account, schemaVersion: 99 }), JSON.stringify({ ...account, positions: [null] }), JSON.stringify({ ...account, orders: [{ ...account.positions[0], size: null }] }), JSON.stringify({ ...account, trades: [{ size: 1, notes: {} }] })]) {
  values.set(ACCOUNT_KEY, invalid);const reader = new AccountPersistence(storage);
  assert.deepEqual(reader.load(), initialAccount());assert.ok(reader.snapshot().includes('preserved'));
  assert.equal(reader.save(processCandle(initialAccount(), quote)), false);assert.equal(values.get(ACCOUNT_KEY), invalid, 'Never overwrite malformed/future original account bytes.');
}
values.set(ACCOUNT_KEY, bytes);
const oversized = new AccountPersistence(storage); oversized.load();
assert.equal(oversized.save({ ...account, customMetadata: 'x'.repeat(8 * 1024 * 1024) }), false);
assert.equal(values.get(ACCOUNT_KEY), bytes, 'Never save a record that the same reader cannot safely reload.');
const quota = new AccountPersistence({ getItem: storage.getItem, setItem: () => { throw Error('Quota exceeded'); } });
quota.load();let changes = 0;const unsubscribe = quota.subscribe(() => changes++);
assert.equal(quota.save(account), false);assert.equal(values.get(ACCOUNT_KEY), bytes);assert.ok(quota.snapshot().includes('memory'));assert.equal(changes, 1);unsubscribe();
const unavailable = new AccountPersistence(() => { throw Error('Storage disabled'); });unavailable.load();assert.equal(unavailable.save(account), false);
console.log('PASS Phase16 valid/legacy account lossless storage, partial-exit identity, malformed/future preservation, quota/unavailable handling and status lifecycle.');
for (const raw of ['null','{}','[{}]','["Trend Line","Trend Line"]','{broken']) {
  values.set(FAVORITES_KEY,raw);const prefs=readFavorites(storage);assert.equal(prefs.writable,false);assert.deepEqual(prefs.value,DEFAULT_FAVORITES);assert.equal(values.get(FAVORITES_KEY),raw);
}
values.set(FAVORITES_KEY,'["Trend Line","Unknown future tool"]');assert.equal(readFavorites(storage).writable,true);
assert.equal(readFavorites(()=>{throw Error('Disabled storage');}).writable,false);
values.set(ACCOUNT_KEY,bytes);const foreign=new AccountPersistence(storage);foreign.load();
const changed=JSON.stringify({...account,balance:98765});values.set(ACCOUNT_KEY,changed);
assert.equal(foreign.save(account),false);assert.equal(values.get(ACCOUNT_KEY),changed);assert.ok(foreign.snapshot().includes('outside'));
console.log('PASS malformed favorites retained without blanking workspace or silently replacing preferences.');
let reads=0;const first=1717416000;
const history=new Proxy(Array.from({length:100000},(_,i)=>({time:first+i*60})),{get(target,key,receiver){if(/^\d+$/.test(String(key)))reads++;return Reflect.get(target,key,receiver);}});
assert.deepEqual(markerGroups([],history,'1m',()=>true,first+1000),[]);assert.equal(reads,0,'No candle history scan when no news markers exist.');
assert.equal(markerGroups([{occurrenceId:'bounded-anchor',fields:{schedule:{value:first+600}}}],history,'1m',()=>true,first+1000).length,1);assert.ok(reads<100,'Exact anchor lookup must be logarithmic, not a full-history Set rebuild.');
console.log('PASS marker anchoring over 100k revealed candles without full-history scanning.');
const source=pilot(300);
source.occurrences.forEach((row,i)=>{
 const at=START+i*90;
 row.facts.schedule.push(fact(iso(START+i*1800+60),at,{version:'revision'}));
 row.facts.currency.push(fact(i%2?'EUR':'USD',at+30,{version:'revision'}));
 row.facts.impact.push(fact(i%3?'Medium':'High',at+60,{version:'revision'}));
});
const dataset=validateDataset(source), index=new EventIndex(dataset);
let seed=73;
for(let sample=0;sample<150;sample++){
 seed=(Math.imul(seed,1664525)+1013904223)>>>0;
 const time=START+(seed%40000)-600,from=time-86400,to=time+86400;
 const filters={currency:sample%3?'All':'USD',impact:sample%2?'All':'High',category:'All'};
 const expected=dataset.occurrences.map(row=>projectOccurrence(row,time)).filter(event=>event&&Number.isFinite(event.fields.schedule?.value)&&matchesFilters(event,filters)&&event.fields.schedule.value>=from&&event.fields.schedule.value<to).sort((a,b)=>a.fields.schedule.value-b.fields.schedule.value||(a.occurrenceId<b.occurrenceId?-1:1));
 assert.deepEqual(index.range(from,to,time,filters),expected,'Cached availability views must equal direct strict projection across randomized rewinds/revisions/filter changes.');
}
function scan(directory){for(const item of readdirSync(directory,{withFileTypes:true})){const file=path.join(directory,item.name);if(item.isDirectory())scan(file);else if(/\.(js|jsx|css)$/.test(file)){const text=readFileSync(file,'utf8');assert.ok(!/\beval\s*\(|new\s+Function\b|dangerouslySetInnerHTML\b|document\.write\s*\(/.test(text),'Unsafe executable-input sink: '+file);assert.ok(!/-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|sk-[A-Za-z0-9]{40,}/.test(text),'Potential embedded credential; review filename without printing secret: '+file);}}}
scan(fileURLToPath(new URL('../src/',import.meta.url)));
console.log('PASS randomized news-cache differential and active-source executable-input/embedded-credential checks (bounded heuristic, not a complete security proof).');

// S-7 research preferences: actual roundtrip/edit/hide/remove, independent
// Sessions, hostile/future bytes and concurrent foreign-tab preservation.
const {IndicatorPreferences}=await import('../src/workspacePreferences.js');
const {productionRegistry}=await import('../src/indicators/productionRegistry.js');
const prefValues=new Map(),prefStorage={getItem:key=>prefValues.get(key)??null,setItem:(key,value)=>prefValues.set(key,value)};
const newPrefs=workspace=>new IndicatorPreferences(prefStorage,workspace,productionRegistry);
const a=newPrefs('tick-alpha:A');assert.deepEqual(a.load(),[]);
const instances=[{id:'rsi',type:'RSI',parameters:{period:3},visible:false},{id:'sma',type:'SMA',parameters:{period:5},visible:true}];
assert.equal(a.save(instances),true);const aReload=newPrefs('tick-alpha:A');assert.deepEqual(aReload.load(),instances);
const b=newPrefs('tick-alpha:B');assert.deepEqual(b.load(),[]);assert.equal(b.save([]),true);assert.deepEqual(newPrefs('tick-alpha:A').load(),instances);
const edited=[{...instances[0],visible:true,parameters:{period:7}}];assert.equal(aReload.save(edited),true);assert.deepEqual(newPrefs('tick-alpha:A').load(),edited);
const currentBytes=prefValues.get(a.key);
for(const bad of ['{broken',JSON.stringify({version:2,workspace:a.workspace,instances}),JSON.stringify({version:1,workspace:'foreign',instances}),JSON.stringify({version:1,workspace:a.workspace,instances:[instances[0],instances[0]]}),JSON.stringify({version:1,workspace:a.workspace,instances:[{...instances[0],type:'FUTURE'}]}),JSON.stringify({version:1,workspace:a.workspace,instances:[{...instances[0],parameters:{period:0}}]}),' '.repeat(32769)]){
 prefValues.set(a.key,bad);const held=newPrefs(a.workspace);assert.deepEqual(held.load(),[]);assert.equal(held.save([]),false);assert.equal(prefValues.get(a.key),bad);assert.ok(held.status);
}
prefValues.set(a.key,currentBytes);const concurrent=newPrefs(a.workspace);concurrent.load();prefValues.set(a.key,'foreign-new-bytes');assert.equal(concurrent.save([]),false);assert.equal(prefValues.get(a.key),'foreign-new-bytes');assert.equal(concurrent.writable,false);
const blocked=new IndicatorPreferences(()=>{throw Error('Storage denied');},'tick-alpha:C',productionRegistry);assert.deepEqual(blocked.load(),[]);assert.equal(blocked.save([]),false);
const prefQuota=new IndicatorPreferences({getItem:()=>null,setItem:()=>{throw Error('Quota');}},'tick-alpha:D',productionRegistry);prefQuota.load();assert.equal(prefQuota.save(instances),false);assert.ok(prefQuota.status);assert.equal(prefQuota.raw,null);
console.log('PASS S-7 per-Session indicator roundtrip/edit/hide/remove, isolation, future/corrupt/oversized/duplicate/invalid preferences, foreign-tab and unavailable/quota byte preservation.');

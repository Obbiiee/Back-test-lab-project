import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {periodAvailability,periodChoiceOk,defaultPeriod,monthLabel} from '../src/tickAlpha/periodAvailability.js';

const base={startPeriod:'2024-11',profile:{instrumentId:'XAUUSD'}};

// Synthetic fixture: fixed, nothing to choose.
assert.deepEqual(periodAvailability(base,'XAUUSD',false),{mode:'fixed',earliest:'2024-11'});
assert.equal(periodChoiceOk({mode:'fixed'},null),true);

// No DTO: only the earliest month is stated; later months (also across years) go to the server.
const none=periodAvailability(base,'XAUUSD',true);
assert.equal(none.mode,'unpublished');
assert.equal(defaultPeriod(none),'2024-11');
assert.equal(periodChoiceOk(none,'2024-11'),true);
assert.equal(periodChoiceOk(none,'2025-03'),true,'cross-year month is not excluded by a guessed max');
assert.equal(periodChoiceOk(none,'2024-10'),false,'before the earliest observed month');
assert.equal(periodChoiceOk(none,'2025-13'),false);
assert.equal(periodChoiceOk(none,''),false);
assert.equal(periodAvailability({...base,startPeriod:undefined},'XAUUSD',true).earliest,null);

// Published DTO: exact months only, gaps / rights / expiry disabled with a reason.
const dto={...base,availability:{schemaVersion:1,instruments:[{instrumentId:'XAUUSD',status:'AVAILABLE',periods:[
  {period:'2025-01',status:'AVAILABLE'},{period:'2024-11',status:'AVAILABLE'},{period:'2024-12',status:'GAP'},
  {period:'2025-02',status:'RIGHTS_BLOCKED'},{period:'2025-03',status:'EXPIRED',reason:'Retired 2026-10'},{period:'bad',status:'AVAILABLE'}]},
  {instrumentId:'EURUSD',status:'QA_BLOCKED',periods:[{period:'2025-01',status:'AVAILABLE'}]}]}};
const pub=periodAvailability(dto,'XAUUSD',true);
assert.equal(pub.mode,'published');
assert.deepEqual(pub.months.map(m=>m.period),['2024-11','2024-12','2025-01','2025-02','2025-03'],'sorted, malformed rows dropped');
assert.deepEqual(pub.months.map(m=>m.selectable),[true,false,true,false,false]);
assert.equal(pub.months[1].reason,'No observations in this month');
assert.equal(pub.months[3].reason,'Data rights do not cover this month');
assert.equal(pub.months[4].reason,'Retired 2026-10');
assert.equal(periodChoiceOk(pub,'2024-12'),false,'a gap inside the range is not eligible');
assert.equal(periodChoiceOk(pub,'2025-01'),true);
assert.equal(periodChoiceOk(pub,'2025-04'),false,'unlisted month');
assert.equal(defaultPeriod(pub),'2024-11');

// Rights/QA/unknown instrument states remain closed even if a row claims AVAILABLE.
const eur=periodAvailability(dto,'EURUSD',true);
assert.equal(eur.months[0].selectable,false);
assert.equal(eur.months[0].reason,'Held back until data checks pass');
assert.equal(defaultPeriod(eur),null);
assert.deepEqual(periodAvailability(dto,'GBPUSD',true),{mode:'published',months:[],instrumentStatus:'NOT_LISTED'});

// Pinned fixtures per instrument status (REQ-01). GAP rows never open.
const fixture=status=>({...base,label:'QA FIXTURE / INSTRUMENT STATUS / NOT MARKET DATA',availability:{schemaVersion:1,instruments:[{instrumentId:'XAUUSD',status,periods:[
  {period:'2024-11',status:'AVAILABLE'},{period:'2024-12',status:'GAP'},{period:'2025-01',status:'AVAILABLE'}]}]}});
// A PARTIAL instrument may expose individually verified AVAILABLE start months.
const partial=periodAvailability(fixture('PARTIAL'),'XAUUSD',true);
assert.deepEqual(partial.months.map(m=>m.selectable),[true,false,true]);
assert.equal(partial.months[0].reason,null,'available row has no blocking reason');
for(const status of ['RIGHTS_BLOCKED','QA_BLOCKED','UNKNOWN','PLANNED','SOMETHING_NEW']){
  const a=periodAvailability(fixture(status),'XAUUSD',true);
  assert.equal(a.instrumentStatus,status);
  assert.ok(a.months.every(m=>!m.selectable),status+' opened a month');
  assert.equal(defaultPeriod(a),null,status);
  assert.equal(periodChoiceOk(a,'2024-11'),false,status);
  assert.equal(a.months[1].reason,'No observations in this month','GAP keeps its own reason');
}
assert.equal(partial.months[0].selectable,true);
assert.equal(periodAvailability(fixture('SOMETHING_NEW'),'XAUUSD',true).months[0].reason,'Instrument not available');
const okGap=periodAvailability(fixture('AVAILABLE'),'XAUUSD',true);
assert.deepEqual(okGap.months.map(m=>m.selectable),[true,false,true]);

// Unknown or malformed schema versions fail closed rather than falling back to a guessed range.
const unknownVersion=periodAvailability({...dto,availability:{...dto.availability,schemaVersion:2}},'XAUUSD',true);
assert.equal(unknownVersion.mode,'published');
assert.equal(defaultPeriod(unknownVersion),null);
assert.equal(periodAvailability({...dto,availability:null},'XAUUSD',false).mode,'published');
assert.equal(monthLabel('2025-01'),'January 2025');

// The wizard keeps the selected instrument in its UI event; TickAlpha maps the
// approved fields into the unchanged Session API payload.
const wizard=readFileSync(new URL('../src/tickAlpha/AlphaSessionWizard.jsx',import.meta.url),'utf8');
assert.doesNotMatch(wizard,/maxPeriod|slice\(0,4\)/);
assert.match(wizard,/onCreate\(\{name:finalName,methodId:method\.id,symbol:instrument,initialBalance:balance,\s*startPeriod:/);
console.log('period availability: ok');

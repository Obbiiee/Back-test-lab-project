// Unit proof for the confirm outcome model (founder P0 2026-11-06).
import assert from 'node:assert/strict';
import {classifyConfirmError,committedReceipt,reconcile} from '../src/tickAlpha/confirmOutcome.js';
const err=(message,status)=>Object.assign(Error(message),status===undefined?{}:{status});

// Definitive refusals.
assert.deepEqual(classifyConfirmError(err('REFUSED_STALE_REVISION',409)),{outcome:'STALE',code:'REFUSED_STALE_REVISION'});
assert.deepEqual(classifyConfirmError(err('PROTOCOL_BLOCKED',409)),{outcome:'REFUSED',code:'PROTOCOL_BLOCKED'});
assert.equal(classifyConfirmError(err('The saved record changed. Reload before retrying.',409)).outcome,'STALE');
for(const status of [400,401,403,404,413,415,422])assert.equal(classifyConfirmError(err('X',status)).outcome,'REFUSED',String(status));
assert.equal(classifyConfirmError(err('LOCAL_BUSY',429)).outcome,'REFUSED');
assert.equal(classifyConfirmError(err('RATE_LIMITED',429)).outcome,'REFUSED');
// Unknown outcomes: never "not placed".
for(const e of [err('LOCAL_SERVICE_UNAVAILABLE',503),err('LOCAL_REQUEST_TIMEOUT',408),err('Account service unavailable.',502),
  err('The service is busy. Wait and retry.',429),err('Failed to fetch'),err('The operation was aborted due to timeout'),
  err('Unexpected token < in JSON'),err('Account changed; this response was discarded.'),null,undefined])
  assert.equal(classifyConfirmError(e).outcome,'UNKNOWN',String(e?.message));
assert.equal(classifyConfirmError(err('')).code,'NO_RESPONSE');

// Receipt.
const ok={artifact:'BTL-TICK-EXECUTION-RESULT-1',commandId:'order:a',durable:true};
assert.equal(committedReceipt(ok,'order:a'),true);
assert.equal(committedReceipt({...ok,commandId:'order:b'},'order:a'),false);
assert.equal(committedReceipt({...ok,durable:false},'order:a'),false);
assert.equal(committedReceipt({schemaVersion:1},'order:a'),false);
assert.equal(committedReceipt(null,'order:a'),false);

// Reconciliation.
const pending={commandId:'order:a',expectedRevision:4};
assert.equal(reconcile({state:{revision:5,orders:{'order:a':{}}}},pending),'COMMITTED');
assert.equal(reconcile({state:{revision:4,orders:{}}},pending),'UNKNOWN');
assert.equal(reconcile({state:{revision:6,orders:{'order:z':{}}}},pending),'REFUSED');
assert.equal(reconcile({state:{revision:4}},pending),'UNKNOWN');
assert.equal(reconcile({},pending),'UNKNOWN');
assert.equal(reconcile({state:{revision:'5',orders:{}}},pending),'UNKNOWN');
assert.equal(reconcile({state:{revision:9,orders:Object.create({'order:a':1})}},pending),'REFUSED','inherited keys are not orders');
console.log('confirm-outcome: PASS');

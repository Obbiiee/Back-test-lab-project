// Unit proof for the confirm outcome model (founder P0 2026-11-06).
import assert from 'node:assert/strict';
import {classifyConfirmError,committedReceipt,classifyCommandResult} from '../src/tickAlpha/confirmOutcome.js';
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

// Receipt reconciliation is bound to the exact Session, command, review, and basis.
const pending={sessionId:'session:a',commandId:'order:a',expectedRevision:4,reviewHash:'b'.repeat(64)};
const receipt={artifact:'BTL-TICK-EXECUTION-RESULT-1',commandId:'order:a',commandHash:'a'.repeat(64),durable:true,
  state:{sessionId:'session:a',revision:5}};
const status=(status,extra={})=>({schemaVersion:1,artifact:'BTL-TICK-COMMAND-STATUS-1',
  sessionId:'session:a',commandId:'order:a',reviewHash:pending.reviewHash,currentRevision:5,
  status,...extra});
assert.deepEqual(classifyCommandResult(status('COMMITTED',{receipt}),pending),{outcome:'COMMITTED',code:'DURABLE_RECEIPT'});
assert.equal(classifyCommandResult(status('COMMITTED',{receipt:{...receipt,durable:false}}),pending).outcome,'UNKNOWN');
assert.equal(classifyCommandResult(status('COMMITTED',{receipt:{...receipt,commandId:'order:b'}}),pending).outcome,'UNKNOWN');
assert.equal(classifyCommandResult(status('COMMITTED',{receipt:{...receipt,commandHash:'bad'}}),pending).outcome,'UNKNOWN');
assert.equal(classifyCommandResult(status('COMMITTED',{receipt:{...receipt,state:{sessionId:'session:b',revision:5}}}),pending).outcome,'UNKNOWN');
assert.deepEqual(classifyCommandResult(status('NOT_COMMITTED',{expectedRevision:4,currentRevision:6,
  reason:'SESSION_REVISION_ADVANCED'}),pending),{outcome:'REFUSED',code:'SESSION_REVISION_ADVANCED'});
assert.equal(classifyCommandResult(status('NOT_COMMITTED',{expectedRevision:4,currentRevision:4,
  reason:'SESSION_REVISION_ADVANCED'}),pending).outcome,'UNKNOWN');
assert.equal(classifyCommandResult(status('UNKNOWN',{reason:'NO_DURABLE_COMMAND_AT_REVIEW_REVISION'}),pending).outcome,'UNKNOWN');
assert.equal(classifyCommandResult(status('UNKNOWN',{reason:'REVIEW_OR_COMMAND_NOT_VISIBLE'}),pending).outcome,'UNKNOWN');
assert.equal(classifyCommandResult({...status('COMMITTED',{receipt}),reviewHash:'c'.repeat(64)},pending).outcome,'UNKNOWN');
assert.equal(classifyCommandResult({...status('COMMITTED',{receipt}),sessionId:'session:b'},pending).outcome,'UNKNOWN');
assert.equal(classifyCommandResult({...status('COMMITTED',{receipt}),schemaVersion:2},pending).outcome,'UNKNOWN');
console.log('confirm-outcome: PASS');

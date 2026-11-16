import assert from 'node:assert/strict';
import {retryExactConfirm} from './browser-tools/retry-exact-confirm.mjs';

const body={commandId:'cmd:stable',commandHash:'a'.repeat(64)};
const attempts=[];const delays=[];const observed=[];
const result=await retryExactConfirm({
  send:async()=>{
    attempts.push(body);
    if(attempts.length===1)return {status:()=>503,headers:()=>({'retry-after':'1'}),json:async()=>({detail:'SERVICE_BUSY'})};
    return {status:()=>200,headers:()=>({}),json:async()=>({durable:true,receipt:'same'})};
  },
  onResponse:row=>observed.push(row),sleep:async ms=>delays.push(ms),random:()=>0,
});
assert.equal(attempts.length,2);
assert.equal(attempts[0],attempts[1],'retry must retain the exact command payload object');
assert.deepEqual(delays,[1000]);
assert.deepEqual(observed.map(row=>[row.status,row.code]),[[503,'SERVICE_BUSY'],[200,null]]);
assert.deepEqual(result.body,{durable:true,receipt:'same'});

let recoveredAttempts=0;
const recovered=await retryExactConfirm({send:async()=>{
  recoveredAttempts++;
  return recoveredAttempts<6
    ?{status:()=>503,headers:()=>({'retry-after':'1'}),json:async()=>({detail:'SERVICE_BUSY'})}
    :{status:()=>200,headers:()=>({}),json:async()=>({durable:true})};
},sleep:async()=>{}});
assert.equal(recoveredAttempts,6);
assert.deepEqual(recovered.body,{durable:true});

let researchBusyAttempts=0;const researchBusyDelays=[];
const researchBusy=await retryExactConfirm({random:()=>0,sleep:async ms=>researchBusyDelays.push(ms),send:async()=>{
  researchBusyAttempts++;
  return researchBusyAttempts===1
    ?{status:()=>429,headers:()=>({}),json:async()=>({detail:'RESEARCH_BUSY'})}
    :{status:()=>200,headers:()=>({}),json:async()=>({durable:true,receipt:'same'})};
}});
assert.equal(researchBusyAttempts,2);
assert.deepEqual(researchBusyDelays,[50]);
assert.deepEqual(researchBusy.body,{durable:true,receipt:'same'});

let rejectedAttempts=0;
await assert.rejects(retryExactConfirm({send:async()=>{
  rejectedAttempts++;
  return {status:()=>503,headers:()=>({'retry-after':'1'}),json:async()=>({detail:'SERVICE_BUSY'})};
},sleep:async()=>{}}),error=>error.code==='SERVICE_BUSY');
assert.equal(rejectedAttempts,9,'bounded admission retry must match the product limit of eight retries');

let deadlineClock=0;let deadlineAttempts=0;
await assert.rejects(retryExactConfirm({deadlineMs:1900,now:()=>deadlineClock,random:()=>0,
  send:async()=>{deadlineAttempts++;return {status:()=>503,headers:()=>({'retry-after':'1'}),json:async()=>({detail:'SERVICE_BUSY'})};},
  sleep:async ms=>{deadlineClock+=ms;}}),error=>error.code==='SERVICE_BUSY'&&error.message==='EXACT_CONFIRM_RETRY_DEADLINE');
assert.equal(deadlineAttempts,2,'retry must stop before crossing the request deadline');

let ambiguousAttempts=0;
await assert.rejects(retryExactConfirm({send:async()=>{ambiguousAttempts++;throw Error('transport outcome ambiguous');}}),
  /transport outcome ambiguous/);
assert.equal(ambiguousAttempts,1,'ambiguous transport outcomes must not be retried');

let staleAttempts=0;
await assert.rejects(retryExactConfirm({send:async()=>{staleAttempts++;return {
  status:()=>409,headers:()=>({}),json:async()=>({detail:'REFUSED_STALE_REVISION'})};}}),
  error=>error.code==='REFUSED_STALE_REVISION');
assert.equal(staleAttempts,1,'stale revision refusals must never be retried');
console.log('PASS exact Confirm retry: only pre-admission SERVICE_BUSY, Retry-After respected, bounded attempts, unchanged payload.');

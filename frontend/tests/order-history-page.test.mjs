import assert from 'node:assert/strict';
import {orderHistoryPagePath,validateOrderHistoryPage} from '../src/tickAlpha/client.js';

assert.equal(orderHistoryPagePath('session:alpha'),
  '/sessions/session%3Aalpha/orders/pages?limit=64');
assert.equal(orderHistoryPagePath('session:alpha',{limit:32,afterSequence:63,revision:9}),
  '/sessions/session%3Aalpha/orders/pages?limit=32&after_sequence=63&revision=9');
assert.throws(()=>orderHistoryPagePath('session:alpha',{limit:257}),/Invalid order history page request/);
assert.throws(()=>orderHistoryPagePath('session:alpha',{afterSequence:-2}),/Invalid order history cursor/);

const row=(sequence)=>({orderId:`order:${sequence}`,sequence,finalizedRevision:sequence+1,
  recordHash:'a'.repeat(64),order:{status:'CLOSED',grossPosted:'1.25'}});
const first={artifact:'BTL-ORDER-HISTORY-PAGE-1',sessionId:'session:alpha',revision:9,total:3,
  records:[row(0),row(1)],nextCursor:{revision:9,afterSequence:1},complete:false};
assert.equal(validateOrderHistoryPage(first,'session:alpha',{limit:2}),first);
const last={...first,records:[row(2)],nextCursor:null,complete:true};
assert.equal(validateOrderHistoryPage(last,'session:alpha',{limit:2,afterSequence:1,revision:9}),last);
assert.throws(()=>validateOrderHistoryPage(last,'session:alpha',{revision:8}),/revision changed/);
assert.throws(()=>validateOrderHistoryPage({...first,records:[row(0),row(0)]},'session:alpha',{limit:2}),/Invalid order history record/);
assert.throws(()=>validateOrderHistoryPage({...first,nextCursor:{revision:8,afterSequence:1}},'session:alpha',{limit:2}),/Invalid order history cursor/);

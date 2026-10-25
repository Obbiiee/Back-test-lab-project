// Display-only ticket estimates must mirror the server risk_quantity rule exactly.
import assert from 'node:assert/strict';
import {plannedEstimate,targetForRR,decimalText,orderTypeForEntry} from '../src/tickAlpha/orderEstimate.js';
const profile={contractSize:'100',lotStep:'0.01',tickSize:'0.01',commissionPerLotSide:'0'};
const long=plannedEstimate({side:'LONG',entry:'1957.245',sl:'1937.673',tp:'1996.389',riskPercent:'1',balance:'100000',profile});
assert.equal(long.valid,true);assert.equal(long.lots,'0.51');assert.equal(long.riskMoney,'998.17');
assert.equal(long.rr,'2.00');assert.equal(long.rewardMoney,'1996.34');assert.equal(long.stopTicks,'1957');
const short=plannedEstimate({side:'SHORT',entry:'2000',sl:'2010',tp:'1980',riskPercent:'0.5',balance:'10000',profile});
assert.deepEqual([short.lots,short.riskMoney,short.rr,short.rewardMoney],['0.05','50.00','2.00','100.00']);
const fees=plannedEstimate({side:'LONG',entry:'2000',sl:'1999',tp:'2002',riskPercent:'1',balance:'10000',profile:{...profile,commissionPerLotSide:'3.5'}});
assert.deepEqual([fees.lots,fees.riskMoney,fees.rewardMoney],['0.93','99.51','179.49']);
assert.equal(plannedEstimate({side:'LONG',entry:'2000',sl:'2001',riskPercent:'1',balance:'10000',profile}).valid,false);
assert.equal(plannedEstimate({side:'SHORT',entry:'2000',sl:'2010',tp:'2005',riskPercent:'1',balance:'10000',profile}).valid,false);
assert.match(plannedEstimate({side:'LONG',entry:'2000',sl:'1000',riskPercent:'0.001',balance:'100',profile}).reason,/smaller than one lot step/);
assert.equal(plannedEstimate({side:'LONG',entry:'abc',sl:'1',riskPercent:'1',balance:'1',profile}).valid,false);
assert.equal(targetForRR({side:'LONG',entry:'2000',sl:'1990',rr:'2',tickSize:'0.01'}),'2020.00');
assert.equal(targetForRR({side:'SHORT',entry:'2000.05',sl:'2000.12',rr:'1.5',tickSize:'0.01'}),'1999.95');
assert.equal(targetForRR({side:'LONG',entry:'2000',sl:'2010',rr:'2',tickSize:'0.01'}),null);
assert.equal(decimalText('1234.5'),'1234.50');assert.equal(decimalText('x'),null);
console.log('PASS order estimate: exact server-mirrored risk lots/money, R:R, target-on-grid and invalid-side refusal.');

const quote={bid:'1.10005',ask:'1.10007'};
for(const [side,entry,type] of [['LONG','1.1','LIMIT'],['LONG','1.100070','MARKET'],['LONG','1.100070000000000000001','STOP'],['SHORT','1.10006','LIMIT'],['SHORT','1.10005','MARKET'],['SHORT','1.1','STOP']])assert.equal(orderTypeForEntry({side,entry,quote}),type);
assert.equal(orderTypeForEntry({side:'LONG',entry:'bad',quote}),null);
assert.equal(targetForRR({side:'LONG',entry:'1.1',sl:'1.099',rr:'1.25',tickSize:'0.00001'}),'1.10125');
const converted=plannedEstimate({side:'LONG',entry:'150',sl:'149',tp:'152',riskPercent:'1',balance:'10000',profile:{...profile,quoteCurrency:'JPY'}});
assert.equal(converted.valid,false);assert.equal(converted.lots,null);assert.equal(converted.riskMoney,null);assert.match(converted.reason,/Conversion preview unavailable/);
console.log('PASS exact Bid/Ask order-type proposal, 1.25R grid target and no invented USD conversion estimate.');

import assert from 'node:assert/strict';
import {analyticsPagePath,validateAnalyticsPage} from '../src/tickAlpha/client.js';

assert.equal(analyticsPagePath('session:alpha'),
  '/sessions/session%3Aalpha/analytics/pages?limit=32&offset=0');
assert.equal(analyticsPagePath('session:alpha',{limit:16,offset:64,revision:9}),
  '/sessions/session%3Aalpha/analytics/pages?limit=16&offset=64&revision=9');
assert.throws(()=>analyticsPagePath('session:alpha',{limit:65}),/Invalid analytics page request/);
assert.throws(()=>analyticsPagePath('session:alpha',{offset:-1}),/Invalid analytics page request/);

const building={artifact:'BTL-OBSERVED-ANALYTICS-PAGE-1',sessionId:'session:alpha',revision:9,
  status:'BUILDING',processedEvents:128,totalEvents:256,completed:[],nextTradeOffset:null};
assert.equal(validateAnalyticsPage(building,'session:alpha'),building);
const complete={artifact:'BTL-OBSERVED-ANALYTICS-PAGE-1',sessionId:'session:alpha',revision:9,
  status:'COMPLETE',metrics:{tradeCount:65},completed:[{id:'order:64',status:'CLOSED'}],
  nextTradeOffset:65,account:{balance:'10000'},provenance:{revision:9}};
assert.equal(validateAnalyticsPage(complete,'session:alpha',{limit:1,offset:64,revision:9}),complete);
assert.throws(()=>validateAnalyticsPage(complete,'session:alpha',{revision:8}),/revision changed/);
assert.throws(()=>validateAnalyticsPage({...complete,completed:[{},{}]},'session:alpha',{limit:1}),/invalid analytics page/);
assert.throws(()=>validateAnalyticsPage({...building,processedEvents:257},'session:alpha'),/build progress/);

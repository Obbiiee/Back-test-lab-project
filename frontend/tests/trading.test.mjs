import assert from 'node:assert/strict';
import {initialAccount,placeOrder,closePosition,processCandle,validateOrder,pnl} from '../src/trading/simulator.js';
const candle=(time,open,high=open,low=open,close=open)=>({time,open,high,low,close});
const order=(fields={})=>({id:'position',side:'Buy',type:'Market',size:1,entry:2000,sl:1990,tp:2020,...fields});
assert.ok(validateOrder(order({type:'Limit',entry:2010}),2000));
assert.ok(validateOrder(order({side:'Sell',sl:1990}),2000));
assert.ok(validateOrder(order({size:0}),2000));
assert.equal(validateOrder(order(),2000),'');
let account=placeOrder(initialAccount(),order(),candle(60,2000));
assert.equal(account.positions.length,1);assert.equal(pnl(account.positions[0],2005),500);
account=processCandle(account,candle(120,2000,2025,1999,2023));
assert.equal(account.balance,102000);assert.equal(account.trades[0].reason,'Take profit');assert.equal(account.positions.length,0);
let stop=placeOrder(initialAccount(),order(),candle(60,2000));
stop=processCandle(stop,candle(120,1980,1988,1970,1975));
assert.equal(stop.balance,98000,'Stop fills at opening gap, not an unavailable stop price');
let ambiguous=placeOrder(initialAccount(),order(),candle(60,2000));
ambiguous=processCandle(ambiguous,candle(120,2000,2025,1985,2000));
assert.equal(ambiguous.balance,99000,'OHLC cannot order two touches: conservative stop wins');
let limit=placeOrder(initialAccount(),order({type:'Limit',entry:1995,sl:1980,tp:2010}),candle(60,2000));
assert.equal(limit.positions.length,0);assert.equal(limit.orders.length,1);
limit=processCandle(limit,candle(120,1990,2000,1985,1997));
assert.equal(limit.positions[0].entry,1990,'Limit opening gap improves entry');assert.equal(limit.orders.length,0);
assert.equal(limit.positions.length,1,'A pre-entry high/low does not establish an entry-bar exit');
let sell=placeOrder(initialAccount(),order({side:'Sell',type:'Stop',entry:1995,sl:2010,tp:1970}),candle(60,2000));
sell=processCandle(sell,candle(120,1990,1998,1985,1993));
assert.equal(sell.positions[0].entry,1990);
sell=processCandle(sell,candle(180,1993,1998,1965,1970));assert.equal(sell.balance,102000);
let partial=placeOrder(initialAccount(),order(),candle(60,2000));
partial=closePosition(partial,'position',2010,120,'Manual close',.5);
assert.equal(partial.balance,100500);assert.equal(partial.positions[0].size,.5);assert.equal(partial.trades[0].size,.5);
partial=closePosition(partial,'position',2020,180);assert.equal(partial.balance,101500);
const same=processCandle(partial,candle(180,2000));assert.strictEqual(processCandle(same,candle(180,1980)),same,'A candle is settled only once');
let tick=placeOrder(initialAccount(),order(),candle(60,2000));
tick=processCandle(tick,candle(60,2000,2005,1980,2000),true);assert.equal(tick.positions.length,1,'Live ticks ignore earlier cumulative OHLC');
tick=processCandle(tick,candle(60,1990),true);assert.equal(tick.trades[0].reason,'Stop loss');
let targets=placeOrder(initialAccount(),order({partials:[{id:'target-1',price:2005,percent:25},{id:'target-2',price:2010,percent:25}]}),candle(60,2000));
targets=processCandle(targets,candle(120,2000,2012,1995,2008));
assert.equal(targets.positions[0].size,.5);assert.equal(targets.positions[0].partials.length,0);assert.equal(targets.balance,100375);
targets=processCandle(targets,candle(180,2008,2025,2000,2020));assert.equal(targets.balance,101375);assert.equal(targets.trades.length,3);
assert.ok(validateOrder(order({partials:[{id:'bad',price:2005,percent:100}]}),2000));
assert.ok(validateOrder(order({partials:[{id:'bad',price:2025,percent:25}]}),2000));
console.log('PASS: buy/sell orders, market/limit/stop fills, SL/TP, gaps, conservative OHLC handling, partial closes, live ticks and duplicate-candle protection.');
// Opening crossings precede later intrabar reversals; observed tick gaps use the supplied price.
for(const side of ['Buy','Sell']) {
  const buy=side==='Buy',entry=2,sl=buy?1:3,tp=buy?3:1;
  for(const tickMode of [false,true]) {
    for(const reason of ['Take profit','Stop loss']) {
      const jump=reason==='Take profit'?(buy?4:.5):(buy?.5:4);
      let state=placeOrder(initialAccount(),order({side,entry,sl,tp}),candle(60,entry));
      state=processCandle(state,tickMode?candle(61,entry,5,.1,jump):candle(120,jump,5,.1,entry),tickMode);
      assert.equal(state.trades[0].reason,reason);
      assert.equal(state.trades[0].exit,jump);
      assert.equal(state.balance,100000+(jump-entry)*(buy?1:-1)*100);
      assert.equal(state.positions.length,0);
    }
    for(const type of ['Limit','Stop']) {
      const level=type==='Limit'?(buy?1:3):(buy?3:1),jump=level===1?.5:4;
      let state=placeOrder(initialAccount(),order({side,type,entry:level,sl:null,tp:null}),candle(60,entry));
      state=processCandle(state,candle(120,jump),tickMode);
      assert.equal(state.positions[0].entry,jump,`${side} ${type} gap entry`);
      assert.equal(state.orders.length,0);
    }
  }
}
let gapPartials=placeOrder(initialAccount(),order({entry:1,sl:.5,tp:3,partials:[{id:'p',price:2,percent:25}]}),candle(60,1));
gapPartials=processCandle(gapPartials,candle(120,4,4,.25,1));
assert.deepEqual(gapPartials.trades.map(t=>[t.reason,t.exit]),[['Partial take profit',4],['Take profit',4]]);
assert.equal(gapPartials.balance,100300);
assert.strictEqual(processCandle(gapPartials,candle(120,1)),gapPartials);
console.log('PASS symmetric first supplied price: entries, TP/SL, opening precedence, tick gaps, partials and balance.');
for(const side of ['Buy','Sell'])for(const type of ['Limit','Stop']) {
  const buy=side==='Buy',limit=type==='Limit',level=limit?(buy?1:3):(buy?3:1);
  const jump=level===1?.5:4,sl=buy?.75:3.5,tp=buy?3.5:.75;
  let state=placeOrder(initialAccount(),order({side,type,entry:level,sl,tp}),candle(60,2));
  state=processCandle(state,candle(120,jump,4,.5,2));
  assert.equal(state.trades[0].entry,jump);
  assert.equal(state.trades[0].exit,jump);
  assert.equal(state.trades[0].reason,limit?'Stop loss':'Take profit');
  assert.equal(state.balance,100000,'Entry and immediate opening exit use the same supplied price');
}

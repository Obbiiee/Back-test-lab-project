import assert from 'node:assert/strict';
import {planningIntent} from '../src/tickAlpha/planningIntent.js';
import {createServer} from 'vite';
import {renderToStaticMarkup} from 'react-dom/server';
import {RiskRewardController} from '../src/trading/RiskRewardController.js';
const long={type:'long-position',points:[{time:1,price:2000.125},{time:2,price:1998.25},{time:3,price:2004.75}],quantity:999,accountSize:999999,riskValue:80};
const before=JSON.stringify(long);
assert.deepEqual(planningIntent(long),{side:'LONG',workflow:'PLANNED',orderType:'LIMIT',entry:'2000.125',sl:'1998.25',tp:'2004.75'});
assert.equal(JSON.stringify(long),before);
assert.deepEqual(planningIntent(long,{tickSize:'0.01'}),{side:'LONG',workflow:'PLANNED',orderType:'LIMIT',entry:'2000.13',sl:'1998.25',tp:'2004.75'});
assert.equal(planningIntent(long,{tickSize:'0.25'}).entry,'2000.25');
assert.throws(()=>planningIntent({...long,points:[{price:1},{price:.999},{price:1.001}]},{tickSize:'0.01'}),/collapse/);
assert.throws(()=>planningIntent(long,{tickSize:'0'}),/price grid/);
assert.equal(JSON.stringify(long),before,'Intent rounding must never move drawing/source prices');
const geometry=new RiskRewardController().create('long-position',{time:120,price:2000},{x:1,y:100},{coordinateToPrice:y=>2100-y},[{time:60},{time:120}], 'actual-geometry');
assert.equal(geometry.points.length,4);assert.deepEqual(planningIntent(geometry),{side:'LONG',workflow:'PLANNED',orderType:'LIMIT',entry:'2000',sl:'1952',tp:'2048'});
assert.deepEqual(planningIntent({...long,type:'short-position',points:[{price:2000},{price:2002},{price:1996}]}),{side:'SHORT',workflow:'PLANNED',orderType:'LIMIT',entry:'2000',sl:'2002',tp:'1996'});
assert.deepEqual(planningIntent(long,{protocol:true}),{side:'LONG',workflow:'PLANNED',orderType:'LIMIT',entry:'2000.125',sl:'1998.25'});
for(const bad of [null,{...long,type:'trend-line'},{...long,points:[]},{...long,points:[{price:2000},{price:2001},{price:2002}]},{...long,points:[{price:2000},{price:NaN},{price:2002}]}])assert.throws(()=>planningIntent(bad));
// Render actual adapted presentation: preserve wire precision and escape text;
// clicking a side is a draft callback, not a provider/financial command.
const server=await createServer({server:{middlewareMode:true},appType:'custom'});
try{
  const {DirectionQuotes,ReviewedIntent}=await server.ssrLoadModule('/src/tickAlpha/AlphaOrderPresentation.jsx');
  const callbacks=[],exact='2000.123456789012345678';
  const quote=DirectionQuotes({side:'LONG',quote:{ask:exact,bid:'1999.99'},disabled:false,onChange:s=>callbacks.push(s)});
  const html=renderToStaticMarkup(quote);
  assert.ok(html.includes(exact)&&html.includes('Observed Ask')&&html.includes('Observed Bid'));
  quote.props.children[1].props.onClick();assert.deepEqual(callbacks,['SHORT']);
  assert.ok(DirectionQuotes({side:'SHORT',disabled:true,onChange(){}}).props.children.every(x=>x.props.disabled));
  const reviewed=renderToStaticMarkup(ReviewedIntent({payload:{side:'SHORT',orderType:'LIMIT',entry:exact,sl:'2002',tp:'1996',quantity:'0.01',riskPercent:'1'},methodName:'<img src=x onerror=alert(1)>',riskBasis:'10000.0001'}));
  assert.ok(reviewed.includes(exact)&&reviewed.includes('10000.0001')&&reviewed.includes('&lt;img'));
  assert.ok(!reviewed.includes('<img'));
}finally{await server.close();}
console.log('PASS S-5 drawing-to-draft only, Long/Short orientation/refusal, Protocol target/risk ownership, exact quote/review display, intent callbacks and escaped user text.');

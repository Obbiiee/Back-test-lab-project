import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { analyzeAccount, utcTime, sizeTolerance } from '../src/trading/backtestAnalysis.js';
import { exportExitRecords, exportCompletedPositions, downloadCsv } from '../src/trading/backtestExport.js';
import { requestAccountReset } from '../src/trading/replayResetGuard.js';
import { initialAccount, placeOrder, closePosition, processCandle } from '../src/trading/simulator.js';
const candle = (time, close) => ({ time, open: close, high: close, low: close, close });
const order = id => ({ id, side: 'Buy', type: 'Market', size: 1, tags: '黄金, test', strategy: 'Breakout', notes: 'line 1, "quote"\nbaris kedua' });
let account = placeOrder(initialAccount(), order('a'), candle(60, 2000));
account = closePosition(account, 'a', 2010, 120, 'Manual close', .5);
let projection = analyzeAccount(account);
assert.equal(projection.summary.completed, 0); assert.equal(projection.summary.winRate, null);
assert.equal(projection.summary.realizedPnl, 500); assert.equal(projection.groups[0].status, 'Open / partial');
assert.equal(projection.issues.length, 0); assert.ok(projection.reconciliation.reconciled);
account = closePosition(account, 'a', 2020, 180);
projection = analyzeAccount(account);
assert.equal(projection.summary.exitRecords, 2); assert.equal(projection.summary.completed, 1);
assert.equal(projection.summary.realizedPnl, 1500); assert.equal(projection.completedPositions[0].duration, 120);
assert.equal(projection.summary.winRate, 100); assert.equal(projection.summary.profitFactor, Infinity);
for (const [id, exit] of [['loss', 1995], ['be', 2000]]) {
  account = placeOrder(account, order(id), candle(240, 2000)); account = closePosition(account, id, exit, 300);
}
projection = analyzeAccount(account);
assert.deepEqual([projection.summary.completed, projection.summary.winners, projection.summary.losers, projection.summary.breakEven], [3,1,1,1]);
assert.equal(projection.summary.winRate, 100/3); assert.equal(projection.summary.averageWin, 1500);
assert.equal(projection.summary.averageLoss, 500); assert.equal(projection.summary.expectancy, 1000/3);
assert.equal(projection.summary.profitFactor, 3); assert.equal(projection.summary.maxDrawdown, 500);
assert.equal(projection.summary.drawdownPercent, 100*500/101500);
assert.deepEqual(projection.balanceEvents.map(event=>event.balance), [100000,100500,101500,101000,101000]);
assert.ok(projection.reconciliation.reconciled);
const frozen = structuredClone(account); Object.freeze(frozen); Object.freeze(frozen.trades); frozen.trades.forEach(Object.freeze);
assert.deepEqual(analyzeAccount(frozen), projection);
assert.deepEqual(analyzeAccount(JSON.parse(JSON.stringify(account))), projection, 'Persisted account reconstruction');
const edited = {...account,trades:account.trades.map(row=>({...row,notes:'new note'}))};
assert.deepEqual(analyzeAccount(edited).summary, projection.summary, 'Notes are not financial inputs');
assert.deepEqual(analyzeAccount({...account,lastTime:999999, timeframe:'1h', hiddenCandles:[{close:0,volume:999}]}), projection, 'Cursor, timeframe and hidden future are not analytics inputs');
const empty = analyzeAccount(initialAccount());
assert.equal(empty.summary.profitFactor,null); assert.equal(empty.summary.winRate,null); assert.equal(empty.summary.expectancy,null);
assert.equal(empty.summary.maxDrawdown,0); assert.ok(empty.reconciliation.reconciled);
const beAccount = {...initialAccount(),trades:[{...account.trades.at(-1),pnl:1e-9}],balance:100000+1e-9};
assert.equal(analyzeAccount(beAccount).summary.breakEven,1);
const pending = placeOrder(initialAccount(), {...order('pending'),type:'Limit',entry:1990}, candle(60,2000));
assert.equal(analyzeAccount({...pending,orders:[]}).summary.completed,0,'Cancelled order is not a completed position');
const wrongBalance = analyzeAccount({...account,balance:account.balance+1});
assert.equal(wrongBalance.reconciliation.reconciled,false); assert.ok(wrongBalance.issues.some(issue=>issue.message.includes('reconcile')));
const row = account.trades.at(-1), base = {...initialAccount(), balance:100000, trades:[row]};
for (const fields of [{positionId:undefined},{initialSize:undefined},{size:.5},{pnl:NaN},{entryTime:Infinity},{exitTime:200},{id:null},{entry:NaN}]) {
  const result=analyzeAccount({...base,trades:[{...row,...fields}]});
  assert.equal(result.summary.completed,0); assert.ok(result.issues.length); assert.equal(result.groups.length,1);
}
assert.equal(analyzeAccount({...base,trades:[null]}).summary.realizedPnl,null);
assert.equal(analyzeAccount({...base,trades:[{...row,pnl:Infinity}]}).balanceEvents.at(-1).balance,null);
assert.equal(analyzeAccount({...base,trades:[row,{...row,positionId:'another'}]}).summary.completed,0,'Duplicate identities invalidate both groups');
assert.equal(analyzeAccount({...base,trades:[{...row,size:1+5e-10}]}).summary.completed,1);
assert.equal(analyzeAccount({...base,trades:[{...row,size:1+2e-9}]}).summary.completed,0);
assert.equal(sizeTolerance(100),100*1e-9); assert.equal(utcTime(NaN),null);
assert.equal(analyzeAccount({...base,initialBalance:-100,balance:-100}).summary.drawdownPercent,null);
const partials=account.trades.slice(0,2);
assert.equal(analyzeAccount({...base,trades:[partials[0],{...partials[1],entry:2001}]}).summary.completed,0);
assert.equal(analyzeAccount({...base,trades:[partials[1],partials[0]]}).summary.completed,0);
assert.ok(analyzeAccount({...base,trades:[partials[0]],positions:[{id:'a',size:.25}]}).issues.length);

// Independent CSV parser verifies actual fields, not just substring assertions.
function parseCsv(text) {
  const rows=[]; let row=[],field='',quoted=false;
  for(let i=1;i<text.length;i++) {const c=text[i]; if(c==='"'){if(quoted&&text[i+1]==='"'){field+='"';i++;}else quoted=!quoted;}else if(c===','&&!quoted){row.push(field);field='';}else if(c==='\r'&&!quoted&&text[i+1]==='\n'){row.push(field);rows.push(row);row=[];field='';i++;}else field+=c;}
  return rows;
}
const before=JSON.stringify(account), raw=parseCsv(exportExitRecords(account.trades));
assert.equal(raw.length,account.trades.length+1); assert.equal(raw[1][15],account.trades[0].notes);
assert.equal(raw[1][13],account.trades[0].tags); assert.equal(raw[1][5],'1970-01-01T00:01:00.000Z');
assert.equal(Number(raw[1][10]),500);
const complete=parseCsv(exportCompletedPositions(projection));
assert.equal(complete.length,4); assert.equal(Number(complete[1][9]),2);
assert.equal(JSON.parse(complete[1][14])[0].value,account.trades[0].notes);
assert.equal(JSON.stringify(account),before,'Exports and projection do not mutate canonical state');
assert.equal(parseCsv(exportExitRecords([{entryTime:NaN}]))[1][5],'Invalid UTC timestamp: NaN');
const originalDocument=globalThis.document,originalSetTimeout=globalThis.setTimeout,originalCreate=URL.createObjectURL,originalRevoke=URL.revokeObjectURL;
let blob,clicked=false,removed=false,cleanup,revoked=false;
try {
  URL.createObjectURL=value=>{blob=value;return 'blob:test';};URL.revokeObjectURL=value=>{assert.equal(value,'blob:test');revoked=true;};
  globalThis.setTimeout=(callback,delay)=>{assert.equal(delay,1000);cleanup=callback;};
  const link={click(){clicked=true;},remove(){removed=true;}};
  globalThis.document={createElement:()=>link,body:{append:element=>assert.equal(element,link)}};
  const contents=exportExitRecords(account.trades);downloadCsv(contents,'exit.csv');
  assert.deepEqual(new Uint8Array(await blob.arrayBuffer()),new TextEncoder().encode(contents),'Blob preserves exact UTF-8 bytes including BOM');assert.equal(blob.type,'text/csv;charset=utf-8');
  assert.equal(link.download,'exit.csv');assert.equal(link.href,'blob:test');assert.ok(clicked&&removed);assert.equal(revoked,false);cleanup();assert.ok(revoked);
} finally {globalThis.document=originalDocument;globalThis.setTimeout=originalSetTimeout;URL.createObjectURL=originalCreate;URL.revokeObjectURL=originalRevoke;}

let pendingAction=null,resets=0,replay={active:true,cursor:42};
const stateBefore=JSON.stringify({account,replay});
const reset=()=>{resets++;account=initialAccount();replay={active:false,cursor:null};};
requestAccountReset(account,reset,action=>pendingAction=action);
assert.equal(resets,0); pendingAction=null;
assert.equal(JSON.stringify({account,replay}),stateBefore,'Cancel performs no account/replay operation');
requestAccountReset(account,reset,action=>pendingAction=action);pendingAction();
assert.equal(resets,1);assert.deepEqual(account,initialAccount());assert.equal(replay.active,false);
requestAccountReset(account,reset,()=>assert.fail('Empty account needs no confirmation'));assert.equal(resets,2);
for (const key of ['orders','positions','trades']) {let asked=false;requestAccountReset({...initialAccount(),[key]:[{}]},()=>assert.fail('Activity must be gated'),()=>asked=true);assert.ok(asked);}

// Real execution -> projection, including a pending gap and conservative stop-first.
let simulated=placeOrder(initialAccount(),{...order('limit'),type:'Limit',entry:1995,sl:1980,tp:2010},candle(60,2000));
simulated=processCandle(simulated,{time:120,open:1990,high:2015,low:1970,close:1997});
assert.equal(simulated.positions.length,1);
simulated=processCandle(simulated,{time:180,open:1997,high:2020,low:1970,close:2000});
assert.equal(simulated.trades[0].reason,'Stop loss');assert.ok(analyzeAccount(simulated).reconciliation.reconciled);
const panel=readFileSync(new URL('../src/trading/PositionsPanel.jsx',import.meta.url),'utf8');
assert.ok(panel.includes('[tab,trades,positions,initialBalance,balance]'),'Memo ignores cursor-only account changes');
assert.ok(panel.includes("items=tab==='Analysis'?[]"),'Analysis avoids re-copying/sorting history on cursor-only renders');
assert.ok(readFileSync(new URL('../src/trading/BacktestAnalysis.jsx',import.meta.url),'utf8').includes('memo(BacktestAnalysis)'),'Stable projection/trades/note callback also skip analytics UI rendering');
const workspace=readFileSync(new URL('../src/FigmaWorkspace.jsx',import.meta.url),'utf8');
assert.ok(workspace.includes('requestReset(beginReplay)')&&workspace.includes('requestReset(exitReplay)'),'Both existing reset actions must pass the guard');
const analysisSource=readFileSync(new URL('../src/trading/backtestAnalysis.js',import.meta.url),'utf8');
assert.ok(!/from|localStorage|processCandle|setAccount/.test(analysisSource),'Pure projection has no external state/execution dependencies');
console.log('PASS Phase14: canonical projection, partial grouping, financial vectors, drawdown, data issues, CSV roundtrip, reset gate, persistence/hidden-input independence and execution integration.');

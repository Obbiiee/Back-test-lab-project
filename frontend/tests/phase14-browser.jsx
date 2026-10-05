// Isolated test fixture; production never imports counters or test controls.
import { StrictMode, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { initialAccount, placeOrder, processCandle } from '../src/trading/simulator.js';
import CandleChart from '../src/components/CandleChart.jsx';
import { IndicatorSeriesAdapter } from '../src/indicators/IndicatorSeriesAdapter.js';
import { productionRegistry } from '../src/indicators/productionRegistry.js';
import { PlaybackScheduler } from '../src/market/PlaybackScheduler.js';
import useReplayMarket from '../src/market/useReplayMarket.js';
import useReplayPlayback from '../src/market/useReplayPlayback.js';
import useTrading from '../src/trading/useTrading.js';
import PositionsPanel from '../src/trading/PositionsPanel.jsx';
import OrderTicket from '../src/trading/OrderTicket.jsx';
import Journal from '../src/trading/Journal.jsx';
import ReplayResetConfirmation from '../src/trading/ReplayResetConfirmation.jsx';
import { requestAccountReset } from '../src/trading/replayResetGuard.js';
import { riskRewardOrderSeed } from '../src/trading/riskReward.js';
import { analyzeAccount } from '../src/trading/backtestAnalysis.js';
import '../src/FigmaWorkspace.css';
import '../src/FxWorkspace.css';
const charts = new Set(), schedulers = new Set(); let analysisCalculations = 0, currentChart;
const attach = IndicatorSeriesAdapter.prototype.attach;
IndicatorSeriesAdapter.prototype.attach = function(chart) { if(chart){charts.add(chart);currentChart=chart;}return attach.call(this,chart); };
const commit = PlaybackScheduler.prototype.commit;
PlaybackScheduler.prototype.commit = function(...args) { schedulers.add(this);return commit.apply(this,args); };
const downloads=[];
document.addEventListener('click',async event=>{const link=event.target.closest?.('a[download]');if(link){const contents=await fetch(link.href).then(response=>response.text());downloads.push({filename:link.download,contents});}});
export default function Harness() {
  const [frame,setFrame]=useState('15m'),[tab,setTab]=useState('Open Positions'),[terminal,setTerminal]=useState(true),[height,setHeight]=useState(300);
  const [mode,setMode]=useState('none'),[ticket,setTicket]=useState(null),[journal,setJournal]=useState(false),[reset,setReset]=useState(null),[report,setReport]=useState(''),[speed,setSpeed]=useState(1),[indicators,setIndicators]=useState([]);
  const replay=useReplayMarket(frame),trading=useTrading(replay.raw,replay.active,replay.transition),{playing,setPlaying}=useReplayPlayback(replay,speed);
  const proxyTrades=useMemo(()=>new Proxy(trading.account.trades,{get(target,key,receiver){if(key==='entries')return ()=>{analysisCalculations++;return target.entries();};return Reflect.get(target,key,receiver);}}),[trading.account.trades]);
  const observedTrading={...trading,account:{...trading.account,trades:proxyTrades}};
  const request=action=>requestAccountReset(trading.account,action,action=>setReset({action}));
  const start=async()=>{setPlaying(false);const time=await replay.start('2024-06-03T12:00:00Z');trading.reset(time);};
  const exit=()=>{setPlaying(false);replay.stop();trading.reset(0);};
  const resize=event=>{const startY=event.clientY,initial=height;const move=point=>setHeight(Math.max(120,Math.min(650,initial+startY-point.clientY)));const end=()=>{window.removeEventListener('pointermove',move);window.removeEventListener('pointerup',end);};window.addEventListener('pointermove',move);window.addEventListener('pointerup',end);};
  const snapshot=()=>setReport(JSON.stringify({account:trading.account,analysis:analyzeAccount(trading.account),revision:replay.transition.revision,last:replay.raw.at(-1)?.time,active:replay.active,playing,chartCount:charts.size,schedulerCount:schedulers.size,analysisCalculations,downloads,frame,range:currentChart?.timeScale().getVisibleLogicalRange()},null,2));
  return <><div style={{display:'flex',flexWrap:'wrap',gap:8,padding:8}}>
    <button onClick={()=>request(start)}>Start replay</button><button onClick={()=>request(exit)}>Exit replay</button>
    <button onClick={()=>{setPlaying(false);replay.step();}}>Next candle</button><button onClick={()=>setPlaying(value=>!value)}>Play / Pause</button>
    <select aria-label="Speed" value={speed} onChange={event=>setSpeed(Number(event.target.value))}>{[1,2,5,10,20].map(n=><option key={n}>{n}</option>)}</select>
    <button onClick={()=>setFrame(frame==='15m'?'1h':'15m')}>Timeframe</button><button onClick={()=>replay.loadOlder()}>Prepend history</button>
    <button onClick={()=>setTerminal(value=>!value)}>Terminal mount toggle</button><button onClick={()=>setJournal(value=>!value)}>Journal</button><button onClick={snapshot}>Snapshot</button>
    <button onClick={()=>setIndicators(productionRegistry.types().map(type=>({id:type,type,parameters:{},visible:true})))}>Seven indicators</button>
    {['long-position','short-position'].map(tool=><button key={tool} onClick={()=>setMode(tool)}>{tool}</button>)}
    <button onClick={()=>setTicket({side:'Buy'})}>Buy ticket</button><button onClick={()=>setTicket({side:'Sell'})}>Sell ticket</button>
    <button onClick={()=>{
      const results=[];
      for(const side of ['Buy','Sell'])for(const type of ['TP','SL','Limit','Stop'])for(const tick of [false,true]){
        const buy=side==='Buy',pending=type==='Limit'||type==='Stop';
        const level=type==='Limit'?(buy?1:3):(buy?3:1);
        const jump=type==='SL'?(buy?.5:4):(level===1?.5:4);
        const seed={id:'gap-fixture',side,type:pending?type:'Market',size:1,entry:pending?level:2,sl:pending?null:buy?1:3,tp:pending?null:buy?3:1};
        const account=placeOrder(initialAccount(),seed,{time:60,close:2});
        const result=processCandle(account,{time:120,open:jump,high:5,low:.1,close:tick?jump:2},tick);
        const price=pending?result.positions[0]?.entry:result.trades[0]?.exit;
        const reason=pending?type:result.trades[0]?.reason;
        const pass=price===jump&&(pending||reason===(type==='TP'?'Take profit':'Stop loss'));
        results.push({side,type,tick,expected:jump,price,reason,pass});
      }
      setReport(JSON.stringify({policy:'FIRST_SUPPLIED_PRICE / MODELLED',pass:results.every(item=>item.pass),results},null,2));
    }}>Gap policy scenarios</button>
    <button onClick={()=>{localStorage.setItem('backtest-paper-account-v1',JSON.stringify({...initialAccount(),balance:100012,trades:[{id:'legacy-exit',side:'Buy',entry:2000,exit:2001,entryTime:60,exitTime:120,size:.1,pnl:12,notes:'Legacy محفوظ'}]}));window.location.reload();}}>Load legacy fixture</button>
    <button onClick={()=>{currentChart.timeScale().setVisibleLogicalRange({from:30,to:80});}}>Pan / zoom range</button>
  </div><div style={{height:410,position:'relative'}}><CandleChart candles={replay.candles} transition={replay.transition} sessionId={'XAUUSD-replay-'+frame} viewportKey={frame} onLoadOlder={replay.loadOlder} indicatorRegistry={productionRegistry} indicatorInstances={indicators}
    positions={trading.account.positions} orders={trading.account.orders} simulatedTrades={trading.account.trades} drawingMode={mode} onDrawingModeChange={setMode} chartPreferences={{showVolume:true,showCrosshair:true,showGrid:true}}
    onCreateOrder={object=>setTicket(riskRewardOrderSeed(object,trading.quote?.close))}/></div>
    {terminal&&<div style={{height,display:'flex',flexDirection:'column'}}><PositionsPanel trading={observedTrading} tab={tab} onTab={setTab} onResize={resize} onHide={()=>setTerminal(false)} onEdit={()=>{}}/></div>}
    {ticket&&<OrderTicket side={ticket.side} seed={ticket} price={trading.quote?.close} balance={trading.account.balance} initialBalance={trading.account.initialBalance} onClose={()=>setTicket(null)} onPickPrice={()=>{}} onPlace={(order,openJournal)=>{trading.place(order);setTab(order.type==='Market'?'Open Positions':'Pending Orders');if(openJournal)setJournal(true);}}/>}
    {journal&&<Journal account={trading.account} onNotes={trading.notes} onClose={()=>setJournal(false)}/>}
    {reset&&<ReplayResetConfirmation onCancel={()=>setReset(null)} onConfirm={()=>{const action=reset.action;setReset(null);action();}}/>}
    <pre id="evidence" style={{maxHeight:170,overflow:'auto'}}>{report}</pre>
  </>;
}
const root=import.meta.hot?.data.root??createRoot(document.getElementById('root'));if(import.meta.hot)import.meta.hot.data.root=root;
root.render(<StrictMode><Harness/></StrictMode>);

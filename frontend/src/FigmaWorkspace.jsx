import Icon from './workspace/WorkspaceIcon.jsx';
import { DRAWING_SPECS } from './drawings/DrawingTypes.js';
import IndicatorControls from './components/IndicatorControls.jsx';
import { productionRegistry } from './indicators/productionRegistry.js';
import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import { RISK_REWARD_TOOLS } from "./trading/RiskRewardController";
import useGoldMarket from "./market/useGoldMarket";
import {TIMEFRAMES} from "./market/candles";
import OrderTicket from "./trading/OrderTicket";
import PositionsPanel from "./trading/PositionsPanel";
import {money} from "./trading/format";
import useTrading from "./trading/useTrading";
import Journal from "./trading/Journal";
import ReplayResetConfirmation from './trading/ReplayResetConfirmation';
import {requestAccountReset} from './trading/replayResetGuard';
import useReplayPlayback from './market/useReplayPlayback';
import {PLAYBACK_SPEEDS} from './market/PlaybackScheduler';
import useReplayMarket from "./market/useReplayMarket";
import {riskRewardOrderSeed} from "./trading/riskReward";
import useNews from './news/useNews.js';
import NewsPanel from './news/NewsPanel.jsx';
import { NewsContext } from './news/NewsContext.js';
import WorkspaceModal from "./workspace/WorkspaceModal.jsx";
import usePanelResize from "./workspace/usePanelResize.js";
import { readFavorites, FAVORITES_KEY } from './workspacePreferences.js';
import "./FigmaWorkspace.css";
import "./FxWorkspace.css";
import "./workspace/designTokens.css";
const CandleChart=lazy(()=>import('./components/CandleChart'));

const toolGroups = {
  trend: [{ title: "LINES", items: ["Trend Line", "Horizontal Line", "Vertical Line"] }, { title: "SHAPES", items: ["Rectangle", "Arrow", "Text"] }, { title: "RESEARCH", items: ["Fibonacci Retracement", "Measure"] }],
  cursor: [{ title: "", items: ["Cross", "Dot", "Arrow Cursor"] }],
  measure: [{ title: "POSITION PLANNING", items: ["Long Position", "Short Position"] }],
};
const TOOL_ICONS = { "Trend Line": "trend", "Horizontal Line": "horizontal", "Vertical Line": "vertical", Rectangle: "rectangle", Arrow: "arrow", Text: "text", "Fibonacci Retracement": "fib", Measure: "ruler", "Long Position": "long", "Short Position": "short", Cross: "cursor", Dot: "cursor", "Arrow Cursor": "arrow" };
const TOOL_MODES = Object.freeze(Object.assign(Object.create(null), { Cross: 'none', Dot: 'cursor-dot', 'Arrow Cursor': 'cursor-arrow', Arrow: 'arrow', 'Trend Line': 'trend-line', 'Horizontal Line': 'horizontal-line', 'Vertical Line': 'vertical-line', Rectangle: 'rectangle', 'Fibonacci Retracement': 'fibonacci-retracement', Text: 'text', Measure: 'measure', 'Long Position': 'long-position', 'Short Position': 'short-position' }));
const resolveTool = name => TOOL_MODES[name];
function App() {
  const [indicatorInstances, setIndicatorInstances] = useState([]);
	const [drawingMode, setDrawingMode] = useState("none");
	const [chartPreferences, setChartPreferences] = useState({
		showVolume: true,
		showGrid: true,
		showCrosshair: true
	});
	const [drawingState, setDrawingState] = useState({ drawings: [], canUndo: false, canRedo: false, magnet: false, keepDrawing: false });
 const [objectsOpen, setObjectsOpen] = useState(false);
 const [chartCommand, setChartCommand] = useState(null);
	const sendChartCommand = (action) => setChartCommand({
		action,
		id: Date.now()
	});
	const [speed, setSpeed] = useState(1);
	const [notice, setNotice] = useState("");
 const [timeframe,setTimeframe]=useState(()=>{try{const saved=localStorage.getItem('backtest-workspace-interval-v1');return Object.hasOwn(TIMEFRAMES,saved)?saved:'30m';}catch{return '30m';}});
 useEffect(()=>{try{localStorage.setItem('backtest-workspace-interval-v1',timeframe);}catch{/* The current interval remains usable without storage. */}},[timeframe]);
 const [intervalOpen,setIntervalOpen]=useState(false);
 const [marketMode] = useState("live");
 const market = useGoldMarket(timeframe, marketMode === "live");
	const [activeTool, setActiveTool] = useState(null);
	const [orderTab, setOrderTab] = useState("Open Positions");
	const [tradeSide, setTradeSide] = useState("Buy");
	const [terminalOpen, setTerminalOpen] = useState(true);
 const panelResize = usePanelResize();
 const terminalHeight = panelResize.height;
	const [dialog, setDialog] = useState(null);
	const [goToOpen, setGoToOpen] = useState(false);
	const [journalOpen, setJournalOpen] = useState(false);
 const replay=useReplayMarket(timeframe);
 const {playing,setPlaying}=useReplayPlayback(replay,speed);
 const trading=useTrading(replay.loading?[]:replay.active?replay.raw:market.liveBars,replay.active,replay.active?replay.transition:undefined);
 const [newsOpen,setNewsOpen]=useState(false);
 const news=useNews({replay,trading,timeframe,setPlaying,chartCommand:setChartCommand,openPanel:setNewsOpen});
 const [quantity,setQuantity]=useState(1),[orderSeed,setOrderSeed]=useState(null),[ticketId,setTicketId]=useState(0);
 const [dateOpen,setDateOpen]=useState(false),[replayDate,setReplayDate]=useState('2024-06-03T12:00');
 const [resetRequest,setResetRequest]=useState(null);
 const [editPosition,setEditPosition]=useState(null),[editError,setEditError]=useState('');
 const pickCallback=useRef(null);
 const [favoriteStorage]=useState(()=>readFavorites());
 const [favorites,setFavorites]=useState(favoriteStorage.value);
 const [favoritesVisible,setFavoritesVisible]=useState(true),[lastTools,setLastTools]=useState({cursor:'Cross',trend:'Trend Line',measure:'Long Position'});
 const openTicket=(side=tradeSide,seed=null)=>{news.cancel();if(!trading.quote){setNotice('Loading price…');return;}setTradeSide(side);setOrderSeed(seed);setTicketId(value=>value+1);setDialog('order');};
 const fromDrawing=object=>{const seed=riskRewardOrderSeed(object,trading.quote?.close);openTicket(seed.side,seed);};
 const beginReplay=async()=>{news.cancel();setPlaying(false);try{const time=await replay.start(replayDate+'Z');trading.reset(time);setDateOpen(false);}catch{/* The replay form displays the loading error. */}};
 const exitReplay=()=>{news.cancel();setPlaying(false);replay.stop();trading.reset(market.candles.at(-1)?.time);};
 const requestReset=action=>requestAccountReset(trading.account,action,confirmedAction=>setResetRequest({action:confirmedAction}));
 const toggleFavorite=item=>setFavorites(current=>current.includes(item)?current.filter(name=>name!==item):[...current,item]);
 useEffect(()=>{if(!favoriteStorage.writable)return;try{localStorage.setItem(FAVORITES_KEY,JSON.stringify(favorites));}catch{/* In-memory favorites remain available. */}},[favorites,favoriteStorage]);
	const menu = useMemo(() => activeTool ? toolGroups[activeTool] : undefined, [activeTool]);
 const data=replay.loading?[]:replay.active?replay.candles:market.candles;
 const chooseTool = (name,group=activeTool) => { news.cancel(); const mode = resolveTool(name,group); if (mode) setDrawingMode(mode); if(group)setLastTools(current=>({...current,[group]:name}));setPlaying(false); setActiveTool(null); };
 const toolButtons = [
  { icon: "cursor", key: "cursor", title: "Cursor" },
  { icon: "trend", key: "trend", title: "Trend Line" },
  { icon: "measure", key: "measure", title: "Risk / Reward" },
  { icon: "magnet", key: "magnet", title: "Risk/Reward magnet" },
  { icon: "lock", key: "lock", title: "Lock Risk/Reward objects" },
  { icon: "eye", key: "eye", title: "Hide Risk/Reward objects" },
  { icon: "trash", key: "trash", title: "Remove Risk/Reward objects" },
 ];
	return <NewsContext.Provider value={news.context}><div className="replay-app">
      {notice && <button className="design-notice" onClick={() => setNotice("")}>{notice} ×</button>}
      {(trading.storageStatus || favoriteStorage.status) && <div className="account-storage-warning" role="alert">{[trading.storageStatus,favoriteStorage.status].filter(Boolean).join(' ')}</div>}
      <header className="main-toolbar">
        <button className="tool-icon" disabled aria-label="Back (unavailable in local workspace)"><Icon name="back" /></button>
        <div className="replay-logo"><Icon name="play" size={17} /></div>
        <button className="symbol-select" disabled title="XAUUSD local dataset"><Icon name="search" size={18} /><strong>XAUUSD</strong></button>
        <button className="round-plus" disabled aria-label="Add symbol (unavailable)"><Icon name="plus" size={16} /></button>
        <div className="divider" />
        <div className="interval-picker"><button className="time-button active" onClick={()=>setIntervalOpen(value=>!value)} aria-label="Interval" aria-expanded={intervalOpen}>{timeframe}</button>{intervalOpen&&<div className="interval-menu">{['1m','3m','5m','15m','30m','1h','2h','4h','D','W','M'].map(t=><button key={t} className={timeframe===t?'active':''} onClick={()=>{setTimeframe(t);setIntervalOpen(false);}}>{t}</button>)}</div>}</div>
        <button className="tool-icon" disabled aria-label="Candlestick chart"><Icon name="candles" size={19} /></button>
        <IndicatorControls instances={indicatorInstances} onChange={setIndicatorInstances} />
        <div className="divider" />
        <button className="nav-action" onClick={() => {
		sendChartCommand("new-layout");
		setDrawingMode("none");
	}}>New Layout</button>
        <button className="tool-icon" title="Undo Risk/Reward object" disabled={!drawingState.canUndo} onClick={() => sendChartCommand("undo")}><Icon name="undo" size={18} /></button>
        <button className="tool-icon" title="Redo Risk/Reward object" disabled={!drawingState.canRedo} onClick={() => sendChartCommand("redo")}><Icon name="redo" size={18} /></button>
        <div className="toolbar-fill" />
        <span className="workspace-name">Backtest Lab</span>
        <span className="layout-name"><i /> Design workspace⌄</span>
        <button className="tool-icon optional-control" disabled aria-label="Quick actions (unavailable)"><Icon name="bolt" /></button>
        <button className="tool-icon optional-control" disabled aria-label="Extensions (unavailable)"><Icon name="hex" /></button>
        <button className="tool-icon" title="Download chart" onClick={() => sendChartCommand("screenshot")}><Icon name="camera" /></button>
        <button className="editor-button" disabled title="Editor unavailable in local v1.0"><Icon name="code" size={18} />Editor</button>
        <button className="tool-icon optional-control" disabled aria-label="Dark theme"><Icon name="moon" /></button>
        <button className="tool-icon" title="Fullscreen" onClick={() => document.fullscreenElement ? document.exitFullscreen() : document.documentElement.requestFullscreen()}><Icon name="expand" /></button>
      </header>

      <section className={`main-stage ${terminalOpen ? "" : "terminal-closed"}  ${journalOpen?"journal-open":""}`} style={{ "--terminal-height": `${terminalHeight}px` }}>
        <aside className="left-tools">
          {toolButtons.filter(tool=>tool.key!=='keep').map(tool=><div className="drawing-tool-slot" key={tool.key}><button title={tool.title} className={`side-tool ${activeTool===tool.key?'active':''}`} onClick={()=>{
            if(toolGroups[tool.key])chooseTool(lastTools[tool.key],tool.key);
            else sendChartCommand({'trash':'clear','lock':'lock-all','eye':'hide-all','magnet':'magnet'}[tool.key]);
          }}><Icon name={tool.icon}/></button>{toolGroups[tool.key]&&<button className="tool-expander" aria-label={`Expand ${tool.title}`} aria-expanded={activeTool===tool.key} onClick={()=>setActiveTool(activeTool===tool.key?null:tool.key)}>›</button>}</div>)}
          <button className={`side-tool ${drawingState.keepDrawing?'active':''}`} title="Keep Risk/Reward placement mode" onClick={()=>sendChartCommand('keep-drawing')}><Icon name="brush"/></button>
          <button className={`side-tool ${favoritesVisible?'active':''}`} title="Toggle favorites bar" onClick={()=>setFavoritesVisible(value=>!value)}>☆</button>
        </aside>

        <div className={"chart-shell cursor-" + drawingMode}>
          <Suspense fallback={<div className="chart-loading">Loading chart…</div>}>          <CandleChart candles={data} transition={replay.active?replay.transition:undefined} sessionId={`XAUUSD-${marketMode}-${timeframe}`} viewportKey={`XAUUSD-${replay.active?"replay":"live"}-${timeframe}`} onLoadOlder={replay.active?replay.loadOlder:market.loadOlder} positions={trading.account.positions} orders={trading.account.orders} simulatedTrades={trading.account.trades} onCreateOrder={fromDrawing} onAmendOrder={(...args)=>{news.cancel();trading.update(...args);}} onClosePosition={(...args)=>{news.cancel();trading.close(...args);}} onCancelOrder={(...args)=>{news.cancel();trading.cancel(...args);}} onTradingError={setNotice} onPriceSelect={value=>{pickCallback.current?.(value);pickCallback.current=null;setDrawingMode("none");}} drawingMode={drawingMode} onDrawingModeChange={setDrawingMode} chartPreferences={chartPreferences} onChartPreferencesChange={setChartPreferences} command={chartCommand} onDrawingStateChange={setDrawingState} indicatorRegistry={productionRegistry} indicatorInstances={indicatorInstances} news={news.chart} /></Suspense>

          <div className="chart-meta"><strong>XAU / USD · {timeframe} · Backtest Lab</strong><i /><span className="up-text">O {data.at(-1)?.open.toFixed(3)}&nbsp;&nbsp; H {data.at(-1)?.high.toFixed(3)}&nbsp;&nbsp; L {data.at(-1)?.low.toFixed(3)}&nbsp;&nbsp; C {data.at(-1)?.close.toFixed(3)}</span><small>Volume&nbsp; <b>{marketMode === "live" ? "—" : data.at(-1)?.volume}</b></small></div>
          {favoritesVisible&&favorites.length>0&&<div className="drawing-favorites" aria-label="Favorite drawing tools">{favorites.filter(name=>RISK_REWARD_TOOLS[resolveTool(name)] || DRAWING_SPECS[resolveTool(name)]).map(name=><button key={name} title={name} onClick={()=>chooseTool(name,Object.keys(toolGroups).find(group=>toolGroups[group].some(section=>section.items.includes(name))))}>{name==='Long Position'?'↗':name==='Short Position'?'↘':name==='Trend Line'?'╱':name==='Horizontal Line'?'―':name.slice(0,2)}</button>)}</div>}
          <div className="range-bar"><div>{[
		"5y",
		"1y",
		"6m",
		"3m",
		"1m",
		"5d",
		"1d"
	].map((r) => <button key={r} onClick={() => sendChartCommand(`range:${r}`)}>{r}</button>)}<button aria-label="Go to a date" onClick={()=>setDateOpen(true)}><Icon name="calendar" size={17} /></button></div><div><strong>{(data.length ? new Date(data.at(-1).time * 1e3).toISOString().slice(11, 19) : "—")} UTC</strong><button onClick={() => sendChartCommand("percent")}>%</button><button onClick={() => sendChartCommand("log")}>log</button><button className="auto-active" onClick={() => sendChartCommand("fit")}>auto</button></div></div>
          {objectsOpen && <aside className="drawing-object-tree"><header><strong>Risk/Reward objects ({drawingState.drawings.length})</strong><button onClick={() => setObjectsOpen(false)}>×</button></header>{!drawingState.drawings.length && <p>No Risk/Reward objects yet. Chart drawings use their separate controls.</p>}{drawingState.drawings.map((item, index) => <div key={item.id} className={drawingState.selectedId === item.id ? "selected" : ""}><button onClick={() => sendChartCommand("object:select:" + item.id)}>{index + 1}. {item.type.replaceAll("-", " ")}</button><button title="Edit drawing" onClick={() => sendChartCommand("object:edit:" + item.id)}>✎</button><button title={item.hidden ? "Show drawing" : "Hide drawing"} onClick={() => sendChartCommand("object:hide:" + item.id)}>{item.hidden ? "◌" : "◉"}</button><button title={item.locked ? "Unlock drawing" : "Lock drawing"} onClick={() => sendChartCommand("object:lock:" + item.id)}>{item.locked ? "🔒" : "🔓"}</button><button title="Delete drawing" onClick={() => sendChartCommand("object:delete:" + item.id)}>×</button></div>)}</aside>}
          {menu && <div className="tool-menu" aria-label="Chart tool chooser" onKeyDown={event=>{if(event.key==='Escape'){event.stopPropagation();event.currentTarget.ownerDocument.querySelector('.tool-expander[aria-expanded="true"]')?.focus();setActiveTool(null);}}}>
            {activeTool==='measure'&&<p className="tool-menu-hint">Planning previews · review in Order before placing.</p>}
            {menu.map((group,gi)=><div className="menu-group" key={gi}>{group.title&&<div className="menu-title">{group.title}</div>}{group.items.map(item=><div className="drawing-menu-row" key={item}><button aria-label={item} data-tool-type={resolveTool(item,activeTool)} data-anchor-count={DRAWING_SPECS[resolveTool(item)]?.points ?? RISK_REWARD_TOOLS[resolveTool(item,activeTool)]?.points} aria-pressed={resolveTool(item,activeTool)===drawingMode} onClick={()=>chooseTool(item)}><Icon name={TOOL_ICONS[item]} size={17}/><span>{item}</span></button><button className="about-drawing" aria-label={`About ${item}`} onClick={()=>setNotice(`${item} · ${DRAWING_SPECS[resolveTool(item)]?.points ?? RISK_REWARD_TOOLS[resolveTool(item,activeTool)]?.points??1} anchor points. Select the tool, then click on the chart.`)}>ⓘ</button><button aria-label={`Favorite ${item}`} aria-pressed={favorites.includes(item)} onClick={()=>toggleFavorite(item)}>{favorites.includes(item)?'★':'☆'}</button></div>)}</div>)}

          </div>}
        </div>

        <aside className="right-rail"><button className={dialog==='order'?'active':''} onClick={()=>openTicket()}><Icon name="order"/><span>Order</span></button><button title="Risk/Reward object tree" aria-expanded={objectsOpen} onClick={()=>setObjectsOpen(value=>!value)}><Icon name="layers"/><span>Object tree</span></button><button aria-expanded={journalOpen} onClick={()=>setJournalOpen(value=>!value)}><Icon name="journal"/><span>Journal</span></button><button aria-expanded={newsOpen} onClick={()=>setNewsOpen(value=>!value)}><Icon name="news"/><span>News</span></button><div className="rail-fill"/><button aria-label="Account information" onClick={()=>setNotice(`XAUUSD · 100 oz per lot · USD account · ${money(trading.account.initialBalance)} initial balance`)}><Icon name="settings"/></button>
        </aside>

        <section className="trade-controls">
          <button disabled={!!news.navigation} className="buy-pill" onClick={()=>openTicket('Buy')}>↗ Buy</button><button disabled={!!news.navigation} className="sell-pill" onClick={()=>openTicket('Sell')}>↘ Sell</button><div className="quantity"><input aria-label="Quantity" type="number" min="0.0001" step="any" value={quantity} onChange={event=>setQuantity(Number(event.target.value))}/></div>
          <div className="bottom-replay"><button aria-label="Bar replay" onClick={()=>{news.cancel();setDateOpen(true);}}>Ι◀</button><select aria-label="Speed" value={speed} onChange={event=>setSpeed(Number(event.target.value))}>{PLAYBACK_SPEEDS.map(value=><option key={value} value={value}>{value}×</option>)}</select><button aria-label="Go to previous candle" disabled={!!news.navigation||!replay.active||trading.account.positions.length>0||trading.account.orders.length>0||trading.account.trades.length>0} onClick={()=>{news.cancel();setPlaying(false);replay.step(-1);}}>‹</button><button aria-label="Play / Pause" aria-pressed={playing} disabled={!replay.active||replay.atEnd} onClick={()=>{news.cancel();setPlaying(value=>news.navigation?false:!value);}}>{playing?'Ⅱ':'▷'}</button><button aria-label="Replay timeframe" onClick={()=>setIntervalOpen(value=>!value)}>{timeframe}⌄</button><button aria-label="Next candle" disabled={!!news.navigation||!replay.active||replay.atEnd} onClick={()=>{news.cancel();setPlaying(false);replay.step();}}>▷Ι</button><button aria-label="Go to" onClick={()=>setGoToOpen(value=>!value)}>↱</button>{replay.active&&<button aria-label="Exit replay" onClick={()=>requestReset(exitReplay)}>×</button>}</div>
          <button className="balance" onClick={()=>setNotice(`Balance ${money(trading.account.balance)} · Equity ${money(trading.equity)}`)}>{money(trading.equity)}</button><button className="tool-icon" aria-label={terminalOpen&&panelResize.state!=="COLLAPSED"?"Hide positions and orders":"Show positions and orders"} aria-expanded={terminalOpen&&panelResize.state!=="COLLAPSED"} onClick={()=>{if(terminalOpen&&panelResize.state!=="COLLAPSED")setTerminalOpen(false);else{panelResize.restore();setTerminalOpen(true);}}}><Icon name="eye" size={17}/></button>
        </section>
        {terminalOpen&&<PositionsPanel trading={trading} interactionDisabled={!!news.navigation} onResize={panelResize.start} onResizeKeyDown={panelResize.keyDown} resizeHeight={panelResize.height} resizeState={panelResize.state} resizeMin={panelResize.min} resizeMax={panelResize.max} onHide={()=>setTerminalOpen(false)} tab={orderTab} onTab={setOrderTab} onEdit={item=>{setEditPosition({...item});setEditError('');}}/>}
        {dialog==='order'&&<OrderTicket key={ticketId} side={tradeSide} price={trading.quote?.close} balance={trading.account.balance} initialBalance={trading.account.initialBalance} initialSize={quantity} seed={orderSeed} onClose={()=>setDialog(null)} onPickPrice={(key,callback)=>{pickCallback.current=callback;setDrawingMode('order');setNotice(`Click the chart to set ${key.toUpperCase()}.`);}} onPlace={(order,journal)=>{news.cancel();trading.place(order);setOrderTab(order.type==='Market'?'Open Positions':'Pending Orders');setTerminalOpen(true);if(journal)setJournalOpen(true);}}/>}
        {newsOpen&&<NewsPanel news={news} onClose={()=>setNewsOpen(false)}/>}
        {journalOpen&&<Journal account={trading.account} onClose={()=>setJournalOpen(false)} onNotes={trading.notes}/>}
        {goToOpen&&<div className="session-goto"><strong>Go to</strong><button onClick={()=>{setGoToOpen(false);setDateOpen(true);}}>Select date and time</button>{replay.active&&<button onClick={()=>{news.cancel();setPlaying(false);replay.step();setGoToOpen(false);}}>Next candle</button>}</div>}

      </section>

      {dateOpen&&<WorkspaceModal label="Bar replay date" onClose={()=>setDateOpen(false)}><form className="replay-date-dialog" onSubmit={event=>{event.preventDefault();requestReset(beginReplay);}}><header><strong>Bar replay</strong><button type="button" aria-label="Close replay date" onClick={()=>setDateOpen(false)}>×</button></header><label>Start date and time (UTC)<input type="datetime-local" min="2016-10-03T00:00" max="2026-09-25T00:58" value={replayDate} onChange={event=>setReplayDate(event.target.value)} required/></label><p>Start a new session with a $100,000 account. Candles after the selected time stay hidden until you advance replay.</p>{replay.error&&<p role="alert" className="ticket-error">{replay.error}</p>}<button type="submit" className="place-order" disabled={replay.loading}>{replay.loading?'Loading candles…':'Start replay'}</button></form></WorkspaceModal>}
      {resetRequest&&<ReplayResetConfirmation onCancel={()=>setResetRequest(null)} onConfirm={()=>{const action=resetRequest.action;setResetRequest(null);action();}}/>}
      {editPosition&&<WorkspaceModal label="Edit position" onClose={()=>setEditPosition(null)}><form className="replay-date-dialog" onSubmit={event=>{event.preventDefault();try{news.cancel();trading.update(editPosition.id,{sl:editPosition.sl===''?null:Number(editPosition.sl),tp:editPosition.tp===''?null:Number(editPosition.tp)});setEditPosition(null);}catch(error){setEditError(error.message);}}}><header><strong>Edit {editPosition.side} · XAUUSD</strong><button type="button" aria-label="Close position edit" onClick={()=>setEditPosition(null)}>×</button></header>{['sl','tp'].map(key=><label key={key}>{key==='sl'?'Stop loss':'Take profit'}<input type="number" step="any" value={editPosition[key]??''} placeholder="None" onChange={event=>setEditPosition(current=>({...current,[key]:event.target.value}))}/></label>)}{editError&&<p role="alert" className="ticket-error">{editError}</p>}<button className="place-order" type="submit">Save changes</button></form></WorkspaceModal>}



    </div></NewsContext.Provider>;
}
export default App;

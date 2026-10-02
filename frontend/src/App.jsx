import { useCallback, useEffect, useRef, useState } from "react";
import "./App.css";
import CandleChart from "./components/CandleChart";
import ImportData from "./components/ImportData";
import LeftToolbar from "./components/LeftToolbar";
import TopBar from "./components/TopBar";
import TradingPanel from "./components/TradingPanel";
import PositionTabs from "./components/PositionTabs";
import AnalyticsPanel from "./components/AnalyticsPanel";
import RightToolbar from "./components/RightToolbar";
import {
  cancelPendingOrder,
  closePosition,
  marketOrder,
  nextCandle,
  placePendingOrder,
  previousCandle,
  resetReplay,
} from "./api/replayApi";

const money = (value) => new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 2,
}).format(value ?? 0);

function formatTime(timestamp) {
  if (!timestamp) return "—";
  return new Intl.DateTimeFormat("id-ID", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "UTC",
  }).format(new Date(timestamp * 1000)) + " UTC";
}

function App() {
  const [replay, setReplay] = useState(null);
  const [report, setReport] = useState(null);
  const [status, setStatus] = useState({ message: "Impor CSV untuk memulai replay.", kind: "" });
  const [isPlaying, setIsPlaying] = useState(false);
  const [actionBusy, setActionBusy] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [chartSelectedPrice, setChartSelectedPrice] = useState(null);
  const [drawingMode, setDrawingMode] = useState("none");
  const [selectedTool, setSelectedTool] = useState("cursor");
  const [dataOpen, setDataOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [analyticsOpen, setAnalyticsOpen] = useState(false);
  const [goToOpen, setGoToOpen] = useState(false);
  const [newsOpen, setNewsOpen] = useState(false);
  const [actionsPosition, setActionsPosition] = useState(null);
  const [activePositionTab, setActivePositionTab] = useState("open");
  const [positionsOpen, setPositionsOpen] = useState(true);
  const [positionsHeight, setPositionsHeight] = useState(190);
  const [viewTimeframe, setViewTimeframe] = useState("1h");
  const [chartPreferences, setChartPreferences] = useState({ showVolume: true, showOhlc: true, showGrid: true, showCrosshair: true });
  const requestInProgress = useRef(false);
  const positionsRef = useRef(null);
  const tradingPanelRef = useRef(null);
  const chartPanelRef = useRef(null);
  const actionsRef = useRef(null);

  function startResizingPositions(event) {
    event.preventDefault();
    const startY = event.clientY;
    const startHeight = positionsHeight;
    const move = (pointerEvent) => {
      const maxHeight = Math.max(120, window.innerHeight * 0.55);
      setPositionsHeight(Math.max(100, Math.min(maxHeight, startHeight + startY - pointerEvent.clientY)));
    };
    const stop = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", stop);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", stop);
  }

  function startMovingActions(event) {
    event.preventDefault();
    const panel = chartPanelRef.current;
    const actions = actionsRef.current;
    if (!panel || !actions) return;
    const panelBox = panel.getBoundingClientRect();
    const actionsBox = actions.getBoundingClientRect();
    const offsetX = event.clientX - actionsBox.left;
    const offsetY = event.clientY - actionsBox.top;
    const move = (pointerEvent) => {
      const left = Math.max(0, Math.min(panelBox.width - actionsBox.width, pointerEvent.clientX - panelBox.left - offsetX));
      const top = Math.max(50, Math.min(panelBox.height - actionsBox.height - 20, pointerEvent.clientY - panelBox.top - offsetY));
      setActionsPosition({ left, top });
    };
    const stop = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", stop);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", stop);
  }

  const updateDrawingMode = useCallback((mode) => {
    setDrawingMode(mode);
    setSelectedTool(mode === "none" ? "cursor" : mode);
  }, []);

  const showStatus = useCallback((message, kind = "") => {
    setStatus({ message, kind });
  }, []);

  const acceptReplay = useCallback((nextReplay, nextReport) => {
    setReplay(nextReplay);
    setReport(nextReport);
    setIsPlaying(false);
    setChartSelectedPrice(null);
    setViewTimeframe(nextReplay.timeframe);
    setDataOpen(false);
  }, []);

  function selectChartTool(tool) {
    setSelectedTool(tool);
    if (tool === "cursor" || tool === "crosshair") {
      setDrawingMode("none");
      setChartPreferences((current) => ({ ...current, showCrosshair: tool === "crosshair" }));
    }
    else updateDrawingMode(tool);
  }

  const stepForward = useCallback(async () => {
    if (!replay?.session_id || requestInProgress.current || replay.at_end) return;
    requestInProgress.current = true;
    try {
      const nextState = await nextCandle(replay.session_id);
      setReplay(nextState);
      if (nextState.trades.length > (replay.trades?.length ?? 0)) {
        const trade = nextState.trades.at(-1);
        showStatus(`Posisi ditutup oleh ${trade.reason}. Hasil: ${money(trade.pnl)} (${trade.r_multiple.toFixed(2)}R).`, "success");
      }
      if (nextState.at_end) setIsPlaying(false);
    } catch (error) {
      setIsPlaying(false);
      showStatus(error.message || "Gagal memajukan replay.", "error");
    } finally {
      requestInProgress.current = false;
    }
  }, [replay, showStatus]);

  useEffect(() => {
    if (!isPlaying || !replay || replay.at_end) return undefined;
    const timer = window.setInterval(stepForward, 1000 / speed);
    return () => window.clearInterval(timer);
  }, [isPlaying, replay, speed, stepForward]);

  async function stepBackward() {
    if (!replay?.session_id || requestInProgress.current) return;
    setIsPlaying(false);
    requestInProgress.current = true;
    try {
      setReplay(await previousCandle(replay.session_id));
    } catch (error) {
      showStatus(error.message || "Gagal memundurkan tampilan replay.", "error");
    } finally {
      requestInProgress.current = false;
    }
  }

  async function reset() {
    if (!replay?.session_id || requestInProgress.current) return;
    setIsPlaying(false);
    requestInProgress.current = true;
    try {
      setReplay(await resetReplay(replay.session_id));
      showStatus("Replay kembali ke titik awal.", "success");
    } catch (error) {
      showStatus(error.message || "Gagal mengulang replay.", "error");
    } finally {
      requestInProgress.current = false;
    }
  }

  async function placeOrder(order) {
    if (!replay?.session_id || requestInProgress.current) return;
    setIsPlaying(false);
    setActionBusy(true);
    requestInProgress.current = true;
    try {
      const nextState = order.order_type
        ? await placePendingOrder(replay.session_id, order)
        : await marketOrder(replay.session_id, order);
      setReplay(nextState);
      setChartSelectedPrice(null);
      if (order.order_type) {
        showStatus(`${order.order_type.replace("_", " ")} terpasang di ${order.entry_price}.`, "success");
      } else {
        showStatus(`${order.side} terbuka: ${nextState.position.lots.toFixed(3)} lot.`, "success");
      }
    } catch (error) {
      showStatus(error.message || "Order tidak dapat dibuka.", "error");
    } finally {
      requestInProgress.current = false;
      setActionBusy(false);
    }
  }

  async function closeOpenPosition() {
    if (!replay?.session_id || requestInProgress.current) return;
    setIsPlaying(false);
    setActionBusy(true);
    requestInProgress.current = true;
    try {
      const nextState = await closePosition(replay.session_id);
      setReplay(nextState);
      const trade = nextState.trades.at(-1);
      showStatus(`Posisi ditutup. Hasil: ${money(trade.pnl)} (${trade.r_multiple.toFixed(2)}R).`, "success");
    } catch (error) {
      showStatus(error.message || "Posisi tidak dapat ditutup.", "error");
    } finally {
      requestInProgress.current = false;
      setActionBusy(false);
    }
  }

  async function cancelOrder() {
    if (!replay?.session_id || requestInProgress.current) return;
    setActionBusy(true);
    requestInProgress.current = true;
    try {
      setReplay(await cancelPendingOrder(replay.session_id));
      showStatus("Pending order dibatalkan.", "success");
    } catch (error) {
      showStatus(error.message || "Pending order tidak dapat dibatalkan.", "error");
    } finally {
      requestInProgress.current = false;
      setActionBusy(false);
    }
  }

  const enabled = Boolean(replay?.session_id);
  const percent = replay?.total ? Math.round(((replay.cursor + 1) / replay.total) * 100) : 0;
  const currentCandle = replay?.candles?.at(-1);
  const chartSymbol = replay?.symbol?.length === 6
    ? `${replay.symbol.slice(0, 3)} / ${replay.symbol.slice(3)}`
    : replay?.symbol;

  return (
    <main className="app charting-shell">
      <TopBar
        symbol={replay?.symbol}
        timeframe={viewTimeframe}
        dataReady={Boolean(replay)}
        isPlaying={isPlaying}
        onOpenData={() => setDataOpen((open) => !open)}
        onOpenSettings={() => setSettingsOpen((open) => !open)}
        onOpenIndicators={() => document.querySelector('[aria-label="Chart indicators"]')?.scrollIntoView({ behavior: "smooth", block: "center" })}
        onTogglePlay={() => setIsPlaying((playing) => !playing)}
        onTimeframeChange={(value) => {
          setViewTimeframe(value);
          if (replay && value !== replay.timeframe) showStatus(`Timeframe tampilan ${value.toUpperCase()} dipilih. Data candle tetap ${replay.timeframe.toUpperCase()} (mock UI).`);
        }}
      />

      {analyticsOpen && <AnalyticsPanel replay={replay} onClose={() => setAnalyticsOpen(false)} />}

      {dataOpen && <section className="import-panel data-drawer" aria-label="Impor data pasar">
        <div className="section-heading">
          <div><p className="eyebrow">DATA PASAR</p><h2>Muat dataset</h2></div>
          <div className="data-drawer-actions">
            {report && <span className="dataset-badge">{replay?.symbol} · {replay?.timeframe}</span>}
            <button type="button" onClick={() => setDataOpen(false)} aria-label="Tutup panel data">Tutup</button>
          </div>
        </div>
        <ImportData onReplayStarted={acceptReplay} onStatus={showStatus} />
        <p className={`status-message ${status.kind}`} role="status">{status.message}</p>
      </section>}

      {settingsOpen && <section className="settings-drawer" aria-label="Chart settings">
        <div className="settings-drawer-heading"><strong>Chart settings</strong><button type="button" aria-label="Tutup settings" onClick={() => setSettingsOpen(false)}>×</button></div>
        <label><input type="checkbox" checked={chartPreferences.showVolume} onChange={(event) => setChartPreferences((value) => ({ ...value, showVolume: event.target.checked }))} /> Volume</label>
        <label><input type="checkbox" checked={chartPreferences.showOhlc} onChange={(event) => setChartPreferences((value) => ({ ...value, showOhlc: event.target.checked }))} /> OHLC header</label>
        <label><input type="checkbox" checked={chartPreferences.showGrid} onChange={(event) => setChartPreferences((value) => ({ ...value, showGrid: event.target.checked }))} /> Chart grid</label>
        <label><input type="checkbox" checked={chartPreferences.showCrosshair} onChange={(event) => setChartPreferences((value) => ({ ...value, showCrosshair: event.target.checked }))} /> Crosshair</label>
        <button type="button" onClick={() => setChartPreferences({ showVolume: true, showOhlc: true, showGrid: true, showCrosshair: true })}>Reset settings</button>
      </section>}

      <div className="workspace-grid">
        <LeftToolbar activeTool={selectedTool} onSelect={selectChartTool} />
        <section ref={chartPanelRef} className="chart-panel">
          <div className="chart-heading">
            <div className="chart-title-line"><strong>{chartSymbol ?? "Pilih dataset dari Data"}</strong><span>· {viewTimeframe}</span><i className={replay ? "ready" : ""} /><span>{replay ? "Backtest Lab Replay" : "Belum ada dataset"}</span>{replay && viewTimeframe !== replay.timeframe && <small>Data: {replay.timeframe.toUpperCase()}</small>}</div>
            {replay && chartPreferences.showOhlc && <div className="chart-market-data">
              {currentCandle && <div className="ohlc-strip"><span>O <strong>{currentCandle.open}</strong></span><span>H <strong>{currentCandle.high}</strong></span><span>L <strong>{currentCandle.low}</strong></span><span>C <strong>{currentCandle.close}</strong></span></div>}
              <div className="current-price"><span>Waktu replay</span><strong>{formatTime(replay.current_time)}</strong></div>
            </div>}
          </div>
          <CandleChart candles={replay?.candles ?? []} sessionId={replay?.session_id} position={replay?.position} pendingOrder={replay?.pending_order} trades={replay?.trades ?? []} onPriceSelect={setChartSelectedPrice} drawingMode={drawingMode} onDrawingModeChange={updateDrawingMode} chartPreferences={chartPreferences} onChartPreferencesChange={setChartPreferences} />
          <div ref={actionsRef} className={`floating-chart-actions ${actionsPosition ? "was-moved" : ""}`} style={actionsPosition ?? undefined} aria-label="Aksi chart">
            <button className="action-grip" type="button" title="Seret untuk memindahkan menu aksi" onPointerDown={startMovingActions}>✥</button>
            <button type="button" onClick={() => setGoToOpen((open) => !open)} aria-expanded={goToOpen}>↶ <span>Go To</span></button>
            <button type="button" onClick={() => tradingPanelRef.current?.scrollIntoView({ behavior: "smooth", block: "center" })} disabled={!enabled}>⊕ <span>Order</span></button>
            <button type="button" onClick={() => setNewsOpen((open) => !open)} aria-expanded={newsOpen}>▤ <span>News</span></button>
            <button type="button" onClick={() => { setActivePositionTab("closed"); positionsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }); }}>▣ <span>Journal</span></button>
          </div>
          {goToOpen && <div className="chart-goto-menu" role="menu" aria-label="Navigasi replay">
            <strong>Navigasi replay</strong>
            <button type="button" role="menuitem" onClick={() => { setGoToOpen(false); reset(); }} disabled={!enabled}>Kembali ke awal</button>
            <button type="button" role="menuitem" onClick={() => { setGoToOpen(false); stepBackward(); }} disabled={!enabled}>Candle sebelumnya</button>
            <button type="button" role="menuitem" onClick={() => { setGoToOpen(false); stepForward(); }} disabled={!enabled || replay?.at_end}>Candle berikutnya</button>
          </div>}
          {newsOpen && <div className="chart-news-popover" role="status">
            <strong>News</strong>
            <p>Feed berita belum tersedia untuk dataset CSV lokal ini.</p>
            <button type="button" onClick={() => setNewsOpen(false)}>Tutup</button>
          </div>}
          <div className="timeline">
            <div className="timeline-labels"><span>{replay ? `${replay.cursor + 1} dari ${replay.total} candle` : "Belum ada replay"}</span><span>{percent}%</span></div>
            <div className="progress-track"><div style={{ width: `${percent}%` }} /></div>
          </div>

          <section className="floating-replay" aria-label="Kontrol replay">
            <button type="button" onClick={stepBackward} disabled={!enabled} aria-label="Candle sebelumnya">|◀</button>
            <button className="floating-play" type="button" onClick={() => setIsPlaying((playing) => !playing)} disabled={!enabled || replay?.at_end} aria-label={isPlaying ? "Jeda replay" : "Putar replay"}>{isPlaying ? "Ⅱ" : "▶"}</button>
            <button type="button" onClick={stepForward} disabled={!enabled || replay?.at_end} aria-label="Candle berikutnya">▶|</button>
            <label className="floating-speed"><select aria-label="Kecepatan replay" value={speed} onChange={(event) => setSpeed(Number(event.target.value))} disabled={!enabled}>
              <option value={0.5}>0,5×</option><option value={1}>1×</option><option value={2}>2×</option><option value={4}>4×</option>
            </select></label>
            <button type="button" onClick={reset} disabled={!enabled} aria-label="Ulangi replay">↺</button>
          </section>
        </section>
        <RightToolbar
          onOpenData={() => setDataOpen((open) => !open)}
          onOpenAnalytics={() => setAnalyticsOpen(true)}
          onOpenJournal={() => {
            setActivePositionTab("closed");
            positionsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
          }}
          onOpenSettings={() => setSettingsOpen((open) => !open)}
        />
      </div>

      <section className="bottom-trading-dock" aria-label="Order panel">
        <div className="dock-account-bar">
          <div className="dock-quick-actions"><span className="dock-instrument">{replay?.symbol ?? "—"}</span><strong className="dock-current-price">{currentCandle?.close?.toFixed(3) ?? "—"}</strong></div>
          <button className="analytics-button" type="button" aria-expanded={analyticsOpen} onClick={() => setAnalyticsOpen((open) => !open)}>Analytics</button>
          <span className="dock-balance"><span>Saldo</span><strong>{replay ? money(replay.balance) : "$0.00"}</strong></span>
          <button className="terminal-toggle" type="button" aria-expanded={positionsOpen} aria-label={positionsOpen ? "Tutup terminal posisi" : "Buka terminal posisi"} title={positionsOpen ? "Tutup terminal posisi" : "Buka terminal posisi"} onClick={() => setPositionsOpen((open) => !open)}>{positionsOpen ? "−" : "+"}</button>
        </div>
        <div ref={tradingPanelRef} className="trading-panel-anchor">
        <TradingPanel
          enabled={enabled}
          position={replay?.position}
          pendingOrder={replay?.pending_order}
          balance={replay?.balance}
          currentPrice={currentCandle?.close}
          entryPrice={chartSelectedPrice}
          onEntryPriceChange={setChartSelectedPrice}
          onOrder={placeOrder}
          onClose={closeOpenPosition}
          onCancel={cancelOrder}
          busy={actionBusy}
        />
        </div>
      </section>

      <div ref={positionsRef} className={`positions-terminal ${positionsOpen ? "is-open" : "is-closed"}`} style={{ "--positions-height": `${positionsHeight}px` }}>
        {positionsOpen && <>
          <button className="positions-resizer" type="button" onPointerDown={startResizingPositions} aria-label="Seret untuk mengubah tinggi terminal posisi" title="Seret untuk mengubah tinggi terminal posisi"><span /></button>
          <PositionTabs position={replay?.position} pendingOrder={replay?.pending_order} trades={replay?.trades ?? []} symbol={replay?.symbol ?? "—"} onClose={closeOpenPosition} onCancel={cancelOrder} busy={actionBusy} activeTab={activePositionTab} onTabChange={setActivePositionTab} />
        </>}
      </div>
      <footer className="app-footer">
        <span>Waktu chart ditampilkan dalam UTC. Dataset hanya tersimpan selama API berjalan.</span>
        <a href="https://www.tradingview.com/" target="_blank" rel="noreferrer">
          TradingView Lightweight Charts™ Copyright (с) 2025 TradingView, Inc. https://www.tradingview.com/
        </a>
      </footer>
    </main>
  );
}

export default App;

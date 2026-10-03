import { useCallback, useEffect, useRef, useState } from "react";
import { CandlestickSeries, createChart, createSeriesMarkers, HistogramSeries } from "lightweight-charts";
import TradingLayer from "../trading/TradingLayer";
import { syncTradingAnnotations } from "../trading/chartAnnotations";
import { positionStats } from "../trading/riskReward";
import { isRiskReward, normalizeRiskRewardSettings, RISK_REWARD_TOOLS } from "../trading/RiskRewardController";
import RiskRewardSettings from "../trading/RiskRewardSettings";
import { ChartObjectBridge } from "../chart/ChartObjectBridge";
import { LegacyObjectPersistence } from "../chart/LegacyObjectPersistence";
import { logicalAtTime, timeAtLogical } from "../chart/coordinates";
import useDrawingTools from "../drawings/useDrawingTools";
import { DRAWING_SPECS } from "../drawings/DrawingTypes";
import DrawingControls from "../drawings/DrawingControls";
import { IndicatorEngine } from "../indicators/IndicatorEngine";

const EMPTY_TRADES = [];
const EMPTY_INDICATORS = Object.freeze([]);

function CandleChart({ candles, sessionId, viewportKey = sessionId, onLoadOlder, position, pendingOrder, positions=EMPTY_TRADES, orders=EMPTY_TRADES, simulatedTrades=EMPTY_TRADES, onAmendOrder,onClosePosition,onCancelOrder,onTradingError,onCreateOrder, trades = EMPTY_TRADES, onPriceSelect, drawingMode, onDrawingModeChange, chartPreferences, onChartPreferencesChange, command, onDrawingStateChange, indicatorRegistry, indicatorInstances = EMPTY_INDICATORS, onIndicatorError }) {
  const [indicatorEngine] = useState(() => new IndicatorEngine(indicatorRegistry));
  useEffect(() => {
    try { indicatorEngine.replaceInstances(indicatorInstances); }
    catch (error) { onIndicatorError?.(error); }
  }, [indicatorEngine, indicatorInstances, onIndicatorError]);
  const chartContainer = useRef(null);
  const chartRef = useRef(null);
  const seriesRef = useRef(null);
  const [chartForOverlay, setChartForOverlay] = useState(null);
  const [seriesForOverlay, setSeriesForOverlay] = useState(null);
  const primitiveDrawings = useDrawingTools({ chart: chartForOverlay, series: seriesForOverlay, candles, mode: drawingMode, onModeChange: onDrawingModeChange, timeframe: sessionId?.split('-').at(-1), container: chartContainer, workspace: "main:XAUUSD" });
  const markersRef = useRef(null);
  const volumeSeriesRef = useRef(null);
  const priceLinesRef = useRef([]);
  const [objectBridge] = useState(() => new ChartObjectBridge());
  const [persistence] = useState(() => new LegacyObjectPersistence());
  const undoStackRef = useRef([]);
  const redoStackRef = useRef([]);
  const placementRef = useRef(null);
  const [drawings, setDrawings] = useState([]);
  const [historyState, setHistoryState] = useState({ canUndo: false, canRedo: false });
  const [selectedDrawingId, setSelectedDrawingId] = useState(null);
  const [contextMenu, setContextMenu] = useState(null);
  const [drawingSettings, setDrawingSettings] = useState(null);
  const [exportPreview, setExportPreview] = useState(null);
  const [exportStatus, setExportStatus] = useState("");
  const viewportSessionRef = useRef(null);
  const previousCandleCountRef = useRef(0);
  const previousFirstCandleRef = useRef(null);
  const showVolume = chartPreferences.showVolume;
  const magnetRef = useRef(false);
  const [magnetEnabled, setMagnetEnabled] = useState(false);
  const [keepDrawing, setKeepDrawing] = useState(false);
  const restoredSessionRef = useRef(null);
  const storageKey = sessionId && (sessionId.startsWith("design-") || sessionId.startsWith("XAUUSD-")) ? "backtest-drawings-v2:" + sessionId : null;

  useEffect(() => {
    onDrawingStateChange?.({ drawings, selectedId: selectedDrawingId, ...historyState, magnet: magnetEnabled, keepDrawing });
  }, [drawings, selectedDrawingId, historyState, magnetEnabled, keepDrawing, onDrawingStateChange]);

  useEffect(() => {
    const frame = requestAnimationFrame(() => {
      if (!storageKey || restoredSessionRef.current === storageKey) return;
      const saved = persistence.load(() => localStorage, storageKey, item => Boolean(item && isRiskReward(item)
        && Array.isArray(item.points) && item.points.length >= 3
        && item.points.every(point => point && Number.isFinite(point.time) && Number.isFinite(point.price))));
      restoredSessionRef.current = storageKey;
      objectBridge.replace(saved); setDrawings(saved);
      undoStackRef.current = []; redoStackRef.current = [];
      setHistoryState({ canUndo: false, canRedo: false }); setSelectedDrawingId(null);
      setDrawingSettings(null);
    });
    return () => cancelAnimationFrame(frame);
  }, [storageKey, objectBridge, persistence]);

  useEffect(() => {
    if (!storageKey || restoredSessionRef.current !== storageKey) return;
    persistence.save(() => localStorage, storageKey, drawings);
  }, [drawings, storageKey, persistence]);

  useEffect(() => {
    const container = chartContainer.current;
    if (!container) return undefined;

    const chart = createChart(container, {
      width: container.clientWidth,
      height: 460,
      layout: { background: { color: "#08090b" }, textColor: "#a5a8ad" },
      grid: { vertLines: { color: "#1b1c1f" }, horzLines: { color: "#1b1c1f" } },
      rightPriceScale: { borderColor: "#2a2c30" },
      timeScale: { borderColor: "#2a2c30", timeVisible: true, secondsVisible: false, rightOffset: 18 },
      handleScale: {
        mouseWheel: true,
        pinch: true,
        axisPressedMouseMove: { time: true, price: true },
        axisDoubleClickReset: true,
      },
      handleScroll: {
        mouseWheel: false,
        pressedMouseMove: true,
        horzTouchDrag: true,
        vertTouchDrag: true,
      },
      crosshair: {
        mode: 0,
        vertLine: { visible: true, labelVisible: true, color: "#8798aa", labelBackgroundColor: "#344253" },
        horzLine: { visible: true, labelVisible: true, color: "#8798aa", labelBackgroundColor: "#344253" },
      },
    });
    const series = chart.addSeries(CandlestickSeries, {
      priceFormat: {type:'price',precision:3,minMove:.001},
      upColor: "#089981",
      downColor: "#f23645",
      borderUpColor: "#089981",
      borderDownColor: "#f23645",
      wickUpColor: "#089981",
      wickDownColor: "#f23645",
    });
    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceScaleId: "",
      priceFormat: { type: "volume" },
      priceLineVisible: false,
      lastValueVisible: false,
      base: 0,
    });
    chart.priceScale("").applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
    const markers = createSeriesMarkers(series, []);
    chartRef.current = chart;
    seriesRef.current = series;
    volumeSeriesRef.current = volumeSeries;
    markersRef.current = markers;
    indicatorEngine.attach(chart);
    const overlayFrame = window.requestAnimationFrame(() => {
      setChartForOverlay(chart);
      setSeriesForOverlay(series);
    });

    const resizeObserver = new ResizeObserver(([entry]) => {
      chart.applyOptions({
        width: Math.floor(entry.contentRect.width),
        height: Math.floor(entry.contentRect.height),
      });
    });
    resizeObserver.observe(container);
    return () => {
      resizeObserver.disconnect();
      window.cancelAnimationFrame(overlayFrame);
      indicatorEngine.detach();
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
      volumeSeriesRef.current = null;
      markersRef.current = null;
      priceLinesRef.current = [];
    };
  }, [indicatorEngine]);

  const commitDrawings = useCallback((nextValue) => {
    const next = typeof nextValue === "function" ? nextValue(objectBridge.objects) : nextValue;
    undoStackRef.current.push(objectBridge.objects);
    if (undoStackRef.current.length > 100) undoStackRef.current.shift();
    redoStackRef.current = [];
    setHistoryState({ canUndo: true, canRedo: false });
    objectBridge.replace(next);
    setDrawings(next);
  }, [objectBridge]);

  function updateDrawingPoint(id, index, point) {
    replaceDrawings(current => current.map(drawing => {
      if (drawing.id !== id) return drawing;
      if (isRiskReward(drawing)) return objectBridge.riskReward.resize(drawing, index, point, candles);
      const points = drawing.points.map(item => ({ ...item }));
      points[index] = point;
      return { ...drawing, points };
    }));
  }

  function moveDrawing(id, points) {
    replaceDrawings((current) => current.map((drawing) => drawing.id === id ? { ...drawing, points } : drawing));
  }

  function replaceDrawings(nextValue) {
    const next = typeof nextValue === "function" ? nextValue(objectBridge.objects) : nextValue;
    objectBridge.replace(next);
    setDrawings(next);
  }

  function startDrawingDrag() {
    chartRef.current?.applyOptions({ handleScroll: { pressedMouseMove: false, horzTouchDrag: false, vertTouchDrag: false } });
    undoStackRef.current.push(objectBridge.objects);
    if (undoStackRef.current.length > 100) undoStackRef.current.shift();
    redoStackRef.current = [];
    setHistoryState({ canUndo: true, canRedo: false });
  }

  const deleteSelectedDrawing = useCallback(() => {
    if (!selectedDrawingId) return;
    commitDrawings((current) => current.filter((drawing) => drawing.id !== selectedDrawingId));
    setSelectedDrawingId(null);
  }, [selectedDrawingId, commitDrawings]);

  const undoDrawing = useCallback(() => {
    const previous = undoStackRef.current.pop();
    if (!previous) return;
    redoStackRef.current.push(objectBridge.objects);
    setHistoryState({ canUndo: undoStackRef.current.length > 0, canRedo: true });
    objectBridge.replace(previous);
    setDrawings(previous);
    setSelectedDrawingId(null);
  }, [objectBridge]);

  const redoDrawing = useCallback(() => {
    const next = redoStackRef.current.pop();
    if (!next) return;
    undoStackRef.current.push(objectBridge.objects);
    setHistoryState({ canUndo: true, canRedo: redoStackRef.current.length > 0 });
    objectBridge.replace(next);
    setDrawings(next);
  }, [objectBridge]);

  useEffect(() => {
    if (!command) return;
    const frame = requestAnimationFrame(() => {
      const action = command.action;
      if (action === "undo") undoDrawing();
      if (action === "redo") redoDrawing();
      if (action === "clear" || action === "new-layout") { commitDrawings([]); setSelectedDrawingId(null); }
      if (action === "lock-all" || action === "hide-all") {
        const key = action === "lock-all" ? "locked" : "hidden";
        const value = !objectBridge.objects.every(item => item[key]);
        commitDrawings(current => current.map(item => ({ ...item, [key]: value })));
      }
      if (action === "magnet") { magnetRef.current = !magnetRef.current; setMagnetEnabled(magnetRef.current); }
      if (action === "keep-drawing") setKeepDrawing(value => !value);
      if (action.startsWith("object:")) {
        const [, operation, id] = action.split(":");
        if (operation === "select") setSelectedDrawingId(id);
        if (operation === "delete") { commitDrawings(current => current.filter(item => item.id !== id)); setSelectedDrawingId(null); }
        if (["hide", "lock"].includes(operation)) { const key = operation === "hide" ? "hidden" : "locked"; commitDrawings(current => current.map(item => item.id === id ? { ...item, [key]: !item[key] } : item)); }
        if (operation === "edit") { const object = objectBridge.objects.find(item => item.id === id); if (object) setDrawingSettings({ ...object, points: object.points.map(point => ({ ...point })) }); }
      }
      if (action === "fit" || action === "new-layout") { chartRef.current?.priceScale("right").applyOptions({ autoScale: true, mode: 0 }); chartRef.current?.timeScale().fitContent(); }
      if (action === "percent" || action === "log") chartRef.current?.priceScale("right").applyOptions({ mode: action === "log" ? 1 : 2 });
      if (action.startsWith("range:")) {
        const range = action.slice(6), last = candles.at(-1);
        if (last) {
          const date = new Date(last.time * 1000);
          if (range.endsWith("d")) date.setUTCDate(date.getUTCDate()-Number(range.slice(0,-1)));
          if (range.endsWith("m")) date.setUTCMonth(date.getUTCMonth()-Number(range.slice(0,-1)));
          if (range.endsWith("y")) date.setUTCFullYear(date.getUTCFullYear()-Number(range.slice(0,-1)));
          const index = candles.findIndex(bar => bar.time >= date.getTime()/1000);
          chartRef.current?.timeScale().setVisibleLogicalRange({ from: Math.max(0,index), to: candles.length + 4 });
        }
      }
      if (action === "screenshot") {
        setExportStatus("Preparing chart image…");
        const baseCanvas = chartRef.current?.takeScreenshot();
        const canvas = document.createElement("canvas");
        if (baseCanvas) {
          canvas.width = baseCanvas.width; canvas.height = baseCanvas.height;
          canvas.getContext("2d").drawImage(baseCanvas, 0, 0);
        }
        const layers = chartContainer.current?.parentElement.querySelectorAll(".drawings-layer");
        if (baseCanvas && layers?.length) {
          const renderLayer = svg => new Promise((resolve, reject) => {
            const copy = svg.cloneNode(true);
            copy.setAttribute("xmlns", "http://www.w3.org/2000/svg");
            copy.setAttribute("width", canvas.width); copy.setAttribute("height", canvas.height);
            const bounds = svg.getBoundingClientRect();
            const chartBounds = chartContainer.current.getBoundingClientRect();
            copy.setAttribute("viewBox", "0 0 " + bounds.width + " " + chartBounds.height);
            copy.setAttribute("preserveAspectRatio", "none");
            copy.querySelectorAll(".drawing-handle-hit,.drawing-handle").forEach(element => element.remove());
            copy.querySelectorAll(".geometry-label,.position-label").forEach(text => { text.setAttribute("fill", text.getAttribute("fill") || "#eaf2fb"); text.style.fontFamily = "sans-serif"; });
            const url = URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(copy)], { type: "image/svg+xml" }));
            const image = new Image();
            image.onload = () => { canvas.getContext("2d").drawImage(image, 0, 0); URL.revokeObjectURL(url); resolve(); };
            image.onerror = () => { URL.revokeObjectURL(url); reject(new Error("Chart image could not be prepared. Please try again.")); };
            image.src = url;
          });
          (async () => { try { for (const layer of layers) await renderLayer(layer); setExportPreview(canvas.toDataURL()); setExportStatus(""); } catch (error) { setExportStatus(error.message); } })();
        } else setExportStatus("Load a chart before exporting.");
      }
    });
    return () => cancelAnimationFrame(frame);
    // Commands run once per user action; drawing callbacks read the current history refs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [command]);

  function handleContextAction(action) {
    const drawing = drawings.find((item) => item.id === contextMenu?.id);
    setContextMenu(null);
    if (!drawing) {
      if (action === "reset") chartRef.current?.timeScale().fitContent();
      if (action === "undo") undoDrawing();
      return;
    }
    if (action === "delete") {
      commitDrawings((current) => current.filter((item) => item.id !== drawing.id));
      setSelectedDrawingId(null);
    } else if (action === "lock" || action === "hide") {
      const key = action === "lock" ? "locked" : "hidden";
      commitDrawings((current) => current.map((item) => item.id === drawing.id ? { ...item, [key]: !item[key] } : item));
    } else if (action === "duplicate") {
      const price = drawing.points[0]?.price ?? 0;
      const y = seriesRef.current?.priceToCoordinate(price);
      const steppedPrice = y == null ? price : seriesRef.current.coordinateToPrice(y - 22) ?? price;
      const lastPair = candles.slice(-2);
      const timeStep = lastPair.length === 2 ? Math.abs(Number(lastPair[1].time) - Number(lastPair[0].time)) : 3600;
      const clone = {
        ...drawing,
        id: crypto.randomUUID(),
        locked: false,
        hidden: false,
        points: drawing.points.map((point) => ({ time: timeAtLogical(candles, logicalAtTime(candles, point.time) + 1) ?? Number(point.time) + timeStep, price: point.price + (steppedPrice - price) })),
      };
      commitDrawings((current) => [...current, clone]);
      setSelectedDrawingId(clone.id);
    } else if (action === "settings") {
      setDrawingSettings({ ...drawing, points: drawing.points.map((point) => ({ ...point })) });
    }
  }

  function saveDrawingSettings(event) {
    event.preventDefault();
    if (!drawingSettings) return;
    if (drawingSettings.points.some(point => !Number.isFinite(point.price) || !Number.isFinite(point.time))) return;
    if (isRiskReward(drawingSettings) && !positionStats(drawingSettings, candles.at(-1)?.close).valid) return;
    const settings = isRiskReward(drawingSettings) ? normalizeRiskRewardSettings(drawingSettings) : drawingSettings;
    commitDrawings((current) => current.map((drawing) => drawing.id === settings.id ? settings : drawing));
    setDrawingSettings(null);
  }

  function handleChartContextMenu(event) {
    event.preventDefault();
    const bounds = event.currentTarget.getBoundingClientRect();
    setContextMenu({ id: null, x: event.clientX, y: event.clientY, localX: event.clientX - bounds.left, localY: event.clientY - bounds.top });
  }

  useEffect(() => {
    function handleDrawingShortcut(event) {
      const target = event.target;
      if (target instanceof HTMLElement && ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)) return;
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "z") {
        event.preventDefault();
        if (event.shiftKey) redoDrawing(); else undoDrawing();
      } else if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "y") {
        event.preventDefault();
        redoDrawing();
      } else if (["Delete", "Backspace"].includes(event.key) && selectedDrawingId) {
        event.preventDefault();
        deleteSelectedDrawing();
      } else if (event.key === "Escape") {
        onDrawingModeChange("none");
        setSelectedDrawingId(null);
      }
    }
    window.addEventListener("keydown", handleDrawingShortcut);
    return () => window.removeEventListener("keydown", handleDrawingShortcut);
  }, [selectedDrawingId, onDrawingModeChange, deleteSelectedDrawing, commitDrawings, drawingMode, keepDrawing, undoDrawing, redoDrawing]);

  useEffect(() => {
    const chart = chartRef.current, series = seriesRef.current;
    if (!chart || !series) return;
    const tool = RISK_REWARD_TOOLS[drawingMode];
    const placing = Boolean(tool) || DRAWING_SPECS[drawingMode];
    chart.applyOptions({ handleScroll: { pressedMouseMove: !placing, horzTouchDrag: !placing, vertTouchDrag: !placing }, handleScale: { mouseWheel: true } });
    chart.applyOptions({ crosshair: { vertLine: { visible: chartPreferences.showCrosshair && drawingMode !== "cursor-arrow" }, horzLine: { visible: chartPreferences.showCrosshair && drawingMode !== "cursor-arrow" } } });
    function pointFor(param) {
      if (!param.point || (param.paneIndex !== undefined && param.paneIndex !== 0)
        || param.point.y < 0 || param.point.y > chart.paneSize(0).height) return null;
      const logical = chart.timeScale().coordinateToLogical(param.point.x);
      const time = param.time ?? timeAtLogical(candles, logical);
      let price = series.coordinateToPrice(param.point.y);
      if (time == null || price == null) return null;
      if (magnetRef.current) { const bar = candles[Math.round(logical)]; if (bar?.open != null) price = [bar.open, bar.high, bar.low, bar.close].reduce((best, value) => Math.abs(value - price) < Math.abs(best - price) ? value : best); }
      return { time: Number(time), price: Number(price) };
    }
    function handleChartClick(param) {
      const point = pointFor(param); if (!point) return;
      if (drawingMode === "order") { onPriceSelect?.(point.price); onDrawingModeChange("none"); return; }
      if (!tool) { if (["none", "cursor-dot", "cursor-arrow"].includes(drawingMode)) setSelectedDrawingId(null); return; }
      const object = objectBridge.riskReward.create(drawingMode, point, param.point, series, candles, crypto.randomUUID());
      if (!object) return;
      commitDrawings(current => [...current, object]);
      setSelectedDrawingId(object.id);
      if (!keepDrawing) onDrawingModeChange("none");
    }
    placementRef.current = handleChartClick;
    chart.subscribeClick(handleChartClick);
    return () => { chart.unsubscribeClick(handleChartClick); placementRef.current = null; };
  }, [drawingMode, onDrawingModeChange, onPriceSelect, commitDrawings, candles, keepDrawing, chartPreferences.showCrosshair, objectBridge]);

  useEffect(() => {
    const chart = chartRef.current;
    const series = seriesRef.current;
    if (!chart || !series) return;

    const timeScale = chart.timeScale();
    const previousCount = previousCandleCountRef.current;
    const isNewSession = viewportKey !== viewportSessionRef.current;
    const visibleRange = timeScale.getVisibleLogicalRange();
    const wasFollowingLatest = visibleRange == null || visibleRange.to >= previousCount - 1.5;

    series.setData(candles);
    indicatorEngine.setCandles(candles);
    volumeSeriesRef.current?.setData(candles.map((candle) => ({
      time: candle.time,
      value: Number(candle.volume ?? 0),
      color: candle.close >= candle.open ? "#22c99a66" : "#f0647466",
    })));

    const previousFirst = previousFirstCandleRef.current;
    const prepended = previousFirst != null && candles[0]?.time < previousFirst ? candles.findIndex(bar => bar.time === previousFirst) : 0;
    if (candles.length && (isNewSession || previousCount === 0 || (previousCount < 60 && prepended > 0))) {
      if (candles.length < 60) timeScale.setVisibleLogicalRange({ from: -5, to: 65 });
      else timeScale.setVisibleLogicalRange({from:Math.max(0,candles.length-240),to:candles.length+18});
    } else if (candles.length && visibleRange) {
      if (wasFollowingLatest) {
        timeScale.scrollToRealTime();
      } else {
        const shift = Math.max(0,prepended);
        timeScale.setVisibleLogicalRange({from:visibleRange.from+shift,to:visibleRange.to+shift});
      }
    }

    viewportSessionRef.current = viewportKey;
    previousCandleCountRef.current = candles.length;
    previousFirstCandleRef.current = candles[0]?.time ?? null;
  }, [candles, viewportKey, indicatorEngine]);

  useEffect(() => {
    const scale=chartRef.current?.timeScale();
    if(!scale||!onLoadOlder)return;
    const load=range=>{if(range && range.from<20 && range.to<candles.length-1)onLoadOlder().catch(()=>{});};
    scale.subscribeVisibleLogicalRangeChange(load);
    return()=>scale.unsubscribeVisibleLogicalRangeChange(load);
  },[onLoadOlder,candles.length]);

  useEffect(() => {
    volumeSeriesRef.current?.applyOptions({ visible: showVolume });
  }, [showVolume]);

  useEffect(() => {
    chartRef.current?.applyOptions({
      grid: {
        vertLines: { visible: chartPreferences.showGrid },
        horzLines: { visible: chartPreferences.showGrid },
      },
      crosshair: {
        vertLine: { visible: chartPreferences.showCrosshair, labelVisible: chartPreferences.showCrosshair },
        horzLine: { visible: chartPreferences.showCrosshair, labelVisible: chartPreferences.showCrosshair },
      },
    });
  }, [chartPreferences.showGrid, chartPreferences.showCrosshair]);

  useEffect(() => {
    const series = seriesRef.current;
    if (!series) return;

    priceLinesRef.current = syncTradingAnnotations({ series, markerPlugin: markersRef.current,
      priceLines: priceLinesRef.current, candles, positions, orders, position, pendingOrder, simulatedTrades, trades });
  }, [position,pendingOrder,positions,orders,simulatedTrades,trades,candles]);

  const activeSpec = RISK_REWARD_TOOLS[drawingMode];
  const toolHint = DRAWING_SPECS[drawingMode] ? DRAWING_SPECS[drawingMode].name + " · " + (DRAWING_SPECS[drawingMode].points === 1 ? "Klik chart" : "Klik titik A dan B") + " · Esc untuk batal" : activeSpec ? activeSpec.name + " · Klik chart" + (keepDrawing ? " · Keep drawing aktif" : "") : null;

  return (
    <div className="chart-wrap" onContextMenu={handleChartContextMenu} onClick={() => setContextMenu(null)}>
      <div className="chart-tools" aria-label="Chart trading controls">
        <button type="button" className={showVolume ? "active" : ""} aria-pressed={showVolume} onClick={() => onChartPreferencesChange((value) => ({ ...value, showVolume: !value.showVolume }))}>Volume</button>
        <button type="button" className={drawingMode === "order" ? "active" : ""} aria-pressed={drawingMode === "order"} onClick={() => onDrawingModeChange(drawingMode === "order" ? "none" : "order")}>Pilih harga order</button>
        <span className="tool-divider" />
        <button type="button" onClick={undoDrawing} disabled={!historyState.canUndo} aria-label="Undo drawing" title="Undo (Ctrl+Z)">↶ Undo</button>
        <button type="button" onClick={redoDrawing} disabled={!historyState.canRedo} aria-label="Redo drawing" title="Redo (Ctrl+Y)">↷ Redo</button>
        {selectedDrawingId && <>
          <button type="button" onClick={() => commitDrawings((current) => current.map((drawing) => drawing.id === selectedDrawingId ? { ...drawing, locked: !drawing.locked } : drawing))} aria-label="Kunci drawing" title="Kunci / buka drawing">{drawings.find((drawing) => drawing.id === selectedDrawingId)?.locked ? "🔒" : "🔓"}</button>
          <button type="button" onClick={() => commitDrawings((current) => current.map((drawing) => drawing.id === selectedDrawingId ? { ...drawing, hidden: !drawing.hidden } : drawing))} aria-label="Sembunyikan drawing" title="Tampilkan / sembunyikan">◉</button>
          <button type="button" className="clear-drawings" onClick={deleteSelectedDrawing} aria-label="Hapus drawing terpilih" title="Hapus drawing terpilih">Hapus</button>
        </>}
      </div>
      {toolHint && <div className="chart-action-hint" role="status">{toolHint}</div>}
      <DrawingControls tools={primitiveDrawings} />
      <div className="chart-canvas-layer">
        <div ref={chartContainer} tabIndex={-1} className="candle-chart" data-primitive-drawings={JSON.stringify(primitiveDrawings.objects)} data-primitive-selected={primitiveDrawings.selectedId ?? ''} data-primitive-draft={primitiveDrawings.draftActive} />
        <TradingLayer positions={positions} orders={orders} onAmend={onAmendOrder} onClose={onClosePosition} onCancel={onCancelOrder} onError={onTradingError} chart={chartForOverlay} series={seriesForOverlay} candles={candles} objects={objectBridge.riskReward.objects} selectedId={selectedDrawingId} drawingMode={drawingMode} onPlacePoint={param => placementRef.current?.(param)} magnet={magnetEnabled} onSelect={setSelectedDrawingId} onStartDrag={startDrawingDrag} onEndDrag={() => chartRef.current?.applyOptions({ handleScroll: { pressedMouseMove: true, horzTouchDrag: true, vertTouchDrag: true } })} onUpdatePoint={updateDrawingPoint} onMoveDrawing={moveDrawing} onContextMenu={menu => { if (menu.edit) { const object = objectBridge.objects.find(item => item.id === menu.id); if (object) setDrawingSettings({ ...object, points: object.points.map(point => ({ ...point })) }); } else setContextMenu(menu); }} />
      </div>
      {selectedDrawingId&&drawings.find(item=>item.id===selectedDrawingId)&&<div className="selected-drawing-toolbar" aria-label="Selected drawing actions">
        <button aria-label="Drawing settings" onClick={()=>{const item=objectBridge.objects.find(item=>item.id===selectedDrawingId);setDrawingSettings({...item,points:item.points.map(point=>({...point}))});}}>⚙</button>
        <input aria-label="Drawing color" type="color" value={drawings.find(item=>item.id===selectedDrawingId)?.color||'#58a6ff'} onChange={event=>commitDrawings(current=>current.map(item=>item.id===selectedDrawingId?{...item,color:event.target.value}:item))}/>
        <button aria-label="Clone drawing" onClick={()=>{const item=objectBridge.objects.find(item=>item.id===selectedDrawingId);const copy={...item,id:crypto.randomUUID(),points:item.points.map(point=>({...point,time:point.time+(candles.intervalSeconds??60)}))};commitDrawings(current=>[...current,copy]);setSelectedDrawingId(copy.id);}}>⧉</button>
        <button aria-label="Lock selected drawing" onClick={()=>commitDrawings(current=>current.map(item=>item.id===selectedDrawingId?{...item,locked:!item.locked}:item))}>♙</button>
        {onCreateOrder&&['long-position','short-position'].includes(drawings.find(item=>item.id===selectedDrawingId)?.type)&&<button className="drawing-create-order" onClick={()=>onCreateOrder(objectBridge.riskReward.get(selectedDrawingId))}>Create order</button>}
        <button aria-label="Delete selected drawing" onClick={()=>{commitDrawings(current=>current.filter(item=>item.id!==selectedDrawingId));setSelectedDrawingId(null);}}>⌫</button>
      </div>}
      {contextMenu && <div className="chart-context-menu" style={{ left: contextMenu.x, top: contextMenu.y }} onClick={(event) => event.stopPropagation()} role="menu">
        {contextMenu.id ? <>
          <button type="button" role="menuitem" onClick={() => handleContextAction("settings")}>Settings</button>
          <button type="button" role="menuitem" onClick={() => handleContextAction("duplicate")}>Duplicate</button>
          <button type="button" role="menuitem" onClick={() => handleContextAction("lock")}>{drawings.find((item) => item.id === contextMenu.id)?.locked ? "Unlock" : "Lock"}</button>
          <button type="button" role="menuitem" onClick={() => handleContextAction("hide")}>Hide / show</button>
          <button type="button" role="menuitem" className="danger" onClick={() => handleContextAction("delete")}>Delete</button>
        </> : <>
          <button type="button" role="menuitem" onClick={() => handleContextAction("undo")}>Undo drawing</button>
          <button type="button" role="menuitem" onClick={() => handleContextAction("reset")}>Reset chart view</button>
        </>}
      </div>}
      {drawingSettings && <form className="drawing-settings" onSubmit={saveDrawingSettings}>
        <div><strong>{isRiskReward(drawingSettings) ? (drawingSettings.type === "long-position" ? "Long Position" : "Short Position") : "Object settings"}</strong><button type="button" aria-label="Tutup settings" onClick={() => setDrawingSettings(null)}>×</button></div>
        {isRiskReward(drawingSettings) && <RiskRewardSettings drawingSettings={drawingSettings} setDrawingSettings={setDrawingSettings} candles={candles} />}
        <label>Line width<input type="number" min="1" max="24" value={drawingSettings.lineWidth || 2} onChange={event => setDrawingSettings(value => ({ ...value, lineWidth: Math.max(1, Math.min(24, Number(event.target.value))) }))} /></label>
        <label>Font size<input type="number" min="8" max="48" value={drawingSettings.fontSize || 12} onChange={event => setDrawingSettings(value => ({ ...value, fontSize: Math.max(8, Math.min(48, Number(event.target.value))) }))} /></label>
        <label>Color<input type="color" value={drawingSettings.color || "#58a6ff"} onInput={event => setDrawingSettings(value => ({ ...value, color: event.target.value }))} onChange={(event) => setDrawingSettings((value) => ({ ...value, color: event.target.value }))} /></label>
        <details><summary>Coordinates (UTC)</summary>
          {drawingSettings.points.map((point, index) => <div key={index} className="coordinate-fields">
            <label>Point {index + 1} time<input type="datetime-local" step="60" value={new Date(point.time * 1000).toISOString().slice(0, 16)} onChange={event => { if (!event.target.value) return; const time = Date.parse(event.target.value + "Z") / 1000; if (Number.isFinite(time)) setDrawingSettings(value => ({ ...value, points: value.points.map((item, i) => i === index ? { ...item, time } : item) })); }} /></label>
            <label>Point {index + 1} price<input type="number" step="any" value={point.price} onChange={event => setDrawingSettings(value => ({ ...value, points: value.points.map((item, i) => i === index ? { ...item, price: Number(event.target.value) } : item) }))} /></label>
          </div>)}
        </details>
        <button type="submit">Save</button>
      </form>}
      {!candles.length && <div className="chart-empty">Grafik candle akan tampil setelah dataset dimuat.</div>}
      {exportStatus && <div className="chart-action-hint" role="status">{exportStatus}<button type="button" onClick={() => setExportStatus("")}>×</button></div>}
      {exportPreview && <div className="chart-export-backdrop"><section className="chart-export-dialog" role="dialog" aria-label="Export chart">
        <header><strong>Export chart</strong><button type="button" aria-label="Close chart export" onClick={() => setExportPreview(null)}>×</button></header>
        <img src={exportPreview} alt="Chart image with drawings" />
        <a href={exportPreview} download="backtest-chart.png">Download PNG</a>
      </section></div>}
    </div>
  );
}

export default CandleChart;

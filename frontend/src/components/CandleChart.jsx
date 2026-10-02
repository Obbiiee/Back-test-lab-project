import { useCallback, useEffect, useRef, useState } from "react";
import { CandlestickSeries, createChart, createSeriesMarkers, HistogramSeries, LineSeries } from "lightweight-charts";
import DrawingsLayer from "./DrawingsLayer";
import TradingLevels from "./TradingLevels";
import { positionStats } from "../drawings/position";
import { DRAWING_TOOLS, FREEHAND_TOOLS, logicalAtTime, TEXT_TOOLS, timeAtLogical } from "../drawings/tools";

const EMPTY_TRADES = [];

function movingAverage(candles, period, exponential = false) {
  if (exponential) {
    const multiplier = 2 / (period + 1);
    let average = 0;
    return candles.map((candle, index) => {
      average = index === 0 ? candle.close : candle.close * multiplier + average * (1 - multiplier);
      return { time: candle.time, value: average };
    });
  }

  let rollingSum = 0;
  return candles.flatMap((candle, index) => {
    rollingSum += candle.close;
    if (index >= period) rollingSum -= candles[index - period].close;
    return index < period - 1 ? [] : [{ time: candle.time, value: rollingSum / period }];
  });
}

function CandleChart({ candles, sessionId, viewportKey = sessionId, onLoadOlder, position, pendingOrder, positions=EMPTY_TRADES, orders=EMPTY_TRADES, simulatedTrades=EMPTY_TRADES, onAmendOrder,onClosePosition,onCancelOrder,onTradingError,onCreateOrder, trades = EMPTY_TRADES, onPriceSelect, drawingMode, onDrawingModeChange, chartPreferences, onChartPreferencesChange, command, onDrawingStateChange }) {
  const chartContainer = useRef(null);
  const chartRef = useRef(null);
  const seriesRef = useRef(null);
  const [chartForOverlay, setChartForOverlay] = useState(null);
  const [seriesForOverlay, setSeriesForOverlay] = useState(null);
  const markersRef = useRef(null);
  const volumeSeriesRef = useRef(null);
  const priceLinesRef = useRef([]);
  const indicatorSeriesRef = useRef({});
  const drawingsRef = useRef([]);
  const undoStackRef = useRef([]);
  const redoStackRef = useRef([]);
  const draftPointRef = useRef(null);
  const placementRef = useRef(null);
  const previewRef = useRef(null);
  const [drawings, setDrawings] = useState([]);
  const [draftDrawing, setDraftDrawing] = useState(null);
  const [historyState, setHistoryState] = useState({ canUndo: false, canRedo: false });
  const [selectedDrawingId, setSelectedDrawingId] = useState(null);
  const [contextMenu, setContextMenu] = useState(null);
  const [drawingSettings, setDrawingSettings] = useState(null);
  const [exportPreview, setExportPreview] = useState(null);
  const [exportStatus, setExportStatus] = useState("");
  const viewportSessionRef = useRef(null);
  const previousCandleCountRef = useRef(0);
  const previousFirstCandleRef = useRef(null);
  const [indicators, setIndicators] = useState({ sma20: false, ema20: false, ema50: false });
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
      let saved = [];
      try {
        const parsed = JSON.parse(localStorage.getItem(storageKey) || "[]");
        if (Array.isArray(parsed)) saved = parsed.filter(item => DRAWING_TOOLS[item.type] && Array.isArray(item.points) && item.points.length > 0 && item.points.every(point => Number.isFinite(point.time) && Number.isFinite(point.price)));
      } catch { /* An invalid browser draft must not break the chart. */ }
      restoredSessionRef.current = storageKey;
      drawingsRef.current = saved; setDrawings(saved);
      undoStackRef.current = []; redoStackRef.current = [];
      setHistoryState({ canUndo: false, canRedo: false }); setSelectedDrawingId(null);
      setDrawingSettings(null); setDraftDrawing(null); draftPointRef.current = [];
    });
    return () => cancelAnimationFrame(frame);
  }, [storageKey]);

  useEffect(() => {
    if (!storageKey || restoredSessionRef.current !== storageKey) return;
    try { localStorage.setItem(storageKey, JSON.stringify(drawings)); } catch { /* Browser storage may be full or disabled. */ }
  }, [drawings, storageKey]);

  useEffect(() => {
    if (!command) return;
    const frame = requestAnimationFrame(() => {
      const action = command.action;
      if (action === "undo") undoDrawing();
      if (action === "redo") redoDrawing();
      if (action === "clear" || action === "new-layout") { commitDrawings([]); setSelectedDrawingId(null); }
      if (action === "lock-all" || action === "hide-all") {
        const key = action === "lock-all" ? "locked" : "hidden";
        const value = !drawingsRef.current.every(item => item[key]);
        commitDrawings(current => current.map(item => ({ ...item, [key]: value })));
      }
      if (action === "magnet") { magnetRef.current = !magnetRef.current; setMagnetEnabled(magnetRef.current); }
      if (action === "keep-drawing") setKeepDrawing(value => !value);
      if (action.startsWith("object:")) {
        const [, operation, id] = action.split(":");
        if (operation === "select") setSelectedDrawingId(id);
        if (operation === "delete") { commitDrawings(current => current.filter(item => item.id !== id)); setSelectedDrawingId(null); }
        if (["hide", "lock"].includes(operation)) { const key = operation === "hide" ? "hidden" : "locked"; commitDrawings(current => current.map(item => item.id === id ? { ...item, [key]: !item[key] } : item)); }
        if (operation === "edit") { const object = drawingsRef.current.find(item => item.id === id); if (object) setDrawingSettings({ ...object, points: object.points.map(point => ({ ...point })) }); }
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
      if (action.startsWith("indicator:")) {
        const key = { "SMA 20": "sma20", "EMA 20": "ema20", "EMA 50": "ema50" }[action.slice(10)];
        if (key) setIndicators(value => ({ ...value, [key]: !value[key] }));
        else onChartPreferencesChange(value => ({ ...value, showVolume: !value.showVolume }));
      }
      if (action === "screenshot") {
        setExportStatus("Preparing chart image…");
        const baseCanvas = chartRef.current?.takeScreenshot();
        const canvas = document.createElement("canvas");
        if (baseCanvas) {
          canvas.width = baseCanvas.width; canvas.height = baseCanvas.height;
          canvas.getContext("2d").drawImage(baseCanvas, 0, 0);
        }
        const svg = chartContainer.current?.parentElement.querySelector(".drawings-layer");
        if (baseCanvas && svg) {
          const copy = svg.cloneNode(true);
          copy.setAttribute("xmlns", "http://www.w3.org/2000/svg");
          copy.setAttribute("width", canvas.width); copy.setAttribute("height", canvas.height);
          const bounds = svg.getBoundingClientRect();
          const chartBounds = chartContainer.current.getBoundingClientRect();
          copy.setAttribute("viewBox", "0 0 " + bounds.width + " " + chartBounds.height);
          copy.setAttribute("preserveAspectRatio", "none");
          copy.querySelectorAll(".drawing-handle-hit,.drawing-handle,.drawing-draft").forEach(element => element.remove());
          copy.querySelectorAll(".geometry-label,.position-label").forEach(text => { text.setAttribute("fill", text.getAttribute("fill") || "#eaf2fb"); text.style.fontFamily = "sans-serif"; });
          const url = URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(copy)], { type: "image/svg+xml" }));
          const image = new Image();
          image.onload = () => { canvas.getContext("2d").drawImage(image, 0, 0); setExportPreview(canvas.toDataURL()); setExportStatus(""); URL.revokeObjectURL(url); };
          image.onerror = () => { setExportStatus("Chart image could not be prepared. Please try again."); URL.revokeObjectURL(url); };
          image.src = url;
        } else setExportStatus("Load a chart before exporting.");
      }
    });
    return () => cancelAnimationFrame(frame);
    // Commands run once per user action; drawing callbacks read the current history refs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [command]);

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
    const indicatorSeries = {
      sma20: chart.addSeries(LineSeries, { color: "#f3bd55", lineWidth: 2, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false }),
      ema20: chart.addSeries(LineSeries, { color: "#58a6ff", lineWidth: 2, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false }),
      ema50: chart.addSeries(LineSeries, { color: "#bc8cff", lineWidth: 2, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false }),
    };
    const markers = createSeriesMarkers(series, []);
    chartRef.current = chart;
    seriesRef.current = series;
    volumeSeriesRef.current = volumeSeries;
    markersRef.current = markers;
    indicatorSeriesRef.current = indicatorSeries;
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
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
      volumeSeriesRef.current = null;
      markersRef.current = null;
      indicatorSeriesRef.current = {};
      priceLinesRef.current = [];
    };
  }, []);

  const commitDrawings = useCallback((nextValue) => {
    const next = typeof nextValue === "function" ? nextValue(drawingsRef.current) : nextValue;
    undoStackRef.current.push(drawingsRef.current);
    if (undoStackRef.current.length > 100) undoStackRef.current.shift();
    redoStackRef.current = [];
    setHistoryState({ canUndo: true, canRedo: false });
    drawingsRef.current = next;
    setDrawings(next);
  }, []);

  function updateDrawingPoint(id, index, point) {
    replaceDrawings(current => current.map(drawing => {
      if (drawing.id !== id) return drawing;
      const points = drawing.points.map(item => ({ ...item }));
      if (drawing.type.includes("position")) {
        const long = drawing.type === "long-position", entry = points[0];
        if (index === 1) point = { time: entry.time, price: long ? Math.min(entry.price - .001, point.price) : Math.max(entry.price + .001, point.price) };
        if (index === 2) point = { time: entry.time, price: long ? Math.max(entry.price + .001, point.price) : Math.min(entry.price - .001, point.price) };
        if (index === 3) point = { time: Math.max(timeAtLogical(candles, logicalAtTime(candles, entry.time) + 1), point.time), price: entry.price };
        if (index === 0) {
          const deltaPrice = point.price - entry.price;
          points.forEach(item => { item.price += deltaPrice; });
          points[1].time = point.time; points[2].time = point.time;
        }
      }
      points[index] = point;
      return { ...drawing, points };
    }));
  }

  function moveDrawing(id, points, screenAnchor) {
    replaceDrawings((current) => current.map((drawing) => drawing.id === id ? { ...drawing, points, ...(screenAnchor ? { screenAnchor } : {}) } : drawing));
  }

  function replaceDrawings(nextValue) {
    const next = typeof nextValue === "function" ? nextValue(drawingsRef.current) : nextValue;
    drawingsRef.current = next;
    setDrawings(next);
  }

  function startDrawingDrag() {
    chartRef.current?.applyOptions({ handleScroll: { pressedMouseMove: false, horzTouchDrag: false, vertTouchDrag: false } });
    undoStackRef.current.push(drawingsRef.current);
    if (undoStackRef.current.length > 100) undoStackRef.current.shift();
    redoStackRef.current = [];
    setHistoryState({ canUndo: true, canRedo: false });
  }

  const deleteSelectedDrawing = useCallback(() => {
    if (!selectedDrawingId) return;
    commitDrawings((current) => current.filter((drawing) => drawing.id !== selectedDrawingId));
    setSelectedDrawingId(null);
  }, [selectedDrawingId, commitDrawings]);

  function undoDrawing() {
    const previous = undoStackRef.current.pop();
    if (!previous) return;
    redoStackRef.current.push(drawingsRef.current);
    setHistoryState({ canUndo: undoStackRef.current.length > 0, canRedo: true });
    drawingsRef.current = previous;
    setDrawings(previous);
    setSelectedDrawingId(null);
  }

  function redoDrawing() {
    const next = redoStackRef.current.pop();
    if (!next) return;
    undoStackRef.current.push(drawingsRef.current);
    setHistoryState({ canUndo: true, canRedo: redoStackRef.current.length > 0 });
    drawingsRef.current = next;
    setDrawings(next);
  }

  function handleContextAction(action) {
    const drawing = drawings.find((item) => item.id === contextMenu?.id);
    setContextMenu(null);
    if (!drawing) {
      if (action === "reset") chartRef.current?.timeScale().fitContent();
      if (action === "undo") undoDrawing();
      if (["add-horizontal", "add-vertical"].includes(action) && contextMenu) {
        const bounds = chartContainer.current?.getBoundingClientRect();
        if (!bounds) return;
        const x = contextMenu.x - bounds.left;
        const y = contextMenu.y - bounds.top;
        const time = chartRef.current?.timeScale().coordinateToTime(x);
        const price = seriesRef.current?.coordinateToPrice(y);
        if (time == null || price == null) return;
        const type = action === "add-horizontal" ? "horizontal" : "vertical";
        const nextDrawing = { id: crypto.randomUUID(), type, points: [{ time, price: Number(price) }] };
        commitDrawings((current) => [...current, nextDrawing]);
        setSelectedDrawingId(nextDrawing.id);
      }
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
        ...(drawing.screenAnchor ? { screenAnchor: { x: Math.min(.95, drawing.screenAnchor.x + .03), y: Math.max(.05, drawing.screenAnchor.y - .03) } } : {}),
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
    if (drawingSettings.type.includes("position") && !positionStats(drawingSettings, candles.at(-1)?.close).valid) return;
    const settings = drawingSettings.type.includes("position") ? { ...drawingSettings, points: drawingSettings.points.map((point,index) => index === 1 || index === 2 ? {...point,time:drawingSettings.points[0].time} : index === 3 ? {...point,price:drawingSettings.points[0].price} : point) } : drawingSettings;
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
      if(event.altKey){const shortcuts={t:'trendline',h:'horizontal',j:'horizontal-ray',v:'vertical',c:'cross-line',f:'fib-retracement',r:event.shiftKey?'rectangle':undefined};const mode=shortcuts[event.key.toLowerCase()];if(mode){event.preventDefault();draftPointRef.current=null;setDraftDrawing(null);onDrawingModeChange(mode);return;}}
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
        draftPointRef.current = null;
        setDraftDrawing(null);
        onDrawingModeChange("none");
        setSelectedDrawingId(null);
      } else if (event.key === "Enter" && ["path","polyline"].includes(drawingMode) && draftPointRef.current?.length >= 2) {
        const object = { id: crypto.randomUUID(), type: drawingMode, points: draftPointRef.current };
        commitDrawings(current => [...current, object]);
        draftPointRef.current = null; setDraftDrawing(null); setSelectedDrawingId(object.id);
        if (!keepDrawing) onDrawingModeChange("none");
      } else if (event.altKey && event.key.toLowerCase() === "t") {
        event.preventDefault(); onDrawingModeChange("trendline");
      }
    }
    window.addEventListener("keydown", handleDrawingShortcut);
    return () => window.removeEventListener("keydown", handleDrawingShortcut);
  }, [selectedDrawingId, onDrawingModeChange, deleteSelectedDrawing, commitDrawings, drawingMode, keepDrawing]);

  useEffect(() => {
    const chart = chartRef.current, series = seriesRef.current;
    if (!chart || !series) return;
    const tool = drawingMode === "zoom-region" ? { name: "Zoom area", points: 2 } : DRAWING_TOOLS[drawingMode];
    const freehand = FREEHAND_TOOLS.has(drawingMode);
    const placing = Boolean(tool) || drawingMode === "demonstration";
    chart.applyOptions({ handleScroll: { pressedMouseMove: !placing, horzTouchDrag: !placing, vertTouchDrag: !placing }, handleScale: { mouseWheel: !freehand } });
    chart.applyOptions({ crosshair: { vertLine: { visible: chartPreferences.showCrosshair && drawingMode !== "cursor-arrow" }, horzLine: { visible: chartPreferences.showCrosshair && drawingMode !== "cursor-arrow" } } });
    draftPointRef.current = [];
    function pointFor(param) {
      if (!param.point) return null;
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
      if (!tool || freehand) { if (["none", "cursor-dot", "cursor-arrow"].includes(drawingMode)) setSelectedDrawingId(null); return; }
      let points = [...(draftPointRef.current || []), point];
      if (tool.points === 1 && drawingMode.includes("position")) {
        const isLong = drawingMode === "long-position", stop = series.coordinateToPrice(param.point.y + (isLong ? 48 : -48)), target = series.coordinateToPrice(param.point.y + (isLong ? -96 : 96));
        const endTime = timeAtLogical(candles, logicalAtTime(candles, point.time) + 30);
        if (stop == null || target == null) return;
        points = [point, { time: point.time, price: Number(stop) }, { time: point.time, price: point.price + (point.price - Number(stop)) }, { time: endTime, price: point.price }];
      }
      if (tool.points > 0 && points.length >= tool.points) {
        if (drawingMode === "zoom-region") {
          const from = logicalAtTime(candles, Math.min(points[0].time, points[1].time)), to = logicalAtTime(candles, Math.max(points[0].time, points[1].time));
          chart.timeScale().setVisibleLogicalRange({ from, to: Math.max(from + 1, to) });
          const low = Math.min(points[0].price, points[1].price), high = Math.max(points[0].price, points[1].price);
          chart.priceScale("right").setVisibleRange({ from: low, to: Math.max(low + .001, high) });
          setDraftDrawing(null); draftPointRef.current = []; onDrawingModeChange("none"); return;
        }
        const object = { id: crypto.randomUUID(), type: drawingMode, points, ...(TEXT_TOOLS.has(drawingMode) ? { text: drawingMode === "table" ? "Plan | Price\nEntry | " + point.price.toFixed(3) + "\nTarget | —" : tool.name } : {}) };
        if (drawingMode === "anchored-text") object.screenAnchor = { x: param.point.x / chart.timeScale().width(), y: param.point.y / chart.paneSize().height };
        commitDrawings(current => [...current, object]);
        setSelectedDrawingId(object.id); setDraftDrawing(null); draftPointRef.current = [];
        if (TEXT_TOOLS.has(drawingMode)) setDrawingSettings({ ...object, points: object.points.map(item => ({ ...item })) });
        if (!keepDrawing) onDrawingModeChange("none");
      } else {
        draftPointRef.current = points;
        setDraftDrawing({ id: "draft", type: drawingMode, points: [...points, point] });
      }
    }
    function preview(param) {
      const point = pointFor(param);
      if (!point || !tool || !draftPointRef.current?.length) return;
      const points = [...draftPointRef.current, point];
      while (tool.points > 0 && points.length < tool.points) points.push(point);
      setDraftDrawing({ id: "draft", type: drawingMode, points });
    }
    placementRef.current = handleChartClick; previewRef.current = preview;
    chart.subscribeClick(handleChartClick); chart.subscribeCrosshairMove(preview);
    return () => { chart.unsubscribeClick(handleChartClick); chart.unsubscribeCrosshairMove(preview); placementRef.current = null; previewRef.current = null; draftPointRef.current = []; };
  }, [drawingMode, onDrawingModeChange, onPriceSelect, commitDrawings, candles, keepDrawing, chartPreferences.showCrosshair]);

  useEffect(() => {
    if (!candles.length) return;
    indicatorSeriesRef.current.sma20?.setData(indicators.sma20 ? movingAverage(candles, 20) : []);
    indicatorSeriesRef.current.ema20?.setData(indicators.ema20 ? movingAverage(candles, 20, true) : []);
    indicatorSeriesRef.current.ema50?.setData(indicators.ema50 ? movingAverage(candles, 50, true) : []);
  }, [candles, indicators]);

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
  }, [candles, viewportKey]);

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

    const markers=[];
    const aligned=time=>{let lo=0,hi=candles.length-1,index=-1;while(lo<=hi){const mid=(lo+hi)>>1;if(candles[mid].time<=time){index=mid;lo=mid+1;}else hi=mid-1;}return index>=0?candles[index].time:null;};
    const addMarker=(time,side,text,exit=false)=>{const stamp=aligned(time);if(stamp==null)return;markers.push({time:stamp,position:(side==='Buy')!==exit?'belowBar':'aboveBar',color:side==='Buy'?'#22c99a':'#f06474',shape:(side==='Buy')!==exit?'arrowUp':'arrowDown',text});};
    const open=[...positions,...(position?[{id:'legacy',side:position.side==='BUY'?'Buy':'Sell',entry:position.entry_price,sl:position.stop_loss,tp:position.take_profit,entryTime:position.entry_time,size:position.size??1}]:[])];
    const pending=[...orders,...(pendingOrder?[{side:pendingOrder.side==='BUY'?'Buy':'Sell',entry:pendingOrder.entry_price,placedTime:pendingOrder.placed_time,type:pendingOrder.order_type}]:[])];
    open.forEach(item=>addMarker(item.entryTime,item.side,item.side));
    pending.forEach(item=>addMarker(item.placedTime,item.side,item.type));
    simulatedTrades.forEach(item=>{addMarker(item.entryTime,item.side,item.side);addMarker(item.exitTime,item.side,item.reason,true);});
    trades.forEach(item=>{addMarker(item.entry_time,item.side==='BUY'?'Buy':'Sell',item.side);addMarker(item.exit_time,item.side==='BUY'?'Buy':'Sell',item.reason,true);});
    markers.sort((a,b)=>a.time-b.time);markersRef.current?.setMarkers(markers);
    priceLinesRef.current.forEach(line=>series.removePriceLine(line));priceLinesRef.current=[];
    for(const item of [...open,...pending]){
      const lines=[{price:item.entry,title:open.includes(item)?`${item.side} ${item.size??''}`:item.type,color:open.includes(item)?'#5b8ff9':'#eabf64'},{price:item.sl,title:'SL',color:'#f06474'},{price:item.tp,title:'TP',color:'#22c99a'}];
      lines.filter(line=>Number.isFinite(line.price)).forEach(line=>priceLinesRef.current.push(series.createPriceLine({...line,lineWidth:1,lineStyle:2,axisLabelVisible:true})));
    }
  }, [position,pendingOrder,positions,orders,simulatedTrades,trades,candles]);

  const activeSpec = drawingMode === "zoom-region" ? { name: "Zoom area", points: 2 } : DRAWING_TOOLS[drawingMode];
  const toolHint = FREEHAND_TOOLS.has(drawingMode) ? "Drag untuk menggambar. Lepas untuk selesai." : ["path","polyline"].includes(drawingMode) ? "Klik titik path. Tekan Enter untuk selesai; Escape untuk batal." : drawingMode === "eraser" ? "Klik gambar untuk menghapus. Gambar terkunci dilindungi." : drawingMode === "demonstration" ? "Gerakkan pointer untuk menunjukkan area chart." : activeSpec ? activeSpec.name + " · Klik " + activeSpec.points + " titik" + (keepDrawing ? " · Keep drawing aktif" : "") : null;

  return (
    <div className="chart-wrap" onContextMenu={handleChartContextMenu} onClick={() => setContextMenu(null)}>
      <div className="chart-tools" aria-label="Chart indicators">
        <span>Indikator</span>
        <button type="button" className={indicators.sma20 ? "active" : ""} aria-pressed={indicators.sma20} onClick={() => setIndicators((value) => ({ ...value, sma20: !value.sma20 }))}>SMA 20</button>
        <button type="button" className={indicators.ema20 ? "active" : ""} aria-pressed={indicators.ema20} onClick={() => setIndicators((value) => ({ ...value, ema20: !value.ema20 }))}>EMA 20</button>
        <button type="button" className={indicators.ema50 ? "active" : ""} aria-pressed={indicators.ema50} onClick={() => setIndicators((value) => ({ ...value, ema50: !value.ema50 }))}>EMA 50</button>
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
      <div className="chart-canvas-layer">
        <div ref={chartContainer} className="candle-chart" />
        {onAmendOrder&&["none","cursor-dot","cursor-arrow"].includes(drawingMode)&&<TradingLevels chart={chartForOverlay} series={seriesForOverlay} positions={positions} orders={orders} onAmend={onAmendOrder} onClose={onClosePosition} onCancel={onCancelOrder} onError={onTradingError}/>}
        <DrawingsLayer chart={chartForOverlay} series={seriesForOverlay} candles={candles} drawings={draftDrawing && draftDrawing.type === drawingMode ? [...drawings, draftDrawing] : drawings} selectedId={selectedDrawingId} drawingMode={drawingMode} onPlacePoint={param => placementRef.current?.(param)} onPreviewPoint={param => previewRef.current?.(param)} magnet={magnetEnabled} onSelect={setSelectedDrawingId} onStartDrag={startDrawingDrag} onEndDrag={() => chartRef.current?.applyOptions({ handleScroll: { pressedMouseMove: !FREEHAND_TOOLS.has(drawingMode), horzTouchDrag: true, vertTouchDrag: true } })} onUpdatePoint={updateDrawingPoint} onMoveDrawing={moveDrawing} onErase={id => commitDrawings(current => current.filter(item => item.id !== id))} onCreateStroke={(type, points) => { const object = { id: crypto.randomUUID(), type, points }; commitDrawings(current => [...current, object]); setSelectedDrawingId(object.id); if (!keepDrawing) onDrawingModeChange("none"); }} onContextMenu={menu => { if (menu.edit) { const object = drawingsRef.current.find(item => item.id === menu.id); if (object) setDrawingSettings({ ...object, points: object.points.map(point => ({ ...point })) }); } else setContextMenu(menu); }} />
      </div>
      {selectedDrawingId&&drawings.find(item=>item.id===selectedDrawingId)&&<div className="selected-drawing-toolbar" aria-label="Selected drawing actions">
        <button aria-label="Drawing settings" onClick={()=>{const item=drawingsRef.current.find(item=>item.id===selectedDrawingId);setDrawingSettings({...item,points:item.points.map(point=>({...point}))});}}>⚙</button>
        <input aria-label="Drawing color" type="color" value={drawings.find(item=>item.id===selectedDrawingId)?.color||'#58a6ff'} onChange={event=>commitDrawings(current=>current.map(item=>item.id===selectedDrawingId?{...item,color:event.target.value}:item))}/>
        <button aria-label="Clone drawing" onClick={()=>{const item=drawingsRef.current.find(item=>item.id===selectedDrawingId);const copy={...item,id:crypto.randomUUID(),points:item.points.map(point=>({...point,time:point.time+(candles.intervalSeconds??60)}))};commitDrawings(current=>[...current,copy]);setSelectedDrawingId(copy.id);}}>⧉</button>
        <button aria-label="Lock selected drawing" onClick={()=>commitDrawings(current=>current.map(item=>item.id===selectedDrawingId?{...item,locked:!item.locked}:item))}>♙</button>
        {onCreateOrder&&['long-position','short-position'].includes(drawings.find(item=>item.id===selectedDrawingId)?.type)&&<button className="drawing-create-order" onClick={()=>onCreateOrder(drawingsRef.current.find(item=>item.id===selectedDrawingId))}>Create order</button>}
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
          <button type="button" role="menuitem" onClick={() => handleContextAction("add-horizontal")}>Add Horizontal Line</button>
          <button type="button" role="menuitem" onClick={() => handleContextAction("add-vertical")}>Add Vertical Line</button>
          <button type="button" role="menuitem" onClick={() => handleContextAction("reset")}>Reset chart view</button>
        </>}
      </div>}
      {drawingSettings && <form className="drawing-settings" onSubmit={saveDrawingSettings}>
        <div><strong>{drawingSettings.type.includes("position") ? (drawingSettings.type === "long-position" ? "Long Position" : "Short Position") : "Object settings"}</strong><button type="button" aria-label="Tutup settings" onClick={() => setDrawingSettings(null)}>×</button></div>
        {TEXT_TOOLS.has(drawingSettings.type) && <label>Text<textarea value={drawingSettings.text} onChange={(event) => setDrawingSettings((value) => ({ ...value, text: event.target.value }))} autoFocus /></label>}
        {drawingSettings.type.includes("position") && <>
<label>Risk mode<select value={drawingSettings.riskMode || "percent"} onChange={e=>setDrawingSettings(v=>({...v,riskMode:e.target.value}))}><option value="percent">% of account</option><option value="cash">Amount (USD)</option></select></label>
<label>Account size (USD)<input type="number" step="any" min="0.000001"  value={drawingSettings.accountSize ?? 100000} onChange={e=>setDrawingSettings(v=>({...v,accountSize:Number(e.target.value)}))} /></label>
<label>Risk<input type="number" step="any" min="0.000001"  value={drawingSettings.riskValue ?? 1} onChange={e=>setDrawingSettings(v=>({...v,riskValue:Number(e.target.value)}))} /></label>
<label>Lot size (units per lot)<input type="number" step="any" min="0.000001"  value={drawingSettings.lotSize ?? 1} onChange={e=>setDrawingSettings(v=>({...v,lotSize:Number(e.target.value)}))} /></label>
<label>Point value<input type="number" step="any" min="0.000001"  value={drawingSettings.pointValue ?? 1} onChange={e=>setDrawingSettings(v=>({...v,pointValue:Number(e.target.value)}))} /></label>
<label>Leverage<input type="number" step="any" min="0.000001"  value={drawingSettings.leverage ?? 1} onChange={e=>setDrawingSettings(v=>({...v,leverage:Number(e.target.value)}))} /></label>
<label>Tick size<input type="number" step="any" min="0.000001"  value={drawingSettings.tickSize ?? 0.01} onChange={e=>setDrawingSettings(v=>({...v,tickSize:Number(e.target.value)}))} /></label>
<label>Quantity precision<input type="number" step="any" min="0" max="8" value={drawingSettings.quantityPrecision ?? 3} onChange={e=>setDrawingSettings(v=>({...v,quantityPrecision:Number(e.target.value)}))} /></label>
          <label>Entry<input type="number" step="any" value={drawingSettings.points[0].price} onChange={(event) => setDrawingSettings((value) => ({ ...value, points: value.points.map((point, index) => index === 0 ? { ...point, price: Number(event.target.value) } : point) }))} /></label>
          <label>Stop Loss<input type="number" step="any" value={drawingSettings.points[1].price} onChange={(event) => setDrawingSettings((value) => ({ ...value, points: value.points.map((point, index) => index === 1 ? { ...point, price: Number(event.target.value) } : point) }))} /></label>
          <label>Take Profit<input type="number" step="any" value={drawingSettings.points[2].price} onChange={(event) => setDrawingSettings((value) => ({ ...value, points: value.points.map((point, index) => index === 2 ? { ...point, price: Number(event.target.value) } : point) }))} /></label>
        </>}
        {drawingSettings.type.includes("position") && <>
          <label>Risk/Reward Ratio<input type="number" min="0.01" step="any" value={positionStats(drawingSettings,candles.at(-1)?.close).ratio || ''} onChange={e=>setDrawingSettings(v=>({...v,points:v.points.map((p,i)=>i===2?{...p,price:v.points[0].price+(v.points[0].price-v.points[1].price)*Number(e.target.value)}:p)}))} /></label>
          <label><input type="checkbox" checked={drawingSettings.alwaysShowStats !== false} onChange={e=>setDrawingSettings(v=>({...v,alwaysShowStats:e.target.checked}))} />Always show statistics</label>
          <output>Qty: {positionStats(drawingSettings,candles.at(-1)?.close).quantity} · Risk/Reward Ratio: {positionStats(drawingSettings,candles.at(-1)?.close).ratio.toFixed(2)}</output>
          {!positionStats(drawingSettings,candles.at(-1)?.close).valid && <p role="alert">Check entry, stop and target direction; account and sizing values must be positive.</p>}
        </>}
        <label>Line width<input type="number" min="1" max="24" value={drawingSettings.lineWidth || 2} onChange={event => setDrawingSettings(value => ({ ...value, lineWidth: Math.max(1, Math.min(24, Number(event.target.value))) }))} /></label>
        <label>Font size<input type="number" min="8" max="48" value={drawingSettings.fontSize || 12} onChange={event => setDrawingSettings(value => ({ ...value, fontSize: Math.max(8, Math.min(48, Number(event.target.value))) }))} /></label>
        <label>Color<input type="color" value={drawingSettings.color || "#58a6ff"} onInput={event => setDrawingSettings(value => ({ ...value, color: event.target.value }))} onChange={(event) => setDrawingSettings((value) => ({ ...value, color: event.target.value }))} /></label>
        <details><summary>Coordinates (UTC)</summary>
          {drawingSettings.points.map((point, index) => FREEHAND_TOOLS.has(drawingSettings.type) && index !== 0 && index !== drawingSettings.points.length - 1 ? null : <div key={index} className="coordinate-fields">
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

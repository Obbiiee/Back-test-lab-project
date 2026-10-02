import { useEffect, useRef, useState } from "react";
import { FREEHAND_TOOLS, logicalAtTime, timeAtLogical } from "../drawings/tools";
import DrawingGeometry from "./DrawingGeometry";
import { positionStats } from "../drawings/position";

function DrawingsLayer({ chart, series, candles = [], drawings, selectedId, drawingMode = "none", onSelect, onStartDrag, onEndDrag, onUpdatePoint, onMoveDrawing, onContextMenu, onCreateStroke, onErase, onPlacePoint, onPreviewPoint, magnet = false }) {
  const svgRef = useRef(null), dragging = useRef(null), stroke = useRef(null);
  const [strokePreview, setStrokePreview] = useState(null);
  const [pointer, setPointer] = useState(null);
  const [, refreshProjection] = useState(0);
  const freehand = FREEHAND_TOOLS.has(drawingMode);
  const neutral = ["none", "cursor-dot", "cursor-arrow", "eraser"].includes(drawingMode);
  const placing = !neutral && !freehand && drawingMode !== "demonstration";

  useEffect(() => {
    let frame = 0;
    const refresh = () => { if (!frame) frame = requestAnimationFrame(() => { frame = 0; refreshProjection(value => value + 1); }); };
    chart?.timeScale().subscribeVisibleLogicalRangeChange(refresh);
    chart?.timeScale().subscribeSizeChange(refresh);
    window.addEventListener("pointermove", refresh, { passive: true });
    window.addEventListener("wheel", refresh, { passive: true });
    window.addEventListener("resize", refresh);
    return () => {
      chart?.timeScale().unsubscribeVisibleLogicalRangeChange(refresh);
      chart?.timeScale().unsubscribeSizeChange(refresh);
      window.removeEventListener("pointermove", refresh);
      window.removeEventListener("wheel", refresh);
      window.removeEventListener("resize", refresh);
      if (frame) cancelAnimationFrame(frame);
    };
  }, [chart]);

  function coordinates(event) {
    const bounds = svgRef.current.getBoundingClientRect();
    const x = event.clientX - bounds.left, y = event.clientY - bounds.top;
    const logical = chart?.timeScale().coordinateToLogical(x);
    const time = timeAtLogical(candles, logical);
    let price = series?.coordinateToPrice(y);
    if (time == null || price == null) return null;
    if (magnet) {
      const bar = candles[Math.round(logical)];
      if (bar) price = [bar.open, bar.high, bar.low, bar.close].reduce((best, value) => Math.abs(value - price) < Math.abs(best - price) ? value : best);
    }
    return { time, price: Number(price), logical: Math.round(logical), x, y };
  }
  function beginDrag(event, drawing, pointIndex = null) {
    event.preventDefault(); event.stopPropagation();
    if (drawingMode === "eraser") { if (!drawing.locked) onErase(drawing.id); return; }
    onSelect(drawing.id);
    if (drawing.locked || drawing.id === "draft") return;
    const point = coordinates(event);
    if (!point) return;
    svgRef.current.setPointerCapture(event.pointerId);
    onStartDrag();
    dragging.current = { id: drawing.id, pointIndex: drawing.screenAnchor ? null : pointIndex, start: point, drawing, points: drawing.points };
  }
  function movePointer(event) {
    const point = coordinates(event);
    if (!point) return;
    if (drawingMode === "demonstration") setPointer({ x: point.x, y: point.y });
    if (placing) onPreviewPoint?.({ point: { x: point.x, y: point.y }, time: point.time });
    if (stroke.current) {
      stroke.current.push({ time: point.time, price: point.price });
      setStrokePreview({ id: "stroke-preview", type: drawingMode, points: [...stroke.current] });
    }
    const drag = dragging.current;
    if (!drag) return;
    if (drag.pointIndex == null) {
      const delta = point.logical - drag.start.logical, priceDelta = point.price - drag.start.price;
      const points = drag.points.map(item => ({ time: timeAtLogical(candles, logicalAtTime(candles, item.time) + delta), price: item.price + priceDelta }));
      const screenAnchor = drag.drawing.screenAnchor ? { x: Math.max(0, Math.min(1, drag.drawing.screenAnchor.x + (point.x - drag.start.x) / chart.timeScale().width())), y: Math.max(0, Math.min(1, drag.drawing.screenAnchor.y + (point.y - drag.start.y) / chart.paneSize().height)) } : undefined;
      onMoveDrawing(drag.id, points, screenAnchor);
    } else {
      // Stop and target handles change price only, rather than shifting the position's entry time.
      const positionLevel = drag.drawing.type.includes("position") && [1, 2].includes(drag.pointIndex);
      onUpdatePoint(drag.id, drag.pointIndex, { time: positionLevel ? drag.points[drag.pointIndex].time : point.time, price: point.price });
    }
  }
  function stopPointer(event) {
    if (stroke.current) {
      const points = stroke.current;
      stroke.current = null; setStrokePreview(null);
      if (points.length > 1) onCreateStroke(drawingMode, points);
    }
    if (dragging.current) { dragging.current = null; onEndDrag?.(); }
    if (event && svgRef.current.hasPointerCapture(event.pointerId)) svgRef.current.releasePointerCapture(event.pointerId);
  }
  function startStroke(event) {
    if (!freehand) return;
    const point = coordinates(event);
    if (!point) return;
    event.preventDefault(); event.stopPropagation();
    svgRef.current.setPointerCapture(event.pointerId);
    stroke.current = [{ time: point.time, price: point.price }];
  }
  function project(point) {
    if (!chart || !series || !point) return null;
    const x = chart.timeScale().logicalToCoordinate(logicalAtTime(candles, point.time));
    const y = series.priceToCoordinate(point.price);
    return x == null || y == null || !Number.isFinite(x + y) ? null : { x, y };
  }
  function handle(drawing, index, point) {
    return <g key={index} onPointerDown={event => beginDrag(event, drawing, index)}>
      <circle cx={point.x} cy={point.y} r="9" className="drawing-handle-hit" />
      <circle cx={point.x} cy={point.y} r="4" className="drawing-handle" />
    </g>;
  }
  function renderDrawing(drawing) {
    if (drawing.hidden) return null;
    const p = drawing.points.map(project);
    if (p.some(point => !point)) return null;
    const width = chart.timeScale().width(), height = chart.paneSize().height;
    if (drawing.screenAnchor) p[0] = { x: drawing.screenAnchor.x * width, y: drawing.screenAnchor.y * height };
    const selected = selectedId === drawing.id;
    let geometry;
    if (drawing.type === "long-position" || drawing.type === "short-position") {
      const entry = p[0], stop = p[1], target = p[2];
      if (!stop || !target) return null;
      const end = p[3]?.x ?? entry.x + 150, boxWidth = Math.max(20, end - entry.x);
      const stats = positionStats(drawing, candles.at(-1)?.close ?? drawing.points[0].price);
      const labelWidth = Math.max(boxWidth, 310);
      const label = (y, text, color, key) => <g key={key}><rect x={entry.x + boxWidth / 2 - labelWidth / 2} y={y-13} width={labelWidth} height="23" rx="3" fill={color} /><text x={entry.x + boxWidth / 2} y={y+2} textAnchor="middle" className="position-label" style={{fontSize: drawing.fontSize || 11}}>{text}</text></g>;
      geometry = <>
        <rect x={entry.x} y={Math.min(entry.y, target.y)} width={boxWidth} height={Math.max(1, Math.abs(target.y - entry.y))} fill="#25c99632" />
        <rect x={entry.x} y={Math.min(entry.y, stop.y)} width={boxWidth} height={Math.max(1, Math.abs(stop.y - entry.y))} fill="#f0647430" />
        {[entry, stop, target].map((point, i) => <line key={i} x1={entry.x} y1={point.y} x2={entry.x + boxWidth} y2={point.y} stroke={["#58a6ff", "#f06474", "#25c996"][i]} strokeWidth={drawing.lineWidth || 1.5} />)}
        {(selected || drawing.alwaysShowStats !== false) && <>
          {label(target.y + (target.y < entry.y ? -14 : 22), `Target: ${stats.reward.toFixed(2)} (${stats.rewardPercent.toFixed(2)}%) ${stats.targetTicks.toFixed(0)} ticks · Amount: ${stats.targetBalance.toFixed(2)}`, '#16866b', 'target')}
          {label(entry.y, `Open P&L: ${stats.openPnl.toFixed(2)} · Qty: ${stats.quantity} · Risk/Reward Ratio: ${stats.ratio.toFixed(2)}`, '#263d52', 'entry')}
          {label(stop.y + (stop.y < entry.y ? -14 : 22), `Stop: ${stats.risk.toFixed(2)} (${stats.riskPercent.toFixed(2)}%) ${stats.stopTicks.toFixed(0)} ticks · Amount: ${stats.stopBalance.toFixed(2)}`, '#aa3948', 'stop')}
        </>}
        {[entry,stop,target].map((point,index)=><g key={'price-'+index}><rect x={Math.max(0,width-60)} y={point.y-10} width="60" height="20" fill={['#345f8a','#aa3948','#16866b'][index]} /><text x={width-4} y={point.y+4} textAnchor="end" className="position-label">{drawing.points[index].price.toFixed(2)}</text></g>)}
        <rect x={entry.x} y={Math.min(entry.y, stop.y, target.y)} width={boxWidth} height={Math.max(12, Math.max(entry.y, stop.y, target.y) - Math.min(entry.y, stop.y, target.y))} fill="transparent" className="position-hit" />
      </>;
      if (selected) { p[1] = { x: entry.x + boxWidth, y: stop.y }; p[2] = { x: entry.x + boxWidth, y: target.y }; }
    } else geometry = <DrawingGeometry drawing={drawing} projected={p} project={project} candles={candles} width={width} height={height} />;
    return <g key={drawing.id} data-drawing-id={drawing.id} data-drawing-type={drawing.type} data-anchors={JSON.stringify(drawing.points)} data-locked={Boolean(drawing.locked)} className={drawing.id === "draft" ? "drawing-draft" : ""}
      onContextMenu={event => { event.preventDefault(); event.stopPropagation(); onSelect(drawing.id); onContextMenu({ id: drawing.id, x: event.clientX, y: event.clientY }); }}
      onDoubleClick={event => { event.stopPropagation(); onSelect(drawing.id); onContextMenu({ id: drawing.id, x: event.clientX, y: event.clientY, edit: true }); }}
      onPointerDown={event => beginDrag(event, drawing)}>
      {geometry}
      {selected && !drawing.locked && p.filter((_, index) => !FREEHAND_TOOLS.has(drawing.type) || index === 0 || index === p.length - 1).map((point, index) => handle(drawing, FREEHAND_TOOLS.has(drawing.type) && index === 1 ? p.length - 1 : index, point))}
      {selected && drawing.locked && <text x={p[0].x + 10} y={p[0].y - 10} className="geometry-label" fill="#a5a8ad">🔒</text>}
    </g>;
  }
  return <svg ref={svgRef} className={"drawings-layer " + (!neutral ? "tool-active " : "") + (placing ? "placement-active " : "") + (freehand || drawingMode === "demonstration" ? "freehand-active " : "") + (drawingMode === "eraser" ? "erase-active" : "")}
    onClick={event => { if (placing) { const point = coordinates(event); if (point) { event.stopPropagation(); onPlacePoint?.({ point: { x: point.x, y: point.y }, time: point.time }); } } }}
    onPointerDown={startStroke} onPointerMove={movePointer} onPointerUp={stopPointer} onPointerCancel={stopPointer} onLostPointerCapture={() => { if (dragging.current) { dragging.current = null; onEndDrag?.(); } }} aria-label="Drawing objects">
    {drawings.map(renderDrawing)}
    {strokePreview && renderDrawing(strokePreview)}
    {drawingMode === "demonstration" && pointer && <circle cx={pointer.x} cy={pointer.y} r="14" fill="#ff465566" stroke="#ff4655" strokeWidth="2" pointerEvents="none" />}
  </svg>;
}
export default DrawingsLayer;

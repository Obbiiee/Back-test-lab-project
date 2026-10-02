import { useEffect, useRef, useState } from "react";
import { logicalAtTime, timeAtLogical } from "../chart/coordinates";

function ChartObjectOverlay({ chart, series, candles = [], drawings, selectedId, drawingMode = "none", onSelect, onStartDrag, onEndDrag, onUpdatePoint, onMoveDrawing, onContextMenu, onCreateStroke, onErase, onPlacePoint, onPreviewPoint, magnet = false, renderGeometry, isFreehand = () => false, isPriceOnlyAnchor = () => false, handleProjection, layerName = "Drawing objects", layerClass = "" }) {
  const svgRef = useRef(null), dragging = useRef(null), stroke = useRef(null);
  const [strokePreview, setStrokePreview] = useState(null);
  const [pointer, setPointer] = useState(null);
  const [, refreshProjection] = useState(0);
  const freehand = isFreehand(drawingMode);
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
    dragging.current = { id: drawing.id, pointIndex: drawing.screenAnchor ? null : pointIndex, start: point, drawing: { ...drawing }, points: drawing.points.map(point => ({ ...point })) };
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
      const positionLevel = isPriceOnlyAnchor(drag.drawing, drag.pointIndex);
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
    const geometry = renderGeometry({ drawing, projected: p, project, candles, width, height, selected });
    const handles = handleProjection ? handleProjection(p) : p;
    // Pointer callbacks read capture/drag refs only when an event fires, never during render.
    // eslint-disable-next-line react-hooks/refs
    const onPointerDown = event => beginDrag(event, drawing);
    return <g key={drawing.id} data-drawing-id={drawing.id} data-drawing-type={drawing.type} data-anchors={JSON.stringify(drawing.points)} data-locked={Boolean(drawing.locked)} className={drawing.id === "draft" ? "drawing-draft" : ""}
      onContextMenu={event => { event.preventDefault(); event.stopPropagation(); onSelect(drawing.id); onContextMenu({ id: drawing.id, x: event.clientX, y: event.clientY }); }}
      onDoubleClick={event => { event.stopPropagation(); onSelect(drawing.id); onContextMenu({ id: drawing.id, x: event.clientX, y: event.clientY, edit: true }); }}
      onPointerDown={onPointerDown}>
      {geometry}
      {selected && !drawing.locked && handles.filter((_, index) => !isFreehand(drawing.type) || index === 0 || index === handles.length - 1).map((point, index) => handle(drawing, isFreehand(drawing.type) && index === 1 ? handles.length - 1 : index, point))}
      {selected && drawing.locked && <text x={p[0].x + 10} y={p[0].y - 10} className="geometry-label" fill="#a5a8ad">🔒</text>}
    </g>;
  }
  return <svg ref={svgRef} className={"drawings-layer " + layerClass + " " + (!neutral ? "tool-active " : "") + (placing ? "placement-active " : "") + (freehand || drawingMode === "demonstration" ? "freehand-active " : "") + (drawingMode === "eraser" ? "erase-active" : "")}
    onClick={event => { if (placing) { const point = coordinates(event); if (point) { event.stopPropagation(); onPlacePoint?.({ point: { x: point.x, y: point.y }, time: point.time }); } } }}
    onPointerDown={startStroke} onPointerMove={movePointer} onPointerUp={stopPointer} onPointerCancel={stopPointer} onLostPointerCapture={() => { if (dragging.current) { dragging.current = null; onEndDrag?.(); } }} aria-label={layerName}>
    {drawings.map(renderDrawing)}
    {strokePreview && renderDrawing(strokePreview)}
    {drawingMode === "demonstration" && pointer && <circle cx={pointer.x} cy={pointer.y} r="14" fill="#ff465566" stroke="#ff4655" strokeWidth="2" pointerEvents="none" />}
  </svg>;
}
export default ChartObjectOverlay;

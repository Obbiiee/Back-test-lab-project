import { useEffect, useRef, useState } from "react";
import { logicalAtTime, timeAtLogical } from "../chart/coordinates";

function ChartObjectOverlay({ chart, series, candles = [], drawings, selectedId, drawingMode = "none", onSelect, onStartDrag, onEndDrag, onUpdatePoint, onMoveDrawing, onContextMenu, onPlacePoint, magnet = false, renderGeometry, isPriceOnlyAnchor = () => false, handleProjection, layerName = "Drawing objects", layerClass = "" }) {
  const svgRef = useRef(null), dragging = useRef(null);
  const [, refreshProjection] = useState(0);
  const neutral = ["none", "cursor-dot", "cursor-arrow"].includes(drawingMode);
  const placing = !neutral;

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
    onSelect(drawing.id);
    if (drawing.locked) return;
    const point = coordinates(event);
    if (!point) return;
    svgRef.current.setPointerCapture(event.pointerId);
    onStartDrag();
    dragging.current = { id: drawing.id, pointIndex, start: point, drawing: { ...drawing }, points: drawing.points.map(point => ({ ...point })) };
  }
  function movePointer(event) {
    const point = coordinates(event);
    if (!point) return;
    const drag = dragging.current;
    if (!drag) return;
    if (drag.pointIndex == null) {
      const delta = point.logical - drag.start.logical, priceDelta = point.price - drag.start.price;
      const points = drag.points.map(item => ({ time: timeAtLogical(candles, logicalAtTime(candles, item.time) + delta), price: item.price + priceDelta }));
      onMoveDrawing(drag.id, points);
    } else {
      // Stop and target handles change price only, rather than shifting the position's entry time.
      const positionLevel = isPriceOnlyAnchor(drag.drawing, drag.pointIndex);
      onUpdatePoint(drag.id, drag.pointIndex, { time: positionLevel ? drag.points[drag.pointIndex].time : point.time, price: point.price });
    }
  }
  function stopPointer(event) {
    if (dragging.current) { dragging.current = null; onEndDrag?.(); }
    if (event && svgRef.current.hasPointerCapture(event.pointerId)) svgRef.current.releasePointerCapture(event.pointerId);
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
    const selected = selectedId === drawing.id;
    const geometry = renderGeometry({ drawing, projected: p, project, candles, width, height, selected });
    const handles = handleProjection ? handleProjection(p) : p;
    // Pointer callbacks read capture/drag refs only when an event fires, never during render.
    const onPointerDown = event => beginDrag(event, drawing);
    return <g key={drawing.id} data-drawing-id={drawing.id} data-drawing-type={drawing.type} data-anchors={JSON.stringify(drawing.points)} data-locked={Boolean(drawing.locked)}
      onContextMenu={event => { event.preventDefault(); event.stopPropagation(); onSelect(drawing.id); onContextMenu({ id: drawing.id, x: event.clientX, y: event.clientY }); }}
      onDoubleClick={event => { event.stopPropagation(); onSelect(drawing.id); onContextMenu({ id: drawing.id, x: event.clientX, y: event.clientY, edit: true }); }}
      onPointerDown={onPointerDown}>
      {geometry}
      {selected && !drawing.locked && handles.map((point, index) => handle(drawing, index, point))}
      {selected && drawing.locked && <text x={p[0].x + 10} y={p[0].y - 10} className="geometry-label" fill="#a5a8ad">🔒</text>}
    </g>;
  }
  return <svg ref={svgRef} className={"drawings-layer " + layerClass + " " + (!neutral ? "tool-active " : "") + (placing ? "placement-active " : "")}
    onClick={event => { if (placing) { const point = coordinates(event); if (point) { event.stopPropagation(); onPlacePoint?.({ point: { x: point.x, y: point.y }, time: point.time }); } } }}
    onPointerMove={movePointer} onPointerUp={stopPointer} onPointerCancel={stopPointer} onLostPointerCapture={() => { if (dragging.current) { dragging.current = null; onEndDrag?.(); } }} aria-label={layerName}>
    {drawings.map(renderDrawing)}
  </svg>;
}
export default ChartObjectOverlay;

import { RISK_REWARD_TOOLS } from "../trading/RiskRewardController.js";

// Drawing names come from the user's Figma reference; this is the shared tool registry.
const groups = {
  trend: [
    ["Trend Line", "trendline", 2], ["Ray", "ray", 2], ["Info Line", "info-line", 2],
    ["Extended Line", "extended-line", 2], ["Trend Angle", "trend-angle", 2],
    ["Horizontal Line", "horizontal", 1], ["Horizontal Ray", "horizontal-ray", 1],
    ["Vertical Line", "vertical", 1], ["Cross Line", "cross-line", 1],
    ["Parallel Channel", "parallel-channel", 3], ["Regression Trend", "regression", 2],
    ["Flat Top / Bottom", "flat-channel", 3], ["Disjoint Channel", "disjoint-channel", 4],
    ["Pitchfork", "pitchfork", 3], ["Schiff Pitchfork", "schiff-pitchfork", 3], ["Modified Schiff Pitchfork", "modified-schiff-pitchfork", 3], ["Inside Pitchfork", "inside-pitchfork", 3],
  ],
  fib: [
    ["Fib Retracement", "fib-retracement", 2], ["Trend-Based Fib Extension", "fib-extension", 3],
    ["Fib Channel", "fib-channel", 3], ["Fib Time Zone", "fib-time-zone", 2],
    ["Fib Speed Resistance Fan", "fib-fan", 2], ["Trend-Based Fib Time", "fib-time", 3],
    ["Fib Circles", "fib-circles", 2], ["Fib Spiral", "fib-spiral", 2],
    ["Fib Speed Resistance Arcs", "fib-arcs", 2], ["Fib Wedge", "fib-wedge", 3],
    ["Pitchfan", "pitchfan", 3], ["Gann Box", "gann-box", 2],
    ["Gann Square Fixed", "gann-fixed", 2], ["Gann Square", "gann-square", 3],
    ["Gann Fan", "gann-fan", 2],
  ],
  pattern: [
    ["XABCD Pattern", "xabcd", 5], ["Cypher Pattern", "cypher", 5],
    ["Head and Shoulders", "head-shoulders", 7], ["ABCD Pattern", "abcd", 4],
    ["Triangle Pattern", "triangle", 3], ["Three Drives Pattern", "three-drives", 6],
    ["Elliott Impulse Wave (12345)", "elliott-impulse", 6],
    ["Elliott Correction Wave (ABC)", "elliott-correction", 4],
    ["Elliott Triangle Wave (ABCDE)", "elliott-triangle", 6],
    ["Elliott Double Combo Wave", "elliott-combo", 8],
    ["Elliott Triple Combo Wave", "elliott-triple", 8], ["Cyclic Lines", "cyclic-lines", 2], ["Time Cycles", "time-cycles", 2],
  ],
  measure: [
    ["Position Forecast", "forecast", 2], ["Bars Pattern", "bars-pattern", 3],
    ["Ghost Feed", "ghost-feed", 3], ["Sector", "sector", 3],
    ["Anchored VWAP", "anchored-vwap", 1], ["Fixed Range Volume Profile", "volume-profile", 2],
    ["Anchored Volume Profile", "anchored-profile", 1],
    ["Price Range", "price-range", 2], ["Date Range", "date-range", 2],
    ["Date and Price Range", "date-price-range", 2],
  ],
  brush: [
    ["Brush", "brush", 0], ["Highlighter", "highlighter", 0],
    ["Arrow Marker", "arrow-marker", 1], ["Arrow", "arrow", 2],
    ["Arrow Mark Up", "arrow-up", 1], ["Arrow Mark Down", "arrow-down", 1],
    ["Arrow Mark Left", "arrow-left", 1], ["Arrow Mark Right", "arrow-right", 1],
    ["Rectangle", "rectangle", 2], ["Rotated Rectangle", "rotated-rectangle", 3],
    ["Path", "path", -1], ["Circle", "circle", 2], ["Ellipse", "ellipse", 2],
    ["Polyline", "polyline", -1], ["Triangle", "shape-triangle", 3], ["Arc", "arc", 3], ["Curve", "curve", 3], ["Double Curve", "double-curve", 4],
  ],
  text: [
    ["Text", "text", 1], ["Anchored Text", "anchored-text", 1], ["Note", "note", 1],
    ["Price Note", "price-note", 1], ["Pin", "pin", 1], ["Table", "table", 1],
    ["Callout", "callout", 2], ["Comment", "comment", 1], ["Price Label", "price-label", 1],
    ["Signpost", "signpost", 1], ["Flag Mark", "flag", 1],
  ],
  smile: [["Smile", "emoji-smile", 1], ["Star", "emoji-star", 1], ["Check", "emoji-check", 1], ["Warning", "emoji-warning", 1]],
};
export const DRAWING_TOOLS = { ...RISK_REWARD_TOOLS, ...Object.fromEntries(Object.entries(groups).flatMap(([group, rows]) => rows.map(([name, type, points]) => [type, { name, type, points, group }]))) };
export function resolveTool(name, group) {
  if (group === "cursor") return ({ Cross: "none", Dot: "cursor-dot", Arrow: "cursor-arrow", Demonstration: "demonstration", Eraser: "eraser" })[name];
  return Object.values(DRAWING_TOOLS).find(tool => tool.name === name && tool.group === group)?.type;
}
export const TEXT_TOOLS = new Set(Object.values(DRAWING_TOOLS).filter(tool => tool.group === "text").map(tool => tool.type));
export const FREEHAND_TOOLS = new Set(["brush", "highlighter"]);
export const PATTERN_TOOLS = new Set(Object.values(DRAWING_TOOLS).filter(tool => tool.group === "pattern").map(tool => tool.type));
export const FIB_LEVELS = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1];

export { timeAtLogical, logicalAtTime } from "../chart/coordinates.js";
export function selectedBars(candles, points, anchored = false) {
  const start = Math.min(points[0].time, anchored ? points[0].time : points[1]?.time ?? points[0].time);
  const end = anchored ? Infinity : Math.max(points[0].time, points[1]?.time ?? points[0].time);
  return candles.filter(bar => bar.time >= start && bar.time <= end);
}
export function regression(bars) {
  if (!bars.length) return null;
  const n = bars.length, meanX = (n - 1) / 2, meanY = bars.reduce((sum, b) => sum + b.close, 0) / n;
  let top = 0, bottom = 0;
  bars.forEach((b, i) => { top += (i - meanX) * (b.close - meanY); bottom += (i - meanX) ** 2; });
  const slope = bottom ? top / bottom : 0, intercept = meanY - slope * meanX;
  const deviation = Math.sqrt(bars.reduce((sum, b, i) => sum + (b.close - intercept - slope * i) ** 2, 0) / n);
  return { slope, intercept, deviation };
}
export function anchoredVWAP(bars) {
  let total = 0, weighted = 0;
  return bars.flatMap(bar => { const volume = Math.max(0, Number(bar.volume || 0)); total += volume; weighted += (bar.high + bar.low + bar.close) / 3 * volume; return total ? [{ time: bar.time, price: weighted / total }] : []; });
}
export function volumeProfile(bars, rows = 20) {
  if (!bars.length) return [];
  const low = Math.min(...bars.map(b => b.low)), high = Math.max(...bars.map(b => b.high)), step = (high - low || 1) / rows;
  const buckets = Array.from({ length: rows }, (_, index) => ({ price: low + (index + .5) * step, volume: 0 }));
  // OHLCV cannot tell us exact volume-at-price. Spread each bar's volume uniformly over its range.
  bars.forEach(bar => {
    const first = Math.max(0, Math.min(rows - 1, Math.floor((bar.low - low) / step)));
    const last = Math.max(first, Math.min(rows - 1, Math.floor((bar.high - low) / step)));
    for (let i = first; i <= last; i++) buckets[i].volume += Math.max(0, Number(bar.volume || 0)) / (last - first + 1);
  });
  return buckets;
}

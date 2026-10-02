import { anchoredVWAP, FIB_LEVELS, PATTERN_TOOLS, regression, selectedBars, TEXT_TOOLS, volumeProfile } from "../drawings/tools";

function DrawingGeometry({ drawing, projected: p, project, candles, width, height }) {
  const type = drawing.type, color = drawing.color || "#58a6ff", strokeWidth = drawing.lineWidth || 2;
  const a = p[0], b = p[1] || a, c = p[2] || b, d = p[3] || c;
  if (!a) return null;
  const left = Math.min(a.x, b.x), top = Math.min(a.y, b.y), w = Math.max(1, Math.abs(b.x - a.x)), h = Math.max(1, Math.abs(b.y - a.y));
  const line = (x1, y1, x2, y2, key, dash) => <g key={key}><line x1={x1} y1={y1} x2={x2} y2={y2} stroke={color} strokeWidth={strokeWidth} strokeDasharray={dash} /><line x1={x1} y1={y1} x2={x2} y2={y2} stroke="transparent" strokeWidth="12" /></g>;
  const label = (x, y, text, key = text) => <text key={key} x={x} y={y} fill={color} fontSize={drawing.fontSize || 12} className="geometry-label">{text}</text>;
  const poly = (points, closed = false, fill = "none", key = "poly") => closed
    ? <polygon key={key} points={points.map(point => point.x + "," + point.y).join(" ")} stroke={color} strokeWidth={strokeWidth} fill={fill} />
    : <g key={key}><polyline points={points.map(point => point.x + "," + point.y).join(" ")} stroke={color} strokeWidth={strokeWidth} fill="none" /><polyline points={points.map(point => point.x + "," + point.y).join(" ")} stroke="transparent" strokeWidth="12" fill="none" /></g>;
  const yAt = x => a.y + (b.y - a.y) * ((x - a.x) / (b.x - a.x || .001));
  const ratios = drawing.levels || FIB_LEVELS;
  const bars = selectedBars(candles, drawing.points, type === "anchored-profile" || type === "anchored-vwap");

  if(type.includes('pitchfork')) {
    const origin=type==='schiff-pitchfork'?{x:a.x,y:(a.y+b.y)/2}:type==='modified-schiff-pitchfork'||type==='inside-pitchfork'?{x:(a.x+b.x)/2,y:(a.y+b.y)/2}:a;
    const center={x:(b.x+c.x)/2,y:(b.y+c.y)/2},dx=center.x-origin.x,dy=center.y-origin.y;
    const end=start=>Math.abs(dx)<.01?{x:start.x,y:dy>=0?height:0}:{x:dx>=0?width:0,y:start.y+dy/dx*((dx>=0?width:0)-start.x)};
    return <>{line(b.x,b.y,c.x,c.y,'base','3 3')}{[origin,b,c].map((start,i)=>{const to=end(start);return line(start.x,start.y,to.x,to.y,i,i===0?'4 4':undefined);})}</>;
  }
  if(type==='gann-fan')return [.125,.25,.5,1,2,4,8].map(ratio=>{const dx=b.x-a.x,dy=(b.y-a.y)*ratio;const edge=dx>=0?width:0;const y=Math.abs(dx)<.01?(dy>=0?height:0):a.y+dy/dx*(edge-a.x);return <g key={ratio}>{line(a.x,a.y,Math.abs(dx)<.01?a.x:edge,y,'fan')}{label(b.x,b.y+(b.y-a.y)*(ratio-1),`${ratio}:1`)}</g>;});
  if(type==='cyclic-lines'||type==='time-cycles'){
    const step=Math.max(1,Math.abs(b.x-a.x)),first=a.x-Math.ceil(a.x/step)*step;
    return Array.from({length:Math.min(250,Math.ceil(width/step)+2)},(_,i)=>{const x=first+i*step;return type==='cyclic-lines'?line(x,0,x,height,i,'4 4'):<path key={i} d={`M ${x} ${a.y} A ${step/2} ${Math.max(1,Math.abs(b.y-a.y))} 0 0 1 ${x+step} ${a.y}`} fill="none" stroke={color} strokeWidth={strokeWidth}/>;});
  }
  if(type==='shape-triangle')return poly(p,true,color+'18');
  if(type==='arc'){
    const det=2*(a.x*(b.y-c.y)+b.x*(c.y-a.y)+c.x*(a.y-b.y));if(Math.abs(det)<.01)return line(a.x,a.y,b.x,b.y,'arc');
    const aa=a.x*a.x+a.y*a.y,bb=b.x*b.x+b.y*b.y,cc=c.x*c.x+c.y*c.y;
    const center={x:(aa*(b.y-c.y)+bb*(c.y-a.y)+cc*(a.y-b.y))/det,y:(aa*(c.x-b.x)+bb*(a.x-c.x)+cc*(b.x-a.x))/det},radius=Math.hypot(a.x-center.x,a.y-center.y);
    const tau=2*Math.PI,start=Math.atan2(a.y-center.y,a.x-center.x),end=(Math.atan2(b.y-center.y,b.x-center.x)-start+tau)%tau,middle=(Math.atan2(c.y-center.y,c.x-center.x)-start+tau)%tau,sweep=middle<=end?1:0,large=(sweep?end:tau-end)>Math.PI?1:0;
    const path=`M ${a.x} ${a.y} A ${radius} ${radius} 0 ${large} ${sweep} ${b.x} ${b.y}`;return <><path d={path} fill="none" stroke={color} strokeWidth={strokeWidth}/><path d={path} fill="none" stroke="transparent" strokeWidth="12"/></>;
  }
  if(['arc','curve','double-curve'].includes(type)){
    const curve=type==='double-curve'?`M ${a.x} ${a.y} C ${b.x} ${b.y} ${c.x} ${c.y} ${d.x} ${d.y}`:`M ${a.x} ${a.y} Q ${c.x} ${c.y} ${b.x} ${b.y}`;
    return <><path d={curve} fill="none" stroke={color} strokeWidth={strokeWidth}/><path d={curve} fill="none" stroke="transparent" strokeWidth="12"/></>;
  }

  if (["trendline", "ray", "extended-line", "info-line", "trend-angle", "arrow"].includes(type)) {
    let from = a, to = b;
    if (type === "extended-line") { from = { x: 0, y: yAt(0) }; to = { x: width, y: yAt(width) }; }
    if (type === "ray") to = { x: b.x >= a.x ? width : 0, y: yAt(b.x >= a.x ? width : 0) };
    if (Math.abs(b.x - a.x) < .01 && ["extended-line", "ray"].includes(type)) { from = { x: a.x, y: type === "extended-line" ? 0 : a.y }; to = { x: a.x, y: b.y >= a.y ? height : 0 }; }
    const angle = Math.atan2(b.y - a.y, b.x - a.x);
    return <>{line(from.x, from.y, to.x, to.y, "line")}{type === "arrow" && poly([{ x: b.x - 13 * Math.cos(angle - .45), y: b.y - 13 * Math.sin(angle - .45) }, b, { x: b.x - 13 * Math.cos(angle + .45), y: b.y - 13 * Math.sin(angle + .45) }])}
      {type === "info-line" && label((a.x + b.x) / 2, (a.y + b.y) / 2 - 10, (drawing.points[1].price - drawing.points[0].price).toFixed(3) + " · " + Math.round(Math.abs(drawing.points[1].time - drawing.points[0].time) / 60) + " min")}
      {type === "trend-angle" && label(b.x + 8, b.y - 8, (-angle * 180 / Math.PI).toFixed(1) + "°")}
    </>;
  }
  if (["horizontal", "horizontal-ray", "vertical", "cross-line"].includes(type)) return <>
    {type !== "vertical" && line(type === "horizontal-ray" ? a.x : 0, a.y, width, a.y, "horizontal")}
    {["vertical", "cross-line"].includes(type) && line(a.x, 0, a.x, height, "vertical")}
    {type !== "vertical" && label(width - 75, a.y - 6, drawing.points[0].price.toFixed(3))}
  </>;
  if (TEXT_TOOLS.has(type) || type.startsWith("emoji-") || type.startsWith("arrow-") && type !== "arrow") {
    const symbols = { "emoji-smile": "🙂", "emoji-star": "⭐", "emoji-check": "✅", "emoji-warning": "⚠️", "arrow-marker": "➤", "arrow-up": "↑", "arrow-down": "↓", "arrow-left": "←", "arrow-right": "→", pin: "📌", flag: "⚑" };
    if (symbols[type]) return <><text x={a.x} y={a.y} fill={color} fontSize={drawing.fontSize || 28}>{symbols[type]}</text>{["pin", "flag"].includes(type) && label(a.x + 30, a.y - 5, drawing.text || "")}</>;
    const text = drawing.text || "Text", rows = text.split("\n"), boxW = Math.max(95, ...rows.map(row => row.length * (drawing.fontSize || 12) * .62 + 18)), boxH = rows.length * 18 + 14;
    if (type === "table") {
      const cells = rows.map(row => row.split("|")), columns = Math.max(...cells.map(row => row.length)), cellWidth = 105, cellHeight = 25;
      return <><rect x={a.x} y={a.y} width={columns * cellWidth} height={cells.length * cellHeight} fill="#131923ee" stroke={color} />
        {cells.map((row, i) => <g key={i}>{line(a.x, a.y + i * cellHeight, a.x + columns * cellWidth, a.y + i * cellHeight, "row")}{row.map((cell, j) => label(a.x + j * cellWidth + 7, a.y + i * cellHeight + 17, cell.trim(), j))}</g>)}
        {Array.from({ length: columns - 1 }, (_, i) => line(a.x + (i + 1) * cellWidth, a.y, a.x + (i + 1) * cellWidth, a.y + cells.length * cellHeight, i))}
      </>;
    }
    const target = type === "callout" ? b : a;
    const value = ["price-note", "price-label"].includes(type) ? text + " · " + drawing.points[0].price.toFixed(3) : text;
    return <>
      {type === "callout" && line(a.x, a.y, b.x, b.y, "callout")}
      <rect x={target.x} y={target.y - boxH} width={Math.max(boxW, value.length * 7 + 16)} height={boxH} rx={type === "comment" ? 12 : 4} fill="#131923ee" stroke={color} strokeWidth={strokeWidth} />
      {type === "signpost" && line(a.x, a.y, a.x, a.y + 45, "post")}
      {rows.map((row, i) => label(target.x + 8, target.y - boxH + 20 + i * 18, rows.length === 1 ? value : row, i))}
      {type === "table" && rows.slice(1).map((_, i) => line(target.x, target.y - boxH + 25 + i * 18, target.x + boxW, target.y - boxH + 25 + i * 18, "row" + i))}
    </>;
  }
  if (["rectangle", "zoom-region", "price-range", "date-range", "date-price-range", "forecast"].includes(type)) {
    const diff = drawing.points[1]?.price - drawing.points[0].price || 0, percent = drawing.points[0].price ? diff / drawing.points[0].price * 100 : 0;
    const minutes = Math.abs((drawing.points[1]?.time ?? drawing.points[0].time) - drawing.points[0].time) / 60;
    const text = type === "date-range" ? Math.round(minutes) + " min" : diff.toFixed(3) + " (" + percent.toFixed(2) + "%)" + (type === "price-range" ? "" : " · " + Math.round(minutes) + " min");
    return <><rect x={left} y={type === "date-range" ? 0 : top} width={w} height={type === "date-range" ? height : h} stroke={color} strokeWidth={strokeWidth} fill={color + "18"} />
      {type !== "rectangle" && label(left + 6, type === "date-range" ? 55 : top - 8, text)}
      {type === "forecast" && line(a.x, a.y, b.x, b.y, "forecast", "5 4")}
    </>;
  }
  if (type === "rotated-rectangle") {
    const dx = b.x - a.x, dy = b.y - a.y, length = Math.hypot(dx, dy) || 1;
    const offset = ((c.x - a.x) * -dy + (c.y - a.y) * dx) / length;
    const delta = { x: -dy / length * offset, y: dx / length * offset };
    return poly([a, b, { x: b.x + delta.x, y: b.y + delta.y }, { x: a.x + delta.x, y: a.y + delta.y }], true, color + "18");
  }
  if (type === "circle" || type === "ellipse") return <ellipse cx={(a.x + b.x) / 2} cy={(a.y + b.y) / 2} rx={type === "circle" ? Math.max(2, Math.hypot(w, h) / 2) : w / 2} ry={type === "circle" ? Math.max(2, Math.hypot(w, h) / 2) : h / 2} stroke={color} strokeWidth={strokeWidth} fill={color + "18"} />;
  if (["brush", "highlighter", "path", "polyline"].includes(type)) return <><polyline points={p.map(point => point.x + "," + point.y).join(" ")} fill="none" stroke={color} strokeWidth={type === "highlighter" ? (drawing.lineWidth || 16) : strokeWidth} opacity={type === "highlighter" ? .35 : 1} strokeLinecap="round" strokeLinejoin="round" /><polyline points={p.map(point => point.x + "," + point.y).join(" ")} fill="none" stroke="transparent" strokeWidth="16" /></>;
  if (PATTERN_TOOLS.has(type)) {
    const labels = { xabcd: ["X", "A", "B", "C", "D"], cypher: ["X", "A", "B", "C", "D"], abcd: ["A", "B", "C", "D"], "head-shoulders": ["", "LS", "", "Head", "", "RS", ""], "three-drives": ["1", "A", "2", "B", "3", "C"], "elliott-impulse": ["0", "1", "2", "3", "4", "5"], "elliott-correction": ["0", "A", "B", "C"], "elliott-triangle": ["0", "A", "B", "C", "D", "E"], "elliott-combo": ["0", "W", "A", "B", "X", "A", "B", "Y"], "elliott-triple": ["0", "W", "A", "X", "Y", "B", "Z", "C"] }[type] || [];
    return <>{poly(p, type === "triangle", type === "triangle" ? color + "15" : "none")}
      {p.map((point, i) => label(point.x + 6, point.y - 9, labels[i] || "", i))}
      {["xabcd", "cypher", "abcd"].includes(type) && p.length >= 3 && <>
        {poly(p.slice(0, 3), true, color + "15", "triangle1")}{p.length >= 5 && poly(p.slice(2, 5), true, color + "15", "triangle2")}
        {p.slice(2).map((point, i) => { const points = drawing.points; const previous = Math.abs(points[i + 1].price - points[i].price); const ratio = previous ? Math.abs(points[i + 2].price - points[i + 1].price) / previous : 0; return label((point.x + p[i + 1].x) / 2, (point.y + p[i + 1].y) / 2 + 16, ratio.toFixed(3), "ratio" + i); })}
      </>}
      {type === "head-shoulders" && p.length >= 5 && line(p[2].x, p[2].y, p[4].x, p[4].y, "neck", "4 4")}
    </>;
  }
  if (["parallel-channel", "disjoint-channel", "flat-channel", "fib-channel", "regression"].includes(type)) {
    if (type === "regression") {
      const fit = regression(bars);
      if (!fit) return label(a.x, a.y, "Select a range with candles");
      return [-2, 0, 2].map(level => { const first = project({ time: bars[0].time, price: fit.intercept + fit.deviation * level }); const last = project({ time: bars.at(-1).time, price: fit.intercept + fit.slope * (bars.length - 1) + fit.deviation * level }); return first && last ? line(first.x, first.y, last.x, last.y, level, level === 0 ? "4 4" : undefined) : null; });
    }
    if (type === "flat-channel") return <>{line(a.x, a.y, b.x, b.y, "trend")}{line(a.x, c.y, b.x, c.y, "flat")}{line(a.x, (a.y + c.y) / 2, b.x, (b.y + c.y) / 2, "mid", "4 4")}</>;
    const offset = c.y - yAt(c.x), baseY = yAt;
    const levels = type === "fib-channel" ? ratios : [0, .5, 1];
    return <>{type === "disjoint-channel" ? <>{line(a.x, a.y, b.x, b.y, "first")}{line(c.x, c.y, d.x, c.y + (d.x - c.x) * (b.y - a.y) / (b.x - a.x || 1), "disjoint")}</> : levels.map(level => line(a.x, baseY(a.x) + offset * level, b.x, baseY(b.x) + offset * level, level, level === .5 ? "4 4" : undefined))}
      {type === "fib-channel" && levels.map(level => label(b.x + 6, baseY(b.x) + offset * level, String(level)))}
    </>;
  }
  if (type === "fib-retracement" || type === "fib-extension") return <>{line(a.x, a.y, b.x, b.y, "base", "4 4")}{(type === "fib-extension" ? [0, .618, 1, 1.618, 2.618] : ratios).map(level => {
    const value = type === "fib-extension" ? (drawing.points[2]?.price ?? drawing.points[1].price) + (drawing.points[1].price - drawing.points[0].price) * level : drawing.points[0].price + (drawing.points[1].price - drawing.points[0].price) * level;
    const y = project({ time: drawing.points[0].time, price: value })?.y;
    return y == null ? null : <g key={level}>{line(left, y, left + w, y, "level")}{label(left + w + 6, y - 3, level + " (" + value.toFixed(3) + ")")}</g>;
  })}</>;
  if (type === "fib-time-zone" || type === "fib-time") return [0, 1, 2, 3, 5, 8, 13, 21].map(value => {
    const x = (type === "fib-time" ? c.x : a.x) + (b.x - a.x) * value;
    return <g key={value}>{line(x, 0, x, height, "time")}{label(x + 4, 55, String(value))}</g>;
  });
  if (type === "fib-fan" || type === "pitchfan") {
    const center = type === "pitchfan" ? { x: (b.x + c.x) / 2, y: (b.y + c.y) / 2 } : b;
    return <>{line(a.x, a.y, center.x, center.y, "base", "4 4")}{(type === "pitchfan" ? [-1, -.618, -.382, 0, .382, .618, 1] : ratios.slice(1)).map(level => {
      const y = type === "pitchfan" ? center.y + (c.y - b.y) / 2 * level : a.y + (b.y - a.y) * level;
      const endX = center.x >= a.x ? width : 0, endY = a.y + (y - a.y) * (endX - a.x) / (center.x - a.x || 1);
      return <g key={level}>{line(a.x, a.y, endX, endY, "ray")}{label(center.x, y - 5, String(level))}</g>;
    })}</>;
  }
  if (["fib-circles", "fib-arcs", "fib-wedge", "sector", "fib-spiral"].includes(type)) {
    const radius = Math.max(1, Math.hypot(b.x - a.x, b.y - a.y)), startAngle = Math.atan2(b.y - a.y, b.x - a.x), endAngle = Math.atan2(c.y - a.y, c.x - a.x);
    if (type === "fib-spiral") return poly(Array.from({ length: 240 }, (_, i) => { const theta = i / 239 * Math.PI * 4; const r = radius * Math.exp((theta - Math.PI * 4) * Math.log(1.61803398875) / (Math.PI / 2)); return { x: a.x + r * Math.cos(startAngle + theta), y: a.y + r * Math.sin(startAngle + theta) }; }));
    if (type === "sector" || type === "fib-wedge") return (type === "sector" ? [1] : ratios.slice(1)).map(level => {
      const r = radius * level, x1 = a.x + r * Math.cos(startAngle), y1 = a.y + r * Math.sin(startAngle), x2 = a.x + r * Math.cos(endAngle), y2 = a.y + r * Math.sin(endAngle);
      let delta = endAngle - startAngle; if (delta < 0) delta += Math.PI * 2;
      return <path key={level} d={"M " + a.x + " " + a.y + " L " + x1 + " " + y1 + " A " + r + " " + r + " 0 " + (delta > Math.PI ? 1 : 0) + " 1 " + x2 + " " + y2 + " Z"} fill={type === "sector" ? color + "18" : "none"} stroke={color} strokeWidth={strokeWidth} />;
    });
    return ratios.slice(1).map(level => type === "fib-circles" ? <circle key={level} cx={a.x} cy={a.y} r={radius * level} stroke={color} strokeWidth={strokeWidth} fill="none" /> : <path key={level} d={"M " + (a.x - radius * level) + " " + a.y + " A " + radius * level + " " + radius * level + " 0 0 1 " + (a.x + radius * level) + " " + a.y} stroke={color} strokeWidth={strokeWidth} fill="none" />);
  }
  if (["gann-box", "gann-fixed", "gann-square"].includes(type)) {
    const size = type === "gann-fixed" ? Math.max(w, h) : w, boxH = type === "gann-fixed" ? size : type === "gann-square" ? Math.max(1, Math.abs(c.y - a.y)) : h;
    return <><rect x={left} y={top} width={size} height={boxH} fill={color + "08"} stroke={color} strokeWidth={strokeWidth} />
      {[.25, .5, .75].map(value => <g key={value}>{line(left + size * value, top, left + size * value, top + boxH, "vertical")}{line(left, top + boxH * value, left + size, top + boxH * value, "horizontal")}</g>)}
      {type !== "gann-box" && <>{[.125, .25, .5, 1, 2, 4, 8].map(value => line(left, top + boxH, left + Math.min(size, size / value), top + boxH - Math.min(boxH, boxH * value), value))}{line(left, top, left + size, top + boxH, "diagonal")}{[.5, 1].map(value => <path key={value} d={"M " + left + " " + (top + boxH - boxH * value) + " A " + size * value + " " + boxH * value + " 0 0 1 " + (left + size * value) + " " + (top + boxH)} fill="none" stroke={color} strokeWidth={strokeWidth} />)}</>}
    </>;
  }
  if (type === "anchored-vwap") {
    const points = anchoredVWAP(bars).map(project).filter(Boolean);
    return points.length ? <>{poly(points)}{label(a.x + 8, a.y - 10, "Anchored VWAP · HLC3")}</> : label(a.x, a.y, "VWAP requires volume");
  }
  if (type === "volume-profile" || type === "anchored-profile") {
    const profile = volumeProfile(bars), maximum = Math.max(1, ...profile.map(row => row.volume));
    return <>{profile.map((row, i) => { const y = project({ time: drawing.points[0].time, price: row.price })?.y; const nextY = project({ time: drawing.points[0].time, price: profile[i + 1]?.price ?? row.price + (profile[1]?.price - profile[0]?.price || 1) })?.y; return y == null ? null : <rect key={i} x={Math.min(a.x, b.x)} y={Math.min(y, nextY ?? y)} width={Math.max(1, row.volume / maximum * 140)} height={Math.max(1, Math.abs(y - (nextY ?? y)))} fill={row.volume === maximum ? "#e8b45caa" : color + "66"} stroke="none" />; })}{label(a.x, a.y - 10, bars.some(bar => bar.volume > 0) ? "Volume profile · OHLCV estimate" : "Volume profile requires volume")}</>;
  }
  if (type === "bars-pattern" || type === "ghost-feed") {
    if (!bars.length || !drawing.points[2]) return label(a.x, a.y, "Select source, then destination");
    const deltaTime = drawing.points[2].time - bars[0].time, deltaPrice = drawing.points[2].price - bars[0].open;
    return bars.map((bar, i) => {
      const open = project({ time: bar.time + deltaTime, price: bar.open + deltaPrice }), close = project({ time: bar.time + deltaTime, price: bar.close + deltaPrice }), high = project({ time: bar.time + deltaTime, price: bar.high + deltaPrice }), low = project({ time: bar.time + deltaTime, price: bar.low + deltaPrice });
      if (!open || !close || !high || !low) return null;
      const tint = bar.close >= bar.open ? "#089981" : "#f23645";
      return <g key={i} opacity={type === "ghost-feed" ? .4 : .85}><line x1={open.x} y1={high.y} x2={open.x} y2={low.y} stroke={tint} /><rect x={open.x - 2} y={Math.min(open.y, close.y)} width="4" height={Math.max(1, Math.abs(open.y - close.y))} fill={tint} /></g>;
    });
  }
  return null;
}
export default DrawingGeometry;

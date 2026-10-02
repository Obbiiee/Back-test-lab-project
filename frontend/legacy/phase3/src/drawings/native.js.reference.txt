import { defaultStyleFor, OVERLAY_SPECS } from 'lightweight-charts-drawing';

const names = { trendline:'trend-line', horizontal:'horizontal-line', vertical:'vertical-line', regression:'regression-trend', 'flat-channel':'flat-top-bottom', 'fib-extension':'trend-based-fib-extension', 'fib-fan':'fib-speed-resistance-fan', 'fib-time':'trend-based-fib-time', 'fib-arcs':'fib-speed-resistance-arcs', 'gann-fixed':'gann-square-fixed', xabcd:'xabcd-pattern', cypher:'cypher-pattern', 'head-shoulders':'head-and-shoulders', abcd:'abcd-pattern', triangle:'triangle-pattern', 'three-drives':'three-drives-pattern', 'elliott-combo':'elliott-double-combo', 'elliott-triple':'elliott-triple-combo', forecast:'position-forecast', 'bars-pattern':'bar-pattern', 'volume-profile':'fixed-range-volume-profile', 'anchored-profile':'anchored-volume-profile', 'date-price-range':'date-and-price-range', 'arrow-up':'arrow-mark-up', 'arrow-down':'arrow-mark-down', 'shape-triangle':'triangle', flag:'flag-mark', 'anchored-text':'text' };
const reverse = Object.fromEntries(Object.entries(names).filter(([key])=>key!=='anchored-text').map(([key,value])=>[value,key]));
export const nativeKind = type => type?.startsWith('emoji-') ? 'font-icon' : OVERLAY_SPECS[names[type] || type] ? names[type] || type : null;
export const nativeType = kind => reverse[kind] || kind;
export function toNative(drawing) {
  const kind = nativeKind(drawing.type);
  if (!kind) return null;
  const style = { ...defaultStyleFor(kind), ...drawing.native?.style };
  if (drawing.color) style.color = drawing.color;
  if (drawing.lineWidth) style.width = drawing.lineWidth;
  if (drawing.fontSize) style.fontSize = drawing.fontSize;
  let points = drawing.points;
  if (kind.includes('position') && points.length >= 4) {
    const direction = kind === 'long-position' ? 1 : -1;
    style.stopLevel = (points[0].price - points[1].price) * direction;
    style.profitLevel = (points[2].price - points[0].price) * direction;
    for (const [field, key] of Object.entries({accountSize:'accountSize',riskPercent:'riskValue',lotSize:'lotSize',leverage:'leverage'})) if (drawing[key] != null) style[field] = Number(drawing[key]);
    style.riskDisplayMode = drawing.riskMode === 'cash' ? 'money' : 'percents';
    style.riskAmount = drawing.riskValue;
    style.qtyPrecision = String(drawing.quantityPrecision ?? 'default');
    style.showStats = drawing.alwaysShowStats === true;
    points = [points[0], points[3]];
  }
  // Legacy one-click annotations are expanded once without losing the user's data.
  if (['note','price-note','arrow-marker'].includes(kind) && points.length === 1) points = [points[0], {time:points[0].time + 3600,price:points[0].price + 1}];
  const glyphs = {'emoji-smile':'🙂','emoji-star':'⭐','emoji-check':'✅','emoji-warning':'⚠️'};
  return { ...drawing.native, id:drawing.id, kind, points, style, text:drawing.text, locked:drawing.locked, hidden:drawing.hidden, anchored:drawing.screenAnchor, glyph:glyphs[drawing.type] || drawing.native?.glyph, visibility:drawing.visibility ?? drawing.native?.visibility };
}
export function fromNative(drawing, previous) {
  let points = drawing.points;
  const result = { ...previous, id:drawing.id, type:previous?.type || nativeType(drawing.kind), native:drawing, color:drawing.style.color, lineWidth:drawing.style.width, fontSize:drawing.style.fontSize, text:drawing.text, locked:drawing.locked, hidden:drawing.hidden, screenAnchor:drawing.anchored, visibility:drawing.visibility };
  if (drawing.kind.includes('position')) {
    const direction = drawing.kind === 'long-position' ? 1 : -1;
    points = [drawing.points[0], {...drawing.points[0],price:drawing.points[0].price-drawing.style.stopLevel*direction}, {...drawing.points[0],price:drawing.points[0].price+drawing.style.profitLevel*direction}, {...drawing.points[1],price:drawing.points[0].price}];
    Object.assign(result, {accountSize:drawing.style.accountSize,riskValue:drawing.style.riskDisplayMode==='money'?drawing.style.riskAmount:drawing.style.riskPercent,riskMode:drawing.style.riskDisplayMode==='money'?'cash':'percent',lotSize:drawing.style.lotSize,leverage:drawing.style.leverage,quantityPrecision:drawing.style.qtyPrecision==='default'?0:Number(drawing.style.qtyPrecision),tickSize:.001,alwaysShowStats:drawing.style.showStats});
  }
  result.points = points;
  return result;
}

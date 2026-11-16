// Issue #21 C-05: per-instance presentation settings. Stored sparsely so
// configs saved before this schema keep their exact shape.
export const LINE_STYLE_IDS = Object.freeze({ solid: 0, dotted: 1, dashed: 2 });
const HEX = /^#[0-9a-fA-F]{6}$/;
const OUTPUT_STYLE_RULES = Object.freeze({
  visible: value => typeof value === 'boolean',
  color: value => typeof value === 'string' && HEX.test(value),
  lineWidth: value => Number.isInteger(value) && value >= 1 && value <= 5,
  lineStyle: value => Object.hasOwn(LINE_STYLE_IDS, value),
  opacity: value => Number.isFinite(value) && value >= 0 && value <= 1,
  positiveColor: value => typeof value === 'string' && HEX.test(value),
  negativeColor: value => typeof value === 'string' && HEX.test(value),
});
function presentation(spec, value) {
  const result = {};
  if (value.style !== undefined) {
    if (!value.style || Object.getPrototypeOf(value.style) !== Object.prototype) throw Error('Invalid indicator style');
    const style = {};
    for (const [key, output] of Object.entries(value.style)) {
      const owner = spec.outputs.find(item => item.key === key);
      if (!owner || !output || Object.getPrototypeOf(output) !== Object.prototype) throw Error('Invalid indicator style output');
      for (const [name, setting] of Object.entries(output)) {
        if (!OUTPUT_STYLE_RULES[name]?.(setting)) throw Error('Invalid indicator style: ' + key + '.' + name);
        if ((name === 'positiveColor' || name === 'negativeColor') && owner.outputType !== 'histogram') throw Error('Histogram colours only apply to histograms');
      }
      if (Object.keys(output).length) style[key] = Object.freeze({ ...output });
    }
    if (Object.keys(style).length) result.style = Object.freeze(style);
  }
  if (value.placement !== undefined) {
    if (!['price', 'pane'].includes(value.placement) || spec.placement === 'pane' && value.placement !== 'pane') throw Error('Invalid indicator placement');
    if (value.placement !== spec.placement) result.placement = value.placement;
  }
  if (value.paneHeight !== undefined) {
    if (!Number.isFinite(value.paneHeight) || value.paneHeight < 0.1 || value.paneHeight > 1) throw Error('Invalid pane height');
    result.paneHeight = value.paneHeight;
  }
  if (value.references !== undefined) {
    const refs = value.references;
    if ((value.placement ?? spec.placement) !== 'pane' || !Array.isArray(refs) || refs.length > 6 || refs.some(price => !Number.isFinite(price)) || new Set(refs).size !== refs.length) throw Error('Invalid reference lines');
    result.references = Object.freeze([...refs]);
  }
  return result;
}
export function effectivePlacement(spec, config) { return config.placement ?? spec.placement; }

export function instanceConfig(registry, value) {
  if (!value || typeof value.id !== 'string' || !value.id.trim() || typeof value.type !== 'string'
    || (value.visible !== undefined && typeof value.visible !== 'boolean')
    || Object.keys(value).some(key => !['id', 'type', 'parameters', 'visible', 'style', 'placement', 'paneHeight', 'references'].includes(key))) throw Error('Invalid indicator instance');
  const spec = registry.get(value.type), supplied = value.parameters === undefined ? {} : value.parameters;
  if (!supplied || Object.getPrototypeOf(supplied) !== Object.prototype
    || Object.keys(supplied).some(key => !Object.hasOwn(spec.parameters, key))) throw Error('Invalid parameters');
  const parameters = {};
  for (const [key, rule] of Object.entries(spec.parameters)) {
    const parameter = Object.hasOwn(supplied, key) ? supplied[key] : rule.default;
    if (typeof parameter !== typeof rule.default || (typeof parameter === 'number' && !Number.isFinite(parameter))
      || !rule.validate(parameter)) throw Error('Invalid parameter: ' + key);
    parameters[key] = parameter;
  }
  if (spec.validateParameters && !spec.validateParameters(parameters)) throw Error('Invalid parameter combination');
  return Object.freeze({ id: value.id, type: value.type, parameters: Object.freeze(parameters), visible: value.visible ?? true, ...presentation(spec, value) });
}

// Copy only public candle fields. Hidden datasets and mutable caller objects never reach a calculator.
export function revealedInput(candles) {
  if (!Array.isArray(candles)) throw Error('Invalid revealed candles');
  let previous = -Infinity;
  return Object.freeze(candles.map(bar => {
    if (!bar || !Number.isFinite(bar.time) || bar.time <= previous
      || !['open', 'high', 'low', 'close'].every(key => Number.isFinite(bar[key]))) throw Error('Invalid revealed candle');
    previous = bar.time;
    return Object.freeze({ time: bar.time, open: bar.open, high: bar.high, low: bar.low, close: bar.close,
      ...(Number.isFinite(bar.volume) ? { volume: bar.volume } : {}) });
  }));
}

export function normalizedOutput(points, candles) {
  if (!Array.isArray(points)) throw Error('Invalid indicator output');
  const times = new Set(candles.map(bar => bar.time)), seen = new Set();
  return Object.freeze(points.map(point => {
    if (!point || !times.has(point.time) || seen.has(point.time) || !Number.isFinite(point.value)
      || Object.keys(point).some(key => !['time', 'value', 'color'].includes(key))
      || (point.color !== undefined && (typeof point.color !== 'string' || !point.color.trim()))) throw Error('Invalid or unrevealed indicator point');
    seen.add(point.time);
    return Object.freeze({ time: point.time, value: point.value, ...(point.color === undefined ? {} : { color: point.color }) });
  }).sort((a, b) => a.time - b.time));
}

export function normalizedIndicatorOutput(spec, result, candles) {
  // Preserve the Phase 10 array contract for specs using the legacy single output field.
  if (spec.output !== undefined) return normalizedOutput(result, candles);
  if (!result || Object.getPrototypeOf(result) !== Object.prototype
    || Object.keys(result).length !== spec.outputs.length
    || spec.outputs.some(output => !Object.hasOwn(result, output.key))) throw Error('Incomplete indicator outputs');
  return Object.freeze(Object.fromEntries(spec.outputs.map(output => [output.key, normalizedOutput(result[output.key], candles)])));
}

export function emptyIndicatorOutput(spec) {
  return spec.output !== undefined ? Object.freeze([])
    : Object.freeze(Object.fromEntries(spec.outputs.map(output => [output.key, Object.freeze([])])));
}

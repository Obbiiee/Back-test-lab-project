export function instanceConfig(registry, value) {
  if (!value || typeof value.id !== 'string' || !value.id.trim() || typeof value.type !== 'string'
    || (value.visible !== undefined && typeof value.visible !== 'boolean')
    || Object.keys(value).some(key => !['id', 'type', 'parameters', 'visible'].includes(key))) throw Error('Invalid indicator instance');
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
  return Object.freeze({ id: value.id, type: value.type, parameters: Object.freeze(parameters), visible: value.visible ?? true });
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

// Close-only causal calculators. Each call derives output solely from its supplied prefix.
export function sma(candles, { period }) {
  if (period === 1) return candles.map(bar => ({ time: bar.time, value: bar.close }));
  const points = [];
  let sum = 0;
  for (let index = 0; index < candles.length; index++) {
    sum += candles[index].close;
    if (index >= period) sum -= candles[index - period].close;
    if (index >= period - 1) points.push({ time: candles[index].time, value: sum / period });
  }
  return points;
}

export function ema(candles, { period }) {
  if (candles.length < period) return [];
  const alpha = 2 / (period + 1);
  let value = 0;
  for (let index = 0; index < period; index++) value += candles[index].close;
  value /= period;
  const points = [{ time: candles[period - 1].time, value }];
  for (let index = period; index < candles.length; index++) {
    value = candles[index].close * alpha + value * (1 - alpha);
    points.push({ time: candles[index].time, value });
  }
  return points;
}

export function bollinger(candles, { period, multiplier }) {
  const basis = sma(candles, { period }), upper = [], lower = [];
  for (let index = period - 1; index < candles.length; index++) {
    const mean = basis[index - period + 1].value;
    // Centered population variance avoids subtracting large raw squared-price sums.
    let squared = 0;
    for (let offset = index - period + 1; offset <= index; offset++) squared += (candles[offset].close - mean) ** 2;
    const spread = multiplier * Math.sqrt(squared / period);
    upper.push({ time: candles[index].time, value: mean + spread });
    lower.push({ time: candles[index].time, value: mean - spread });
  }
  return { basis, upper, lower };
}

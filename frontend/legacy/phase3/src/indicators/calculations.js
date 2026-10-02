export function ema(bars, period = 20) {
  const alpha = 2 / (period + 1);
  let value;
  return bars.map(bar => {
    value = value == null ? bar.close : alpha * bar.close + (1 - alpha) * value;
    return { time: bar.time, value };
  });
}

// Wilder's smoothing, seeded with the first period of price changes.
export function rsi(bars, period = 14) {
  let gain = 0, loss = 0;
  const result = [];
  for (let i = 1; i < bars.length; i++) {
    const change = bars[i].close - bars[i - 1].close;
    const up = Math.max(0, change), down = Math.max(0, -change);
    if (i <= period) { gain += up / period; loss += down / period; }
    else { gain = (gain * (period - 1) + up) / period; loss = (loss * (period - 1) + down) / period; }
    if (i >= period) result.push({ time: bars[i].time, value: loss === 0 ? gain === 0 ? 50 : 100 : 100 - 100 / (1 + gain / loss) });
  }
  return result;
}

export function macd(bars, fast = 12, slow = 26, signal = 9) {
  const fastValues = ema(bars, fast), slowValues = ema(bars, slow);
  const line = bars.map((bar, i) => ({ time: bar.time, value: fastValues[i].value - slowValues[i].value }));
  const signalLine = ema(line.map(point => ({ time: point.time, close: point.value })), signal);
  const histogram = line.map((point, i) => ({ time: point.time, value: point.value - signalLine[i].value, color: point.value >= signalLine[i].value ? '#26a69a' : '#ef5350' }));
  return { line, signal: signalLine, histogram };
}

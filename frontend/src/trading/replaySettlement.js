import { forwardChange } from '../market/replayTransitions.js';
import { processCandle } from './simulator.js';

export function settleReplay(current, candles, previous = [], hint) {
  const quote = candles.at(-1);
  if (!quote) return current;
  if (quote.time < current.lastTime && !current.positions.length && !current.orders.length && !current.trades.length) return { ...current, lastTime: quote.time };
  if (current.lastTime == null) return { ...current, lastTime: quote.time };
  const change = forwardChange(previous, candles, hint);
  // Raw replay append must preserve the entire previous prefix. A latest-bucket
  // replacement or an account behind that prefix uses the original scan.
  const from = change?.appendOnly && current.lastTime >= previous.at(-1).time ? change.from : 0;
  let result = current;
  for (let i = from; i < candles.length; i++) if (candles[i].time > current.lastTime) result = processCandle(result, candles[i]);
  return result;
}

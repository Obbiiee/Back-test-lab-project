import { IndicatorRegistry } from './IndicatorRegistry.js';
import { sma, ema, bollinger } from './overlayCalculations.js';

const period = min => ({ default: 20, min, max: 1000, step: 1, validate: value => Number.isInteger(value) && value >= min && value <= 1000 });
export const overlayRegistry = new IndicatorRegistry()
  .register({ type: 'SMA', name: 'SMA', output: 'line', options: { color: '#f59e0b', lineWidth: 2 }, warmup: 1, parameters: { period: period(1) }, calculate: sma })
  .register({ type: 'EMA', name: 'EMA', output: 'line', options: { color: '#f472b6', lineWidth: 2 }, warmup: 1, parameters: { period: period(1) }, calculate: ema })
  .register({ type: 'BOLLINGER_BANDS', name: 'Bollinger Bands', warmup: 2,
    parameters: { period: period(2), multiplier: { default: 2, min: 0, max: 20, step: 'any', validate: value => Number.isFinite(value) && value > 0 && value <= 20 } },
    outputs: [{ key: 'basis', outputType: 'line', options: { color: '#a78bfa', lineWidth: 1 } },
      { key: 'upper', outputType: 'line', options: { color: '#38bdf8', lineWidth: 1 } },
      { key: 'lower', outputType: 'line', options: { color: '#38bdf8', lineWidth: 1 } }], calculate: bollinger });

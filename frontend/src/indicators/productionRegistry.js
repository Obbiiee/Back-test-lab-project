import { IndicatorRegistry } from './IndicatorRegistry.js';
import { overlayRegistry } from './overlayRegistry.js';
import { rsi, macd, atr, stochastic } from './paneCalculations.js';

const period = (defaultValue, min = 1, label = 'Period') => ({ default: defaultValue, min, max: 1000, step: 1, label,
  validate: value => Number.isInteger(value) && value >= min && value <= 1000 });
export const productionRegistry = new IndicatorRegistry();
for (const type of overlayRegistry.types()) {
  const spec = overlayRegistry.get(type);
  productionRegistry.register({ ...spec, outputs: spec.output !== undefined ? undefined : spec.outputs });
}
productionRegistry
  .register({ type: 'RSI', name: 'RSI', placement: 'pane', output: 'line', options: { color: '#a78bfa', lineWidth: 2 },
    warmup: 3, parameters: { period: period(14, 2) }, range: [0, 100], references: [70, 30], calculate: rsi })
  .register({ type: 'MACD', name: 'MACD', placement: 'pane', warmup: 2,
    parameters: { fastPeriod: period(12, 1, 'Fast period'), slowPeriod: period(26, 1, 'Slow period'), signalPeriod: period(9, 1, 'Signal period') },
    validateParameters: values => values.fastPeriod < values.slowPeriod,
    outputs: [{ key: 'macd', outputType: 'line', options: { color: '#38bdf8', lineWidth: 2 } },
      { key: 'signal', outputType: 'line', options: { color: '#f59e0b', lineWidth: 1 } },
      { key: 'histogram', outputType: 'histogram' }], calculate: macd })
  .register({ type: 'ATR', name: 'ATR', placement: 'pane', output: 'line', options: { color: '#f472b6', lineWidth: 2 },
    warmup: 1, parameters: { period: period(14) }, calculate: atr })
  .register({ type: 'STOCHASTIC', name: 'Stochastic', placement: 'pane', warmup: 1,
    parameters: { kPeriod: period(14, 1, '%K period'), dPeriod: period(3, 1, '%D period') }, range: [0, 100], references: [80, 20],
    outputs: [{ key: 'k', outputType: 'line', options: { color: '#38bdf8', lineWidth: 2 } },
      { key: 'd', outputType: 'line', options: { color: '#f59e0b', lineWidth: 1 } }], calculate: stochastic });

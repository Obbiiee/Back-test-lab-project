import { IndicatorRegistry } from './IndicatorRegistry.js';
import { overlayRegistry } from './overlayRegistry.js';
import { rsi, macd, atr, stochastic } from './paneCalculations.js';
import * as pro from './proCalculations.js';

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

// ---- Issue #21 C-06: professional price indicators ---------------------------
// Each entry pins its formula convention (see proCalculations.js and
// docs/terminal-indicators.md). `version` changes if a convention ever changes.
const P = (value, min = 1, label = 'Period', max = 1000) => ({ default: value, min, max, step: 1, label, validate: v => Number.isInteger(v) && v >= min && v <= max });
const F = (value, min, max, label, step = 'any') => ({ default: value, min, max, step, label, validate: v => Number.isFinite(v) && v >= min && v <= max });
const line = (key, color, lineWidth = 2, extra = {}) => ({ key, outputType: 'line', options: { color, lineWidth, ...extra } });
const hist = key => ({ key, outputType: 'histogram' });
const MA = 'Moving averages', BANDS = 'Bands & channels', TREND = 'Trend', OSC = 'Momentum & oscillators', VOL = 'Volatility', LEVELS = 'Levels & structure';
const single = (type, name, category, calculate, parameters, color, extra = {}) => productionRegistry.register({ type, name, category, version: 1, output: 'line', options: { color, lineWidth: 2 }, warmup: 1, parameters, calculate, ...extra });
const multi = (type, name, category, calculate, parameters, outputs, extra = {}) => productionRegistry.register({ type, name, category, version: 1, warmup: 1, parameters, outputs, calculate, ...extra });
const pane = { placement: 'pane' };

single('WMA', 'WMA', MA, pro.wma, { period: P(20), source: pro.sourceRule() }, '#22d3ee', { description: 'Weighted moving average, linear weights 1…N.' });
single('RMA', 'RMA / SMMA', MA, pro.rma, { period: P(14), source: pro.sourceRule() }, '#a3e635', { description: 'Wilder smoothed moving average (SMA seed).' });
single('HMA', 'Hull MA', MA, pro.hma, { period: P(20, 2), source: pro.sourceRule() }, '#fb923c', { description: 'WMA(2·WMA(N/2) − WMA(N), √N).' });
single('DEMA', 'DEMA', MA, pro.dema, { period: P(20), source: pro.sourceRule() }, '#e879f9', { description: '2·EMA − EMA(EMA).' });
single('TEMA', 'TEMA', MA, pro.tema, { period: P(20), source: pro.sourceRule() }, '#60a5fa', { description: '3·EMA − 3·EMA² + EMA³.' });
single('KAMA', 'KAMA', MA, pro.kama, { period: P(10, 2, 'Efficiency period'), fast: P(2, 1, 'Fast'), slow: P(30, 2, 'Slow') }, '#facc15',
  { description: 'Kaufman adaptive MA; seed = close at bar N−1.', validateParameters: v => v.fast < v.slow, constraint: 'Fast must be smaller than slow.' });
single('ZLEMA', 'ZLEMA', MA, pro.zlema, { period: P(20, 2), source: pro.sourceRule() }, '#34d399', { description: 'EMA of 2·x − x[lag], lag = ⌊(N−1)/2⌋.' });
single('LINREG', 'Linear Regression', MA, pro.linearRegression, { period: P(20, 2), source: pro.sourceRule() }, '#c084fc', { description: 'Least-squares fitted value at the latest bar of each lookback.' });
multi('MA_RIBBON', 'Moving Average Ribbon', MA, pro.maRibbon, {
  kind: { default: 'EMA', label: 'Average', options: ['EMA', 'SMA'], validate: v => v === 'EMA' || v === 'SMA' },
  period1: P(20, 0, 'Period 1'), period2: P(30, 0, 'Period 2'), period3: P(40, 0, 'Period 3'), period4: P(50, 0, 'Period 4'), period5: P(0, 0, 'Period 5 (0 = off)'), period6: P(0, 0, 'Period 6 (0 = off)'),
}, [line('ma1', '#fde68a', 1), line('ma2', '#fcd34d', 1), line('ma3', '#fbbf24', 1), line('ma4', '#f59e0b', 1), line('ma5', '#d97706', 1), line('ma6', '#b45309', 1)],
{ validateParameters: v => [1, 2, 3, 4, 5, 6].filter(k => v['period' + k] > 0).length >= 3, constraint: 'Use at least 3 non-zero periods.', description: '3–6 moving averages.' });

single('STDDEV', 'Standard Deviation', VOL, pro.standardDeviation, { period: P(20, 2), source: pro.sourceRule() }, '#f472b6', { ...pane, description: 'Population standard deviation (same convention as Bollinger Bands).' });
single('NATR', 'Normalized ATR', VOL, pro.natr, { period: P(14) }, '#fb7185', { ...pane, description: '100 · ATR(Wilder) / close.' });
single('ADR', 'Average Daily Range', VOL, pro.averageDailyRange, { period: P(14, 1, 'Days') }, '#fda4af', { ...pane, options: { color: '#fda4af', lineWidth: 2, lineType: 1 }, description: 'Mean high−low of the last N completed UTC days.' });

multi('SUPERTREND', 'Supertrend', TREND, pro.supertrend, { atrPeriod: P(10, 1, 'ATR period'), multiplier: F(3, 0.1, 20, 'Multiplier') }, [line('trend', '#089981', 2)], { description: 'hl2 ± m·ATR with ratcheting bands.' });
multi('ICHIMOKU', 'Ichimoku Cloud', TREND, pro.ichimoku, { conversion: P(9, 1, 'Conversion'), base: P(26, 1, 'Base'), spanB: P(52, 1, 'Span B'), displacement: P(26, 1, 'Displacement', 200) },
  [line('conversion', '#2962ff', 1), line('base', '#b71c1c', 1), line('spanA', '#43a047', 1), line('spanB', '#e53935', 1), line('lagging', '#9c27b0', 1)],
  { description: 'Leading spans plot on later revealed bars only; no future quotes are read.' });
multi('KELTNER', 'Keltner Channels', BANDS, pro.keltner, { period: P(20, 1, 'EMA period'), atrPeriod: P(10, 1, 'ATR period'), multiplier: F(2, 0.1, 20, 'Multiplier') },
  [line('middle', '#38bdf8', 1), line('upper', '#0ea5e9', 1), line('lower', '#0ea5e9', 1)], { description: 'EMA ± m·ATR(Wilder).' });
multi('DONCHIAN', 'Donchian Channels', BANDS, pro.donchian, { period: P(20) }, [line('upper', '#2dd4bf', 1), line('lower', '#2dd4bf', 1), line('basis', '#f59e0b', 1)], { description: 'Highest high / lowest low of N bars.' });
multi('LINREG_CHANNEL', 'Linear Regression Channel', BANDS, pro.regressionChannel, { period: P(20, 2), deviations: F(2, 0.1, 10, 'Deviations') },
  [line('basis', '#c084fc', 1), line('upper', '#a78bfa', 1), line('lower', '#a78bfa', 1)], { description: 'Rolling fit ± k · residual standard deviation (volume-free).' });
single('PSAR', 'Parabolic SAR', TREND, pro.parabolicSar, { start: F(0.02, 0.001, 1, 'Start'), increment: F(0.02, 0.001, 1, 'Increment'), maximum: F(0.2, 0.01, 1, 'Maximum') }, '#f8fafc',
  { options: { color: '#f8fafc', lineWidth: 2, markers: true }, validateParameters: v => v.start <= v.maximum, constraint: 'Start must not exceed maximum.', description: 'Wilder SAR, shown as dots.' });
multi('ALLIGATOR', 'Williams Alligator', TREND, pro.alligator, { jaw: P(13, 1, 'Jaw'), teeth: P(8, 1, 'Teeth'), lips: P(5, 1, 'Lips'), jawShift: P(8, 0, 'Jaw shift', 100), teethShift: P(5, 0, 'Teeth shift', 100), lipsShift: P(3, 0, 'Lips shift', 100) },
  [line('jaw', '#2563eb', 2), line('teeth', '#dc2626', 2), line('lips', '#16a34a', 2)], { description: 'SMMA(hl2); shifts move plots onto later revealed bars only.' });
multi('PIVOTS', 'Pivot Points (daily)', LEVELS, pro.pivotPoints, { method: { default: 'classic', label: 'Method', options: pro.PIVOT_METHODS, validate: v => pro.PIVOT_METHODS.includes(v) } },
  ['p', 'r1', 'r2', 'r3', 's1', 's2', 's3'].map(key => line(key, key === 'p' ? '#facc15' : key.startsWith('r') ? '#f87171' : '#4ade80', 1, { lineType: 1 })),
  { description: 'From the prior completed UTC day only.' });
multi('FRACTALS', 'Williams Fractals', LEVELS, pro.williamsFractals, { left: P(2, 1, 'Left bars', 20), right: P(2, 1, 'Right bars', 20) },
  [line('up', '#f87171', 2, { markers: true }), line('down', '#4ade80', 2, { markers: true })], { description: 'A fractal appears only after its right-side bars are revealed.' });
multi('ZIGZAG', 'ZigZag', LEVELS, pro.zigzag, { depth: P(12, 1, 'Depth'), deviation: F(5, 0.01, 50, 'Deviation %') },
  [line('confirmed', '#f59e0b', 2), line('provisional', '#f59e0b', 1)], { description: 'Confirmed pivots never move; the last leg is provisional and can change.', notes: 'Repainting: only the provisional last leg can change as new bars arrive.' });

multi('STOCH_RSI', 'Stochastic RSI', OSC, pro.stochRsi, { rsiPeriod: P(14, 2, 'RSI period'), stochPeriod: P(14, 1, 'Stochastic period'), kSmoothing: P(3, 1, '%K smoothing'), dSmoothing: P(3, 1, '%D smoothing') },
  [line('k', '#38bdf8'), line('d', '#f59e0b', 1)], { ...pane, range: [0, 100], references: [80, 20], description: 'Stochastic of RSI(Wilder), smoothed %K and %D.' });
single('ADX', 'ADX', TREND, pro.adx, { period: P(14, 2) }, '#f97316', { ...pane, references: [25], description: 'Wilder ADX.' });
multi('DMI', 'DMI (+DI / −DI)', TREND, pro.dmi, { period: P(14, 2) }, [line('plus', '#22c55e'), line('minus', '#ef4444')], { ...pane, description: 'Wilder directional indicators.' });
single('CCI', 'CCI', OSC, pro.cci, { period: P(20, 2) }, '#06b6d4', { ...pane, references: [100, -100], description: '(TP − SMA(TP)) / (0.015 · mean deviation), TP = hlc3.' });
single('ROC', 'Rate of Change', OSC, pro.roc, { period: P(12), source: pro.sourceRule() }, '#818cf8', { ...pane, references: [0], description: '100 · (x − x[N]) / x[N].' });
single('MOMENTUM', 'Momentum', OSC, pro.momentum, { period: P(10), source: pro.sourceRule() }, '#a78bfa', { ...pane, references: [0], description: 'x − x[N].' });
single('WILLIAMS_R', 'Williams %R', OSC, pro.williamsR, { period: P(14) }, '#c084fc', { ...pane, range: [-100, 0], references: [-20, -80], description: '−100 · (highest high − close) / range; flat range = −50.' });
multi('AO', 'Awesome Oscillator', OSC, pro.awesome, { fast: P(5, 1, 'Fast'), slow: P(34, 2, 'Slow') }, [hist('value')], { ...pane, validateParameters: v => v.fast < v.slow, constraint: 'Fast must be smaller than slow.', description: 'SMA(hl2, fast) − SMA(hl2, slow).' });
single('TRIX', 'TRIX', OSC, pro.trix, { period: P(15) }, '#f43f5e', { ...pane, references: [0], description: '1-bar % change of triple EMA.' });
single('ULTIMATE', 'Ultimate Oscillator', OSC, pro.ultimate, { fast: P(7, 1, 'Fast'), medium: P(14, 1, 'Medium'), slow: P(28, 1, 'Slow') }, '#e11d48',
  { ...pane, range: [0, 100], references: [70, 30], validateParameters: v => v.fast < v.medium && v.medium < v.slow, constraint: 'Fast < medium < slow.', description: 'Weighted buying pressure over three lookbacks (4:2:1).' });
multi('AROON', 'Aroon', TREND, pro.aroon, { period: P(25) }, [line('up', '#f97316'), line('down', '#3b82f6')], { ...pane, range: [0, 100], description: 'Bars since highest high / lowest low over N, as %.' });
single('CMO', 'Chande Momentum', OSC, pro.cmo, { period: P(14) }, '#14b8a6', { ...pane, range: [-100, 100], references: [50, -50], description: '100 · (Σup − Σdown) / (Σup + Σdown).' });
single('DPO', 'Detrended Price Osc.', OSC, pro.dpo, { period: P(20, 2) }, '#84cc16', { ...pane, references: [0], description: 'Causal (non-centred) variant.' });
multi('TSI', 'True Strength Index', OSC, pro.tsi, { long: P(25, 1, 'Long'), short: P(13, 1, 'Short'), signal: P(7, 1, 'Signal') }, [line('tsi', '#38bdf8'), line('signal', '#f59e0b', 1)], { ...pane, references: [0], description: 'Double-smoothed momentum ratio with signal EMA.' });
multi('VORTEX', 'Vortex', TREND, pro.vortex, { period: P(14, 2) }, [line('plus', '#22c55e'), line('minus', '#ef4444')], { ...pane, description: 'Σ|high − prior low| and Σ|low − prior high| over Σ true range.' });
multi('FISHER', 'Fisher Transform', OSC, pro.fisher, { period: P(10, 2) }, [line('fisher', '#3b82f6'), line('trigger', '#f97316', 1)], { ...pane, references: [1.5, -1.5], description: 'Ehlers Fisher transform of hl2 position in its range.' });
multi('ELDER_RAY', 'Elder Ray', OSC, pro.elderRay, { period: P(13) }, [hist('bull'), hist('bear')], { ...pane, references: [0], description: 'Bull power = high − EMA, bear power = low − EMA.' });
single('BOP', 'Balance of Power', OSC, pro.balanceOfPower, { smoothing: P(14, 1, 'Smoothing') }, '#ef4444', { ...pane, range: [-1, 1], references: [0], description: 'SMA of (close − open) / (high − low).' });
multi('PPO', 'PPO', OSC, pro.ppo, { fastPeriod: P(12, 1, 'Fast period'), slowPeriod: P(26, 1, 'Slow period'), signalPeriod: P(9, 1, 'Signal period') },
  [line('ppo', '#38bdf8'), line('signal', '#f59e0b', 1), hist('histogram')], { ...pane, validateParameters: v => v.fastPeriod < v.slowPeriod, constraint: 'Fast must be smaller than slow.', description: 'Percentage MACD: 100 · (EMA fast − EMA slow) / EMA slow.' });
multi('CHANDELIER', 'Chandelier Exit', TREND, pro.chandelier, { period: P(22), multiplier: F(3, 0.1, 20, 'ATR multiplier') }, [line('long', '#22c55e', 1, { lineType: 1 }), line('short', '#ef4444', 1, { lineType: 1 })], { description: 'Highest high − m·ATR (long), lowest low + m·ATR (short).' });
multi('SQUEEZE', 'Squeeze Momentum', VOL, pro.squeeze, { period: P(20, 2), bbMultiplier: F(2, 0.1, 10, 'BB multiplier'), kcMultiplier: F(1.5, 0.1, 10, 'KC multiplier') },
  [hist('momentum'), line('squeeze', '#f8fafc', 2, { markers: true })], { ...pane, description: 'LazyBear variant (pinned).' });

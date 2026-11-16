// Indicator catalog grouping and honest "unavailable" entries (Issue #21).
export const CATEGORY_ORDER = Object.freeze(['Moving averages', 'Bands & channels', 'Trend', 'Momentum & oscillators', 'Volatility', 'Levels & structure', 'Volume']);
const DEFAULT_CATEGORY = {
  SMA: 'Moving averages', EMA: 'Moving averages', BOLLINGER_BANDS: 'Bands & channels',
  RSI: 'Momentum & oscillators', MACD: 'Momentum & oscillators', STOCHASTIC: 'Momentum & oscillators', ATR: 'Volatility',
};
export function categoryOf(spec) { return spec.category ?? DEFAULT_CATEGORY[spec.type] ?? 'Trend'; }

// Volume / order-flow studies need a qualified traded-volume feed. The current
// sources are Bid/Ask quotes only, so these are listed but never enabled and
// never fed synthetic volume or tick counts.
const NEEDS_VOLUME = 'Needs a qualified traded-volume feed. Current data is Bid/Ask quotes only, so volume is not available.';
export const UNAVAILABLE_INDICATORS = Object.freeze([
  ['V01', 'Volume'], ['V02', 'Volume MA'], ['V03', 'VWMA'], ['V04', 'VWAP (session)'], ['V05', 'Anchored VWAP'], ['V06', 'OBV'],
  ['V07', 'MFI'], ['V08', 'Accumulation/Distribution'], ['V09', 'Chaikin Money Flow'], ['V10', 'Chaikin Oscillator'],
  ['V11', 'Volume Profile'], ['V12', 'CVD'],
].map(([id, name]) => Object.freeze({ id, name, category: 'Volume', reason: id === 'V12' ? 'Needs signed aggressor (taker) trade flow; it cannot be inferred from Bid/Ask quotes.' : NEEDS_VOLUME })));

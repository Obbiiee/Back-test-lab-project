// Shared, registry-driven drawing style schema (Issue #21 C-01).
// Options stay sparse: only keys a user actually set are stored, so records
// written before this schema keep their exact canonical shape.
import { DRAWING_SPECS } from './DrawingTypes.js';

export const LINE_STYLES = Object.freeze(['solid', 'dashed', 'dotted']);
export const TEXT_ALIGN = Object.freeze(['left', 'center', 'right']);
export const LABEL_POSITION = Object.freeze(['top', 'center', 'bottom']);
export const COLOR_PRESETS = Object.freeze(['#58a6ff', '#2ec4b6', '#ffd23f', '#ff6b6b', '#c084fc', '#f8fafc', '#94a3b8', '#22c55e', '#f97316']);
export const DEFAULT_FIB_LEVELS = Object.freeze([0, 0.236, 0.382, 0.5, 0.618, 0.786, 1, 1.272, 1.618]);
// Levels shown by default; 1.272/1.618 exist as editable rows but start hidden
// so the Phase 9 default rendering (0…1) is unchanged.
export const DEFAULT_VISIBLE_FIB = Object.freeze([0, 0.236, 0.382, 0.5, 0.618, 0.786, 1]);
export const UI_WIDTH = Object.freeze({ min: 1, max: 6 });
export const FONT_SIZE = Object.freeze({ min: 10, max: 32 });
const HEX = /^#[0-9a-fA-F]{6}$/;

const isHex = value => typeof value === 'string' && HEX.test(value);
const bool = value => typeof value === 'boolean';
const unit = value => Number.isFinite(value) && value >= 0 && value <= 1;

// Capability flags decide which Properties controls are shown. A control that
// has no rendering effect for a tool is hidden instead of left inert.
const LINE = { lineStyle: true, opacity: true };
export const CAPABILITIES = Object.freeze({
  'trend-line': { ...LINE, extend: true, priceLabels: true },
  ray: { ...LINE, priceLabels: true },
  'extended-line': { ...LINE, priceLabels: true },
  'horizontal-line': { ...LINE, priceLabels: true },
  'horizontal-ray': { ...LINE, priceLabels: true },
  'vertical-line': { ...LINE, timeLabels: true },
  'cross-line': { ...LINE, priceLabels: true, timeLabels: true },
  rectangle: { ...LINE, fill: true, extend: true },
  arrow: { ...LINE },
  'fibonacci-retracement': { ...LINE, levels: 'fib', extend: true, priceLabels: true, reverse: true, fill: true },
  text: { opacity: true, text: true },
  measure: { ...LINE, text: 'size' },
});
export function capabilities(type) { return CAPABILITIES[type] ?? { ...LINE }; }

function validLevels(levels) {
  return Array.isArray(levels) && levels.length >= 1 && levels.length <= 24 && levels.every(level =>
    level && typeof level === 'object' && Object.keys(level).every(key => ['value', 'visible', 'color'].includes(key))
    && Number.isFinite(level.value) && level.value >= -10 && level.value <= 10 && bool(level.visible)
    && (level.color === undefined || isHex(level.color)));
}

// Every optional key with its validator. Unknown keys are refused so a future
// or hostile record can never smuggle state into the canvas renderer.
const RULES = Object.freeze({
  lineStyle: value => LINE_STYLES.includes(value),
  opacity: unit,
  fillColor: isHex,
  fillOpacity: unit,
  extendLeft: bool,
  extendRight: bool,
  showPriceLabels: bool,
  showTimeLabels: bool,
  fontSize: value => Number.isInteger(value) && value >= FONT_SIZE.min && value <= FONT_SIZE.max,
  bold: bool,
  italic: bool,
  textColor: isHex,
  textBackground: value => value === 'none' || isHex(value),
  textBorder: bool,
  textAlign: value => TEXT_ALIGN.includes(value),
  fontFamily: value => value === 'mono' || value === 'sans',
  labelPosition: value => LABEL_POSITION.includes(value),
  levels: validLevels,
  reverse: bool,
});
export const STYLE_KEYS = Object.freeze(Object.keys(RULES));

export function normalizeOptions(options = {}) {
  if (!options || typeof options !== 'object' || Array.isArray(options)) throw new TypeError('Invalid drawing options');
  const width = options.lineWidth ?? 2;
  if (!Number.isFinite(width) || width < 1 || width > 10) throw new TypeError('Invalid line width');
  if (options.color !== undefined && typeof options.color !== 'string') throw new TypeError('Invalid color');
  const result = { color: typeof options.color === 'string' ? options.color : '#58a6ff', lineWidth: width };
  for (const [key, value] of Object.entries(options)) {
    if (key === 'color' || key === 'lineWidth' || value === undefined) continue;
    const rule = RULES[key];
    if (!rule || !rule(value)) throw new TypeError('Invalid drawing option: ' + key);
    result[key] = key === 'levels' ? Object.freeze(value.map(level => Object.freeze({ ...level }))) : value;
  }
  return Object.freeze(result);
}

// Resolved view of a model's options with defaults filled in for rendering.
export function resolvedStyle(model) {
  const o = model.options;
  return {
    color: o.color, lineWidth: o.lineWidth, lineStyle: o.lineStyle ?? 'solid', opacity: o.opacity ?? 1,
    fillColor: o.fillColor ?? o.color, fillOpacity: o.fillOpacity ?? (model.type === 'rectangle' ? 0 : 0),
    extendLeft: o.extendLeft ?? false, extendRight: o.extendRight ?? false,
    showPriceLabels: o.showPriceLabels ?? (model.type === 'fibonacci-retracement'),
    showTimeLabels: o.showTimeLabels ?? false,
    fontSize: o.fontSize ?? 12, fontFamily: o.fontFamily ?? 'mono', bold: o.bold ?? false, italic: o.italic ?? false,
    textColor: o.textColor ?? o.color, textBackground: o.textBackground ?? '#10141b', textBorder: o.textBorder ?? false,
    textAlign: o.textAlign ?? 'left', labelPosition: o.labelPosition ?? 'center',
    reverse: o.reverse ?? false,
    levels: o.levels ?? DEFAULT_FIB_LEVELS.map(value => ({ value, visible: DEFAULT_VISIBLE_FIB.includes(value) })),
  };
}

export function dashFor(lineStyle, width) {
  if (lineStyle === 'dashed') return [Math.max(4, width * 3), Math.max(3, width * 2)];
  if (lineStyle === 'dotted') return [Math.max(1, width), Math.max(2, width * 1.5)];
  return [];
}

export function withAlpha(hex, alpha) {
  if (!isHex(hex)) return hex;
  const a = Math.round(Math.max(0, Math.min(1, alpha)) * 255).toString(16).padStart(2, '0');
  return hex + a;
}

export function fontFor(style) {
  // Self-hosted OFL fonts only (see riksoraBrand.css); system fallbacks otherwise.
  const family = style.fontFamily === 'sans' ? '"Inter Variable", Inter, ui-sans-serif, system-ui, sans-serif' : '"IBM Plex Mono", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace';
  return `${style.italic ? 'italic ' : ''}${style.bold ? '700 ' : '400 '}${style.fontSize}px ${family}`;
}

export function displayName(model) {
  return model.name || DRAWING_SPECS[model.type]?.name || model.type;
}

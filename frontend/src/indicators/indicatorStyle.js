// Chart-library-free presentation helpers so eagerly loaded UI (the indicator
// studio) does not pull lightweight-charts into the entry bundle.
export function colorWithOpacity(color, opacity = 1) {
  if (typeof color !== 'string' || !/^#[0-9a-fA-F]{6}$/.test(color) || opacity >= 1) return color;
  const n = parseInt(color.slice(1), 16);
  return `rgba(${n >> 16 & 255}, ${n >> 8 & 255}, ${n & 255}, ${Math.max(0, opacity)})`;
}
// Effective presentation of one output: registry defaults + instance overrides.
export function outputStyle(spec, config, output) {
  const override = config.style?.[output.key] ?? {};
  const base = output.options ?? {};
  const color = override.color ?? base.color ?? (output.outputType === 'histogram' ? '#26a69a' : '#2962ff');
  return {
    visible: config.visible && override.visible !== false,
    color, opacity: override.opacity ?? 1,
    lineWidth: override.lineWidth ?? base.lineWidth ?? (output.outputType === 'line' ? 2 : 1),
    lineStyle: override.lineStyle ?? 'solid',
    positiveColor: override.positiveColor, negativeColor: override.negativeColor,
  };
}

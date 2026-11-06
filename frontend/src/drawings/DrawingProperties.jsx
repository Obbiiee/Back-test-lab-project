import { useEffect, useMemo, useRef, useState } from 'react';
import { DRAWING_SPECS, TEXT, HORIZONTAL_LINE, VERTICAL_LINE, ANCHORED_TEXT, POLYLINE_MAX_NODES } from './DrawingTypes.js';
import { capabilities, resolvedStyle, COLOR_PRESETS, LINE_STYLES, UI_WIDTH, FONT_SIZE, LEVEL_DEFAULTS, ICONS, dashFor, displayName } from './drawingStyle.js';
import { stepPrice, stepBars, parseUtc, formatUtc, formatPrice, decimalsOf } from './drawingEdits.js';
import './DrawingProperties.css';

// Shared registry-driven Properties editor for every drawing (Issue #21 C-01).
// Every control writes straight to the canonical model through the drawing
// manager, so the chart, Object Tree, undo history and storage stay in sync.
// Controls that would have no effect on a tool are not rendered.

const ANCHOR_NAMES = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';
const LARGE_STEP = 10;

function NumberField({ value, onCommit, disabled, step, label, onArrow, format = String, inputMode = 'decimal', ...rest }) {
  const [draft, setDraft] = useState(null);
  const shown = draft ?? format(value);
  return <input {...rest} aria-label={label} type="text" inputMode={inputMode} disabled={disabled} value={shown} data-step={step}
    onFocus={() => setDraft(format(value))}
    onChange={event => { setDraft(event.target.value); const parsed = Number(event.target.value); if (event.target.value.trim() && Number.isFinite(parsed)) onCommit(parsed, false); }}
    onBlur={() => setDraft(null)}
    onKeyDown={event => {
      if (event.key === 'Enter') { event.preventDefault(); setDraft(null); event.currentTarget.blur(); }
      if (event.key === 'Escape') { setDraft(null); }
      if (onArrow && (event.key === 'ArrowUp' || event.key === 'ArrowDown')) {
        event.preventDefault(); setDraft(null); onArrow((event.key === 'ArrowUp' ? 1 : -1) * (event.shiftKey ? LARGE_STEP : 1));
      }
    }} />;
}

function Segmented({ label, options, value, onChange, disabled, render }) {
  return <div className="dp-segmented" role="radiogroup" aria-label={label}>
    {options.map(option => <button key={String(option)} type="button" role="radio" aria-checked={value === option} disabled={disabled}
      className={value === option ? 'is-active' : ''} onClick={() => onChange(option)}>{render ? render(option) : String(option)}</button>)}
  </div>;
}

function Toggle({ label, checked, onChange, disabled }) {
  return <label className="dp-toggle"><input type="checkbox" checked={checked} disabled={disabled} onChange={event => onChange(event.target.checked)} /><span>{label}</span></label>;
}

function ColorField({ label, value, onChange, disabled, allowNone = false, presets = true }) {
  return <div className="dp-color" role="group" aria-label={label}>
    {presets && COLOR_PRESETS.map(color => <button key={color} type="button" className={`dp-swatch${value === color ? ' is-active' : ''}`} style={{ background: color }}
      aria-label={`${label} ${color}`} aria-pressed={value === color} disabled={disabled} onClick={() => onChange(color)} />)}
    <input type="color" aria-label={`${label} picker`} disabled={disabled || value === 'none'} value={value === 'none' ? '#000000' : value}
      onChange={event => onChange(event.target.value)} />
    <input className="dp-hex" aria-label={`${label} hex`} disabled={disabled} defaultValue={value} key={value} maxLength={7}
      onBlur={event => { if (/^#[0-9a-fA-F]{6}$/.test(event.target.value)) onChange(event.target.value.toLowerCase()); else event.target.value = value; }}
      onKeyDown={event => { if (event.key === 'Enter') event.currentTarget.blur(); }} />
    {allowNone && <button type="button" className={value === 'none' ? 'is-active' : ''} aria-pressed={value === 'none'} disabled={disabled} onClick={() => onChange(value === 'none' ? '#10141b' : 'none')}>None</button>}
  </div>;
}

function LinePreview({ width, lineStyle, color, opacity = 1 }) {
  const dash = dashFor(lineStyle, width).join(' ');
  return <svg className="dp-preview" viewBox="0 0 30 12" aria-hidden="true"><line x1="3" y1="6" x2="27" y2="6" stroke={color} strokeOpacity={opacity} strokeWidth={width} strokeDasharray={dash || undefined} strokeLinecap="round" /></svg>;
}

function anchorLabel(type, index, count) {
  if (type === HORIZONTAL_LINE) return 'Level';
  if (type === VERTICAL_LINE) return 'Time';
  if (count === 1) return 'Anchor';
  return 'Point ' + ANCHOR_NAMES[index];
}

export default function DrawingProperties({ tools }) {
  const model = tools.objects.find(object => object.id === tools.propertiesId);
  const [tab, setTab] = useState('style');
  // Snapshot at open for Reset; the parent keys this component by drawing id.
  const [initial] = useState(() => tools.objects.find(object => object.id === tools.propertiesId) ?? null);
  const [tickStep, setTickStep] = useState(1), [barStep, setBarStep] = useState(1);
  const panel = useRef(null);
  const openId = tools.propertiesId;
  useEffect(() => { panel.current?.querySelector('[role=tab][aria-selected=true]')?.focus({ preventScroll: true }); }, [openId]);
  const caps = useMemo(() => model ? capabilities(model.type) : {}, [model]);
  if (!model) return null;
  const style = resolvedStyle(model);
  const locked = model.locked;
  const tickSize = tools.tickSize;
  const priceText = value => { const text = formatPrice(value, tickSize); return Number(text) === value ? text : String(value); };
  const set = (patch, coalesce = null) => tools.setOptions(model.id, patch, coalesce);
  const points = model.points;
  const hasText = Boolean(DRAWING_SPECS[model.type]?.text);
  const isText = model.type === TEXT || model.type === ANCHORED_TEXT; // text-only: no line controls
  const levelDefaults = LEVEL_DEFAULTS[caps.levels] ?? LEVEL_DEFAULTS.fib;
  const sizeOnly = caps.text === 'size'; // tools whose only text is a computed label: size control only
  const tabs = [['style', 'Style'], ['coordinates', 'Coordinates'],
    ...(hasText || caps.text ? [['text', 'Text']] : []), ...(caps.levels ? [['levels', 'Levels']] : []), ['object', 'Object']];
  const activeTab = tabs.some(([key]) => key === tab) ? tab : 'style';
  const movePoint = (index, ticks, bars) => {
    const next = points.map((point, i) => (index == null || i === index) ? {
      time: bars ? stepBars(point.time, tools.bars, bars) : point.time,
      price: ticks ? stepPrice(point.price, ticks, tickSize) : point.price,
    } : point);
    tools.setPoints(model.id, next, `move:${index ?? 'all'}:${ticks ? 'p' : 't'}`);
  };
  const setPoint = (index, patch, coalesce) => tools.setPoints(model.id, points.map((point, i) => i === index ? { ...point, ...patch } : point), coalesce);
  const layerIndex = tools.objects.findIndex(object => object.id === model.id);
  const levels = style.levels;
  const setLevels = next => set({ levels: next });
  const close = () => tools.closeProperties();
  return <section ref={panel} className="drawing-properties" role="dialog" aria-label={`${displayName(model)} properties`}
    onKeyDown={event => { if (event.key === 'Escape') { event.stopPropagation(); close(); } }}>
    <header className="dp-header">
      <div className="dp-title">
        <span className="dp-kind">{DRAWING_SPECS[model.type]?.name ?? model.type}</span>
        <input aria-label="Drawing name" className="dp-name" placeholder={DRAWING_SPECS[model.type]?.name} defaultValue={model.name ?? ''} key={model.id + ':' + (model.name ?? '')} maxLength={64}
          onBlur={event => { if ((event.target.value.trim()) !== (model.name ?? '')) tools.rename(model.id, event.target.value); }}
          onKeyDown={event => { if (event.key === 'Enter') event.currentTarget.blur(); }} />
      </div>
      <button type="button" className="dp-close" aria-label="Close drawing properties" onClick={close}>×</button>
    </header>
    {locked && <p className="dp-locked" role="status">Locked. <button type="button" onClick={() => tools.setProperties(model.id, { locked: false })}>Unlock to edit</button></p>}
    <div className="dp-tabs" role="tablist" aria-label="Property groups">
      {tabs.map(([key, label]) => <button key={key} type="button" role="tab" id={`dp-tab-${key}`} aria-selected={activeTab === key} aria-controls={`dp-panel-${key}`}
        onClick={() => setTab(key)}
        onKeyDown={event => {
          const index = tabs.findIndex(([k]) => k === key);
          const next = event.key === 'ArrowRight' ? tabs[(index + 1) % tabs.length] : event.key === 'ArrowLeft' ? tabs[(index - 1 + tabs.length) % tabs.length] : null;
          if (next) { event.preventDefault(); setTab(next[0]); event.currentTarget.parentElement.querySelector(`#dp-tab-${next[0]}`)?.focus(); }
        }}>{label}</button>)}
    </div>
    <div className="dp-body" role="tabpanel" id={`dp-panel-${activeTab}`} aria-labelledby={`dp-tab-${activeTab}`}>
      {activeTab === 'style' && <>
        {!isText && <div className="dp-row"><span className="dp-label">Line color</span><ColorField label="Line color" value={style.color} disabled={locked} onChange={color => set({ color }, 'color')} /></div>}
        {isText && <div className="dp-row"><span className="dp-label">Accent color</span><ColorField label="Accent color" value={style.color} disabled={locked} onChange={color => set({ color }, 'color')} /></div>}
        {!isText && !caps.marker && <div className="dp-row"><span className="dp-label">Thickness</span>
          <Segmented label="Line thickness" disabled={locked} value={Math.min(UI_WIDTH.max, style.lineWidth)} options={[1, 2, 3, 4, 5, 6]} onChange={lineWidth => set({ lineWidth })}
            render={width => <><LinePreview width={width} lineStyle="solid" color="currentColor" /><span className="dp-sr">{width} px</span></>} />
          <span className="dp-value" aria-live="polite">{style.lineWidth}px</span></div>}
        {caps.lineStyle && <div className="dp-row"><span className="dp-label">Line style</span>
          <Segmented label="Line style" disabled={locked} value={style.lineStyle} options={LINE_STYLES} onChange={lineStyle => set({ lineStyle })}
            render={option => <><LinePreview width={2} lineStyle={option} color="currentColor" /><span className="dp-sr">{option}</span></>} /></div>}
        {caps.opacity && <div className="dp-row"><span className="dp-label">Opacity</span>
          <input type="range" aria-label="Opacity" min="0" max="100" step="5" disabled={locked} value={Math.round(style.opacity * 100)} onChange={event => set({ opacity: Number(event.target.value) / 100 }, 'opacity')} />
          <span className="dp-value">{Math.round(style.opacity * 100)}%</span></div>}
        {caps.fill && <>
          <div className="dp-row"><span className="dp-label">{caps.levels ? 'Band fill' : 'Fill'}</span>
            {!caps.levels && <ColorField label="Fill color" presets={false} value={style.fillColor} disabled={locked} onChange={fillColor => set({ fillColor }, 'fill-color')} />}
            <input type="range" aria-label="Fill opacity" min="0" max="100" step="5" disabled={locked} value={Math.round(style.fillOpacity * 100)} onChange={event => set({ fillOpacity: Number(event.target.value) / 100 }, 'fill-opacity')} />
            <span className="dp-value">{Math.round(style.fillOpacity * 100)}%</span></div>
        </>}
        {caps.extend && <div className="dp-row"><span className="dp-label">Extend</span>
          <Toggle label="Left" checked={style.extendLeft} disabled={locked} onChange={extendLeft => set({ extendLeft })} />
          <Toggle label="Right" checked={style.extendRight} disabled={locked} onChange={extendRight => set({ extendRight })} /></div>}
        {(caps.priceLabels || caps.timeLabels) && <div className="dp-row"><span className="dp-label">Labels</span>
          {caps.priceLabels && <Toggle label="Price labels" checked={style.showPriceLabels} disabled={locked} onChange={showPriceLabels => set({ showPriceLabels })} />}
          {caps.timeLabels && <Toggle label="Time label" checked={style.showTimeLabels} disabled={locked} onChange={showTimeLabels => set({ showTimeLabels })} />}</div>}
        {caps.deviation && <div className="dp-row"><span className="dp-label">Bands</span>
          <NumberField label="Band deviations" disabled={locked} value={style.deviation} onCommit={value => { if (value >= 0 && value <= 5) set({ deviation: value }, 'deviation'); }}
            onArrow={steps => set({ deviation: Math.max(0, Math.min(5, Math.round((style.deviation + steps * 0.5) * 2) / 2)) }, 'deviation')} />
          <span className="dp-value">× residual σ (0 hides bands)</span></div>}
        {caps.repeats && <div className="dp-row"><span className="dp-label">Repeats</span>
          <NumberField label="Cycle repeats" inputMode="numeric" disabled={locked} value={style.repeats} onCommit={value => { const n = Math.round(value); if (n >= 1 && n <= 100) set({ repeats: n }, 'repeats'); }}
            onArrow={steps => set({ repeats: Math.max(1, Math.min(100, style.repeats + steps)) }, 'repeats')} />
          <span className="dp-value">interval = A → B</span></div>}
        {caps.icon && <div className="dp-row"><span className="dp-label">Icon</span>
          <Segmented label="Marker icon" disabled={locked} value={style.icon} options={ICONS} onChange={icon => set({ icon })} render={option => <span title={option}>{({ circle: '●', square: '■', diamond: '◆', 'triangle-up': '▲', 'triangle-down': '▼', star: '★', flag: '⚑', cross: '✚' })[option]}<span className="dp-sr">{option}</span></span>} /></div>}
        {caps.direction && <div className="dp-row"><span className="dp-label">Direction</span>
          <Segmented label="Arrow direction" disabled={locked} value={style.direction} options={['up', 'down']} onChange={direction => set({ direction })} render={option => option === 'up' ? '▲ Up' : '▼ Down'} /></div>}
        {caps.marker && <div className="dp-row"><span className="dp-label">Size</span>
          <input type="range" aria-label="Marker size" min="8" max="48" step="2" disabled={locked} value={style.markerSize} onChange={event => set({ markerSize: Number(event.target.value) }, 'marker-size')} />
          <span className="dp-value">{style.markerSize}px</span></div>}
        {caps.middle && <div className="dp-row"><span className="dp-label">Middle</span><Toggle label="Middle line" checked={style.showMiddle} disabled={locked} onChange={showMiddle => set({ showMiddle })} /></div>}
        {caps.reverse && <div className="dp-row"><span className="dp-label">Direction</span><Toggle label="Reverse levels" checked={style.reverse} disabled={locked} onChange={reverse => set({ reverse })} /></div>}
      </>}
      {activeTab === 'coordinates' && <>
        <p className="dp-hint">Exact UTC time and price. Anchors stay on time and price when you zoom, pan or change timeframe.</p>
        <div className="dp-row dp-steps">
          <label>Ticks per step<NumberField label="Ticks per step" inputMode="numeric" value={tickStep} onCommit={value => setTickStep(Math.max(1, Math.min(10000, Math.round(value))))} /></label>
          <label>Bars per step<NumberField label="Bars per step" inputMode="numeric" value={barStep} onCommit={value => setBarStep(Math.max(1, Math.min(10000, Math.round(value))))} /></label>
          <span className="dp-value">1 tick = {formatPrice(tickSize, tickSize)}</span>
        </div>
        {caps.freehand && <p className="dp-hint">{points.length} stroke points. Move the whole stroke below; individual points are not edited.</p>}
        {caps.nodes && <div className="dp-row"><span className="dp-label">Nodes {points.length}</span>
          <button type="button" disabled={locked || points.length >= POLYLINE_MAX_NODES} onClick={() => { const a = points.at(-2), b = points.at(-1); tools.setPoints(model.id, [...points.slice(0, -1), { time: (a.time + b.time) / 2, price: (a.price + b.price) / 2 }, b]); }}>+ Insert node</button>
          <button type="button" disabled={locked || points.length <= 2} onClick={() => tools.setPoints(model.id, points.slice(0, -1))}>− Remove last node</button></div>}
        {!caps.freehand && points.map((point, index) => <fieldset key={index} className="dp-anchor" disabled={locked}>
          <legend>{anchorLabel(model.type, index, points.length)}</legend>
          {model.type !== HORIZONTAL_LINE && <div className="dp-row">
            <label className="dp-grow">Time (UTC)<input type="datetime-local" step="1" aria-label={`${anchorLabel(model.type, index, points.length)} time UTC`} value={formatUtc(point.time)}
              onChange={event => { const time = parseUtc(event.target.value); if (time != null) setPoint(index, { time }, 'time:' + index); }} /></label>
            <div className="dp-stepper" role="group" aria-label={`${anchorLabel(model.type, index, points.length)} time steps`}>
              <button type="button" aria-label={`Move ${anchorLabel(model.type, index, points.length)} left ${barStep} bar`} onClick={event => movePoint(index, 0, -barStep * (event.shiftKey ? LARGE_STEP : 1))}>◀</button>
              <button type="button" aria-label={`Move ${anchorLabel(model.type, index, points.length)} right ${barStep} bar`} onClick={event => movePoint(index, 0, barStep * (event.shiftKey ? LARGE_STEP : 1))}>▶</button>
            </div>
          </div>}
          {model.type !== VERTICAL_LINE && <div className="dp-row">
            <label className="dp-grow">Price<NumberField label={`${anchorLabel(model.type, index, points.length)} price`} step={tickSize} value={point.price} format={priceText}
              onCommit={price => setPoint(index, { price }, 'price:' + index)} onArrow={steps => movePoint(index, steps * tickStep, 0)} /></label>
            <div className="dp-stepper" role="group" aria-label={`${anchorLabel(model.type, index, points.length)} price steps`}>
              <button type="button" aria-label={`Move ${anchorLabel(model.type, index, points.length)} up ${tickStep} tick`} onClick={event => movePoint(index, tickStep * (event.shiftKey ? LARGE_STEP : 1), 0)}>▲</button>
              <button type="button" aria-label={`Move ${anchorLabel(model.type, index, points.length)} down ${tickStep} tick`} onClick={event => movePoint(index, -tickStep * (event.shiftKey ? LARGE_STEP : 1), 0)}>▼</button>
            </div>
          </div>}
        </fieldset>)}
        {points.length > 1 && <fieldset className="dp-anchor" disabled={locked}><legend>Whole drawing</legend>
          <div className="dp-stepper dp-stepper-wide" role="group" aria-label="Move whole drawing">
            <button type="button" aria-label={`Move drawing up ${tickStep} tick`} onClick={event => movePoint(null, tickStep * (event.shiftKey ? LARGE_STEP : 1), 0)}>▲ Up</button>
            <button type="button" aria-label={`Move drawing down ${tickStep} tick`} onClick={event => movePoint(null, -tickStep * (event.shiftKey ? LARGE_STEP : 1), 0)}>▼ Down</button>
            <button type="button" aria-label={`Move drawing left ${barStep} bar`} onClick={event => movePoint(null, 0, -barStep * (event.shiftKey ? LARGE_STEP : 1))}>◀ Left</button>
            <button type="button" aria-label={`Move drawing right ${barStep} bar`} onClick={event => movePoint(null, 0, barStep * (event.shiftKey ? LARGE_STEP : 1))}>▶ Right</button>
          </div>
          <p className="dp-hint">Shift + click or Shift + arrow moves {LARGE_STEP}× the step. On the chart, arrow keys move the selected drawing.</p>
        </fieldset>}
      </>}
      {activeTab === 'text' && <>
        {hasText && <label className="dp-block">Content<textarea aria-label="Text content" rows={3} maxLength={2000} disabled={locked} defaultValue={model.text} key={model.text}
          onBlur={event => { const value = event.target.value.trim(); if (value && value !== model.text) tools.setTextContent?.(model.id, value); else event.target.value = model.text; }} /></label>}
        <div className="dp-row"><span className="dp-label">Font size</span>
          <div className="dp-stepper" role="group" aria-label="Font size">
            <button type="button" aria-label="Decrease font size" disabled={locked || style.fontSize <= FONT_SIZE.min} onClick={() => set({ fontSize: Math.max(FONT_SIZE.min, style.fontSize - 1) }, 'font-size')}>A−</button>
            <select aria-label="Font size value" disabled={locked} value={style.fontSize} onChange={event => set({ fontSize: Number(event.target.value) })}>
              {Array.from({ length: FONT_SIZE.max - FONT_SIZE.min + 1 }, (_, i) => FONT_SIZE.min + i).map(size => <option key={size} value={size}>{size}px</option>)}
            </select>
            <button type="button" aria-label="Increase font size" disabled={locked || style.fontSize >= FONT_SIZE.max} onClick={() => set({ fontSize: Math.min(FONT_SIZE.max, style.fontSize + 1) }, 'font-size')}>A+</button>
          </div></div>
        {!sizeOnly && <>
          <div className="dp-row"><span className="dp-label">Font</span><Segmented label="Font family" disabled={locked} value={style.fontFamily} options={['mono', 'sans']} onChange={fontFamily => set({ fontFamily })} render={option => option === 'mono' ? 'Plex Mono' : 'Inter'} /></div>
          <div className="dp-row"><span className="dp-label">Emphasis</span>
            <button type="button" className={`dp-icon${style.bold ? ' is-active' : ''}`} aria-pressed={style.bold} aria-label="Bold" disabled={locked} onClick={() => set({ bold: !style.bold })}><b>B</b></button>
            <button type="button" className={`dp-icon${style.italic ? ' is-active' : ''}`} aria-pressed={style.italic} aria-label="Italic" disabled={locked} onClick={() => set({ italic: !style.italic })}><i>I</i></button>
            {hasText && <Toggle label="Border" checked={style.textBorder} disabled={locked} onChange={textBorder => set({ textBorder })} />}
          </div>
          <div className="dp-row"><span className="dp-label">Text color</span><ColorField label="Text color" value={style.textColor} disabled={locked} onChange={textColor => set({ textColor }, 'text-color')} /></div>
          <div className="dp-row"><span className="dp-label">Background</span><ColorField label="Text background" presets={false} allowNone value={style.textBackground} disabled={locked} onChange={textBackground => set({ textBackground }, 'text-bg')} /></div>
          <div className="dp-row"><span className="dp-label">Align</span><Segmented label="Text alignment" disabled={locked} value={style.textAlign} options={['left', 'center', 'right']} onChange={textAlign => set({ textAlign })} /></div>
          <div className="dp-row"><span className="dp-label">Position</span><Segmented label="Label position" disabled={locked} value={style.labelPosition} options={['top', 'center', 'bottom']} onChange={labelPosition => set({ labelPosition })} /></div>
        </>}
      </>}
      {activeTab === 'levels' && <>
        <table className="dp-levels"><thead><tr><th>Show</th><th>Level</th><th>Color</th><th><span className="dp-sr">Remove</span></th></tr></thead><tbody>
          {levels.map((level, index) => <tr key={index}>
            <td><input type="checkbox" aria-label={`Show level ${level.value}`} disabled={locked} checked={level.visible} onChange={event => setLevels(levels.map((item, i) => i === index ? { ...item, visible: event.target.checked } : item))} /></td>
            <td><NumberField label={`Level ${index + 1} value`} disabled={locked} value={level.value} onCommit={value => { if (value >= -100 && value <= 100) set({ levels: levels.map((item, i) => i === index ? { ...item, value } : item) }, 'level-value:' + index); }} /></td>
            <td><input type="color" aria-label={`Level ${index + 1} color`} disabled={locked} value={level.color ?? style.color} onChange={event => set({ levels: levels.map((item, i) => i === index ? { ...item, color: event.target.value } : item) }, 'level-color:' + index)} /></td>
            <td><button type="button" aria-label={`Remove level ${level.value}`} disabled={locked || levels.length <= 1} onClick={() => setLevels(levels.filter((_, i) => i !== index))}>×</button></td>
          </tr>)}
        </tbody></table>
        <div className="dp-row">
          <button type="button" disabled={locked || levels.length >= 24} onClick={() => setLevels([...levels, { value: Number(((levels.at(-1)?.value ?? 1) + 0.5).toFixed(3)), visible: true }])}>+ Add level</button>
          <button type="button" disabled={locked} onClick={() => set({ levels: undefined })}>Default levels</button>
        </div>
        <p className="dp-hint">Defaults: {levelDefaults.values.join(' · ')} ({levelDefaults.visible.length} shown).</p>
      </>}
      {activeTab === 'object' && <>
        <div className="dp-row"><span className="dp-label">State</span>
          <Toggle label="Visible" checked={model.visible} onChange={visible => { tools.setProperties(model.id, { visible }); }} />
          <Toggle label="Locked" checked={model.locked} onChange={locked => tools.setProperties(model.id, { locked })} /></div>
        <div className="dp-row"><span className="dp-label">Layer {layerIndex + 1} of {tools.objects.length}</span>
          <div className="dp-stepper dp-stepper-wide" role="group" aria-label="Layer order">
            <button type="button" aria-label="Bring to front" disabled={layerIndex === tools.objects.length - 1} onClick={() => tools.reorder(model.id, 'front')}>⤒ Front</button>
            <button type="button" aria-label="Bring forward" disabled={layerIndex === tools.objects.length - 1} onClick={() => tools.reorder(model.id, 'forward')}>↑ Forward</button>
            <button type="button" aria-label="Send backward" disabled={layerIndex === 0} onClick={() => tools.reorder(model.id, 'backward')}>↓ Backward</button>
            <button type="button" aria-label="Send to back" disabled={layerIndex === 0} onClick={() => tools.reorder(model.id, 'back')}>⤓ Back</button>
          </div></div>
        <div className="dp-row"><span className="dp-label">Object</span>
          <button type="button" onClick={() => tools.duplicate(model.id)}>Duplicate</button>
          <button type="button" className="dp-danger" onClick={() => { tools.remove(model.id); close(); }}>Delete</button></div>
        <p className="dp-hint">ID {model.id.slice(0, 8)} · {points.length} anchor{points.length > 1 ? 's' : ''} · price grid {decimalsOf(tickSize)} decimals. Undo/redo covers drawing edits only, never trades.</p>
      </>}
    </div>
    <footer className="dp-footer">
      <button type="button" disabled={!initial || initial.id !== model.id || JSON.stringify(initial) === JSON.stringify(model)} onClick={() => tools.replaceModel(initial)}>Reset</button>
      <button type="button" className="dp-primary" onClick={close}>Done</button>
    </footer>
  </section>;
}

import WorkspaceModal from "../workspace/WorkspaceModal.jsx";
import { useMemo, useRef, useState } from 'react';
import { productionRegistry } from '../indicators/productionRegistry.js';
import { instanceConfig, effectivePlacement } from '../indicators/indicatorValidation.js';
import { outputStyle } from '../indicators/indicatorStyle.js';
import { CATEGORY_ORDER, UNAVAILABLE_INDICATORS, categoryOf } from './indicatorCatalog.js';

// Shown first, before the collapsed category groups.
const POPULAR = ['SMA', 'EMA', 'BOLLINGER_BANDS', 'RSI', 'MACD', 'ATR', 'SUPERTREND', 'ICHIMOKU'];
import './IndicatorControls.css';

// Issue #21 C-05: indicator picker + per-instance settings (Inputs / Style /
// Placement). Every control writes a validated instance config; the chart
// engine re-renders from that config and IndicatorPreferences persists it.
const OUTPUT_LABEL = key => ({ value: 'Line', basis: 'Basis', upper: 'Upper', lower: 'Lower', macd: 'MACD', signal: 'Signal', histogram: 'Histogram', k: '%K', d: '%D' })[key] ?? key.replace(/([A-Z])/g, ' $1').replace(/^./, c => c.toUpperCase());
const LINE_STYLES = ['solid', 'dashed', 'dotted'];

function paramsText(spec, item) { return Object.values(item.parameters).join(', '); }

export default function IndicatorControls({ instances, onChange, onOpen, registry = productionRegistry, paused = new Set() }) {
  const trigger = useRef(null);
  const [open, setOpen] = useState(false), [editing, setEditing] = useState(null), [error, setError] = useState('');
  const [query, setQuery] = useState(''), [tab, setTab] = useState('inputs');
  const catalog = useMemo(() => {
    const groups = new Map(CATEGORY_ORDER.map(name => [name, []]));
    for (const type of registry.types()) {
      const spec = registry.get(type), category = categoryOf(spec);
      if (!groups.has(category)) groups.set(category, []);
      groups.get(category).push({ type, name: spec.name, description: spec.description ?? '' });
    }
    return groups;
  }, [registry]);
  const q = query.trim().toLowerCase();
  const matches = item => !q || [item.name, item.type, item.description, item.reason].some(text => typeof text === 'string' && text.toLowerCase().includes(q));
  const editingItem = editing && instances.find(item => item.id === editing.id);
  const editingSpec = editingItem && registry.get(editingItem.type);

  function commit(next) {
    try { onChange(next.map(item => instanceConfig(registry, item))); setError(''); return true; }
    catch (failure) { setError(failure.message || 'Invalid indicator settings.'); return false; }
  }
  function add(type) {
    const config = instanceConfig(registry, { id: crypto.randomUUID(), type });
    if (commit([...instances, config])) { setEditing({ id: config.id, parameters: stringParams(config) }); setTab('inputs'); }
  }
  function stringParams(item) { return Object.fromEntries(Object.entries(item.parameters).map(([key, value]) => [key, String(value)])); }
  function patch(id, change) { return commit(instances.map(item => item.id === id ? { ...item, ...change } : item)); }
  function setOutputStyle(item, key, change) {
    const style = { ...(item.style ?? {}) }, next = { ...(style[key] ?? {}), ...change };
    for (const [name, value] of Object.entries(next)) if (value === undefined) delete next[name];
    if (Object.keys(next).length) style[key] = next; else delete style[key];
    patch(item.id, { style: Object.keys(style).length ? style : undefined });
  }
  function apply(event) {
    event.preventDefault();
    if (!editingItem) { setEditing(null); return; }
    const parameters = Object.fromEntries(Object.entries(editing.parameters).map(([key, value]) => {
      const rule = editingSpec.parameters[key];
      if (typeof rule.default === 'boolean') return [key, value === 'true'];
      if (typeof rule.default === 'string') return [key, value];
      return [key, value.trim() ? Number(value) : NaN];
    }));
    try {
      const config = instanceConfig(registry, { ...editingItem, parameters });
      onChange(instances.map(item => item.id === config.id ? config : item)); setError('');
    } catch { setError('Enter valid parameter values within the shown limits.'); }
  }
  function movePane(item, direction) {
    const panes = instances.filter(entry => effectivePlacement(registry.get(entry.type), entry) === 'pane');
    const index = panes.findIndex(entry => entry.id === item.id), target = panes[index + direction];
    if (!target) return;
    const next = [...instances], a = next.findIndex(entry => entry.id === item.id), b = next.findIndex(entry => entry.id === target.id);
    [next[a], next[b]] = [next[b], next[a]];
    commit(next);
  }
  function duplicate(item) {
    if (instances.length >= 16) { setError('At most 16 indicators can be displayed.'); return; }
    const index = instances.findIndex(entry => entry.id === item.id), copy = { ...item, id: crypto.randomUUID() };
    commit([...instances.slice(0, index + 1), copy, ...instances.slice(index + 1)]);
  }
  function close() { setOpen(false); setEditing(null); setError(''); setQuery(''); }
  const paneIds = instances.filter(item => effectivePlacement(registry.get(item.type), item) === 'pane').map(item => item.id);

  return <>
    <button ref={trigger} type="button" className="nav-action" aria-label="Indicators" onClick={() => { onOpen?.(); setOpen(true); }}>Indicators{instances.length ? ` (${instances.length})` : ''}</button>
    {open && <WorkspaceModal label="Overlay indicators" onClose={close} returnFocusRef={trigger}>
      <section className="overlay-indicator-dialog indicator-studio">
        <header><strong>Indicators</strong><span className="ind-count">{instances.length}/16 on chart · saved in this browser only{paused.size ? ` · ${paused.size} paused: phones draw 8 at a time, hide one to show another` : ''}</span><button type="button" aria-label="Close indicators" onClick={close}>×</button></header>
        <div className="ind-layout">
          <div className="ind-catalog">
            <input type="search" aria-label="Search indicators" placeholder="Search indicators…" value={query} onChange={event => setQuery(event.target.value)} />
            {/* Progressive disclosure: a short Popular row, then collapsed groups with counts.
                Searching opens every group that has a match. */}
            {!query.trim() && <div className="ind-group ind-popular" role="group" aria-label="Popular">
              <h3>Popular</h3>
              <div className="indicator-add-tools">
                {POPULAR.filter(type => registry.types().includes(type)).map(type => { const spec = registry.get(type); return <button type="button" key={type} title={spec.description ?? ''} disabled={instances.length >= 16} onClick={() => add(type)}><span className="ind-plus" aria-hidden="true">+</span><span className="dp-sr">Add </span>{spec.name}</button>; })}
              </div>
            </div>}
            {[...catalog].map(([category, items]) => {
              const shown = items.filter(matches), blocked = UNAVAILABLE_INDICATORS.filter(item => item.category === category && matches({ ...item, type: item.id }));
              if (!shown.length && !blocked.length) return null;
              const tools = <div className="indicator-add-tools">
                {shown.map(item => <button type="button" key={item.type} title={item.description} disabled={instances.length >= 16} onClick={() => add(item.type)}><span className="ind-plus" aria-hidden="true">+</span><span className="dp-sr">Add </span>{item.name}</button>)}
                {blocked.map(item => <button type="button" key={item.id} disabled className="ind-blocked" title={item.reason} aria-label={`${item.name} unavailable: ${item.reason}`}>{item.name}<small>needs volume</small></button>)}
              </div>;
              return query.trim()
                ? <div key={category} className="ind-group" role="group" aria-label={category}><h3>{category}</h3>{tools}</div>
                : <details key={category} className="ind-group ind-fold"><summary><h3>{category}</h3><span className="ind-fold-count">{shown.length + blocked.length}</span></summary>{tools}</details>;
            })}
          </div>
          <div className="ind-active">
            <h3>On chart</h3>
            <div className="indicator-instance-list">
              {!instances.length && <p>No indicators added.</p>}
              {instances.map((item, index) => {
                const spec = registry.get(item.type), placement = effectivePlacement(spec, item), paneIndex = paneIds.indexOf(item.id);
                return <div className={`indicator-instance${editing?.id === item.id ? ' is-editing' : ''}`} key={item.id} role="group" aria-label={`${spec.name} instance ${index + 1}`}>
                  <span className="ind-swatches" aria-hidden="true">{spec.outputs.slice(0, 3).map(output => <i key={output.key} style={{ background: outputStyle(spec, item, output).color }} />)}</span>
                  <span className="ind-name">{spec.name} <small>({paramsText(spec, item)}){placement === 'pane' ? ` · pane ${paneIndex + 1}` : ' · price'}{paused.has(item.id) ? ' · paused on this phone' : ''}</small></span>
                  <button type="button" aria-label={`${item.visible ? 'Hide' : 'Show'} indicator ${index + 1}`} onClick={() => patch(item.id, { visible: !item.visible })}>{item.visible ? 'Hide' : 'Show'}</button>
                  <button type="button" aria-label={`Edit indicator ${index + 1}`} aria-pressed={editing?.id === item.id} onClick={() => { setEditing(editing?.id === item.id ? null : { id: item.id, parameters: stringParams(item) }); setError(''); }}>⚙</button>
                  {placement === 'pane' && <>
                    <button type="button" aria-label={`Move indicator ${index + 1} pane up`} disabled={paneIndex <= 0} onClick={() => movePane(item, -1)}>↑</button>
                    <button type="button" aria-label={`Move indicator ${index + 1} pane down`} disabled={paneIndex >= paneIds.length - 1} onClick={() => movePane(item, 1)}>↓</button>
                  </>}
                  <button type="button" aria-label={`Duplicate indicator ${index + 1}`} onClick={() => duplicate(item)}>⧉</button>
                  <button type="button" aria-label={`Remove indicator ${index + 1}`} onClick={() => { commit(instances.filter(config => config.id !== item.id)); if (editing?.id === item.id) setEditing(null); }}>✕</button>
                </div>;
              })}
            </div>
            {editingItem && <div className="ind-settings" aria-label={`${editingSpec.name} settings`}>
              <div className="ind-tabs" role="tablist" aria-label="Indicator settings">
                {[['inputs', 'Inputs'], ['style', 'Style'], ['placement', 'Placement']].map(([key, label]) => <button key={key} type="button" role="tab" aria-selected={tab === key} onClick={() => setTab(key)}>{label}</button>)}
              </div>
              {tab === 'inputs' && <form onSubmit={apply} aria-label="Indicator parameters">
                <strong>Edit {editingSpec.name}</strong>
                {Object.entries(editingSpec.parameters).map(([key, rule], index) => typeof rule.default === 'string' && rule.options
                  ? <label key={key}>{rule.label ?? key}<select aria-label={'Indicator ' + (rule.label ?? key).toLowerCase()} value={editing.parameters[key]} onChange={event => setEditing(value => ({ ...value, parameters: { ...value.parameters, [key]: event.target.value } }))}>{rule.options.map(option => <option key={option} value={option}>{option}</option>)}</select></label>
                  : typeof rule.default === 'boolean'
                    ? <label key={key} className="ind-check"><input type="checkbox" checked={editing.parameters[key] === 'true'} onChange={event => setEditing(value => ({ ...value, parameters: { ...value.parameters, [key]: String(event.target.checked) } }))} />{rule.label ?? key}</label>
                    : <label key={key}>{rule.label ?? (key === 'period' ? 'Period' : key === 'multiplier' ? 'Multiplier' : key)} ({key === 'multiplier' ? '>0' : rule.min}–{rule.max})
                      <input autoFocus={index === 0} aria-label={rule.label ? 'Indicator ' + rule.label.toLowerCase() : key === 'period' ? 'Indicator period' : key === 'multiplier' ? 'Indicator multiplier' : 'Indicator ' + key} type="number" min={rule.min} max={rule.max} step={rule.step} required value={editing.parameters[key]} onChange={event => setEditing(value => ({ ...value, parameters: { ...value.parameters, [key]: event.target.value } }))} />
                    </label>)}
                {editingSpec.validateParameters && editingSpec.constraint && <p>{editingSpec.constraint}</p>}
                {editingItem.type === 'MACD' && <p>Fast period must be smaller than slow period.</p>}
                {editingSpec.notes && <p className="ind-note">{editingSpec.notes}</p>}
                <div><button type="submit">Apply parameters</button><button type="button" onClick={() => { setEditing(null); setError(''); }}>Cancel edit</button></div>
              </form>}
              {tab === 'style' && <div className="ind-style">
                {editingSpec.outputs.map(output => {
                  const style = outputStyle(editingSpec, editingItem, output), name = OUTPUT_LABEL(output.key);
                  return <fieldset key={output.key}><legend>{name}</legend>
                    <label className="ind-check"><input type="checkbox" aria-label={`Show ${name}`} checked={editingItem.style?.[output.key]?.visible !== false} onChange={event => setOutputStyle(editingItem, output.key, { visible: event.target.checked ? undefined : false })} />Visible</label>
                    {output.outputType === 'line' && <>
                      <label className="ind-inline">Color<input type="color" aria-label={`${name} color`} value={style.color} onChange={event => setOutputStyle(editingItem, output.key, { color: event.target.value })} /></label>
                      <div className="ind-seg" role="radiogroup" aria-label={`${name} thickness`}>{[1, 2, 3, 4, 5].map(width => <button key={width} type="button" role="radio" aria-checked={style.lineWidth === width} aria-label={`${width} px`} onClick={() => setOutputStyle(editingItem, output.key, { lineWidth: width })}><svg viewBox="0 0 24 10" aria-hidden="true"><line x1="2" y1="5" x2="22" y2="5" stroke="currentColor" strokeWidth={width} /></svg></button>)}</div>
                      <div className="ind-seg" role="radiogroup" aria-label={`${name} line style`}>{LINE_STYLES.map(option => <button key={option} type="button" role="radio" aria-checked={style.lineStyle === option} onClick={() => setOutputStyle(editingItem, output.key, { lineStyle: option === 'solid' ? undefined : option })}>{option}</button>)}</div>
                    </>}
                    {output.outputType === 'histogram' && <>
                      <label className="ind-inline">Rising<input type="color" aria-label={`${name} positive color`} value={style.positiveColor ?? '#089981'} onChange={event => setOutputStyle(editingItem, output.key, { positiveColor: event.target.value })} /></label>
                      <label className="ind-inline">Falling<input type="color" aria-label={`${name} negative color`} value={style.negativeColor ?? '#f23645'} onChange={event => setOutputStyle(editingItem, output.key, { negativeColor: event.target.value })} /></label>
                    </>}
                    <label className="ind-inline">Opacity<input type="range" aria-label={`${name} opacity`} min="10" max="100" step="5" value={Math.round(style.opacity * 100)} onChange={event => setOutputStyle(editingItem, output.key, { opacity: Number(event.target.value) === 100 ? undefined : Number(event.target.value) / 100 })} /><span>{Math.round(style.opacity * 100)}%</span></label>
                  </fieldset>;
                })}
                <button type="button" onClick={() => patch(editingItem.id, { style: undefined })}>Reset style</button>
              </div>}
              {tab === 'placement' && <div className="ind-placement">
                {editingSpec.placement === 'price' && <div className="ind-seg" role="radiogroup" aria-label="Placement">
                  {[['price', 'Overlay on price'], ['pane', 'Own pane']].map(([value, label]) => <button key={value} type="button" role="radio" aria-checked={effectivePlacement(editingSpec, editingItem) === value} onClick={() => patch(editingItem.id, { placement: value === editingSpec.placement ? undefined : value, ...(value === 'price' ? { paneHeight: undefined, references: undefined } : {}) })}>{label}</button>)}
                </div>}
                {effectivePlacement(editingSpec, editingItem) === 'pane' ? <>
                  <p>Pane {paneIds.indexOf(editingItem.id) + 1} of {paneIds.length} below the price chart.</p>
                  <div className="ind-seg"><button type="button" aria-label="Move pane up" disabled={paneIds.indexOf(editingItem.id) <= 0} onClick={() => movePane(editingItem, -1)}>↑ Move pane up</button><button type="button" aria-label="Move pane down" disabled={paneIds.indexOf(editingItem.id) >= paneIds.length - 1} onClick={() => movePane(editingItem, 1)}>↓ Move pane down</button></div>
                  <label className="ind-inline">Pane height<input type="range" aria-label="Pane height" min="10" max="100" step="5" value={Math.round((editingItem.paneHeight ?? 0.35) * 100)} onChange={event => patch(editingItem.id, { paneHeight: Number(event.target.value) / 100 })} /><span>{Math.round((editingItem.paneHeight ?? 0.35) * 100)}%</span></label>
                  {(editingSpec.references.length > 0 || editingItem.references) && <label>Reference lines (comma separated)
                    <input aria-label="Reference lines" defaultValue={(editingItem.references ?? editingSpec.references).join(', ')} key={editingItem.id + (editingItem.references ?? []).join()} onBlur={event => {
                      const values = event.target.value.split(',').map(part => part.trim()).filter(Boolean).map(Number);
                      if (values.every(Number.isFinite)) patch(editingItem.id, { references: values.join() === editingSpec.references.join() ? undefined : values });
                    }} /></label>}
                </> : <p>Drawn on the price scale with the candles.</p>}
                <p className="ind-note">Indicators use revealed candles only; display precision never affects settlement.</p>
              </div>}
            </div>}
            {error && <p role="alert">{error}</p>}
          </div>
        </div>
      </section>
    </WorkspaceModal>}
  </>;
}

import { useState } from 'react';
import { productionRegistry } from '../indicators/productionRegistry.js';
import { instanceConfig } from '../indicators/indicatorValidation.js';
import './IndicatorControls.css';

export default function IndicatorControls({ instances, onChange }) {
  const [open, setOpen] = useState(false), [editing, setEditing] = useState(null), [error, setError] = useState('');
  function add(type) {
    const config = instanceConfig(productionRegistry, { id: crypto.randomUUID(), type });
    onChange([...instances, config]); setError('');
  }
  function apply(event) {
    event.preventDefault();
    try {
      const current = instances.find(item => item.id === editing.id);
      if (!current) { setEditing(null); return; }
      const parameters = Object.fromEntries(Object.entries(editing.parameters).map(([key, value]) => [key, value.trim() ? Number(value) : NaN]));
      const config = instanceConfig(productionRegistry, { ...current, parameters });
      onChange(instances.map(item => item.id === config.id ? config : item)); setEditing(null); setError('');
    } catch { setError('Enter valid parameter values within the shown limits.'); }
  }
  function close() { setOpen(false); setEditing(null); setError(''); }
  return <>
    <button type="button" className="nav-action" aria-label="Indicators" onClick={() => setOpen(true)}>Indicators{instances.length ? ` (${instances.length})` : ''}</button>
    {open && <div className="dialog-backdrop" onKeyDown={event => { if (event.key === 'Escape') { event.stopPropagation(); close(); } }}>
      <section className="overlay-indicator-dialog" role="dialog" aria-modal="true" aria-label="Overlay indicators">
        <header><strong>Indicators</strong><button type="button" aria-label="Close indicators" onClick={close}>×</button></header>
        <div className="indicator-add-tools">{productionRegistry.types().map(type => <button type="button" key={type} onClick={() => add(type)}>Add {productionRegistry.get(type).name}</button>)}</div>
        <div className="indicator-instance-list">
          {!instances.length && <p>No indicators added.</p>}
          {instances.map((item, index) => <div className="indicator-instance" key={item.id} role="group" aria-label={`${productionRegistry.get(item.type).name} instance ${index + 1}`}>
            <span>{productionRegistry.get(item.type).name} ({Object.values(item.parameters).join(', ')})</span>
            <button type="button" aria-label={`${item.visible ? 'Hide' : 'Show'} indicator ${index + 1}`} onClick={() => onChange(instances.map(config => config.id === item.id ? { ...config, visible: !config.visible } : config))}>{item.visible ? 'Hide' : 'Show'}</button>
            <button type="button" aria-label={`Edit indicator ${index + 1}`} onClick={() => { setEditing({ id: item.id, type: item.type, parameters: Object.fromEntries(Object.entries(item.parameters).map(([key, value]) => [key, String(value)])) }); setError(''); }}>Edit</button>
            <button type="button" aria-label={`Remove indicator ${index + 1}`} onClick={() => { onChange(instances.filter(config => config.id !== item.id)); if (editing?.id === item.id) setEditing(null); }}>Remove</button>
          </div>)}
        </div>
        {editing && <form onSubmit={apply} aria-label="Indicator parameters">
          <strong>Edit {productionRegistry.get(editing.type).name}</strong>
          {Object.entries(productionRegistry.get(editing.type).parameters).map(([key, rule], index) => <label key={key}>{rule.label ?? (key === 'period' ? 'Period' : 'Multiplier')} ({key === 'multiplier' ? '>0' : rule.min}–{rule.max})
            <input autoFocus={index === 0} aria-label={rule.label ? 'Indicator ' + rule.label.toLowerCase() : key === 'period' ? 'Indicator period' : 'Indicator multiplier'} type="number" min={rule.min} max={rule.max} step={rule.step} required value={editing.parameters[key]} onChange={event => setEditing(value => ({ ...value, parameters: { ...value.parameters, [key]: event.target.value } }))} />
          </label>)}
          {editing.type === 'MACD' && <p>Fast period must be smaller than slow period.</p>}
          {error && <p role="alert">{error}</p>}
          <div><button type="submit">Apply parameters</button><button type="button" onClick={() => { setEditing(null); setError(''); }}>Cancel edit</button></div>
        </form>}
      </section>
    </div>}
  </>;
}

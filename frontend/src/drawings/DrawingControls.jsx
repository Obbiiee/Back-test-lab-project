import DrawingTextEditor from './DrawingTextEditor.jsx';
import DrawingProperties from './DrawingProperties.jsx';
import { TEXT } from './DrawingTypes.js';
import { resolvedStyle, LINE_STYLES, UI_WIDTH, displayName } from './drawingStyle.js';

// Quick toolbar for the selected drawing plus the shared Properties panel.
function QuickBar({ tools, selected }) {
  const style = resolvedStyle(selected), locked = selected.locked;
  return <div className="drawing-quickbar" role="toolbar" aria-label={`${displayName(selected)} quick style`}>
    <input type="color" aria-label="Quick line color" disabled={locked} value={style.color} onChange={event => tools.setOptions(selected.id, { color: event.target.value }, 'color')} />
    {selected.type !== TEXT && <select aria-label="Quick line thickness" disabled={locked} value={Math.min(UI_WIDTH.max, style.lineWidth)} onChange={event => tools.setOptions(selected.id, { lineWidth: Number(event.target.value) })}>
      {[1, 2, 3, 4, 5, 6].map(width => <option key={width} value={width}>{width}px</option>)}
    </select>}
    {selected.type !== TEXT && <select aria-label="Quick line style" disabled={locked} value={style.lineStyle} onChange={event => tools.setOptions(selected.id, { lineStyle: event.target.value })}>
      {LINE_STYLES.map(option => <option key={option} value={option}>{option}</option>)}
    </select>}
    {selected.type === TEXT && <button type="button" aria-label="Quick bold" aria-pressed={style.bold} disabled={locked} onClick={() => tools.setOptions(selected.id, { bold: !style.bold })}><b>B</b></button>}
    <span className="qb-sep" aria-hidden="true" />
    <button type="button" aria-label="Open drawing properties" aria-pressed={tools.propertiesId === selected.id} onClick={() => tools.propertiesId === selected.id ? tools.closeProperties() : tools.openProperties(selected.id)}>⚙ Properties</button>
    <button type="button" aria-label="Duplicate drawing" onClick={() => tools.duplicate(selected.id)}>⧉</button>
    <button type="button" aria-label="Delete drawing" onClick={() => tools.remove(selected.id)}>🗑</button>
  </div>;
}

export default function DrawingControls({ tools }) {
  const selected = tools.objects.find(object => object.id === tools.selectedId);
  if (!tools.objects.length && !tools.canUndo && !tools.canRedo && !tools.storageStatus && !tools.textEditor) return null;
  return <>
    {tools.textEditor && <DrawingTextEditor key={tools.textEditor.id ?? 'new'} editor={tools.textEditor} onSave={tools.saveText} onCancel={tools.cancelText} />}
    {selected && <QuickBar tools={tools} selected={selected} />}
    {tools.propertiesId && <DrawingProperties key={tools.propertiesId} tools={tools} />}
    <div className="primitive-drawing-controls" aria-label="drawing controls">
    <button type="button" aria-label="Undo chart drawing" disabled={!tools.canUndo} onClick={tools.undo}>↶</button>
    <button type="button" aria-label="Redo chart drawing" disabled={!tools.canRedo} onClick={tools.redo}>↷</button>
    {selected && <>
      {selected.type === TEXT && <button type="button" aria-label="Edit text drawing" disabled={selected.locked} onClick={()=>tools.editText(selected.id)}>Edit text</button>}
      <button type="button" aria-label={selected.locked ? 'Unlock drawing' : 'Lock drawing'} onClick={() => tools.setProperties(selected.id, { locked: !selected.locked })}>{selected.locked ? 'Unlock' : 'Lock'}</button>
      <button type="button" aria-label="Hide drawing" onClick={() => tools.setProperties(selected.id, { visible: false })}>Hide</button>
    </>}
    {tools.objects.some(object => !object.visible) && <button type="button" aria-label="Show hidden drawings" onClick={tools.showHidden}>Show hidden</button>}
    {tools.storageStatus && <span role="status">{tools.storageStatus}</span>}
  </div></>;
}

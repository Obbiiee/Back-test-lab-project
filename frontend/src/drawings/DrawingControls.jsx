import DrawingTextEditor from './DrawingTextEditor.jsx';
import { TEXT } from './DrawingTypes.js';
export default function DrawingControls({ tools }) {
  const selected = tools.objects.find(object => object.id === tools.selectedId);
  if (!tools.objects.length && !tools.canUndo && !tools.canRedo && !tools.storageStatus && !tools.textEditor) return null;
  return <>
    {tools.textEditor && <DrawingTextEditor key={tools.textEditor.id ?? 'new'} editor={tools.textEditor} onSave={tools.saveText} onCancel={tools.cancelText} />}
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

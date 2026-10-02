export default function DrawingControls({ tools }) {
  const selected = tools.objects.find(object => object.id === tools.selectedId);
  if (!tools.objects.length && !tools.canUndo && !tools.canRedo && !tools.storageStatus) return null;
  return <div className="primitive-drawing-controls" aria-label="Trend Line controls">
    <button type="button" aria-label="Undo Trend Line" disabled={!tools.canUndo} onClick={tools.undo}>↶</button>
    <button type="button" aria-label="Redo Trend Line" disabled={!tools.canRedo} onClick={tools.redo}>↷</button>
    {selected && <>
      <button type="button" aria-label={selected.locked ? 'Unlock Trend Line' : 'Lock Trend Line'} onClick={() => tools.setProperties(selected.id, { locked: !selected.locked })}>{selected.locked ? 'Unlock' : 'Lock'}</button>
      <button type="button" aria-label="Hide Trend Line" onClick={() => tools.setProperties(selected.id, { visible: false })}>Hide</button>
    </>}
    {tools.objects.some(object => !object.visible) && <button type="button" aria-label="Show hidden Trend Lines" onClick={tools.showHidden}>Show hidden</button>}
    {tools.storageStatus && <span role="status">{tools.storageStatus}</span>}
  </div>;
}

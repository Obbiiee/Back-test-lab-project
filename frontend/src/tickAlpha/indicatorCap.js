// Phone indicator cap (owner decision 2026-11-06, PR #36 C-15). On phones only the
// first PHONE_INDICATOR_CAP visible indicators are drawn; the rest stay stored with
// their own visible flag and are paused (not mounted on the chart). Desktop is unchanged and
// nothing here is written back to storage. Measured reason: phone frame p95 33 ms at
// 8 indicators vs 50 ms at 16 (docs/terminal-mobile-gate.md).
export const PHONE_INDICATOR_CAP=8;
export const PHONE_QUERY='(max-width: 760px)';

// -> {rendered: instances to draw, paused: Set of ids paused on this phone}
export function capIndicators(instances,phone){
  const paused=new Set();
  if(!phone)return {rendered:instances,paused};
  let shown=0;
  for(const item of instances){
    if(item.visible===false)continue;
    if(shown<PHONE_INDICATOR_CAP)shown++;else paused.add(item.id);
  }
  // Paused indicators are left out of the chart entirely (no calculation, no pane),
  // which is what saves frame time; a hidden-but-mounted pane still costs layout.
  return {rendered:paused.size?instances.filter(item=>!paused.has(item.id)):instances,paused};
}

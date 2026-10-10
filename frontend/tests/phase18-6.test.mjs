import assert from 'node:assert/strict';
import { COLLAPSED_HEIGHT, COMPACT_HEIGHT, panelBounds, clampPanel, panelState, keyboardPanelHeight } from '../src/workspace/usePanelResize.js';
for (const [width,height] of [[1280,800],[1024,720],[390,844],[320,700]]) {
  const bounds=panelBounds(height,width);
  assert.equal(clampPanel(-100,height,width),COLLAPSED_HEIGHT);
  assert.equal(clampPanel(70,height,width),COLLAPSED_HEIGHT);
  assert.equal(clampPanel(90,height,width),COMPACT_HEIGHT);
  assert.equal(clampPanel(10000,height,width),bounds.max);
  assert.equal(keyboardPanelHeight(150,'Home',false,height,width),COLLAPSED_HEIGHT);
  assert.equal(keyboardPanelHeight(COLLAPSED_HEIGHT,'ArrowUp',false,height,width),COMPACT_HEIGHT);
  assert.equal(keyboardPanelHeight(COMPACT_HEIGHT,'ArrowDown',false,height,width),COLLAPSED_HEIGHT);
  assert.equal(keyboardPanelHeight(COLLAPSED_HEIGHT,'Enter',false,height,width,200),Math.min(200,bounds.max));
  assert.equal(keyboardPanelHeight(COLLAPSED_HEIGHT,'Enter',false,height,width,COLLAPSED_HEIGHT),COMPACT_HEIGHT,'A restored collapsed preference must still reopen');
  assert.equal(keyboardPanelHeight(200,' ',false,height,width),COLLAPSED_HEIGHT);
  assert.equal(keyboardPanelHeight(150,'ArrowUp',true,height,width),Math.min(200,bounds.max));
  assert.equal(keyboardPanelHeight(150,'End',false,height,width),bounds.max);
}
assert.equal(panelState(COLLAPSED_HEIGHT),'COLLAPSED');
assert.equal(panelState(COMPACT_HEIGHT),'COMPACT');
assert.equal(panelState(200),'EXPANDED');
assert.equal(clampPanel(NaN,800),COMPACT_HEIGHT);
console.log('PASS Phase18.6 collapsed/compact/expanded boundaries, narrow bounds, keyboard restore/toggle, Shift resizing and invalid height fallback.');
import { readFileSync } from 'node:fs';
const css=readFileSync(new URL('../src/workspace/designTokens.css',import.meta.url),'utf8');
const tokens=Object.fromEntries([...css.matchAll(/--lab-([\w-]+):\s*(#[\da-f]{6})/gi)].map(m=>[m[1],m[2]]));
const luminance=hex=>{const channels=hex.slice(1).match(/../g).map(c=>parseInt(c,16)/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4);return channels[0]*.2126+channels[1]*.7152+channels[2]*.0722;};
for(const [foreground,background] of [['text-primary','surface-secondary'],['text-secondary','surface-workspace'],['text-primary','selected'],['text-on-light','surface-research']]){
 const a=luminance(tokens[foreground]),b=luminance(tokens[background]);const ratio=(Math.max(a,b)+.05)/(Math.min(a,b)+.05);
 assert(ratio>=4.5,`${foreground}/${background}: ${ratio}`);
}
console.log('PASS design-token text contrast on chooser, terminal, selected and future light research surfaces.');

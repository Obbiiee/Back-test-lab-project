// Unsaved journal note drafts. Research text only: never prices, fills or cash.
// Kept in sessionStorage (this browser tab, cleared when the tab closes), scoped
// to the signed-in workspace, the Session and the order. `baseRevision` is the
// note revision the person started from, so a save sends it as
// expectedNoteRevision and the server refuses it if someone saved in between.
import {accountStorageKey} from './accountClient.js';

const PREFIX='riksora-note-draft';
export const draftKey=(sessionId,orderId)=>accountStorageKey(`${PREFIX}:${sessionId}:${orderId}`);

const store=()=>{try{return globalThis.sessionStorage??null;}catch{return null;}};

export function readDraft(sessionId,orderId){
  try{
    const raw=store()?.getItem(draftKey(sessionId,orderId));
    if(!raw)return null;
    const value=JSON.parse(raw);
    if(typeof value?.text!=='string'||typeof value?.tags!=='string'||!Number.isInteger(value?.baseRevision))return null;
    return {text:value.text.slice(0,4096),tags:value.tags.slice(0,512),baseRevision:value.baseRevision};
  }catch{return null;}
}

// True only when the draft is actually in tab storage. Missing storage, a blocked
// accessor or a full quota all return false, so the page can say the text is not kept.
export function writeDraft(sessionId,orderId,draft){
  const target=store();
  if(!target||typeof target.setItem!=='function')return false;
  try{target.setItem(draftKey(sessionId,orderId),JSON.stringify({text:draft.text,tags:draft.tags,baseRevision:draft.baseRevision}));return true;}
  catch{return false;}
}

export function clearDraft(sessionId,orderId){try{store()?.removeItem(draftKey(sessionId,orderId));}catch{/* storage may be blocked */}}

export const tagList=text=>text.split(',').map(item=>item.trim()).filter(Boolean);
export const tagText=tags=>(tags??[]).join(', ');

// A draft is dirty when it differs from the saved note it would replace.
export function isDirty(draft,note){
  if(!draft)return false;
  return draft.text!==(note?.text??'')||tagList(draft.tags).join('\n')!==(note?.tags??[]).join('\n');
}

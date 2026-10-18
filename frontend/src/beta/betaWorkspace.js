import {canonicalBytes,sha256} from '../tickReview/ReviewImport.js';

export const newId=prefix=>`${prefix}:${crypto.randomUUID()}`;
export function executionCommand(view,kind,payload){
  if(view?.artifact!=='BTL-RESEARCH-SESSION-VIEW-2')throw Error('Unsupported Beta Session.');
  return {schemaVersion:1,artifact:'BTL-TICK-EXECUTION-COMMAND-2',sessionId:view.metadata.id,
    commandId:newId('command'),expectedRevision:view.state.revision,kind,payload};
}
export async function confirmation(review){
  if(review?.artifact!=='BTL-ORDER-REVIEW-2')throw Error('Unsupported review.');
  return {reviewId:review.id,reviewHash:await sha256(canonicalBytes(review))};
}
export function accessMessage(access){
  if(access?.artifact!=='BTL-SANDBOX-ACCESS-1'||access.mode!=='SANDBOX'||access.fundsCollected!==false)throw Error('Unsupported access policy.');
  return `${access.tier} · ${access.savedSessions}/${access.savedLimit} saved Sessions · reset 00:00 ${access.resetTimezone}`;
}
export function betaNotice(error){
  if(error.reconciliationRequired)return 'The request outcome is uncertain. Reload saved evidence before submitting another change.';
  const messages={DAILY_WINDOW_LIMIT:'Today’s Free activation is used. Continue your activated Session, or return after 00:00 UTC.',
    SAVED_SESSION_LIMIT:'Your saved Session limit is reached. Move an unused Session to Trash before creating another.',
    WINDOW_ACTIVATION_REQUIRED:'Activate this Session before replay or trading. Free can activate one monthly window per UTC day.',
    SESSION_TRASHED:'Restore this Session from Trash before continuing.',TRASH_EXPIRED:'The 30-day restore period has expired.',
    WINDOW_CONTINUATION_UNAVAILABLE:'This replay target is outside the activated window.',
    SIGN_IN_REQUIRED:'Your sign-in has expired. Sign in again.',UNAVAILABLE:'Beta sandbox is unavailable here. The operator must enable it; no local feed is substituted.',
    HTTPS_REQUIRED:'Sign-in requires the secure application address.',RELOAD_REQUIRED:'The saved state changed or the request was refused. Reload before trying again.',
    SERVICE_BUSY:'The service is busy. Wait, then reload.',SERVICE_UNAVAILABLE:'The service is unavailable. Reload when it is ready.'};
  return messages[error.code]||'The request was refused. Reload saved evidence and check your inputs.';
}

// Order confirmation outcome model (founder P0, 2026-11-06). The commit result and
// the later Session refresh are separate facts:
//   COMMITTED  the server returned a durable execution result for this review's
//              commandId. A refresh failure afterwards never undoes this.
//   REFUSED    a definitive server refusal: an HTTP status the server sends only
//              after deciding not to apply the command (or before reading it).
//   STALE      a definitive refusal because the Session or review changed.
//   UNKNOWN    anything else: lost response, timeout, 5xx, unreadable body, an
//              unexpected 200 body. The order may or may not be saved.
// UNKNOWN is resolved only by reading the saved Session (read-only GET), never by
// sending the confirmation again or creating a new review on the user's behalf.
//
// HOLD: CODEX RECEIPT INSPECTION. There is no receipt endpoint. reconcile() reads
// GET /sessions/{id} and relies on current backend behaviour (order id = commandId,
// engine.py; commands apply only at their expectedRevision, postgres.py). See
// docs/codex-api-requests.md REQ-02.

// Statuses the services return after a decision, never for a half-applied command:
// 400/422 validation, 401/403 auth, 404 missing review/session, 409 contract refusal
// (the transaction rolls back), 413/415 body checks.
const DEFINITIVE=new Set([400,401,403,404,409,413,415,422]);
// The local service answers these 429 codes before the request reaches a handler.
const NOT_ADMITTED=/^(LOCAL_BUSY|RATE_LIMITED)$/;
const STALE=/STALE|REVISION|REVIEW_EXPIRED|REFUSED_REVIEW|saved record changed/i;

export const UNKNOWN_TEXT='Could not verify whether the order was saved; checking Session status.';

export function classifyConfirmError(error){
  const code=String(error?.message??'');
  const status=error?.status;
  const definitive=DEFINITIVE.has(status)||(status===429&&NOT_ADMITTED.test(code));
  if(!definitive)return {outcome:'UNKNOWN',code:code||'NO_RESPONSE'};
  return {outcome:status===409&&STALE.test(code)?'STALE':'REFUSED',code};
}

// A 200 is a commit only when it is the durable result for this exact command.
export function committedReceipt(result,commandId){
  return result?.artifact==='BTL-TICK-EXECUTION-RESULT-1'&&result.commandId===commandId&&result.durable===true;
}

// Read-only check of a saved Session for an unverified confirmation.
//   COMMITTED  the order exists (its id is the reviewed commandId).
//   REFUSED    absent and the Session moved past the reviewed revision, so this
//              command can no longer apply.
//   UNKNOWN    absent at the same revision: it may still be in flight.
export function reconcile(saved,{commandId,expectedRevision}){
  const state=saved?.state;
  if(!state||typeof state.revision!=='number'||typeof state.orders!=='object'||state.orders===null)return 'UNKNOWN';
  if(Object.hasOwn(state.orders,commandId))return 'COMMITTED';
  return state.revision>expectedRevision?'REFUSED':'UNKNOWN';
}

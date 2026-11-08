// Order confirmation outcome model (founder P0, 2026-11-06). The commit result and
// the later Session refresh are separate facts:
//   COMMITTED  the server returned a durable execution result for this review's
//              commandId. A refresh failure afterwards never undoes this.
//   REFUSED    a definitive server refusal: an HTTP status the server sends only
//              after deciding not to apply the command (or before reading it).
//   STALE      a definitive refusal because the Session or review changed.
//   UNKNOWN    anything else: lost response, timeout, 5xx, unreadable body, an
//              unexpected 200 body. The order may or may not be saved.
// UNKNOWN is resolved only by reading the durable command result (read-only GET),
// never by sending the confirmation again or creating a new review on the user's behalf.
//
// The local API publishes GET /sessions/{id}/commands/{commandId}. The backend
// returns COMMITTED only from the immutable transactional command receipt,
// NOT_COMMITTED only after the reviewed expected revision has been superseded,
// and UNKNOWN while neither fact is durable.

// Statuses the services return after a decision, never for a half-applied command:
// 400/422 validation, 401/403 auth, 404 missing review/session, 409 contract refusal
// (the transaction rolls back), 413/415 body checks.
const DEFINITIVE=new Set([400,401,403,404,409,413,415,422]);
// The local service answers these 429 codes before the request reaches a handler.
const NOT_ADMITTED=/^(LOCAL_BUSY|RATE_LIMITED)$/;
const STALE=/STALE|REVISION|REVIEW_EXPIRED|REFUSED_REVIEW|saved record changed/i;

export const UNKNOWN_TEXT='Could not verify whether the order was saved; checking its durable command receipt.';

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

// A status response is trusted only when it names this exact Session, command,
// and review. An absent receipt without revision proof remains UNKNOWN.
export function classifyCommandResult(result,pending){
  if(result?.schemaVersion!==1||result?.artifact!=='BTL-TICK-COMMAND-STATUS-1'||
     result.sessionId!==pending.sessionId||result.commandId!==pending.commandId||
     result.reviewHash!==pending.reviewHash)return {outcome:'UNKNOWN',code:'UNBOUND_COMMAND_STATUS'};
  if(result.status==='COMMITTED'){
    const receipt=result.receipt;
    if(committedReceipt(receipt,pending.commandId)&&/^[0-9a-f]{64}$/.test(receipt.commandHash||'')&&
       receipt.state?.sessionId===pending.sessionId&&receipt.state.revision===pending.expectedRevision+1&&
       Number.isInteger(result.currentRevision)&&receipt.state.revision<=result.currentRevision)
      return {outcome:'COMMITTED',code:'DURABLE_RECEIPT'};
    return {outcome:'UNKNOWN',code:'INVALID_DURABLE_RECEIPT'};
  }
  if(result.status==='NOT_COMMITTED'&&result.reason==='SESSION_REVISION_ADVANCED'&&
     result.expectedRevision===pending.expectedRevision&&Number.isInteger(result.currentRevision)&&
     result.currentRevision>pending.expectedRevision)
    return {outcome:'REFUSED',code:'SESSION_REVISION_ADVANCED'};
  if(result.status==='UNKNOWN')return {outcome:'UNKNOWN',code:result.reason||'UNRESOLVED'};
  return {outcome:'UNKNOWN',code:'UNKNOWN_COMMAND_STATUS'};
}

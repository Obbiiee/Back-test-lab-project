// Pure helpers for the Account "Plan" panel (tested without a browser).
// A payment redirect must go to Midtrans' hosted page over HTTPS and nowhere else: an unexpected URL is refused, never followed.
const MIDTRANS_HOST=/^https:\/\/app(\.sandbox)?\.midtrans\.com\/(snap|snap\/v[0-9]+)\//;
export const isPaymentRedirect=url=>typeof url==='string'&&url.length<=2048&&MIDTRANS_HOST.test(url);

const int=value=>Number.isInteger(value)&&value>=0?value:null;
// status: BTL-ENTITLEMENT-STATUS-1 (tier, sessions{limit,used,resetsAt}, windows{...}); anything unexpected is shown as unknown, never guessed.
export function planSummary(status){
  if(!status||status.schemaVersion!==1||status.artifact!=='BTL-ENTITLEMENT-STATUS-1'||!['FREE','PRO'].includes(status.tier))return {known:false};
  const sessions=status.sessions||{},windows=status.windows||{};
  return {known:true,tier:status.tier,pro:status.tier==='PRO',
    sessions:{used:int(sessions.used),limit:int(sessions.limit),resetsAt:typeof sessions.resetsAt==='string'?sessions.resetsAt:null},
    windows:{used:int(windows.used),limit:int(windows.limit),resetsAt:typeof windows.resetsAt==='string'?windows.resetsAt:null}};
}
export const formatRupiah=value=>{const n=Number(value);return Number.isInteger(n)&&n>=0?'Rp '+n.toLocaleString('id-ID'):null;};
export const periodDays=seconds=>{const n=Number(seconds);return Number.isInteger(n)&&n>0&&n%86400===0?n/86400:null;};
export function planOffer(plan){
  if(!plan||plan.schemaVersion!==1)return null;
  const price=formatRupiah(plan.amountIdr),days=periodDays(plan.durationSeconds);
  return price&&days?{price,days,testMode:plan.mode==='SANDBOX'||plan.fundsCollected===false}:null;
}

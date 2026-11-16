// What works today, stated per capability (CP4, founder remediation 2026-11-06).
// A capability is AVAILABLE only when this build ships it against a published
// route; otherwise it is NOT_PUBLISHED (backend route missing, see
// docs/product-screen-inventory.md and docs/codex-api-requests.md) or NOT_LIVE
// (a product decision that is not switched on). Nothing here is inferred from
// candidate branches or plans.
export const STATUS_LABEL={AVAILABLE:'Available',NOT_PUBLISHED:'Not published yet',NOT_LIVE:'Not live'};

const BASE=[
  {id:'replay',label:'Replay with Draft → Review → Confirm orders',status:'AVAILABLE',note:'Orders fill on later observed Bid/Ask quotes only.'},
  {id:'journal',label:'Journal notes per Session',status:'AVAILABLE',note:'Notes never change fills or cash.'},
  {id:'session-analytics',label:'Analysis per Session',status:'AVAILABLE',note:'Committed orders only; unknown values stay “—”.'},
  {id:'months',label:'List of start months per instrument',status:'NOT_PUBLISHED',note:'Other months are checked when you create a Session.'},
  {id:'instruments',label:'Instruments beyond the confirmed one',status:'NOT_PUBLISHED',note:'Listed only after the service confirms their data and rights.'},
  {id:'method-analytics',label:'Analytics across all Sessions of a Method',status:'NOT_PUBLISHED',note:'Open each Session’s analysis instead; win rates are never averaged.'},
  {id:'cross-journal',label:'Journal across Sessions',status:'NOT_PUBLISHED',note:'Pick one Session at a time.'},
  {id:'drawing-sync',label:'Drawings on other devices',status:'NOT_PUBLISHED',note:'Drawings are kept in this browser only.'},
  {id:'google',label:'Google sign-in',status:'NOT_LIVE',note:'Email and password only.'},
  {id:'plans',label:'Plans and billing',status:'NOT_LIVE',note:'No payment is taken.'},
];

export function capabilities(catalog){
  const published=catalog?.availability?.schemaVersion===1;
  return BASE.map(item=>item.id==='months'&&published?{...item,status:'AVAILABLE',note:'Months come from the service list.'}:item);
}

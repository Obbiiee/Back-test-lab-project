// Which start months a New Session may use. The frontend never derives
// eligibility from a range: a min/max pair says nothing about gaps, rights or
// expiry. Only a versioned server DTO can list selectable months.
//
// Proposed Codex DTO (frontend/docs/codex-api-requests.md, REQ-01), carried on
// GET /catalog as `availability`:
//   {schemaVersion: 1, instruments: [{instrumentId, status,
//     periods: [{period: 'YYYY-MM', status: 'AVAILABLE'|'GAP'|'RIGHTS_BLOCKED'|'EXPIRED'|'QA_BLOCKED', reason?}]}]}
// Until it is published, the only month the server itself states is
// `catalog.startPeriod` (the first observed quote of the source); any other
// month is checked by POST /sessions and refused if it has no observations.

const MONTH=/^\d{4}-(0[1-9]|1[0-2])$/;
const REASONS={
  PARTIAL:'Only the start months explicitly listed as available can be selected; month coverage is not implied',
  GAP:'No observations in this month',
  RIGHTS_BLOCKED:'Data rights do not cover this month',
  EXPIRED:'No longer offered for new Sessions',
  QA_BLOCKED:'Held back until data checks pass',
  UNKNOWN:'Availability is not verified',
};
// PARTIAL is an instrument-level summary, not a blanket month refusal. The server
// may expose individual AVAILABLE start months while other months remain unavailable.
// RIGHTS_BLOCKED, QA_BLOCKED and unknown instrument states remain closed.
export const INSTRUMENT_REASONS={
  PARTIAL:'Coverage is partial; only start months individually marked available by the server can be selected',
  QA_BLOCKED:'Held back until data checks pass',
  RIGHTS_BLOCKED:'Data rights do not cover this instrument',
  UNKNOWN:'Availability and eligibility are not verified',
  NOT_LISTED:'The server does not list this instrument',
};
export const instrumentReason=status=>INSTRUMENT_REASONS[status]||'Instrument not available';

export const isMonth=value=>typeof value==='string'&&MONTH.test(value);

// -> {mode:'fixed'} for the synthetic fixture,
//    {mode:'published', months:[{period,status,selectable,reason}]} when the DTO exists,
//    {mode:'unpublished', earliest} otherwise.
export function periodAvailability(catalog,instrumentId,historical){
  const dto=catalog?.availability;
  if(catalog&&Object.hasOwn(catalog,'availability')){
    if(!dto||typeof dto!=='object'||dto.schemaVersion!==1||!Array.isArray(dto.instruments))return {mode:'published',months:[],instrumentStatus:'UNKNOWN'};
    const entry=dto.instruments.find(item=>item?.instrumentId===instrumentId);
    if(!entry)return {mode:'published',months:[],instrumentStatus:'NOT_LISTED'};
    const parentEligible=entry.status==='AVAILABLE'||entry.status==='PARTIAL';
    const months=(Array.isArray(entry.periods)?entry.periods:[])
      .filter(item=>isMonth(item?.period))
      .map(item=>{
        const known=['AVAILABLE','PARTIAL','GAP','RIGHTS_BLOCKED','QA_BLOCKED','UNKNOWN','EXPIRED'].includes(item.status);
        const status=known?item.status:'UNKNOWN';
        const selectable=parentEligible&&status==='AVAILABLE';
        return {period:item.period,status,selectable,
          reason:selectable?null:(item.reason||REASONS[status]||instrumentReason(entry.status))};
      })
      .sort((a,b)=>a.period.localeCompare(b.period));
    return {mode:'published',months,instrumentStatus:entry.status};
  }
  if(!historical)return {mode:'fixed',earliest:catalog?.startPeriod??null};
  return {mode:'unpublished',earliest:isMonth(catalog?.startPeriod)?catalog.startPeriod:null};
}

// Is `period` acceptable to send? Published: only a selectable listed month.
// Unpublished: the earliest month, or any later well-formed month (the server
// decides; the UI says so). Never before the earliest observed month.
export function periodChoiceOk(availability,period){
  if(availability.mode==='fixed')return true;
  if(!isMonth(period))return false;
  if(availability.mode==='published')return availability.months.some(item=>item.period===period&&item.selectable);
  return Boolean(availability.earliest)&&period>=availability.earliest;
}

export function defaultPeriod(availability){
  if(availability.mode==='published')return availability.months.find(item=>item.selectable)?.period??null;
  return availability.earliest??null;
}

export const monthLabel=period=>{
  if(!isMonth(period))return '—';
  const [year,month]=period.split('-').map(Number);
  return new Date(Date.UTC(year,month-1,1)).toLocaleDateString('en-GB',{month:'long',year:'numeric',timeZone:'UTC'});
};

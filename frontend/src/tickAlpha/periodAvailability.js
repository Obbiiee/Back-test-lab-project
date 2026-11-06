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
  GAP:'No observations in this month',
  RIGHTS_BLOCKED:'Data rights do not cover this month',
  EXPIRED:'No longer offered for new Sessions',
  QA_BLOCKED:'Held back until data checks pass',
};

export const isMonth=value=>typeof value==='string'&&MONTH.test(value);

// -> {mode:'fixed'} for the synthetic fixture,
//    {mode:'published', months:[{period,status,selectable,reason}]} when the DTO exists,
//    {mode:'unpublished', earliest} otherwise.
export function periodAvailability(catalog,instrumentId,historical){
  if(!historical)return {mode:'fixed',earliest:catalog?.startPeriod??null};
  const dto=catalog?.availability;
  if(dto&&dto.schemaVersion===1&&Array.isArray(dto.instruments)){
    const entry=dto.instruments.find(item=>item?.instrumentId===instrumentId);
    if(!entry)return {mode:'published',months:[],instrumentStatus:'NOT_LISTED'};
    const months=(Array.isArray(entry.periods)?entry.periods:[])
      .filter(item=>isMonth(item?.period)&&typeof item.status==='string')
      .map(item=>({period:item.period,status:item.status,selectable:entry.status==='AVAILABLE'&&item.status==='AVAILABLE',
        reason:item.status==='AVAILABLE'?(entry.status==='AVAILABLE'?null:REASONS[entry.status]||'Instrument not available'):(item.reason||REASONS[item.status]||'Not available')}))
      .sort((a,b)=>a.period.localeCompare(b.period));
    return {mode:'published',months,instrumentStatus:entry.status};
  }
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

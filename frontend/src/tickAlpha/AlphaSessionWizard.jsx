import {useState} from 'react';
import {PageHead,StatePanel} from './AlphaShell.jsx';
import {InstrumentPicker,MethodPicker,SearchableSelect} from './AlphaSelect.jsx';
import {periodAvailability,periodChoiceOk,defaultPeriod,monthLabel,instrumentReason} from './periodAvailability.js';
import {sourceContext} from './client.js';
import {money,kindLabel} from './productData.js';
import {linkTo} from './productRoute.js';

// New Session wizard (founder instruction 2026-11-06 §6E): Method → instrument →
// eligible period → capital → review. The request sent on Create is exactly the
// existing POST /sessions payload; the server stays the authority for validation.
// Months are never inferred from a range (see periodAvailability.js).
const STEPS=['Method','Instrument','Period','Capital','Review'];
const BALANCES=['10000','50000','100000'];
const DECIMAL=/^\d{1,12}(\.\d{1,2})?$/;
const PERIOD_CODES=['REFUSED_HISTORICAL_PERIOD','REFUSED_FIXTURE_PERIOD'];

export default function AlphaSessionWizard({catalog,route,busy,error,onCreate}){
  const historical=sourceContext()==='historical';
  const [step,setStep]=useState(0);
  const [methodId,setMethodId]=useState(()=>catalog.methods.some(m=>m.id===route.method)?route.method:null);
  const [instrument,setInstrument]=useState(catalog.profile?.instrumentId??null);
  const [period,setPeriod]=useState(()=>defaultPeriod(periodAvailability(catalog,catalog.profile?.instrumentId,historical)));
  const [otherMonth,setOtherMonth]=useState(false);
  const [balance,setBalance]=useState('10000');
  const [custom,setCustom]=useState(false);
  const [name,setName]=useState('');
  const method=catalog.methods.find(m=>m.id===methodId)||null;
  const availability=periodAvailability(catalog,instrument,historical);
  const periodError=error&&PERIOD_CODES.includes(error.code);
  const suggested=method&&instrument?`${instrument} · ${method.name}`.slice(0,128):'';
  const finalName=(name.trim()||suggested).slice(0,128);
  const periodOk=periodChoiceOk(availability,period);
  const balanceOk=DECIMAL.test(balance)&&Number(balance)>0;
  const ready=[Boolean(method),Boolean(instrument),periodOk,balanceOk&&Boolean(finalName),true];
  const canOpen=index=>ready.slice(0,index).every(Boolean);
  const changeInstrument=value=>{setInstrument(value);setOtherMonth(false);setPeriod(defaultPeriod(periodAvailability(catalog,value,historical)));};
  // A refused month sends the user back to the Period step with the server's reason.
  const [seenError,setSeenError]=useState(error);
  if(error!==seenError){setSeenError(error);if(periodError)setStep(2);}
  if(!catalog.methods.length)return <><PageHead back={{label:'Sessions',to:{screen:'sessions'}}} eyebrow="New Session" title="Create a Method first"/>
    <StatePanel kind="empty" title="A Session replays one Method" action={<a className="rk-btn rk-btn-primary" {...linkTo({screen:'method-new'})}>Create your first Method</a>}><p>Write the rules first, then replay them on history.</p></StatePanel></>;
  const submit=event=>{
    event.preventDefault();
    if(step<4){if(ready[step])setStep(step+1);return;}
    if(!ready.every(Boolean)||busy)return;
    onCreate({name:finalName,methodId:method.id,symbol:instrument,initialBalance:balance,
      startPeriod:availability.mode==='fixed'?catalog.startPeriod:period});
  };
  return <>
    <PageHead back={method?{label:method.name,to:{screen:'method',method:method.id}}:{label:'Sessions',to:{screen:'sessions'}}} eyebrow="New Session" title="Set up a replay"
      lead="Five short steps. Nothing is saved until you press Create Session."/>
    <ol className="rk-steps" aria-label="Steps">{STEPS.map((label,index)=><li key={label}>
      <button type="button" className={index===step?'is-current':index<step&&ready[index]?'is-done':''} aria-current={index===step?'step':undefined} disabled={!canOpen(index)||busy} onClick={()=>setStep(index)}>
        <span aria-hidden="true">{index<step&&ready[index]?'✓':index+1}</span>{label}</button></li>)}</ol>
    <form className="rk-card rk-form rk-wizard" onSubmit={submit} noValidate>
      {step===0&&<fieldset className="rk-wizard-step"><legend>Which Method should this Session replay?</legend>
        <MethodPicker methods={catalog.methods} value={methodId} onChange={setMethodId} disabled={busy}/>
        {method&&<p className="rk-wizard-note">{method.kind==='PROTOCOL'?`Protocol rules are copied into the Session: risk ${method.riskPercent}% and R:R ${method.rr}, planned entries only. They cannot be changed inside the Session.`:'Free Style: quick or planned orders, with stop and target chosen per order.'}</p>}
      </fieldset>}
      {step===1&&<fieldset className="rk-wizard-step"><legend>What do you want to replay?</legend>
        <InstrumentPicker catalog={catalog} value={instrument} onChange={changeInstrument} disabled={busy}/>
        <p className="rk-wizard-note">One instrument per Session. Changing the instrument resets the period.</p>
      </fieldset>}
      {step===2&&<fieldset className="rk-wizard-step"><legend>Which period?</legend>
        {availability.mode==='fixed'?<div className="rk-wizard-fixed"><strong>Synthetic test fixture</strong><span>Starts at the first observed quote of {catalog.startPeriod}. There is no period to choose for this feed.</span></div>
          :availability.mode==='published'?(availability.months.some(item=>item.selectable)
            ?<SearchableSelect label="Start month (UTC)" placeholder="Search or select month" searchPlaceholder="Search months…" value={period} onChange={setPeriod} disabled={busy}
              options={availability.months.map(item=>({value:item.period,label:monthLabel(item.period),description:item.period,keywords:[item.period],badge:item.selectable?'Available':undefined,disabled:!item.selectable,disabledReason:item.reason}))}
              hint="Only months the server lists as available can be chosen."/>
            :<div className="rk-wizard-fixed" role="status"><strong>No month is available for {instrument}</strong><span>{availability.instrumentStatus&&availability.instrumentStatus!=='AVAILABLE'?`${instrumentReason(availability.instrumentStatus)}.`:'The server lists no available start month for this instrument right now.'} Nothing is filled from other data.</span></div>)
          :!availability.earliest?<div className="rk-wizard-fixed" role="status"><strong>Start months are not published</strong><span>The server did not state an earliest month for this source, so a Session cannot be set up here.</span></div>
          :<div className="rk-period">
            <div className="rk-chips" role="group" aria-label="Start month">
              <button type="button" className="rk-chip" aria-pressed={!otherMonth} disabled={busy} onClick={()=>{setOtherMonth(false);setPeriod(availability.earliest);}}>Earliest observed · {monthLabel(availability.earliest)}</button>
              <button type="button" className="rk-chip" aria-pressed={otherMonth} disabled={busy} onClick={()=>setOtherMonth(true)}>Another month</button>
            </div>
            {otherMonth&&<label className="rk-field">Start month (UTC)<input name="startPeriod" type="month" value={period??''} min={availability.earliest} required disabled={busy} onChange={event=>setPeriod(event.target.value)} aria-invalid={!periodOk} aria-describedby="rk-period-check"/>
              {!periodOk&&<small className="rk-field-error">Choose {monthLabel(availability.earliest)} or a later month.</small>}</label>}
            <p className="rk-wizard-note" id="rk-period-check">{otherMonth
              ?'The server does not publish its list of months yet, so this month is checked when you press Create. A month without observations is refused and never filled with other data.'
              :`${monthLabel(availability.earliest)} is the first month the server reports for this source. Replay starts at its first observed quote.`}</p>
          </div>}
        {periodError&&<p className="rk-form-error" role="alert">{error.text} Pick another month; nothing was created.</p>}
      </fieldset>}
      {step===3&&<fieldset className="rk-wizard-step"><legend>Starting capital</legend>
        <div className="rk-chips" role="group" aria-label="Starting balance">{BALANCES.map(value=><button key={value} type="button" className="rk-chip rk-num" aria-pressed={!custom&&balance===value} onClick={()=>{setCustom(false);setBalance(value);}}>{money(value).replace('.00','')}</button>)}
          <button type="button" className="rk-chip" aria-pressed={custom} onClick={()=>setCustom(true)}>Custom</button></div>
        {custom&&<label className="rk-field">Starting balance (USD)<input inputMode="decimal" value={balance} onChange={event=>setBalance(event.target.value.trim())} aria-invalid={!balanceOk} disabled={busy}/>{!balanceOk&&<small className="rk-field-error">Enter an amount above 0 with at most 2 decimals.</small>}</label>}
        <label className="rk-field">Session name<input value={name} placeholder={suggested} maxLength={128} onChange={event=>setName(event.target.value)} disabled={busy}/><small>Leave empty to use “{suggested}”.</small></label>
      </fieldset>}
      {step===4&&<fieldset className="rk-wizard-step"><legend>Review</legend>
        <dl className="rk-facts rk-review">
          <div><dt>Session</dt><dd>{finalName}</dd></div>
          <div><dt>Method</dt><dd>{method?.name} · {kindLabel(method?.kind)}</dd></div>
          <div><dt>Instrument</dt><dd><span className="rk-num">{instrument}</span> <small className="rk-note">pinned from this workspace’s server profile</small></dd></div>
          <div><dt>Period</dt><dd><span className="rk-num">{availability.mode==='fixed'?`Synthetic fixture · ${catalog.startPeriod}`:`From ${monthLabel(period)} (UTC)`}</span>
            {availability.mode==='unpublished'&&otherMonth&&period!==availability.earliest&&<small className="rk-note"> · checked by the server when you create</small>}</dd></div>
          <div><dt>Starting balance</dt><dd className="rk-num">{money(balance)}</dd></div>
          <div><dt>Data</dt><dd>{catalog.label}</dd></div>
        </dl>
        <p className="rk-wizard-note">The Session pins this Method, instrument and source. Committed orders cannot be rewound; start another Session for a different experiment.</p>
      </fieldset>}
      {error&&!periodError&&<p className="rk-form-error" role="alert">{error.text} Nothing was created; your choices are kept.</p>}
      <div className="rk-wizard-actions">
        {step>0?<button type="button" className="rk-btn" disabled={busy} onClick={()=>setStep(step-1)}>Back</button>:<a className="rk-btn rk-btn-quiet" {...linkTo(method?{screen:'method',method:method.id}:{screen:'sessions'})}>Cancel</a>}
        <button className="rk-btn rk-btn-primary" disabled={busy||!ready[step]}>{step<4?'Continue':busy?'Creating…':'Create Session'}</button>
      </div>
    </form>
  </>;
}

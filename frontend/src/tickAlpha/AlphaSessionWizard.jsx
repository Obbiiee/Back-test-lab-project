import {useState} from 'react';
import {PageHead,StatePanel} from './AlphaShell.jsx';
import {InstrumentPicker,MethodPicker} from './AlphaSelect.jsx';
import {sourceContext} from './client.js';
import {money,kindLabel} from './productData.js';
import {linkTo} from './productRoute.js';

// New Session wizard (founder instruction 2026-11-06 §6E): Method → instrument →
// eligible period → capital → review. The request sent on Create is exactly the
// existing POST /sessions payload; the server stays the authority for validation.
const STEPS=['Method','Instrument','Period','Capital','Review'];
const BALANCES=['10000','50000','100000'];
const DECIMAL=/^\d{1,12}(\.\d{1,2})?$/;

export default function AlphaSessionWizard({catalog,route,busy,error,onCreate}){
  const historical=sourceContext()==='historical';
  const [step,setStep]=useState(0);
  const [methodId,setMethodId]=useState(()=>catalog.methods.some(m=>m.id===route.method)?route.method:null);
  const [instrument,setInstrument]=useState(catalog.profile?.instrumentId??null);
  const [period,setPeriod]=useState(catalog.startPeriod);
  const [balance,setBalance]=useState('10000');
  const [custom,setCustom]=useState(false);
  const [name,setName]=useState('');
  const method=catalog.methods.find(m=>m.id===methodId)||null;
  const maxPeriod=`${catalog.startPeriod.slice(0,4)}-12`;
  const suggested=method&&instrument?`${instrument} · ${method.name}`.slice(0,128):'';
  const finalName=(name.trim()||suggested).slice(0,128);
  const periodOk=!historical||(period>=catalog.startPeriod&&period<=maxPeriod);
  const balanceOk=DECIMAL.test(balance)&&Number(balance)>0;
  const ready=[Boolean(method),Boolean(instrument),periodOk,balanceOk&&Boolean(finalName),true];
  const canOpen=index=>ready.slice(0,index).every(Boolean);
  const changeInstrument=value=>{setInstrument(value);setPeriod(catalog.startPeriod);};
  if(!catalog.methods.length)return <><PageHead back={{label:'Sessions',to:{screen:'sessions'}}} eyebrow="New Session" title="Create a Method first"/>
    <StatePanel kind="empty" title="A Session replays one Method" action={<a className="rk-btn rk-btn-primary" {...linkTo({screen:'method-new'})}>Create your first Method</a>}><p>Write the rules first, then replay them on history.</p></StatePanel></>;
  const submit=event=>{
    event.preventDefault();
    if(step<4){if(ready[step])setStep(step+1);return;}
    if(!ready.every(Boolean)||busy)return;
    onCreate({name:finalName,methodId:method.id,initialBalance:balance,startPeriod:historical?period:catalog.startPeriod});
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
        {historical?<label className="rk-field">Start month (UTC)<input name="startPeriod" type="month" value={period} min={catalog.startPeriod} max={maxPeriod} required disabled={busy} onChange={event=>setPeriod(event.target.value)} aria-invalid={!periodOk}/>
          <small>{periodOk?`Eligible months: ${catalog.startPeriod} to ${maxPeriod}. Replay starts at the first observed quote; a month the server refuses is never filled with other data.`:`Choose a month from ${catalog.startPeriod} to ${maxPeriod}.`}</small></label>
          :<div className="rk-wizard-fixed"><strong>Synthetic test fixture</strong><span>Starts at the first observed quote of {catalog.startPeriod}. There is no period to choose for this feed.</span></div>}
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
          <div><dt>Instrument</dt><dd className="rk-num">{instrument}</dd></div>
          <div><dt>Period</dt><dd className="rk-num">{historical?`From ${period} (UTC)`:`Synthetic fixture · ${catalog.startPeriod}`}</dd></div>
          <div><dt>Starting balance</dt><dd className="rk-num">{money(balance)}</dd></div>
          <div><dt>Data</dt><dd>{catalog.label}</dd></div>
        </dl>
        <p className="rk-wizard-note">The Session pins this Method, instrument and source. Committed orders cannot be rewound; start another Session for a different experiment.</p>
      </fieldset>}
      {error&&<p className="rk-form-error" role="alert">{error}</p>}
      <div className="rk-wizard-actions">
        {step>0?<button type="button" className="rk-btn" disabled={busy} onClick={()=>setStep(step-1)}>Back</button>:<a className="rk-btn rk-btn-quiet" {...linkTo(method?{screen:'method',method:method.id}:{screen:'sessions'})}>Cancel</a>}
        <button className="rk-btn rk-btn-primary" disabled={busy||!ready[step]}>{step<4?'Continue':busy?'Creating…':'Create Session'}</button>
      </div>
    </form>
  </>;
}

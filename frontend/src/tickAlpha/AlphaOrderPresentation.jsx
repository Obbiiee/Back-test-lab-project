// Presentation adapted from OpenCharts OrderPanel / OrderConfirmDialog,
// revision 785d1f18cc1ca67b0246031b2b9a08cb5cb60264.
// Copyright (c) 2024 OpenCharts Contributors. MIT, /licenses/opencharts-LICENSE.txt.
// BTL changes: exact quote strings, intent callbacks, accessibility, no donor
// store/API, arithmetic, one-click submit, margin or projected PnL.
export function DirectionQuotes({side,quote,disabled,onChange}){
  return <div className="alpha-direction-quotes" role="group" aria-label="Order direction">
    {['LONG','SHORT'].map(value=><button key={value} type="button" className={value==='LONG'?'alpha-buy':'alpha-sell'}
      aria-pressed={side===value} disabled={disabled} onClick={()=>onChange(value)}>
      <span>{value==='LONG'?'↗ Buy / Long':'↘ Sell / Short'}</span>
      <strong>{(value==='LONG'?quote?.ask:quote?.bid)??'Unavailable'}</strong>
      <small>{value==='LONG'?'Observed Ask':'Observed Bid'} · draft only</small>
    </button>)}
  </div>;
}

export function ReviewedIntent({payload,methodName,riskBasis}){
  return <>
    <div className={`alpha-review-heading ${payload.side==='LONG'?'alpha-buy':'alpha-sell'}`}>
      <span>{methodName}</span><strong>{payload.side==='LONG'?'Buy / Long':'Sell / Short'} · {payload.orderType}</strong>
      <small>Reviewed intent · fill awaits an eligible tick</small>
    </div>
    <dl className="alpha-reviewed-values">{['entry','sl','tp','quantity','riskPercent'].map(k=><div key={k}>
      <dt>{({entry:'Entry intent',sl:'Stop Loss',tp:'Take Profit',quantity:'Lots',riskPercent:'Risk %'})[k]}</dt><dd>{payload[k]??'None'}</dd>
    </div>)}</dl><p>Reviewed risk basis <strong>${riskBasis}</strong>. Values come from the server review.</p>
  </>;
}

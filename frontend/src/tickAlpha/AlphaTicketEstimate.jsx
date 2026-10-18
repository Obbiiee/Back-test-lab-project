import {plannedEstimate} from './orderEstimate.js';

// Live preview inside the order ticket. Display only: the server review decides the
// reviewed quantity, risk basis and values; fills still need the next eligible tick.
export default function AlphaTicketEstimate({plan,view}){
  const estimate=plannedEstimate({side:plan.side,entry:plan.entry,sl:plan.sl,tp:plan.tp,riskPercent:plan.riskPercent,
    balance:view.state.balance,profile:view.state.profile});
  const cell=(label,value,tone)=><div className={tone?`alpha-estimate-${tone}`:undefined}><dt>{label}</dt><dd>{value??'—'}</dd></div>;
  return <section className="alpha-ticket-estimate" aria-label="Order estimate" aria-live="polite">
    <dl>
      {cell('Est. loss',estimate.riskMoney?`-$${estimate.riskMoney}`:null,'loss')}
      {cell('Est. profit',estimate.rewardMoney?`+$${estimate.rewardMoney}`:null,'profit')}
      {cell('R:R',estimate.rr?`1 : ${estimate.rr}`:null)}
      {cell('≈ Lots',estimate.lots)}
    </dl>
    <p>{estimate.reason??`Stop ${estimate.stopTicks} ticks${estimate.targetTicks?` · target ${estimate.targetTicks} ticks`:''} · ${plan.riskPercent}% of saved balance $${view.state.balance}.`} Estimate only; the review shows the exact values.</p>
  </section>;
}

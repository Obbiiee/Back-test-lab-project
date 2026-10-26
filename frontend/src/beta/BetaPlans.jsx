import './plans.css';

// Canvas 03/17 Free and Pro cards (docs/design/RIKSORA_WORKFLOW.md, owner decisions 2026-10-23).
// Display copy only: checkout amounts, quota and access always come from the server.
const PLANS=[
  {id:'FREE',name:'Free',price:'Rp0',period:'',points:['5 saved Sessions','1 replay window a day, reset 00:00 UTC','Journal and Statistics in every Session']},
  {id:'PRO',name:'Pro',price:'Rp139.000',period:'/ month',alternative:'or Rp1.668.000 / year (139.000 × 12)',points:['More room for saved Sessions','Limits are set by the server','Journal and Statistics in every Session']},
];
const PLAN_NOTE='Pro prices are owner drafts and not on sale yet. Term, renewal, refund and tax are still to be decided. Checkout amounts always come from the server.';

export default function PlanCards({current=null,freeAction=null,headingLevel=3}){
  const Heading=`h${headingLevel}`;
  return <div className="rk-plans">
    <ul className="rk-plan-list">{PLANS.map(plan=><li key={plan.id} className={'rk-plan rk-plan-'+plan.id.toLowerCase()}>
      <div className="rk-plan-head"><Heading>{plan.name}</Heading>
        {current===plan.id?<span className="rk-plan-chip">Your plan</span>:plan.id==='PRO'&&<span className="rk-plan-chip">Draft price · not on sale</span>}</div>
      <p className="rk-plan-price"><strong>{plan.price}</strong>{plan.period&&<span>{plan.period}</span>}</p>
      {plan.alternative&&<p className="rk-plan-alt">{plan.alternative}</p>}
      <ul>{plan.points.map(point=><li key={point}>{point}</li>)}</ul>
      {plan.id==='FREE'&&freeAction}
    </li>)}</ul>
    <p className="rk-plan-note">{PLAN_NOTE}</p>
  </div>;
}

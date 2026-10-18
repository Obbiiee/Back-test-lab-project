import {useMemo,useState} from 'react';
import {ratioLabel} from './annotations.js';
import {stamp} from './display.js';
import {decimalText} from './orderEstimate.js';

// Analysis overview: headline tiles plus the committed cash path as a single-series line.
// Geometry uses Number() for drawing only; every value shown comes from the exact
// committed strings in the analysis projection.
const W=640,H=180,PAD={l:8,r:8,t:12,b:12};

export default function AlphaEquityChart({view}){
  const {metrics,equity}=view.analysis;
  const [hover,setHover]=useState(null);
  const startsAtOrigin=metrics.equityWindowStart===0;
  const points=useMemo(()=>[
    ...(startsAtOrigin?[{key:'start',label:'Session start',balance:view.state.initialBalance}]:[]),
    ...equity.map(row=>({key:row.eventId,label:stamp(row.timeNs),balance:row.balance})),
  ],[equity,startsAtOrigin,view.state.initialBalance]);
  const netText=view.analysis.account.netCashChange,netSign=netText.startsWith('-')?-1:/^0(\.0*)?$/.test(netText)?0:1;
  const tiles=[
    ['Net cash change',`${netSign<0?'-':netSign>0?'+':''}$${decimalText(netText.replace(/^-/,''))??netText}`,netSign<0?'loss':netSign>0?'profit':null],
    ['Win rate',ratioLabel(metrics.winRate,{percent:true})],
    ['Profit factor',ratioLabel(metrics.profitFactor)],
    ['Max cash drawdown',`$${metrics.maxDrawdown}`],
    ['Completed trades',String(metrics.tradeCount)],
  ];
  const geometry=useMemo(()=>{
    if(points.length<2)return null;
    const values=points.map(p=>Number(p.balance)),min=Math.min(...values),max=Math.max(...values),span=max-min||1;
    const x=i=>PAD.l+(W-PAD.l-PAD.r)*i/(points.length-1),y=v=>PAD.t+(H-PAD.t-PAD.b)*(1-(v-min)/span);
    const path=values.map((v,i)=>`${i?'L':'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join('');
    const base=startsAtOrigin?y(values[0]):null;
    const low=points[values.indexOf(min)].balance,high=points[values.indexOf(max)].balance;
    return {x,y,values,path,base,low,high};
  },[points,startsAtOrigin]);
  const onMove=event=>{
    if(!geometry)return;
    const box=event.currentTarget.getBoundingClientRect(),ratio=(event.clientX-box.left)/box.width;
    setHover(Math.max(0,Math.min(points.length-1,Math.round(ratio*(points.length-1)))));
  };
  const active=hover===null?null:points[hover];
  return <section className="alpha-equity" aria-labelledby="alpha-equity-title">
    <ul className="alpha-kpis">{tiles.map(([label,value,tone])=><li key={label}><span>{label}</span><strong className={tone?`alpha-kpi-${tone}`:undefined}>{value}</strong></li>)}</ul>
    <div className="alpha-equity-head"><h3 id="alpha-equity-title">Committed balance</h3><span>{active?`${active.label} · $${active.balance}`:startsAtOrigin?'From Session start':`Latest ${equity.length} postings`}</span></div>
    {geometry?<svg className="alpha-equity-plot" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img"
      aria-label={`Committed balance from $${points[0].balance} to $${points.at(-1).balance} across ${points.length} points`}
      onMouseMove={onMove} onMouseLeave={()=>setHover(null)}>
      {[0.25,0.5,0.75].map(f=><line key={f} className="alpha-equity-grid" x1={PAD.l} x2={W-PAD.r} y1={PAD.t+(H-PAD.t-PAD.b)*f} y2={PAD.t+(H-PAD.t-PAD.b)*f}/>)}
      {geometry.base!==null&&<line className="alpha-equity-base" x1={PAD.l} x2={W-PAD.r} y1={geometry.base} y2={geometry.base}/>}
      <path className="alpha-equity-line" d={geometry.path} vectorEffect="non-scaling-stroke"/>
      {active&&<><line className="alpha-equity-cross" x1={geometry.x(hover)} x2={geometry.x(hover)} y1={PAD.t} y2={H-PAD.b} vectorEffect="non-scaling-stroke"/></>}
    </svg>:<p className="alpha-equity-empty">The balance line appears after the first committed cash posting (a closed or partially closed position).</p>}
    {geometry&&<div className="alpha-equity-scale"><span>Low ${geometry.low}</span><span>High ${geometry.high}</span></div>}
  </section>;
}

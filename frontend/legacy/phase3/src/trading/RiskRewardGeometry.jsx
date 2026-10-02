import { positionStats } from "./riskReward";

export default function RiskRewardGeometry({ drawing, projected: p, candles, width, selected }) {
      const entry = p[0], stop = p[1], target = p[2];
      if (!stop || !target) return null;
      const end = p[3]?.x ?? entry.x + 150, boxWidth = Math.max(20, end - entry.x);
      const stats = positionStats(drawing, candles.at(-1)?.close ?? drawing.points[0].price);
      const labelWidth = Math.max(boxWidth, 310);
      const label = (y, text, color, key) => <g key={key}><rect x={entry.x + boxWidth / 2 - labelWidth / 2} y={y-13} width={labelWidth} height="23" rx="3" fill={color} /><text x={entry.x + boxWidth / 2} y={y+2} textAnchor="middle" className="position-label" style={{fontSize: drawing.fontSize || 11}}>{text}</text></g>;
      const geometry = <>
        <rect x={entry.x} y={Math.min(entry.y, target.y)} width={boxWidth} height={Math.max(1, Math.abs(target.y - entry.y))} fill="#25c99632" />
        <rect x={entry.x} y={Math.min(entry.y, stop.y)} width={boxWidth} height={Math.max(1, Math.abs(stop.y - entry.y))} fill="#f0647430" />
        {[entry, stop, target].map((point, i) => <line key={i} x1={entry.x} y1={point.y} x2={entry.x + boxWidth} y2={point.y} stroke={["#58a6ff", "#f06474", "#25c996"][i]} strokeWidth={drawing.lineWidth || 1.5} />)}
        {(selected || drawing.alwaysShowStats !== false) && <>
          {label(target.y + (target.y < entry.y ? -14 : 22), `Target: ${stats.reward.toFixed(2)} (${stats.rewardPercent.toFixed(2)}%) ${stats.targetTicks.toFixed(0)} ticks · Amount: ${stats.targetBalance.toFixed(2)}`, '#16866b', 'target')}
          {label(entry.y, `Open P&L: ${stats.openPnl.toFixed(2)} · Qty: ${stats.quantity} · Risk/Reward Ratio: ${stats.ratio.toFixed(2)}`, '#263d52', 'entry')}
          {label(stop.y + (stop.y < entry.y ? -14 : 22), `Stop: ${stats.risk.toFixed(2)} (${stats.riskPercent.toFixed(2)}%) ${stats.stopTicks.toFixed(0)} ticks · Amount: ${stats.stopBalance.toFixed(2)}`, '#aa3948', 'stop')}
        </>}
        {[entry,stop,target].map((point,index)=><g key={'price-'+index}><rect x={Math.max(0,width-60)} y={point.y-10} width="60" height="20" fill={['#345f8a','#aa3948','#16866b'][index]} /><text x={width-4} y={point.y+4} textAnchor="end" className="position-label">{drawing.points[index].price.toFixed(2)}</text></g>)}
        <rect x={entry.x} y={Math.min(entry.y, stop.y, target.y)} width={boxWidth} height={Math.max(12, Math.max(entry.y, stop.y, target.y) - Math.min(entry.y, stop.y, target.y))} fill="transparent" className="position-hit" />
      </>;
      return geometry;
}

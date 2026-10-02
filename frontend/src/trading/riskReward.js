export function positionStats(drawing, lastPrice) {
  const [entry,stop,target]=drawing.points.map(point=>point.price);
  const direction=drawing.type==='long-position'?1:-1;
  const risk=(entry-stop)*direction,reward=(target-entry)*direction;
  const account=Number(drawing.accountSize??100000),riskInput=Number(drawing.riskValue??1);
  const riskBudget=drawing.riskMode==='cash'?riskInput:account*riskInput/100;
  const lot=Number(drawing.lotSize??1),pointValue=Number(drawing.pointValue??1),leverage=Number(drawing.leverage??1),tick=Number(drawing.tickSize??0.01);
  const valid=entry>0&&risk>0&&reward>0&&account>0&&riskBudget>0&&lot>0&&pointValue>0&&leverage>0&&tick>0;
  const precision=Math.min(8,Math.max(0,Number(drawing.quantityPrecision??3)));
  const qtyRisk=riskBudget/(risk*pointValue*lot),qtyLeverage=account*leverage/entry*pointValue/lot;
  const quantity=valid?Math.floor(Math.min(qtyRisk,qtyLeverage)*10**precision)/10**precision:0;
  const loss=risk*quantity*pointValue*lot,profit=reward*quantity*pointValue*lot;
  return {valid,entry,risk,reward,ratio:valid?reward/risk:0,quantity,loss,profit,account,stopBalance:account-loss,targetBalance:account+profit,riskPercent:risk/entry*100,rewardPercent:reward/entry*100,stopTicks:risk/tick,targetTicks:reward/tick,openPnl:(lastPrice-entry)*direction*quantity*pointValue*lot};
}

// Preserve the existing conversion from risk quantity to simulator lots.
export function riskRewardOrderSeed(object, lastPrice) {
  const stats = positionStats(object, lastPrice);
  const side = object.type === 'long-position' ? 'Buy' : 'Sell';
  const price = lastPrice ?? stats.entry;
  return {
    side,
    type: Math.abs(stats.entry - price) < .001 ? 'Market'
      : (side === 'Buy' ? stats.entry < price : stats.entry > price) ? 'Limit' : 'Stop',
    entry: stats.entry, sl: object.points[1].price, tp: object.points[2].price,
    size: stats.quantity * (object.lotSize ?? 1) / 100,
  };
}

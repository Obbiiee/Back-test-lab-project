export const CONTRACT_SIZE = 100;
export function initialAccount() { return { initialBalance:100000, balance:100000, orders:[], positions:[], trades:[], lastTime:null }; }
export const pnl=(order,price)=>(price-order.entry)*(order.side==='Buy'?1:-1)*order.size*CONTRACT_SIZE;
export function validateOrder(order,price) {
  if(!['Buy','Sell'].includes(order.side)||!['Market','Limit','Stop'].includes(order.type))return 'Choose a valid side and order type.';
  if(!Number.isFinite(order.size)||order.size<=0)return 'Size must be greater than zero.';
  const entry=order.type==='Market'?price:order.entry;
  if(!Number.isFinite(entry)||entry<=0)return 'Enter a valid entry price.';
  const direction=order.side==='Buy'?1:-1;
  if(order.type==='Limit'&&(entry-price)*direction>=0)return 'Limit entry must be below market for Buy, above market for Sell.';
  if(order.type==='Stop'&&(entry-price)*direction<=0)return 'Stop entry must be above market for Buy, below market for Sell.';
  if(order.sl!=null&&(!Number.isFinite(order.sl)||order.sl<=0||(entry-order.sl)*direction<=0))return 'Stop loss must be on the loss side of entry.';
  if(order.tp!=null&&(!Number.isFinite(order.tp)||order.tp<=0||(order.tp-entry)*direction<=0))return 'Take profit must be on the profit side of entry.';
  if((order.partials??[]).some(item=>!Number.isFinite(item.price)||!Number.isFinite(item.percent)||item.percent<=0||item.percent>=100||(item.price-entry)*direction<=0||order.tp==null||(order.tp-item.price)*direction<=0))return 'Partial targets must be between entry and take profit, with a percentage between 0 and 100.';
  if((order.partials??[]).reduce((sum,item)=>sum+item.percent,0)>=100)return 'Partial close percentages must total less than 100%.';
  return '';
}
export function placeOrder(account,order,quote) {
  const error=validateOrder(order,quote.close);if(error)throw new Error(error);
  const item={...order,initialSize:order.size,id:order.id??crypto.randomUUID(),placedTime:quote.time,commission:0};
  return order.type==='Market'?{...account,positions:[...account.positions,{...item,entry:quote.close,entryTime:quote.time}]}:{...account,orders:[...account.orders,item]};
}
export function closePosition(account,id,price,time,reason='Manual close',fraction=1) {
  const position=account.positions.find(item=>item.id===id);if(!position)return account;
  const amount=Math.min(1,Math.max(0,fraction));if(!amount)return account;
  const size=position.size*amount;
  const trade={...position,id:crypto.randomUUID(),positionId:id,size,exit:price,exitTime:time,reason,pnl:pnl({...position,size},price),notes:position.notes??''};
  return {...account,balance:account.balance+trade.pnl,positions:amount===1?account.positions.filter(item=>item.id!==id):account.positions.map(item=>item.id===id?{...item,size:item.size-size}:item),trades:[...account.trades,trade]};
}
export function processCandle(account,candle,tick=false) {
  // Process forward once. Stops win when OHLC alone cannot establish which exit hit first.
  if(!tick&&account.lastTime!=null&&candle.time<=account.lastTime)return account;
  if(tick)candle={...candle,open:candle.close,high:candle.close,low:candle.close};
  let next={...account,lastTime:candle.time};
  for(const order of account.orders) {
    if(!tick&&candle.time<=order.placedTime)continue;
    const buy=order.side==='Buy',limit=order.type==='Limit';
    const hit=limit?(buy?candle.low<=order.entry:candle.high>=order.entry):(buy?candle.high>=order.entry:candle.low<=order.entry);
    if(!hit)continue;
    const entry=limit?(buy?Math.min(candle.open,order.entry):Math.max(candle.open,order.entry)):(buy?Math.max(candle.open,order.entry):Math.min(candle.open,order.entry));
    next={...next,orders:next.orders.filter(item=>item.id!==order.id),positions:[...next.positions,{...order,entry,entryTime:candle.time}]};
  }
  for(const position of next.positions) {
    if(candle.time<position.entryTime)continue;
    const buy=position.side==='Buy';
    // On a pending entry bar, pre-entry highs/lows are unknown: evaluate exits from the close only.
    const justFilled=position.entryTime===candle.time&&position.type!=='Market';
    const stop=position.sl!=null&&(justFilled?(buy?candle.close<=position.sl:candle.close>=position.sl):(buy?candle.low<=position.sl:candle.high>=position.sl));
    const target=position.tp!=null&&(justFilled?(buy?candle.close>=position.tp:candle.close<=position.tp):(buy?candle.high>=position.tp:candle.low<=position.tp));
    if(stop){next=closePosition(next,position.id,justFilled?candle.close:(buy?Math.min(candle.open,position.sl):Math.max(candle.open,position.sl)),candle.time,'Stop loss');continue;}
    for(const partial of (position.partials??[]).slice().sort((a,b)=>(a.price-b.price)*(buy?1:-1))){
      const hit=justFilled?(buy?candle.close>=partial.price:candle.close<=partial.price):(buy?candle.high>=partial.price:candle.low<=partial.price);if(!hit)continue;
      const current=next.positions.find(item=>item.id===position.id);if(!current)break;
      const price=justFilled?candle.close:(buy?Math.max(candle.open,partial.price):Math.min(candle.open,partial.price));
      next=closePosition(next,position.id,price,candle.time,'Partial take profit',Math.min(1,(position.initialSize??position.size)*partial.percent/100/current.size));
      next={...next,positions:next.positions.map(item=>item.id===position.id?{...item,partials:(item.partials??[]).filter(value=>value.id!==partial.id)}:item)};
    }
    if(target)next=closePosition(next,position.id,justFilled?candle.close:(buy?Math.max(candle.open,position.tp):Math.min(candle.open,position.tp)),candle.time,'Take profit');
  }
  return next;
}

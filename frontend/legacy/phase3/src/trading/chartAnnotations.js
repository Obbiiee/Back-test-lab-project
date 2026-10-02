// Native trading markers and price lines, independent of all drawing objects.
export function syncTradingAnnotations({ series, markerPlugin, priceLines = [], candles,
  positions, orders, position, pendingOrder, simulatedTrades, trades }) {
    const markers=[];
    const aligned=time=>{let lo=0,hi=candles.length-1,index=-1;while(lo<=hi){const mid=(lo+hi)>>1;if(candles[mid].time<=time){index=mid;lo=mid+1;}else hi=mid-1;}return index>=0?candles[index].time:null;};
    const addMarker=(time,side,text,exit=false)=>{const stamp=aligned(time);if(stamp==null)return;markers.push({time:stamp,position:(side==='Buy')!==exit?'belowBar':'aboveBar',color:side==='Buy'?'#22c99a':'#f06474',shape:(side==='Buy')!==exit?'arrowUp':'arrowDown',text});};
    const open=[...positions,...(position?[{id:'legacy',side:position.side==='BUY'?'Buy':'Sell',entry:position.entry_price,sl:position.stop_loss,tp:position.take_profit,entryTime:position.entry_time,size:position.size??1}]:[])];
    const pending=[...orders,...(pendingOrder?[{side:pendingOrder.side==='BUY'?'Buy':'Sell',entry:pendingOrder.entry_price,placedTime:pendingOrder.placed_time,type:pendingOrder.order_type}]:[])];
    open.forEach(item=>addMarker(item.entryTime,item.side,item.side));
    pending.forEach(item=>addMarker(item.placedTime,item.side,item.type));
    simulatedTrades.forEach(item=>{addMarker(item.entryTime,item.side,item.side);addMarker(item.exitTime,item.side,item.reason,true);});
    trades.forEach(item=>{addMarker(item.entry_time,item.side==='BUY'?'Buy':'Sell',item.side);addMarker(item.exit_time,item.side==='BUY'?'Buy':'Sell',item.reason,true);});
    markers.sort((a,b)=>a.time-b.time);markerPlugin?.setMarkers(markers);
    priceLines.forEach(line=>series.removePriceLine(line));priceLines=[];
    for(const item of [...open,...pending]){
      const lines=[{price:item.entry,title:open.includes(item)?`${item.side} ${item.size??''}`:item.type,color:open.includes(item)?'#5b8ff9':'#eabf64'},{price:item.sl,title:'SL',color:'#f06474'},{price:item.tp,title:'TP',color:'#22c99a'}];
      lines.filter(line=>Number.isFinite(line.price)).forEach(line=>priceLines.push(series.createPriceLine({...line,lineWidth:1,lineStyle:2,axisLabelVisible:true})));
    }
    return priceLines;
}

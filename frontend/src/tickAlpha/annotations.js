// Presentation adapter only: prices/times stay exact on the wire.
export function syncTickAnnotations({series,markerPlugin,priceLines=[],candles,evidence}){
  priceLines.forEach(line=>series.removePriceLine(line));
  const lines=[],markers=[];
  const align=stamp=>{let lo=0,hi=candles.length-1,index=-1;while(lo<=hi){const mid=(lo+hi)>>1;if(candles[mid].time<=stamp){index=mid;lo=mid+1;}else hi=mid-1;}return index<0?null:candles[index].time;};
  if(evidence?.status==='COMPLETE'){
    for(const event of evidence.annotations){
      const stamp=align(Number(BigInt(event.timeNs)/1000000000n));if(stamp===null)continue;
      const up=(event.side==='LONG')===(event.kind==='ENTRY_FILL');
      markers.push({time:stamp,position:up?'belowBar':'aboveBar',shape:up?'arrowUp':'arrowDown',color:up?'#22c99a':'#f06474',
        text:`${event.kind==='ENTRY_FILL'?'Entry':event.reason} @ ${event.price}${event.chronologyLimited?' (limited chronology)':''}`,id:event.eventId});
    }
    for(const order of evidence.orders.filter(o=>['PENDING','ACTIVE'].includes(o.status))){
      for(const [value,title,color] of [[order.entryPrice??order.entry,order.status==='PENDING'?'Pending '+order.orderType:'Filled '+order.side,'#5b8ff9'],[order.sl,'SL','#f06474'],[order.tp,'TP','#22c99a']]){
        if(value===null)continue;const price=Number(value);if(!Number.isFinite(price))continue;
        lines.push(series.createPriceLine({price,title:`${title} ${value}`,color,lineWidth:1,lineStyle:2,axisLabelVisible:true}));
      }
    }
  }
  markers.sort((a,b)=>a.time-b.time);markerPlugin?.setMarkers(markers);
  return lines;
}

// Rational display rounding is not an account posting or metrics recomputation.
export function ratioLabel(value,{percent=false}={}){
  if(value===null||value===undefined)return 'Unavailable';
  let n=BigInt(value.numerator),d=BigInt(value.denominator);if(d<=0n)throw Error('Invalid ratio');
  if(percent)n*=100n;
  const sign=n<0n?'-':'';if(n<0n)n=-n;
  const scaled=(n*100n+d/2n)/d;
  return `${sign}${scaled/100n}.${String(scaled%100n).padStart(2,'0')}${percent?'%':''}`;
}

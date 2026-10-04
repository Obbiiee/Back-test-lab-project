import {useCallback,useEffect,useRef,useState,useSyncExternalStore} from 'react';
import {initialAccount,placeOrder,closePosition,processCandle,pnl,validateOrder} from './simulator';
import {settleReplay} from './replaySettlement.js';
import {AccountPersistence} from './AccountPersistence.js';
export default function useTrading(candles,replaying=false,transition) {
  const [persistence]=useState(()=>new AccountPersistence());
  const [account,setAccount]=useState(()=>persistence.load());
  const storageStatus=useSyncExternalStore(persistence.subscribe,persistence.snapshot,persistence.snapshot);
  const quote=candles.at(-1);
  const previous=useRef([]);
  useEffect(()=>{
    if(!quote)return;
    // Incoming market candles are an external event; settle orders when that event changes.
    const before=previous.current;
    setAccount(current=>!replaying?processCandle(current,quote,true):settleReplay(current,candles,before,transition));
    previous.current=candles;
  },[candles,quote,replaying,transition]);
  useEffect(()=>{persistence.save(account);},[account,persistence]);
  const place=useCallback(order=>{if(!quote)throw new Error('Wait for a price.');const error=validateOrder(order,quote.close);if(error)throw new Error(error);setAccount(current=>placeOrder(current,order,quote));},[quote]);
  const close=useCallback((id,fraction=1)=>{if(quote)setAccount(current=>closePosition(current,id,quote.close,quote.time,'Manual close',fraction));},[quote]);
  const cancel=useCallback(id=>setAccount(current=>({...current,orders:current.orders.filter(item=>item.id!==id)})),[]);
  const update=useCallback((id,fields)=>{const found=[...account.orders,...account.positions].find(item=>item.id===id);if(!found)return;const pending=account.orders.some(item=>item.id===id);const error=validateOrder({...found,...fields,type:pending?found.type:'Market'},quote?.close??found.entry);if(error)throw new Error(error);setAccount(current=>({...current,positions:current.positions.map(item=>item.id===id?{...item,...fields}:item),orders:current.orders.map(item=>item.id===id?{...item,...fields}:item)}));},[account,quote]);
  const notes=useCallback((id,value)=>setAccount(current=>({...current,trades:current.trades.map(item=>item.id===id?{...item,notes:value}:item)})),[]);
  const reset=useCallback(time=>setAccount({...initialAccount(),lastTime:time}),[]);
  const equity=account.balance+account.positions.reduce((sum,item)=>sum+(quote?pnl(item,quote.close):0),0);
  return {account,equity,quote,place,close,cancel,update,notes,reset,storageStatus};
}

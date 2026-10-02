import {useCallback,useEffect,useState} from 'react';
import {initialAccount,placeOrder,closePosition,processCandle,pnl,validateOrder} from './simulator';
const KEY='backtest-paper-account-v1';
function read(){try{const saved=JSON.parse(localStorage.getItem(KEY));if(saved&&Number.isFinite(saved.balance)&&['orders','positions','trades'].every(key=>Array.isArray(saved[key])))return saved;}catch{/* Start a fresh account if browser storage is unavailable. */}return initialAccount();}
export default function useTrading(candles,replaying=false) {
  const [account,setAccount]=useState(read);
  const quote=candles.at(-1);
  useEffect(()=>{
    if(!quote)return;
    // Incoming market candles are an external event; settle orders when that event changes.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setAccount(current=>{if(!replaying)return processCandle(current,quote,true);if(quote.time<current.lastTime&&!current.positions.length&&!current.orders.length&&!current.trades.length)return {...current,lastTime:quote.time};let result=current;for(const candle of candles)if(current.lastTime!=null&&candle.time>current.lastTime)result=processCandle(result,candle);return current.lastTime==null?{...current,lastTime:quote.time}:result;});
  },[candles,quote,replaying]);
  useEffect(()=>{try{localStorage.setItem(KEY,JSON.stringify(account));}catch{/* In-memory account remains available. */}},[account]);
  const place=useCallback(order=>{if(!quote)throw new Error('Wait for a price.');const error=validateOrder(order,quote.close);if(error)throw new Error(error);setAccount(current=>placeOrder(current,order,quote));},[quote]);
  const close=useCallback((id,fraction=1)=>{if(quote)setAccount(current=>closePosition(current,id,quote.close,quote.time,'Manual close',fraction));},[quote]);
  const cancel=useCallback(id=>setAccount(current=>({...current,orders:current.orders.filter(item=>item.id!==id)})),[]);
  const update=useCallback((id,fields)=>{const found=[...account.orders,...account.positions].find(item=>item.id===id);if(!found)return;const pending=account.orders.some(item=>item.id===id);const error=validateOrder({...found,...fields,type:pending?found.type:'Market'},quote?.close??found.entry);if(error)throw new Error(error);setAccount(current=>({...current,positions:current.positions.map(item=>item.id===id?{...item,...fields}:item),orders:current.orders.map(item=>item.id===id?{...item,...fields}:item)}));},[account,quote]);
  const notes=useCallback((id,value)=>setAccount(current=>({...current,trades:current.trades.map(item=>item.id===id?{...item,notes:value}:item)})),[]);
  const reset=useCallback(time=>setAccount({...initialAccount(),lastTime:time}),[]);
  const equity=account.balance+account.positions.reduce((sum,item)=>sum+(quote?pnl(item,quote.close):0),0);
  return {account,equity,quote,place,close,cancel,update,notes,reset};
}

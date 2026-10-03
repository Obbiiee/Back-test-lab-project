import {useMemo,useState} from 'react';
import BacktestAnalysis from './BacktestAnalysis.jsx';
import {analyzeAccount} from './backtestAnalysis';
import {pnl} from './simulator';
import {money} from './format';
const price=value=>value==null?'—':Number(value).toFixed(3);
export default function PositionsPanel({trading,tab,onTab,onEdit,onResize,onHide}){
  const [page,setPage]=useState(1),[pageSize,setPageSize]=useState(10);
  const {trades,positions,initialBalance,balance}=trading.account;
  const analysis=useMemo(()=>tab==='Analysis'?analyzeAccount({trades,positions,initialBalance,balance}):null,[tab,trades,positions,initialBalance,balance]);
  const {account,quote}=trading,items=tab==='Analysis'?[]:tab==='Open Positions'?account.positions:tab==='Pending Orders'?account.orders:account.trades.slice().reverse();
  const pages=Math.max(1,Math.ceil(items.length/pageSize)),current=Math.min(page,pages),rows=items.slice((current-1)*pageSize,current*pageSize),closed=tab==='Closed Positions';
  return <section className="orders-panel fx-positions"><div className="positions-resize" role="separator" aria-label="Resize positions panel" onPointerDown={onResize}/><div className="order-tabs">{['Open Positions','Pending Orders','Closed Positions','Analysis'].map(value=><button key={value} className={tab===value?'active':''} onClick={()=>{onTab(value);setPage(1);}}>{value}</button>)}{tab==='Open Positions'&&items.length>0&&<button className="close-all" onClick={()=>items.forEach(item=>trading.close(item.id))}>Close all</button>}<button className="hide-positions" aria-label="Close positions panel" onClick={onHide}>×</button></div>
    {tab==='Analysis'?<BacktestAnalysis trades={trades} analysis={analysis} onNotes={trading.notes}/>:<>
    <div className="positions-scroll"><table><thead><tr>{['','Asset','Side','Size','Entry','Take Profit','Stop Loss','Unrealized','Realized','Commission',''].map((name,index)=><th key={index}>{name}</th>)}</tr></thead><tbody>{rows.length?rows.map(item=>{const value=closed?item.pnl:quote?pnl(item,quote.close):0;return <tr key={item.id}><td>{item.type==='Market'?'⋮':item.type}</td><td>XAUUSD</td><td className={item.side==='Buy'?'positive':'negative'}>{item.side}</td><td>{item.size.toFixed(4)}</td><td>{price(item.entry)}</td><td>{closed?price(item.tp):<button onClick={()=>onEdit(item)}>{price(item.tp)}</button>}</td><td>{closed?price(item.sl):<button onClick={()=>onEdit(item)}>{price(item.sl)}</button>}</td><td className={value>=0?'positive':'negative'}>{tab==='Open Positions'?money(value):'—'}</td><td className={value>=0?'positive':'negative'}>{closed?money(value):'—'}</td><td>{money(item.commission)}</td><td className="position-actions">{closed?<span>{item.reason}</span>:<><button aria-label={`Edit ${item.side} position`} onClick={()=>onEdit(item)}>✎</button>{tab==='Open Positions'&&<button onClick={()=>trading.close(item.id,.5)} title="Close 50%">½</button>}<button aria-label={tab==='Pending Orders'?'Cancel order':'Close position'} onClick={()=>tab==='Pending Orders'?trading.cancel(item.id):trading.close(item.id)}>{tab==='Pending Orders'?'Cancel':'Close'}</button></>}</td></tr>;}):<tr><td colSpan="11" className="no-data">No data available</td></tr>}</tbody></table></div>
    <div className="pagination"><span>Rows per page</span><select aria-label="Rows per page" value={pageSize} onChange={event=>{setPageSize(Number(event.target.value));setPage(1);}}>{[10,25,50].map(n=><option key={n}>{n}</option>)}</select><div /><button disabled={current<=1} onClick={()=>setPage(current-1)}>‹</button><span>{current}</span><span>of {pages}</span><button disabled={current>=pages} onClick={()=>setPage(current+1)}>›</button></div>
  </>}
  </section>;
}

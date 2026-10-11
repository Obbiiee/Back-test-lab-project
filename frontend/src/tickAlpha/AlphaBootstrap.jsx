import {useEffect,useRef,useState} from 'react';
import {api,sessionPath,noticeText} from './client.js';
import {ratioLabel} from './annotations.js';

export default function AlphaBootstrap({view,busy=false}){
  const [seed,setSeed]=useState('42'),[result,setResult]=useState(null),[error,setError]=useState(''),[running,setRunning]=useState(false);
  const generation=useRef(0);
  useEffect(()=>()=>{generation.current++;},[]);
  const metrics=view.analysis.metrics;
  async function run(event){
    event.preventDefault();
    const value=Number(seed);
    if(!/^[1-9][0-9]{0,9}$/.test(seed)||!Number.isSafeInteger(value)||value>4294967295){setError('Choose an integer seed from 1 to 4294967295.');return;}
    const current=++generation.current;
    setRunning(true);setError('');setResult(null);
    try{
      const response=await api(sessionPath(view.metadata.id)+'/bootstrap',{seed:value});
      if(current!==generation.current)return;
      const p=response.provenance;
      if(response.artifact!=='BTL-DESCRIPTIVE-BOOTSTRAP-1'||response.seed!==value||
        !['COMPLETE','INSUFFICIENT_SAMPLE'].includes(response.status)||
        p?.sessionId!==view.metadata.id||p?.datasetVersion!==view.state.datasetVersion||
        p?.datasetId!==view.state.datasetId||p?.profileHash!==view.state.profileHash||
        p?.revision!==view.state.revision||p?.eventHead!==view.state.eventHash){
        throw Error('The saved Session changed. Reload it before running research again.');
      }
      setResult(response);
    }catch(failure){if(current===generation.current)setError(noticeText(failure.message));}
    finally{if(current===generation.current)setRunning(false);}
  }
  function exportResult(){
    const url=URL.createObjectURL(new Blob([JSON.stringify(result,null,2)],{type:'application/json'}));
    const link=document.createElement('a');link.href=url;link.download='backtest-descriptive-bootstrap.json';link.click();
    setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  return <section aria-label="Descriptive bootstrap"><h3>Descriptive bootstrap</h3>
    <p>Resamples completed net R outcomes. This describes observed results; it does not predict future profit.</p>
    <p>{metrics.rEligible} eligible positions · {metrics.rExcluded} excluded without pinned initial risk. Minimum 30 eligible positions.</p>
    <form onSubmit={run}><label>Research seed<input aria-label="Research seed" inputMode="numeric" value={seed} onChange={event=>setSeed(event.target.value)} disabled={running}/></label>
      <button disabled={running||busy}>{running?'Calculating…':'Run descriptive bootstrap'}</button></form>
    {error&&<p role="alert">{error}</p>}
    {result&&<><p role="status">{result.status==='INSUFFICIENT_SAMPLE'?'Insufficient eligible sample':'Descriptive resampling complete'} · N={result.eligible} · exclusions={result.exclusions} · seed={result.seed} · computed paths={result.pathsComputed}/{result.paths} · {result.prngVersion}</p>
      {result.status==='COMPLETE'&&<div className="alpha-table-scroll"><table aria-label="Bootstrap percentiles"><thead><tr><th>Observed sample statistic</th><th>Percentiles</th></tr></thead><tbody>
        <tr><th>Terminal R</th><td>{Object.entries(result.terminalR).map(([p,v])=>`${p}: ${ratioLabel(v)}`).join(' · ')}</td></tr>
        <tr><th>Maximum drawdown R</th><td>{Object.entries(result.maxDrawdownR).map(([p,v])=>`${p}: ${ratioLabel(v)}`).join(' · ')}</td></tr>
        <tr><th>Longest negative streak</th><td>{Object.entries(result.longestNegativeStreak).map(([p,v])=>`${p}: ${v}`).join(' · ')}</td></tr>
      </tbody></table></div>}
      <button onClick={exportResult}>Export descriptive result JSON</button></>}
  </section>;
}

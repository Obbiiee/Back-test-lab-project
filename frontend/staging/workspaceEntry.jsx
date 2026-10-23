import {StrictMode,lazy,Suspense} from 'react';
import {createRoot} from 'react-dom/client';
import BetaAccount from '../src/beta/BetaAccount.jsx';
import './preview.css';
const Prototype=lazy(()=>import('../src/tradingUx/PrototypeEntry.jsx'));
export function StagingEntry(){
  const params=new URLSearchParams(location.search);
  const prototype=params.get('auth')!=='google'&&params.get('trading-ux')==='prototype';
  return prototype?<div className="repository-preview"><header><a href="/">Home</a><a href="/login/">Sign in</a><p>Trading UX prototype · authored sample data · memory only, separate from saved Sessions</p></header><Suspense fallback={<p>Loading trading UX prototype…</p>}><Prototype/></Suspense></div>:<BetaAccount googleOnly entryPath="/login/"/>;
}
createRoot(document.getElementById('root')).render(<StrictMode><StagingEntry/></StrictMode>);

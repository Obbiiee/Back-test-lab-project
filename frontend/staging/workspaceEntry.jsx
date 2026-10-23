import {StrictMode,lazy,Suspense} from 'react';
import {createRoot} from 'react-dom/client';
import BetaAccount from '../src/beta/BetaAccount.jsx';
import PublicFeatures from './PublicFeatures.jsx';
const Prototype=lazy(()=>import('../src/tradingUx/PrototypeEntry.jsx'));
export function StagingEntry(){
  const params=new URLSearchParams(location.search);
  const view=params.get('auth')==='google'?null:params.get('view');
  return view==='features'?<PublicFeatures/>:view==='prototype'?<div className="public-preview-shell"><header className="public-preview-nav"><a href="/login/?view=features">Back to features</a><a href="/login/">Saved practice with Google</a><p>Design playground · authored sample data · memory only, no saved account or real trades</p></header><Suspense fallback={<p>Loading design playground…</p>}><Prototype/></Suspense></div>:<BetaAccount googleOnly entryPath="/login/"/>;
}
createRoot(document.getElementById('root')).render(<StrictMode><StagingEntry/></StrictMode>);

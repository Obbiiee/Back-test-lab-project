import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './FigmaWorkspace.jsx'
import WorkspaceErrorBoundary from './WorkspaceErrorBoundary.jsx'
import PrototypeEntry from './tradingUx/PrototypeEntry.jsx';
import TickReviewEntry from './tickReview/TickReviewEntry.jsx';
import {isLocalReview} from './tickReview/LocalOrigin.js';
import TickAlphaEntry from './tickAlpha/TickAlphaEntry.jsx';
const tickAlpha=new URLSearchParams(window.location.search).get('tick-alpha')==='local'||new URLSearchParams(window.location.search).get('tick-alpha')==='exness';
const prototype=new URLSearchParams(window.location.search).get('trading-ux')==='prototype';
const tickReview=new URLSearchParams(window.location.search).get('tick-review')==='local';
const localOrigin=isLocalReview(window.location.hostname);
const legacy=new URLSearchParams(window.location.search).get('legacy')==='local';

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <WorkspaceErrorBoundary>{tickAlpha?(localOrigin?<TickAlphaEntry/>:<main><h1>Tick alpha is available on localhost.</h1><a href="/">Return to workspace</a></main>):tickReview?(localOrigin?<TickReviewEntry/>:<main><h1>Local Tick Review hanya tersedia pada localhost.</h1><a href="/">Kembali ke workspace</a></main>):prototype?<PrototypeEntry/>:legacy?<App />:localOrigin?<TickAlphaEntry/>:<main><h1>Backtest Lab local workspace</h1><p>The private data workspace is available on localhost.</p></main>}</WorkspaceErrorBoundary>
  </StrictMode>,
)

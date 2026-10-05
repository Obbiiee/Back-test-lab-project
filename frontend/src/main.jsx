import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './FigmaWorkspace.jsx'
import WorkspaceErrorBoundary from './WorkspaceErrorBoundary.jsx'
import PrototypeEntry from './tradingUx/PrototypeEntry.jsx';
import TickReviewEntry from './tickReview/TickReviewEntry.jsx';
import {isLocalReview} from './tickReview/LocalOrigin.js';
const prototype=new URLSearchParams(window.location.search).get('trading-ux')==='prototype';
const tickReview=new URLSearchParams(window.location.search).get('tick-review')==='local';
const localOrigin=isLocalReview(window.location.hostname);

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <WorkspaceErrorBoundary>{tickReview?(localOrigin?<TickReviewEntry/>:<main><h1>Local Tick Review hanya tersedia pada localhost.</h1><a href="/">Kembali ke workspace</a></main>):prototype?<PrototypeEntry/>:<App />}</WorkspaceErrorBoundary>
  </StrictMode>,
)

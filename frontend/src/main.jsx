import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './FigmaWorkspace.jsx'
import WorkspaceErrorBoundary from './WorkspaceErrorBoundary.jsx'
import PrototypeEntry from './tradingUx/PrototypeEntry.jsx';
const prototype=new URLSearchParams(window.location.search).get('trading-ux')==='prototype';

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <WorkspaceErrorBoundary>{prototype?<PrototypeEntry/>:<App />}</WorkspaceErrorBoundary>
  </StrictMode>,
)

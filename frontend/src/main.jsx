import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './FigmaWorkspace.jsx'
import WorkspaceErrorBoundary from './WorkspaceErrorBoundary.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <WorkspaceErrorBoundary><App /></WorkspaceErrorBoundary>
  </StrictMode>,
)

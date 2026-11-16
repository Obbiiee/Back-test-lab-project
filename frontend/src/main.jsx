import {StrictMode} from 'react';
import {createRoot} from 'react-dom/client';
import './index.css';
import AppEntry from './AppEntry.jsx';
import WorkspaceErrorBoundary from './WorkspaceErrorBoundary.jsx';
import {registerShellWorker} from './pwa.js';

registerShellWorker();
createRoot(document.getElementById('root')).render(
  <StrictMode>
    <WorkspaceErrorBoundary>
      <AppEntry location={window.location}/>
    </WorkspaceErrorBoundary>
  </StrictMode>,
);

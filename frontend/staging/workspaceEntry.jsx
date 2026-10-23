import {StrictMode} from 'react';
import {createRoot} from 'react-dom/client';
import BetaAccount from '../src/beta/BetaAccount.jsx';

// The same maintained account/workspace components as the repository app.
// Google-only composition never advertises password, support or billing APIs.
createRoot(document.getElementById('root')).render(
  <StrictMode><BetaAccount googleOnly entryPath="/login/"/></StrictMode>,
);

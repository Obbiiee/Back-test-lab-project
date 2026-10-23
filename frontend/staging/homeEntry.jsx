import {StrictMode} from 'react';
import {createRoot} from 'react-dom/client';
import AlphaHome from '../src/tickAlpha/AlphaHome.jsx';
createRoot(document.getElementById('root')).render(<StrictMode><AlphaHome hostedPreview/></StrictMode>);

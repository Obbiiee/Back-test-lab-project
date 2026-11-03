// QA-only harness (Issue #21): mounts the real AlphaWorkspace terminal with a
// deterministic synthetic candle fixture so drawing/indicator UI can be
// exercised in a real browser without a backend. Not shipped; never used as
// market data. Prices are strings, as the Session view delivers them.
import { StrictMode, useState } from 'react';
import { createRoot } from 'react-dom/client';
import AlphaWorkspace from '../../src/tickAlpha/AlphaWorkspace.jsx';
// Production bundles these globally via main.jsx's static imports.
import '../../src/FigmaWorkspace.css';
import '../../src/FxWorkspace.css';
import '../../src/workspace/designTokens.css';
import '../../src/tickAlpha/riksoraBrand.css';
import '../../src/tickAlpha/tickAlpha.css';
import '../../src/index.css';

const params = new URLSearchParams(location.search);
if (params.has('reset')) localStorage.clear();
function fixture(count = 400) {
  const start = Date.UTC(2025, 0, 6, 0, 0) / 1000, candles = [];
  let price = 2650, seed = 7;
  const random = () => { seed = (seed * 16807) % 2147483647; return seed / 2147483647; };
  for (let i = 0; i < count; i++) {
    const drift = Math.sin(i / 23) * 1.6 + Math.cos(i / 61) * 1.1 + (random() - .5) * 3.2;
    const open = price, close = Math.max(1, open + drift);
    const high = Math.max(open, close) + random() * 2.2, low = Math.min(open, close) - random() * 2.2;
    candles.push({ time: start + i * 900, open: open.toFixed(3), high: high.toFixed(3), low: low.toFixed(3), close: close.toFixed(3) });
    price = close;
  }
  return candles;
}
const candles = fixture();
const view = {
  metadata: { id: 'qa-fixture-xauusd', startPeriod: '2025-01' },
  state: { throughNs: String(BigInt(candles.at(-1).time + 900) * 1000000000n), ended: false, datasetVersion: 'qa', profile: { tickSize: '0.001' } },
  chart: { priceBasis: 'EXACT_REVEALED_MID_DISPLAY_ONLY', volumeAvailable: false, timeframe: '15m', candles, windowStartGroup: '0' },
  quote: null,
};
export default function Harness() {
  const [objectsOpen, setObjectsOpen] = useState(params.get('objects') !== '0');
  const [notice, setNotice] = useState('');
  return <div className="tick-alpha" style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
    <header style={{ display: 'flex', gap: 12, alignItems: 'center', color: '#fff', padding: '6px 12px', fontFamily: 'Inter, sans-serif', fontSize: 12 }}>
      <strong>RIKSORA · QA harness</strong><span>Synthetic fixture · not market data</span>
      <button onClick={() => setObjectsOpen(value => !value)} aria-pressed={objectsOpen}>Objects</button>
      {notice && <span role="alert">{notice}</span>}
    </header>
    <div className="alpha-workspace" style={{ flex: 1, display: 'flex' }}>
      <AlphaWorkspace objectsOpen={objectsOpen} view={view} timeframe="15m" busy={false} pauseToken="qa" onNotice={setNotice}
        onTimeframe={() => {}} onReplay={async () => null} onPriceSelect={() => {}} onPlanDrawing={() => {}} />
    </div>
  </div>;
}
createRoot(document.getElementById('root')).render(<StrictMode><Harness /></StrictMode>);

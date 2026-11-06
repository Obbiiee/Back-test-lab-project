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
// ?tf=1m|15m… and ?bars=N (≤ 512, the revealed-window limit). Earlier context
// (≤ 50,000 candles) arrives through the real chart-history API path; the
// performance QA serves it from a Playwright route.
const TF = ['1m', '3m', '5m', '15m', '30m', '1h'].includes(params.get('tf')) ? params.get('tf') : '15m';
const STEP = { '1m': 60, '3m': 180, '5m': 300, '15m': 900, '30m': 1800, '1h': 3600 }[TF];
function fixture(count = 400) {
  const start = (TF === '15m' ? Date.UTC(2025, 0, 6, 0, 0) : Date.UTC(2025, 0, 1, 0, 0)) / 1000, candles = [];
  let price = 2650, seed = 7;
  const random = () => { seed = (seed * 16807) % 2147483647; return seed / 2147483647; };
  for (let i = 0; i < count; i++) {
    const drift = Math.sin(i / 23) * 1.6 + Math.cos(i / 61) * 1.1 + (random() - .5) * 3.2;
    const open = price, close = Math.max(1, open + drift);
    const high = Math.max(open, close) + random() * 2.2, low = Math.min(open, close) - random() * 2.2;
    candles.push({ time: start + i * STEP, open: open.toFixed(3), high: high.toFixed(3), low: low.toFixed(3), close: close.toFixed(3) });
    price = close;
  }
  return candles;
}
const candles = fixture(Math.max(50, Math.min(512, Number(params.get('bars')) || 400)));
const view = {
  metadata: { id: 'qa-fixture-xauusd', startPeriod: '2025-01' },
  state: { throughNs: String(BigInt(candles.at(-1).time + STEP) * 1000000000n), ended: false, datasetId: 'qa-dataset', datasetVersion: 'qa', profile: { tickSize: '0.001' } },
  chart: { priceBasis: 'EXACT_REVEALED_MID_DISPLAY_ONLY', volumeAvailable: false, timeframe: TF, candles, windowStartGroup: '0' },
  quote: null,
  // ?history=1: historical Session, so the terminal loads earlier context via chart-history.
  ...(params.get('history') === '1' ? { replayStepNs: String(BigInt(STEP) * 1000000000n) } : {}),
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
      <AlphaWorkspace objectsOpen={objectsOpen} view={view} timeframe={TF} busy={false} pauseToken="qa" onNotice={setNotice}
        onTimeframe={() => {}} onReplay={async () => null} onPriceSelect={() => {}} onPlanDrawing={() => {}} />
    </div>
  </div>;
}
createRoot(document.getElementById('root')).render(<StrictMode><Harness /></StrictMode>);

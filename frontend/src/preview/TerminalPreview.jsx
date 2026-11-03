import { useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import CandleChart from '../components/CandleChart.jsx';
import IndicatorControls from '../components/IndicatorControls.jsx';
import { DRAWING_SPECS } from '../drawings/DrawingTypes.js';
import { productionRegistry } from '../indicators/productionRegistry.js';
import '../index.css';
import '../FigmaWorkspace.css';
import '../FxWorkspace.css';
import '../workspace/designTokens.css';
import './terminal-preview.css';

const PREVIEW_CANDLES = 360;
const STORAGE_KEY = 'riksora-design-preview:claude-pr36:v1';

function syntheticCandles() {
  const start = Date.UTC(2024, 0, 2, 0, 0) / 1000;
  return Array.from({ length: PREVIEW_CANDLES }, (_, index) => {
    const base = 2040 + Math.sin(index / 18) * 8 + Math.sin(index / 5.3) * 2.1 + index * 0.012;
    const open = base + Math.sin(index * 1.71) * 0.55;
    const close = base + Math.cos(index * 1.13) * 0.62;
    const high = Math.max(open, close) + 0.25 + (index % 5) * 0.08;
    const low = Math.min(open, close) - 0.24 - (index % 7) * 0.06;
    return { time: start + index * 900, open, high, low, close };
  });
}

export function Preview() {
  const candles = useMemo(() => syntheticCandles(), []);
  const [drawingMode, setDrawingMode] = useState('none');
  const [indicators, setIndicators] = useState([]);
  const [preferences, setPreferences] = useState({ showGrid: true, showCrosshair: true, showVolume: false });
  const toolTypes = Object.keys(DRAWING_SPECS).filter(type => !['cursor-dot', 'cursor-arrow', 'order'].includes(type));

  return <main className="terminal-preview">
    <header className="tp-header">
      <a className="tp-brand" href="/" aria-label="RIKSORA home">RIKSORA <span>TERMINAL</span></a>
      <span className="tp-preview-badge">DESIGN PREVIEW · SYNTHETIC DATA · NO LIVE ORDERS</span>
      <span className="tp-header-note">Claude UI · PR #36</span>
    </header>
    <section className="tp-meta" aria-label="Preview scope">
      <div><strong>XAUUSD · 15m</strong><span>Authored fixture · 360 candles · browser-local drawings</span></div>
      <p>Interface preview only. No market feed, order submission, fill, account balance, or financial result is connected.</p>
    </section>
    <nav className="tp-tools" aria-label="Chart tools">
      <label htmlFor="tp-drawing-tool">Drawing</label>
      <select id="tp-drawing-tool" value={drawingMode} onChange={event => setDrawingMode(event.target.value)}>
        <option value="none">Cursor · select drawing</option>
        {toolTypes.map(type => <option key={type} value={type}>{DRAWING_SPECS[type].name}</option>)}
      </select>
      <IndicatorControls instances={indicators} onChange={setIndicators} registry={productionRegistry} />
      <button type="button" onClick={() => setPreferences(value => ({ ...value, showGrid: !value.showGrid }))} aria-pressed={preferences.showGrid}>Grid</button>
      <button type="button" onClick={() => setPreferences(value => ({ ...value, showCrosshair: !value.showCrosshair }))} aria-pressed={preferences.showCrosshair}>Crosshair</button>
      <span className="tp-tool-hint">Select a tool, then draw on the chart. Select a drawing to open Properties.</span>
    </nav>
    <section className="tp-chart-card" aria-label="Synthetic design preview chart">
      <div className="tp-chart-title"><strong>Gold · US Dollar</strong><span>DEMO SERIES · NOT MARKET DATA</span></div>
      <div className="tp-chart-host">
        <CandleChart candles={candles} sessionId="design-preview-synthetic-15m" viewportKey="design-preview-synthetic-15m"
          drawingWorkspace="preview:claude-pr36" drawingStorageKey={STORAGE_KEY} drawingMode={drawingMode}
          onDrawingModeChange={setDrawingMode} chartPreferences={preferences} onChartPreferencesChange={setPreferences}
          indicatorRegistry={productionRegistry} indicatorInstances={indicators} researchOnly previewOnly
          volumeAvailable={false} priceStep={0.01} />
      </div>
    </section>
    <footer className="tp-footer"><span>Preview preferences and drawings stay in this browser only.</span><span>Source, execution, account, review and confirmation actions are disabled.</span></footer>
  </main>;
}

createRoot(document.getElementById('root')).render(<Preview />);

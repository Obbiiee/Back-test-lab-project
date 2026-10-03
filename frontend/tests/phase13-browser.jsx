// Test-only real browser fixture. Production imports none of this instrumentation.
import { StrictMode, useState } from 'react';
import { createRoot } from 'react-dom/client';
import CandleChart from '../src/components/CandleChart.jsx';
import IndicatorControls from '../src/components/IndicatorControls.jsx';
import { productionRegistry } from '../src/indicators/productionRegistry.js';
import { IndicatorSeriesAdapter } from '../src/indicators/IndicatorSeriesAdapter.js';
import { instanceConfig } from '../src/indicators/indicatorValidation.js';
import useReplayMarket from '../src/market/useReplayMarket.js';
import useReplayPlayback from '../src/market/useReplayPlayback.js';
import { PLAYBACK_SPEEDS } from '../src/market/PlaybackScheduler.js';
import useTrading from '../src/trading/useTrading.js';
import '../src/FigmaWorkspace.css';
import '../src/FxWorkspace.css';

const live = new Map(), observed = new WeakSet();
let context = null, currentChart = null, candleSeries = null, volumeSeries = null, full = 0, updates = 0, indicatorFull = 0;
const attach = IndicatorSeriesAdapter.prototype.attach, sync = IndicatorSeriesAdapter.prototype.sync;
IndicatorSeriesAdapter.prototype.attach = function(chart) {
  currentChart = chart;
  if (chart && !observed.has(chart)) {
    observed.add(chart);
    [candleSeries, volumeSeries] = chart.panes()[0].getSeries();
    const set = candleSeries.setData.bind(candleSeries), update = candleSeries.update.bind(candleSeries);
    candleSeries.setData = points => { set(points); full++; };
    candleSeries.update = point => { update(point); updates++; };
    const add = chart.addSeries.bind(chart), remove = chart.removeSeries.bind(chart);
    chart.addSeries = (definition, options, paneIndex) => {
      const series = add(definition, options, paneIndex);
      if (context) live.set(series, { id: context.config.id, type: context.config.type, key: context.spec.outputs[context.index++].key });
      return series;
    };
    chart.removeSeries = series => { remove(series); live.delete(series); };
  }
  attach.call(this, chart);
};
IndicatorSeriesAdapter.prototype.sync = function(config, spec, points) {
  context = { config, spec, index: 0 };
  try { sync.call(this, config, spec, points); indicatorFull++; } finally { context = null; }
};
function equalPoints(actual, expected, keys) { return actual.length === expected.length && actual.every((point, i) => keys.every(key => point[key] === expected[i][key])); }
function Player({ replay, speed, setSpeed, unsafe }) {
  const { playing, setPlaying } = useReplayPlayback(replay, speed);
  return <><select aria-label="Speed" value={speed} onChange={event => setSpeed(Number(event.target.value))}>{PLAYBACK_SPEEDS.map(value => <option key={value} value={value}>{value}×</option>)}</select>
    <button disabled={!replay.active || replay.atEnd} onClick={() => setPlaying(value => !value)}>Play / Pause</button>
    <button disabled={!replay.active || replay.atEnd} onClick={() => { setPlaying(false); replay.step(); }}>Next candle</button>
    <button disabled={!replay.active || unsafe} onClick={() => { setPlaying(false); replay.step(-1); }}>Previous candle</button>
    <button onClick={() => { setPlaying(false); replay.stop(); }}>Exit replay</button>
    <output id="playback-state">{JSON.stringify({ playing, speed, revision: replay.transition.revision, last: replay.candles.at(-1)?.time, atEnd: replay.atEnd, active: replay.active })}</output></>;
}
export default function Harness() {
  const [timeframe, setTimeframe] = useState('15m'), [instances, setInstances] = useState([]), [mounted, setMounted] = useState(true), [playerMounted, setPlayerMounted] = useState(true), [report, setReport] = useState('');
  const [speed, setSpeed] = useState(1), [mode, setMode] = useState('none'), [preferences, setPreferences] = useState({ showVolume: true, showCrosshair: true, showGrid: true }), [testVolume, setTestVolume] = useState(false);
  const replay = useReplayMarket(timeframe), trading = useTrading(replay.raw, replay.active, replay.transition);
  const data = testVolume ? replay.candles.map((bar, index) => ({ ...bar, volume: 10 + index % 50 })) : replay.candles;
  async function start(date) { const time = await replay.start(date); trading.reset(time); }
  function snapshot() {
    const matches = mounted && instances.every(value => {
      const config = instanceConfig(productionRegistry, value), spec = productionRegistry.get(config.type), expected = spec.calculate(data, config.parameters);
      return spec.outputs.every(output => {
        const series = [...live.entries()].find(([, record]) => record.id === config.id && record.key === output.key)?.[0];
        return series && equalPoints(series.data(), spec.output !== undefined ? expected : expected[output.key], ['time','value','color']);
      });
    });
    setReport(JSON.stringify({ count: data.length, first: data[0]?.time, last: data.at(-1)?.time, timeframe, mounted, full, updates, indicatorFull, indicatorReferenceEquality: matches,
      candleEquality: mounted && equalPoints(candleSeries.data(), data, ['time','open','high','low','close']),
      volumeEquality: mounted && equalPoints(volumeSeries.data(), data.map(bar => ({ time: bar.time, value: Number(bar.volume ?? 0), color: bar.close >= bar.open ? '#22c99a66' : '#f0647466' })), ['time','value','color']),
      visible: mounted ? currentChart.timeScale().getVisibleLogicalRange() : null,
      panes: mounted ? currentChart.panes().map(pane => ({ index: pane.paneIndex(), height: pane.getHeight(), series: pane.getSeries().length })) : [],
      account: trading.account, configs: instances,
      series: [...live.entries()].map(([series, record]) => ({ ...record, pane: series.getPane().paneIndex(), count: series.data().length, last: series.data().at(-1), references: series.priceLines().map(line => line.options()) })),
      drawingJSON: localStorage.getItem('backtest-drawing-manager-v1:main%3AXAUUSD'), riskRewardJSON: localStorage.getItem('backtest-drawings-v2:XAUUSD-replay-' + timeframe) }, null, 2));
  }
  return <><div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, padding: 8 }}>
    <IndicatorControls instances={instances} onChange={setInstances}/>
    <button onClick={() => start('2024-06-03T12:00:00Z')}>Start replay</button>
    <button onClick={() => start('2026-09-25T00:55:00Z')}>Start near end</button>
    {playerMounted && <Player replay={replay} speed={speed} setSpeed={setSpeed} unsafe={trading.account.positions.length + trading.account.orders.length + trading.account.trades.length > 0}/>}
    <button onClick={() => setPlayerMounted(value => !value)}>Playback mount toggle</button>
    <button onClick={() => setTimeframe(value => value === '15m' ? '1h' : '15m')}>Timeframe</button><button onClick={() => replay.loadOlder()}>Prepend history</button>
    <button onClick={() => setMounted(value => !value)}>Chart mount toggle</button><button onClick={() => setPreferences(value => ({ ...value, showVolume: !value.showVolume }))}>Toggle Volume</button>
    <button onClick={() => setTestVolume(value => !value)}>Fixture volume data</button><button onClick={snapshot}>Snapshot</button>
    <button onClick={() => trading.place({ id: 'browser-buy', side: 'Buy', type: 'Market', size: .1 })}>Simulator Buy</button><button onClick={() => trading.close('browser-buy')}>Simulator Close</button>
    {['none', 'trend-line', 'horizontal-line', 'vertical-line', 'rectangle', 'fibonacci-retracement', 'arrow', 'text', 'measure', 'long-position', 'short-position'].map(tool => <button key={tool} onClick={() => setMode(tool)}>{tool}</button>)}
  </div><div style={{ height: 550, position: 'relative' }}>{mounted && <CandleChart candles={data} transition={replay.transition}
    sessionId={'XAUUSD-replay-' + timeframe} viewportKey={timeframe} onLoadOlder={replay.loadOlder} indicatorRegistry={productionRegistry} indicatorInstances={instances}
    positions={trading.account.positions} orders={trading.account.orders} simulatedTrades={trading.account.trades}
    drawingMode={mode} onDrawingModeChange={setMode} chartPreferences={preferences} onChartPreferencesChange={setPreferences}
    onCreateOrder={() => setReport('Order ticket trigger received')}/>}</div><pre id="evidence" style={{ maxHeight: 250, overflow: 'auto' }}>{report}</pre></>;
}
const root = import.meta.hot?.data.root ?? createRoot(document.getElementById('root')); if (import.meta.hot) import.meta.hot.data.root = root;
root.render(<StrictMode><Harness/></StrictMode>);

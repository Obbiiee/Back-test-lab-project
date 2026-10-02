const TIMEFRAMES = [
  ["1m", "1m"], ["3m", "3m"], ["5m", "5m"], ["15m", "15m"],
  ["30m", "30m"], ["1h", "1h"], ["2h", "2h"], ["4h", "4h"],
  ["1d", "D"], ["1w", "W"], ["1M", "M"],
];

function TopBar({ symbol, timeframe, dataReady, onOpenData, onOpenSettings, onOpenIndicators, isPlaying, onTogglePlay, onTimeframeChange }) {
  return (
    <header className="platform-topbar">
      <button className="brand-button" type="button" onClick={onOpenData} aria-label="Backtest Lab, buka data">
        <span className="brand-mark">B</span><strong>Backtest Lab</strong>
      </button>
      <span className="topbar-separator" />
      <button className="topbar-symbol" type="button" onClick={onOpenData} title="Pilih dataset">{symbol || "Pilih simbol"}<span>⌄</span></button>
      <div className="topbar-timeframes" aria-label="Pilihan timeframe tampilan; dataset tidak diubah">
        {TIMEFRAMES.map(([value, label]) => <button key={value} type="button" className={timeframe === value ? "active" : ""} aria-pressed={timeframe === value} onClick={() => onTimeframeChange(value)}>{label}</button>)}
      </div>
      <button className="topbar-indicators" type="button" onClick={onOpenIndicators}>Indicators</button>
      <div className={`data-status ${dataReady ? "ready" : ""}`}><span />{dataReady ? "Data siap" : "Belum ada data"}</div>
      <div className="topbar-actions">
        <button type="button" onClick={onOpenData}>Data</button>
        <button type="button" className="topbar-replay" onClick={onTogglePlay} disabled={!dataReady}>{isPlaying ? "Ⅱ Pause" : "▶ Replay"}</button>
        <button type="button" onClick={onOpenSettings}>Settings</button>
      </div>
    </header>
  );
}

export default TopBar;

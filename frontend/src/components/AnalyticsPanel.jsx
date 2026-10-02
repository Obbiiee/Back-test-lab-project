import { useMemo, useState } from "react";

const money = (value) => new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 }).format(value ?? 0);
const percent = (value) => `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
const EMPTY_TRADES = [];

function dayKey(timestamp) {
  return new Date(timestamp * 1000).toISOString().slice(0, 10);
}

function downloadCsv(trades, symbol) {
  const columns = ["symbol", "side", "lots", "entry_time", "exit_time", "entry_price", "exit_price", "pnl", "r_multiple", "reason"];
  const rows = trades.map((trade) => [symbol, trade.side, trade.lots, new Date(trade.entry_time * 1000).toISOString(), new Date(trade.exit_time * 1000).toISOString(), trade.entry_price, trade.exit_price, trade.pnl, trade.r_multiple, trade.reason]);
  const csv = [columns, ...rows].map((row) => row.map((value) => `"${String(value ?? "").replaceAll('"', '""')}"`).join(",")).join("\n");
  const link = document.createElement("a");
  link.href = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  link.download = `${symbol || "backtest"}-trades.csv`;
  link.click();
  URL.revokeObjectURL(link.href);
}

function EquityChart({ points, label, tone = "#22c39a" }) {
  if (points.length < 2) return <div className="analytics-chart-empty">Tutup beberapa posisi untuk membentuk kurva performa.</div>;
  const values = points.map((point) => point.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const coords = values.map((value, index) => `${24 + (index / (values.length - 1)) * 752},${188 - ((value - min) / range) * 160}`).join(" ");
  const first = values[0];
  const last = values.at(-1);
  return <div className="analytics-equity-chart">
    <div className="analytics-chart-summary"><span>{label}</span><strong className={last >= first ? "positive" : "negative"}>{money(last - first)}</strong></div>
    <svg viewBox="0 0 800 220" preserveAspectRatio="none" role="img" aria-label={`${label} chart`}>
      {[28, 81, 134, 188].map((y) => <line key={y} x1="24" x2="776" y1={y} y2={y} className="analytics-gridline" />)}
      <polyline points={coords} fill="none" stroke={tone} strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={coords.split(" ").at(-1).split(",")[0]} cy={coords.split(" ").at(-1).split(",")[1]} r="4" fill={tone} />
    </svg>
    <div className="analytics-chart-labels"><span>{points[0].label}</span><span>{points.at(-1).label}</span></div>
  </div>;
}

function Metric({ label, value, note, tone = "" }) {
  return <article className="analytics-metric"><span>{label}</span><strong className={tone}>{value}</strong>{note && <small>{note}</small>}</article>;
}

function AnalyticsPanel({ replay, onClose }) {
  const [tab, setTab] = useState("performance");
  const trades = replay?.trades ?? EMPTY_TRADES;
  const initialBalance = replay?.config?.initial_balance ?? replay?.balance ?? 0;
  const symbol = replay?.symbol ?? "Backtest";
  const stats = useMemo(() => {
    const sorted = [...trades].sort((a, b) => a.exit_time - b.exit_time);
    const winners = sorted.filter((trade) => trade.pnl > 0);
    const losers = sorted.filter((trade) => trade.pnl < 0);
    const grossProfit = winners.reduce((sum, trade) => sum + trade.pnl, 0);
    const grossLoss = Math.abs(losers.reduce((sum, trade) => sum + trade.pnl, 0));
    let equity = initialBalance;
    let peak = equity;
    let maxDrawdown = 0;
    const curve = [{ value: equity, label: "Mulai" }];
    const daily = new Map();
    sorted.forEach((trade) => {
      equity += trade.pnl;
      peak = Math.max(peak, equity);
      maxDrawdown = Math.max(maxDrawdown, peak > 0 ? ((peak - equity) / peak) * 100 : 0);
      curve.push({ value: equity, label: new Date(trade.exit_time * 1000).toLocaleDateString("id-ID", { day: "2-digit", month: "short", timeZone: "UTC" }) });
      const key = dayKey(trade.exit_time);
      const row = daily.get(key) ?? { date: key, pnl: 0, count: 0, wins: 0 };
      row.pnl += trade.pnl;
      row.count += 1;
      if (trade.pnl > 0) row.wins += 1;
      daily.set(key, row);
    });
    const totalPnl = sorted.reduce((sum, trade) => sum + trade.pnl, 0);
    const durations = sorted.map((trade) => Math.max(0, trade.exit_time - trade.entry_time));
    const averageDuration = durations.length ? durations.reduce((sum, duration) => sum + duration, 0) / durations.length : 0;
    const average = (items, field) => items.length ? items.reduce((sum, trade) => sum + trade[field], 0) / items.length : 0;
    return {
      sorted, winners, losers, totalPnl, grossProfit, grossLoss,
      winRate: sorted.length ? (winners.length / sorted.length) * 100 : 0,
      expectancy: sorted.length ? totalPnl / sorted.length : 0,
      profitFactor: grossLoss ? grossProfit / grossLoss : null,
      averageR: average(sorted, "r_multiple"), averageWin: average(winners, "pnl"), averageLoss: average(losers, "pnl"),
      best: winners.length ? Math.max(...winners.map((trade) => trade.pnl)) : 0,
      worst: losers.length ? Math.min(...losers.map((trade) => trade.pnl)) : 0,
      averageDuration, maxDrawdown, curve, daily: [...daily.values()].sort((a, b) => b.date.localeCompare(a.date)),
    };
  }, [trades, initialBalance]);

  const bySide = ["BUY", "SELL"].map((side) => {
    const group = stats.sorted.filter((trade) => trade.side === side);
    return { side, count: group.length, wins: group.filter((trade) => trade.pnl > 0).length, pnl: group.reduce((sum, trade) => sum + trade.pnl, 0) };
  });
  const durationLabel = stats.averageDuration >= 86400
    ? `${(stats.averageDuration / 86400).toFixed(1)} hari`
    : `${(stats.averageDuration / 3600).toFixed(1)} jam`;

  return <div className="analytics-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <section className="analytics-workspace" role="dialog" aria-modal="true" aria-label="Analytics backtest">
      <header className="analytics-header">
        <div><span className="analytics-eyebrow">BACKTEST LAB · ANALYTICS</span><h2>Performa {symbol}</h2><p>Statistik dihitung dari posisi tertutup pada replay ini.</p></div>
        <div className="analytics-header-actions"><button type="button" onClick={() => downloadCsv(stats.sorted, symbol)} disabled={!stats.sorted.length}>Download CSV</button><button className="analytics-close" type="button" onClick={onClose} aria-label="Tutup analytics">×</button></div>
      </header>
      <nav className="analytics-tabs" aria-label="Kategori analytics">
        {[["performance", "Performance"], ["drawdown", "Drawdown"], ["simulation", "Simulation"]].map(([id, label]) => <button key={id} type="button" className={tab === id ? "active" : ""} onClick={() => setTab(id)}>{label}</button>)}
      </nav>
      {tab === "performance" && <div className="analytics-content">
        <div className="analytics-kpis">
          <Metric label="Total P&L" value={money(stats.totalPnl)} note={percent(initialBalance ? (stats.totalPnl / initialBalance) * 100 : 0)} tone={stats.totalPnl >= 0 ? "positive" : "negative"} />
          <Metric label="Account balance" value={money(replay?.balance ?? initialBalance)} note="Saldo terealisasi" />
          <Metric label="Win rate" value={`${stats.winRate.toFixed(1)}%`} note={`${stats.winners.length} menang · ${stats.losers.length} kalah`} />
          <Metric label="Total trades" value={String(stats.sorted.length)} note={`${stats.sorted.filter((trade) => trade.pnl === 0).length} impas`} />
        </div>
        <div className="analytics-main-grid">
          <section className="analytics-card analytics-chart-card"><h3>Profit and loss over time</h3><EquityChart points={stats.curve} label="Equity" /></section>
          <section className="analytics-card analytics-ratio-card"><h3>Risk & return</h3>
            <Metric label="Average RR" value={`${stats.averageR.toFixed(2)}R`} />
            <Metric label="Expectancy / trade" value={money(stats.expectancy)} tone={stats.expectancy >= 0 ? "positive" : "negative"} />
            <Metric label="Profit factor" value={stats.profitFactor == null ? "—" : stats.profitFactor.toFixed(2)} />
            <Metric label="Max drawdown" value={percent(-stats.maxDrawdown)} tone="negative" />
          </section>
        </div>
        <div className="analytics-main-grid analytics-lower-grid">
          <section className="analytics-card"><h3>Winners and losers</h3>
            <div className="analytics-wl-grid"><div><span>Winners</span><strong className="positive">{stats.winners.length}</strong><small>Best {money(stats.best)}</small><small>Avg win {money(stats.averageWin)}</small></div><div><span>Losers</span><strong className="negative">{stats.losers.length}</strong><small>Worst {money(stats.worst)}</small><small>Avg loss {money(stats.averageLoss)}</small></div></div>
            <div className="analytics-footnote">Rata-rata durasi posisi: {durationLabel}</div>
          </section>
          <section className="analytics-card"><h3>Performance by side</h3>
            {bySide.map((item) => <div className="analytics-breakdown" key={item.side}><span className={item.side === "BUY" ? "positive" : "negative"}>{item.side}</span><span>{item.count} trade · {item.count ? `${(item.wins / item.count * 100).toFixed(0)}% win` : "belum ada trade"}</span><strong className={item.pnl >= 0 ? "positive" : "negative"}>{money(item.pnl)}</strong></div>)}
          </section>
        </div>
        <section className="analytics-card analytics-calendar"><h3>Daily performance</h3>
          {stats.daily.length ? <div className="analytics-daily-list">{stats.daily.map((day) => <div className="analytics-breakdown" key={day.date}><span>{new Date(`${day.date}T00:00:00Z`).toLocaleDateString("id-ID", { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" })}</span><span>{day.count} trade · {day.wins} menang</span><strong className={day.pnl >= 0 ? "positive" : "negative"}>{money(day.pnl)}</strong></div>)}</div> : <div className="analytics-chart-empty">Belum ada posisi tertutup.</div>}
        </section>
      </div>}
      {tab === "drawdown" && <div className="analytics-content"><div className="analytics-kpis analytics-kpis-three"><Metric label="Max drawdown" value={percent(-stats.maxDrawdown)} tone="negative" /><Metric label="Current drawdown" value={percent(replay?.balance < Math.max(initialBalance, ...stats.curve.map((point) => point.value)) ? -((Math.max(initialBalance, ...stats.curve.map((point) => point.value)) - (replay?.balance ?? initialBalance)) / Math.max(initialBalance, ...stats.curve.map((point) => point.value))) * 100 : 0)} tone="negative" /><Metric label="Balance now" value={money(replay?.balance ?? initialBalance)} /></div>
        <section className="analytics-card analytics-chart-card"><h3>Equity curve</h3><EquityChart points={stats.curve} label="Account equity" /></section><p className="analytics-method-note">Drawdown dihitung dari saldo awal dan P&L trade yang sudah terealisasi. Floating P&L belum dimasukkan.</p></div>}
      {tab === "simulation" && <div className="analytics-content"><div className="analytics-sim-intro"><span>RR SIMULATOR</span><h3>Uji target RR pada trade historis</h3><p>Simulasi sederhana ini memakai hasil R aktual setiap trade dan mengubahnya menjadi menang/kalah sesuai target. Ini bukan prediksi hasil masa depan.</p></div>
        <div className="analytics-simulation-grid">{[1, 1.5, 2, 3].map((target) => {
          const resultR = stats.sorted.reduce((sum, trade) => sum + (trade.r_multiple > 0 ? Math.min(trade.r_multiple, target) : trade.r_multiple), 0);
          const profit = stats.sorted.reduce((sum, trade) => sum + (trade.r_multiple > 0 ? Math.min(trade.r_multiple, target) : trade.r_multiple) * trade.risk_amount, 0);
          return <article className="analytics-sim-card" key={target}><span>Target {target}:1</span><strong className={profit >= 0 ? "positive" : "negative"}>{money(profit)}</strong><small>{resultR.toFixed(2)}R dari {stats.sorted.length} trade</small></article>;
        })}</div>
        {!stats.sorted.length && <div className="analytics-chart-empty">Tutup posisi untuk menjalankan simulasi.</div>}
      </div>}
    </section>
  </div>;
}

export default AnalyticsPanel;

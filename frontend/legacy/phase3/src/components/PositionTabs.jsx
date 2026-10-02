import { useState } from "react";

const money = (value) => new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 2,
}).format(value ?? 0);

function PositionTabs({ position, pendingOrder, trades = [], symbol, onClose, onCancel, busy, activeTab: controlledTab, onTabChange }) {
  const [localTab, setLocalTab] = useState("open");
  const activeTab = controlledTab ?? localTab;
  const setActiveTab = onTabChange ?? setLocalTab;
  const tabs = [
    ["open", "Open Positions", position ? 1 : 0],
    ["pending", "Pending Orders", pendingOrder ? 1 : 0],
    ["closed", "Closed Positions", trades.length],
  ];

  return <section className="positions-panel" aria-label="Positions and orders">
    <div className="position-tabs" role="tablist" aria-label="Daftar posisi">
      {tabs.map(([id, label, count]) => <button key={id} type="button" role="tab" aria-selected={activeTab === id} className={activeTab === id ? "active" : ""} onClick={() => setActiveTab(id)}>
        {label}<span>{count}</span>
      </button>)}
    </div>

    <div className="table-scroll">
      {activeTab === "open" && <table>
        <thead><tr><th>Asset</th><th>Side</th><th>Size</th><th>Entry</th><th>Take Profit</th><th>Stop Loss</th><th>Risk</th><th>Action</th></tr></thead>
        {position && <tbody><tr>
          <td>{symbol}</td><td className={position.side.toLowerCase()}>{position.side}</td><td>{position.lots.toFixed(3)}</td>
          <td>{position.entry_price.toFixed(3)}</td><td>{position.take_profit?.toFixed(3) ?? "—"}</td><td>{position.stop_loss.toFixed(3)}</td>
          <td>{money(position.risk_amount)}</td><td><button type="button" className="row-action danger" onClick={onClose} disabled={busy}>Close</button></td>
        </tr></tbody>}
      </table>}

      {activeTab === "pending" && <table>
        <thead><tr><th>Asset</th><th>Order Type</th><th>Entry</th><th>Stop Loss</th><th>Take Profit</th><th>Risk</th><th>Action</th></tr></thead>
        {pendingOrder && <tbody><tr>
          <td>{symbol}</td><td>{pendingOrder.order_type.replaceAll("_", " ")}</td><td>{pendingOrder.entry_price.toFixed(3)}</td>
          <td>{pendingOrder.stop_distance}</td><td>{pendingOrder.take_profit_distance ?? "—"}</td><td>{pendingOrder.risk_percent}%</td>
          <td><button type="button" className="row-action danger" onClick={onCancel} disabled={busy}>Cancel</button></td>
        </tr></tbody>}
      </table>}

      {activeTab === "closed" && <table>
        <thead><tr><th>#</th><th>Asset</th><th>Side</th><th>Size</th><th>Entry</th><th>Exit</th><th>Result</th><th>R</th><th>Reason</th></tr></thead>
        <tbody>{trades.map((trade, index) => <tr key={`${trade.entry_time}-${index}`}>
          <td>{index + 1}</td><td>{symbol}</td><td className={trade.side.toLowerCase()}>{trade.side}</td><td>{trade.lots.toFixed(3)}</td>
          <td>{trade.entry_price.toFixed(3)}</td><td>{trade.exit_price.toFixed(3)}</td><td className={trade.pnl >= 0 ? "positive" : "negative"}>{money(trade.pnl)}</td>
          <td>{trade.r_multiple.toFixed(2)}R</td><td>{trade.reason}</td>
        </tr>)}</tbody>
      </table>}
      {((activeTab === "open" && !position) || (activeTab === "pending" && !pendingOrder) || (activeTab === "closed" && !trades.length)) && <p className="positions-empty">No data available</p>}
    </div>
  </section>;
}

export default PositionTabs;

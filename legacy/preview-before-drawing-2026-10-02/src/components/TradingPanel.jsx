import { useState } from "react";

const money = (value) => new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 2,
}).format(value ?? 0);

const price = (value) => value == null
  ? "—"
  : new Intl.NumberFormat("en-US", { maximumFractionDigits: 5 }).format(value);

const ORDER_TYPES = ["MARKET", "BUY_LIMIT", "SELL_LIMIT", "BUY_STOP", "SELL_STOP"];

function TradingPanel({ enabled, position, pendingOrder, balance, currentPrice, entryPrice, onEntryPriceChange, onOrder, onClose, onCancel, busy }) {
  const [orderType, setOrderType] = useState("MARKET");
  const [stopDistance, setStopDistance] = useState("5");
  const [targetDistance, setTargetDistance] = useState("5");
  const [lockOneToOne, setLockOneToOne] = useState(true);
  const [riskPercent, setRiskPercent] = useState("1");

  const effectiveTargetDistance = lockOneToOne ? stopDistance : targetDistance;
  const rr = Number(stopDistance) > 0 && Number(effectiveTargetDistance) > 0
    ? Number(effectiveTargetDistance) / Number(stopDistance)
    : null;

  function orderPayload(sideOrType) {
    const payload = {
      stop_distance: Number(stopDistance),
      take_profit_distance: effectiveTargetDistance === "" ? null : Number(effectiveTargetDistance),
      risk_percent: Number(riskPercent),
    };
    if (sideOrType === "MARKET") return payload;
    return { ...payload, order_type: sideOrType, entry_price: Number(entryPrice) };
  }

  function submitMarket(side) {
    onOrder({ ...orderPayload("MARKET"), side });
  }

  return (
    <section className="trade-ticket" aria-label="Trading">
      <div className="ticket-heading">
        <div><p className="eyebrow">ORDER & POSISI</p><h3>Trading</h3></div>
        <span className={`position-badge ${position ? position.side.toLowerCase() : pendingOrder ? "pending" : "flat"}`}>
          {position ? `${position.side} terbuka` : pendingOrder ? "Pending aktif" : "Tanpa posisi"}
        </span>
      </div>

      <div className="balance-line"><span>Saldo realized</span><strong>{money(balance)}</strong></div>

      {position ? (
        <div className="open-position">
          <div className="position-grid">
            <span>Ukuran</span><strong>{position.lots.toFixed(3)} lot</strong>
            <span>Entry</span><strong>{price(position.entry_price)}</strong>
            <span>Stop loss</span><strong>{price(position.stop_loss)}</strong>
            <span>Take profit</span><strong>{price(position.take_profit)}</strong>
            <span>Risiko rencana</span><strong>{money(position.risk_amount)}</strong>
          </div>
          <button className="close-position" type="button" onClick={onClose} disabled={busy}>
            {busy ? "Memproses…" : "Tutup posisi sekarang"}
          </button>
        </div>
      ) : pendingOrder ? (
        <div className="open-position">
          <div className="position-grid">
            <span>Tipe order</span><strong>{pendingOrder.order_type.replace("_", " ")}</strong>
            <span>Harga pemicu</span><strong>{price(pendingOrder.entry_price)}</strong>
            <span>Stop loss</span><strong>{price(pendingOrder.stop_distance)} jarak</strong>
            <span>Take profit</span><strong>{price(pendingOrder.take_profit_distance)} jarak</strong>
            <span>Risiko</span><strong>{pendingOrder.risk_percent}%</strong>
          </div>
          <button className="close-position" type="button" onClick={onCancel} disabled={busy}>
            {busy ? "Memproses…" : "Batalkan pending order"}
          </button>
        </div>
      ) : (
        <>
          <div className="ticket-fields">
            <label>Tipe order
              <select value={orderType} onChange={(event) => setOrderType(event.target.value)} disabled={!enabled || busy}>
                {ORDER_TYPES.map((type) => <option key={type} value={type}>{type.replace("_", " ")}</option>)}
              </select>
            </label>
            {orderType !== "MARKET" && (
              <label>Harga pemicu / limit{entryPrice != null && entryPrice !== "" && <span className="selected-price-note">Bisa diedit</span>}
                <input type="number" min="0.00001" step="any" value={entryPrice ?? ""} onChange={(event) => onEntryPriceChange(event.target.value)} placeholder={currentPrice ? `Harga kini ${price(currentPrice)}` : "Masukkan harga"} disabled={!enabled || busy} />
              </label>
            )}
            <label>Jarak stop loss
              <input type="number" min="0.00001" step="any" value={stopDistance} onChange={(event) => {
                setStopDistance(event.target.value);
                if (lockOneToOne) setTargetDistance(event.target.value);
              }} disabled={!enabled || busy} />
            </label>
            <label>Jarak take profit
              <input type="number" min="0.00001" step="any" value={effectiveTargetDistance} onChange={(event) => setTargetDistance(event.target.value)} placeholder="Opsional" disabled={!enabled || busy || lockOneToOne} />
            </label>
            <label>Risiko per trade (%)
              <input type="number" min="0.001" max="100" step="any" value={riskPercent} onChange={(event) => setRiskPercent(event.target.value)} disabled={!enabled || busy} />
            </label>
          </div>
          <div className="ticket-risk-options">
            <label className="rr-lock-option"><input type="checkbox" checked={lockOneToOne} onChange={(event) => {
              const checked = event.target.checked;
              setLockOneToOne(checked);
              if (checked) setTargetDistance(stopDistance);
            }} disabled={!enabled || busy} /> Kunci RR 1:1</label>
            <span className="ticket-rr-preview">Risk / Reward <strong>{rr == null ? "—" : `1 : ${rr.toFixed(2)}`}</strong></span>
          </div>
          {orderType === "MARKET" ? (
            <div className="order-buttons">
              <button className="buy-button" type="button" onClick={() => submitMarket("BUY")} disabled={!enabled || busy}>BUY MARKET</button>
              <button className="sell-button" type="button" onClick={() => submitMarket("SELL")} disabled={!enabled || busy}>SELL MARKET</button>
            </div>
          ) : (
            <button className="pending-submit" type="button" onClick={() => onOrder(orderPayload(orderType))} disabled={!enabled || busy}>
              {busy ? "Memproses…" : `Pasang ${orderType.replace("_", " ")}`}
            </button>
          )}
          <p className="ticket-help">Ukuran posisi dihitung dari risiko dan jarak SL. Pending order hanya aktif setelah candle berikutnya menyentuh harga pemicu.</p>
        </>
      )}
    </section>
  );
}

export default TradingPanel;

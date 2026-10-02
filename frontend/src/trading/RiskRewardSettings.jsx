import { positionStats } from "./riskReward";

export default function RiskRewardSettings({ drawingSettings, setDrawingSettings, candles }) {
  return <>
        <>
<label>Risk mode<select value={drawingSettings.riskMode || "percent"} onChange={e=>setDrawingSettings(v=>({...v,riskMode:e.target.value}))}><option value="percent">% of account</option><option value="cash">Amount (USD)</option></select></label>
<label>Account size (USD)<input type="number" step="any" min="0.000001"  value={drawingSettings.accountSize ?? 100000} onChange={e=>setDrawingSettings(v=>({...v,accountSize:Number(e.target.value)}))} /></label>
<label>Risk<input type="number" step="any" min="0.000001"  value={drawingSettings.riskValue ?? 1} onChange={e=>setDrawingSettings(v=>({...v,riskValue:Number(e.target.value)}))} /></label>
<label>Lot size (units per lot)<input type="number" step="any" min="0.000001"  value={drawingSettings.lotSize ?? 1} onChange={e=>setDrawingSettings(v=>({...v,lotSize:Number(e.target.value)}))} /></label>
<label>Point value<input type="number" step="any" min="0.000001"  value={drawingSettings.pointValue ?? 1} onChange={e=>setDrawingSettings(v=>({...v,pointValue:Number(e.target.value)}))} /></label>
<label>Leverage<input type="number" step="any" min="0.000001"  value={drawingSettings.leverage ?? 1} onChange={e=>setDrawingSettings(v=>({...v,leverage:Number(e.target.value)}))} /></label>
<label>Tick size<input type="number" step="any" min="0.000001"  value={drawingSettings.tickSize ?? 0.01} onChange={e=>setDrawingSettings(v=>({...v,tickSize:Number(e.target.value)}))} /></label>
<label>Quantity precision<input type="number" step="any" min="0" max="8" value={drawingSettings.quantityPrecision ?? 3} onChange={e=>setDrawingSettings(v=>({...v,quantityPrecision:Number(e.target.value)}))} /></label>
          <label>Entry<input type="number" step="any" value={drawingSettings.points[0].price} onChange={(event) => setDrawingSettings((value) => ({ ...value, points: value.points.map((point, index) => index === 0 ? { ...point, price: Number(event.target.value) } : point) }))} /></label>
          <label>Stop Loss<input type="number" step="any" value={drawingSettings.points[1].price} onChange={(event) => setDrawingSettings((value) => ({ ...value, points: value.points.map((point, index) => index === 1 ? { ...point, price: Number(event.target.value) } : point) }))} /></label>
          <label>Take Profit<input type="number" step="any" value={drawingSettings.points[2].price} onChange={(event) => setDrawingSettings((value) => ({ ...value, points: value.points.map((point, index) => index === 2 ? { ...point, price: Number(event.target.value) } : point) }))} /></label>
        </>
        <>
          <label>Risk/Reward Ratio<input type="number" min="0.01" step="any" value={positionStats(drawingSettings,candles.at(-1)?.close).ratio || ''} onChange={e=>setDrawingSettings(v=>({...v,points:v.points.map((p,i)=>i===2?{...p,price:v.points[0].price+(v.points[0].price-v.points[1].price)*Number(e.target.value)}:p)}))} /></label>
          <label><input type="checkbox" checked={drawingSettings.alwaysShowStats !== false} onChange={e=>setDrawingSettings(v=>({...v,alwaysShowStats:e.target.checked}))} />Always show statistics</label>
          <output>Qty: {positionStats(drawingSettings,candles.at(-1)?.close).quantity} · Risk/Reward Ratio: {positionStats(drawingSettings,candles.at(-1)?.close).ratio.toFixed(2)}</output>
          {!positionStats(drawingSettings,candles.at(-1)?.close).valid && <p role="alert">Check entry, stop and target direction; account and sizing values must be positive.</p>}
        </>
  </>;
}

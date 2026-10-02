# FX Replay reference workflow

Reference reviewed in the user's open FX Replay session on October 2, 2026. The page uses a docked order ticket and journal, a drawing rail with separate primary/expander buttons, a floating favorites bar, positions above bottom replay controls, and Market / Limit / Stop tickets with risk sizing, SL, TP and partial exits.

The local workspace now follows that arrangement. The original chart and ten-year HistData bundle remain. This implementation uses Lightweight Charts and custom SVG drawings; it is not the proprietary FX Replay chart or TradingView Advanced Charts bundle. Native chart-library access has been requested from the user. Full pixel and behavioral parity has not been certified.

## Working local flow

- Expand a drawing category using its arrow; the main icon selects the last tool used in that category. Star tools to put them on the favorites bar. Favorites and drawings persist in browser storage.
- Select a drawing for color, settings, clone, lock and delete. Long/Short Position exposes Create order and transfers entry, SL, TP and calculated size to the ticket. The ticket chooses Limit or Stop based on the plan's entry relative to market.
- Buy, Sell or Order opens the docked ticket. Market entry follows current price; Limit and Stop have editable entries, including chart selection. SL and TP are optional and can also be selected from the chart.
- With a stop enabled, the risk buttons size the order from initial or current balance. Lot quantities are rounded down to four decimals. One XAUUSD lot is 100 ounces. Units display ounces.
- Place order creates a local simulated position or pending order. Open positions show current P&L. Pending orders can be cancelled; positions can be closed completely or by 50%. Entry/SL/TP levels appear on chart; pending entry and exit levels can be dragged, and the level's cross removes an exit or closes/cancels its order.
- Partial take-profit targets specify prices and percentages of original size. They must sit between entry and final TP and total less than 100%. The remaining position closes at final TP.
- Closed trades appear in the journal and calendar. Trade notes, tags and strategy persist with the local account.
- Bar replay starts at a real historical date, resets the simulated account to $100,000, hides future prices, and advances using real M1 candles. Playback speed, step, timeframe and exit replay work. More monthly data loads as replay advances. Older history loads when panning left; daily/weekly/monthly charts include prior archive history. The replay time and account restore after reload. Rewinding is disabled after trading activity to prevent changing recorded outcomes.

## Execution assumptions

No real broker orders are sent. Commission is zero. Market fills use the visible close. Pending fills handle opening gaps; stop exits can fill at a worse opening price. Candle data cannot establish the ordering of multiple intrabar touches: an existing position hitting SL and TP within the same M1 candle takes SL first. A pending entry candle evaluates exits against its close because pre-entry high/low order is unknown. Sampled live prices evaluate the new observed price instead of cumulative earlier OHLC.

The reviewed reference also includes features not implemented here: provider news, watchlists for other symbols, paid auto-breakeven, native TradingView drawing settings and chart internals, cloud layouts and a full analytics dashboard. These should not be presented as completed or native parity.

## Validation

Market data tests inspect all decade chunks and all eleven timeframes. Trading tests cover order validation, buy/sell P&L, Market/Limit/Stop activation, gap fills, SL/TP, multiple partial targets, conservative ambiguous candles, sampled live ticks, and duplicate-candle protection. Drawing tests validate finite geometry for 88 non-position tools including collapsed anchors. Browser checks exercise replay, risk sizing, placement, P&L after advancing, manual closure, journal, pending cancellation, and Long Position to order-ticket transfer.

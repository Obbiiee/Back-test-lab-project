# XAU/USD feed and risk/reward update

## Source research

Gold API was selected for live XAU/USD indicative USD prices without an API key. Its documentation requests 30-second caching; this application polls every 30 seconds with timeout, cleanup and retry. Requests work directly from the browser using the provider's documented CORS support.

- https://gold-api.com/docs
- https://gold-api.com/llms.txt

Historical /history and /ohlc require a provider API key. Intraday history grouping requires premium access according to the documentation. This integration does not claim full broker OHLC history or tick-level real time.

Alternatives evaluated:
- Standard Bullion: free quotes and sampled price history, but historical points are closes at limited resolutions rather than complete OHLC candles. https://standardbullion.com/gold-price-api
- Twelve Data: Basic has 8 API credits/minute, 800/day and trial WebSocket credits; commodities are listed under Grow, so unrestricted free XAU/USD access is not assumed. https://twelvedata.com/pricing

## Candle behavior

Live candles derive solely from received Gold API quotes, with provider timestamps. One-minute sampled OHLC is stored locally; all timeframes aggregate those same bars. No synthetic historical candles, missing-period fillers or invented trading volume are added. OHLC extrema may miss moves between polls. Collection runs while the workspace is open, and cached candles survive refresh. UTC daily boundaries, Monday weekly boundaries and actual calendar months are used. Spot broker charts may use different session boundaries and quotes.

Demo mode is explicitly separate from live mode; it now also aggregates a common one-minute simulation rather than relabeling identical candles. Replay controls are disabled for the live feed. Drawings have separate storage keys per symbol/mode/timeframe.

## Risk/reward

Long/Short Position implements draggable entry, stop, target and duration; colored profit/loss zones; target/stop offsets, percentages, ticks, estimated closing balance, quantity, marked-to-market P&L and ratio. Defaults start at 1:1. Account balance, cash/percentage risk, lot units, point value, leverage, tick size, quantity precision and ratio are editable. Invalid stop/target directions cannot be saved. Changing ratio moves the target; dragging SL/TP recalculates statistics. Quantity is rounded down and capped by leverage using TradingView's published formulas.

Reference: https://www.tradingview.com/support/solutions/43000475660-how-to-use-long-and-short-position-drawing-tools/

This is a custom drawing implementation on Lightweight Charts, not TradingView's licensed native tool. Marked-to-market P&L is informational, not a simulated historical trade result; it does not track entry/exit events, fees, spreads or execution. Broker contract specifications must be entered to use broker lot sizing (default lot size 1 represents one unit).

## Verification

Production build and lint pass. Drawing geometry regression suite passes. Market tests cover sampled OHLC, weekly/monthly boundaries, quote validation, and long/short sizing and P&L. Browser verified successful live feed, updated prices, RR 1:3 settings and SL dragging changing RR from 3.00 to 1.97, then undo restoring 3.00.

Browser additionally verified short RR 1:2 and persistence after refresh, live 5m OHLC aggregation, and the initially empty feed rendering safely after fixing its footer timestamp access.

Update: historical M1 bid candles from HistData.com are now available before the sampled live feed. See HISTORICAL_XAU.md for coverage, UTC conversion, source boundary and archive refresh instructions.

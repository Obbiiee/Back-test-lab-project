# XAU/USD chart data

The chart bundles 3,486,461 real M1 bid candles from HistData.com, covering 2016-10-02 23:01 UTC through 2026-09-25 00:58 UTC (120 calendar months). The requested archive window starts October 2016. The first available candle follows the weekend; the latest published monthly archive is partial.

Data lives in frontend/public/market/decade. The manifest records coverage, original archive SHA-256 checksums, source and download time. Intraday files are split by UTC month and timeframe, fetched progressively when the chart is panned left. Daily, weekly and monthly files contain the full window. This avoids downloading millions of candles at startup. Weekly and monthly aggregation spans file boundaries correctly. The prior one-month snapshot remains a fallback.

HistData uses fixed EST (UTC-5), without daylight-saving changes. Downloaded M1 timestamps are converted to UTC, deduplicated and sorted. All 11 display timeframes use the same underlying prices. OHLC bounds and ascending timestamps are validated.

Sampled Gold API quotes continue separately. Historical and sampled prices are aggregated independently; the first sampled timeframe bucket uses only sampled prices. No price shifts, interpolation or invented candles fill missing periods. There is no usable volume from these sources. The chart has no historical/live source labels, boundary markers or history status strip; provenance remains in the data manifest.

Run npm run history:decade from frontend to rebuild the archive using the provider's normal public download form. The current script targets October 2016 through September 2026. Original ZIP downloads are cached in .history-downloads. Publication of the manifest happens after all timeframe files are written. Archives do not refresh automatically.

References:
- https://www.histdata.com/
- https://www.histdata.com/f-a-q/data-files-detailed-specification/

Validation: production build, lint, market and drawing tests. Market tests inspect every published chunk across all 11 timeframes for count, OHLC validity, coverage and non-overlapping timestamps.

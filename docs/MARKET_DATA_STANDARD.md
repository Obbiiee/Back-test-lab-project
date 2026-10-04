# Backtest Lab — Market Data Standard

Status: architecture authority for future market-data work. This document does not authorize implementation.

## Principles
Market data is evidence. Never silently repair, blend, reorder, fabricate, or upgrade its precision. Feed identity, dataset version and provenance remain visible through the research chain. All internal timestamps are UTC; source timezone/provenance is retained.

## Compatibility levels
### L1 — Chart Compatible
Required: timestamp, open, high, low, close; finite numeric OHLC; high >= max(open, close); low <= min(open, close); high >= low; ascending timestamps; no duplicate canonical timestamps; known timeframe/timezone. Volume is optional. L1 is not Precision execution data.

### L2 — Replay Compatible
L1 plus source/provider, timeframe, timezone, price precision, tick size, trading-hours/session metadata, coverage start/end and quality checks for gaps, duplicates, abnormal prices and continuity. L2 supports candle replay. It does not establish same-candle event chronology.

### L3 — Precision Compatible
Preferred minimum event: timestamp, bid, ask. Millisecond timestamps are preferred; preserve microseconds if supplied. Optional: last, bid_size, ask_size, volume, flags, sequence. L3 must preserve chronological ordering and historical spread. If equal timestamps lack a trustworthy sequence, mark ordering quality as unverifiable rather than guessing.

## Canonical tick
```text
timestamp_utc
instrument_id
feed_id
bid
ask
last?
bid_size?
ask_size?
volume?
sequence?
flags?
dataset_version
```

## Instrument descriptor
```text
instrument_id, provider, provider_symbol, asset_class,
base_asset, quote_asset, price_precision, tick_size,
contract_size, min_lot, max_lot, lot_step, currency,
timezone, trading_hours
```
Leverage, margin, swap and commission are execution-profile concerns unless they are immutable instrument facts.

## Dataset Passport
Every research-capable dataset should expose: Dataset ID, Provider, Instrument, Source, Start/End, Resolution, Tick/BidAsk/OHLC classification, Imported/Acquired At, Dataset Version, License Class, Quality Score/Grade and checksum/content identity. Never overwrite an experiment's dataset version.

## Quality engine
Measure coverage, event count, timestamp integrity, chronology confidence, duplicates, missing periods, bid/ask coverage and invalid quotes. Hard-invalid examples include NaN/negative prices, invalid timestamps, corrupted records, impossible OHLC, unknown instrument and unexplained ask < bid. Gaps, wide spreads and outliers are warnings unless proven corrupt; genuine market stress must not be cleaned away.

## Feed identity and symbol normalization
Provider symbols such as XAUUSD, GOLD or broker suffixes may map to a canonical instrument, but provider/feed identities remain distinct. Never silently mix feeds. Any composite feed must be explicitly named and preserve segment provenance.

## Research disclosure
Results should be able to state Instrument, Feed, Dataset Version, Data Quality, execution resolution, Execution Profile, Engine Version and Strategy/Protocol Version.

## Rights gate
Technical accessibility is not redistribution permission. Production ingestion/display/storage/redistribution must honor the provider's commercial, retention and derived-data rights.

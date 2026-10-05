# Backtest Lab — Market Data Standard

Status: architecture authority for future market-data work. This document does not authorize implementation.

## Principles
Market data is evidence. Never silently repair, blend, reorder, fabricate, or upgrade its precision. Feed identity, dataset version and provenance remain visible through the research chain. All internal timestamps are UTC; source timezone/provenance is retained.

## Tick-native execution decision — target invariant

Human-approved target: **NO TRADE MAY BE SETTLED FROM OHLC DATA ALONE.** Canonical ordered Bid/Ask events must own future entry, triggers, exits, settlement and execution-derived statistics. Candles are derived visualization/indicator/research inputs, not execution authority. If evidence is inadequate, return UNRESOLVED/AMBIGUOUS without fill/PnL; no silent candle fallback, guessed intrabar paths or random/optimistic/pessimistic historical ordering.

This is the migration target, not a claim that current runtime enforces it. Existing candle modelling and stored results remain unchanged compatibility artifacts until separately authorized migration and acceptance. They must never be relabelled as tick-native results. The authorized audit, candidate Exness evidence and migration acceptance belong to [existing system blueprint Section 42.14](PRODUCT_SYSTEM_ARCHITECTURE_BLUEPRINT.md#4214-tick-native-decision-exness-candidate-and-migration-audit). No settlement implementation is authorized by this decision record.

## Compatibility levels
### L1 — Chart Compatible
Required: timestamp, open, high, low, close; finite numeric OHLC; high >= max(open, close); low <= min(open, close); high >= low; ascending timestamps; no duplicate canonical timestamps; known timeframe/timezone. Volume is optional. L1 is not Precision execution data.

### L2 — Replay Compatible
L1 plus source/provider, timeframe, timezone, price precision, tick size, trading-hours/session metadata, coverage start/end and quality checks for gaps, duplicates, abnormal prices and continuity. L2 supports candle replay. It does not establish same-candle event chronology.

### L3 — Precision Compatible
Preferred minimum event: timestamp, bid, ask. Millisecond timestamps are preferred; preserve microseconds if supplied. Optional: last, bid_size, ask_size, volume, flags, sequence. L3 must preserve chronological ordering and historical spread. If equal timestamps lack a trustworthy sequence, mark ordering quality as unverifiable rather than guessing.

## Canonical tick

The fields below are the policy-level vocabulary. [Existing blueprint Section 42.15](PRODUCT_SYSTEM_ARCHITECTURE_BLUEPRINT.md#4215-frozen-canonical-tick-provider-and-timeline-contract--v1) is the single owner of frozen V1 wire fields, identity, provider and timeline semantics; do not implement this older sketch as a competing schema. Runtime implementation remains separately authorized.
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

## Phase 23 research specification — no runtime authorization

This existing document owns canonical requirements and fidelity; [system blueprint Section 42](PRODUCT_SYSTEM_ARCHITECTURE_BLUEPRINT.md#425-phase-23-authorized-research--provider-comparison) owns provider evidence, licensing, costs and the decision handoff. Research does not change the current simulator or certify its intrabar outcomes.

### Target and fidelity classification

Primary target: spot/broker XAUUSD Gold, at least ten years where demonstrably available, with exact first/last event and interval coverage. Minimum desired raw quote: `timestamp | bid | ask`; preserve source sizes, flags, contributor and sequence when supplied. Millisecond or better is desired, never invented. Gold futures have separate instrument/contract/expiry identities and cannot substitute silently for spot gold.

| Fidelity | Evidence | Permitted claim |
| --- | --- | --- |
| 1 ORDERED_TICK_BID_ASK | Observed quotes, reliable chronology and both sides | Observed feed path and spread; conditional reconstruction of quote-side crossings, not proof of broker fills |
| 2 ORDERED_TICK_SINGLE_PRICE | Ordered bid/last/mid explicitly identified | One-side path only; missing side/spread cannot be reconstructed as historical fact |
| 3 M1_BID_ASK_OHLC | Separate side candles | Side-specific ranges; simultaneous quotes, spread extremes and intrabar ordering remain unknown |
| 4 M1_OHLC | Known side OHLC | Candle replay/research with intrabar ambiguity; this is the current stored history |
| 5 HIGHER_TIMEFRAME_OHLC | Coarser ranges | Analysis with lower temporal fidelity |

These five fidelity labels refine the existing L1/L2/L3 compatibility levels; they do not replace them. L1/L2 concern compatibility, whereas fidelity concerns evidence actually present. A nominal tick product with gaps, sampling, timestamp ties or missing sides cannot automatically receive fidelity 1.

### No false intrabar certainty

For entry 2645, TP 2650 and SL 2640, OHLC 2645/2651/2639/2647 alone cannot prove which threshold was reached first. Future outcomes must retain `AMBIGUOUS_INTRABAR_PATH` (or an explicitly mapped existing equivalent). Do not silently choose TP-first/SL-first or interpolate O→H→L→C as historical truth. Historical compatibility policies may produce `MODELLED / ASSUMED`, separately from `OBSERVED HISTORICAL SEQUENCE` and `UNKNOWN / AMBIGUOUS`. They are not permitted as a fallback for the future tick-native execution target above. Explicit future tick-based fill assumptions remain separate from proof of broker execution.

An observed path is feed-specific: missing quotes, unresolved equal-time events, stale sides, unknown order activation time or a gap spanning both thresholds can still leave ambiguity. Crossing between discrete quotes is not an observed intermediate price; do not interpolate a fill. Preserve original event order, source ordinal and chronology confidence. Distinct records at the same timestamp are not automatic duplicates. Source ordinal preserves supplied order but does not manufacture a trustworthy venue sequence.

Future execution profile must explicitly define long buy entry at ask, long liquidation at bid, short sell entry at bid, short liquidation at ask; buy-limit/stop and sell-limit/stop trigger sides and activation/latency rules follow the selected broker/profile. TP/SL tests use the liquidation side under that explicit profile. Never infer synchronous spread from separate side-bar highs/lows. Quote availability supports market-path fidelity; slippage, queues, liquidity, commissions, latency and actual fills require separate broker execution evidence/model versions. No execution-authority switch is authorized here.

### Evidence promotion and truthful outcomes

The local assessment policy has three user-facing outcomes: AMBIGUOUS, OBSERVED_QUOTE_CROSSING, NO_OBSERVED_CROSSING. None asserts broker execution. Its implementation/evidence belongs to [existing system blueprint Section 42.9](PRODUCT_SYSTEM_ARCHITECTURE_BLUEPRINT.md#429-local-evidence-policy-and-read-only-audit-checkpoint); this document remains the sole fidelity/quality policy owner.

- Complete recorded-feed coverage requires affirmative scoped evidence, not merely a clean CSV, first/last date, matching candles or absence of long intervals. Freshness requires reviewed source quote semantics or per-side update evidence appropriate to the feed/profile; timestamps and narrow spread alone do not prove it. Neither establishes a global market tape.
- References are traceable declarations supplied by trusted composition after separate source review, not automatic verification, signatures or grants. Bind them to the exact input artifact hash, including its window/version/profile. Unreviewed callers cannot self-certify via a browser/API field. The read-only local CLI offers no certainty overrides.
- Existing incomplete coverage, unknown freshness and untrusted sequence flags may only be retained or downgraded, never promoted by attaching a reference. A stronger subsequently evidenced normalization needs new pinned artifact/version/evidence; prior results remain unchanged.
- Gap duration is diagnostic. The configurable silence threshold does not prove an outage, a closed session, complete history or an acceptable freshness age. Without applicable calendar/feed evidence, keep the explanation unknown; never bridge a gap with interpolated prices.
- Within equal-time events, source ordering needs both reviewed sequence semantics and actual valid sequence values. Unknown activation order, missing sides, declared gaps or invalid chronology retain uncertainty. Coverage/freshness failures disclose their own reasons instead of choosing a profitable or conservative outcome.
- OBSERVED_QUOTE_CROSSING concerns the declared feed path only. It does not establish fill price, liquidity, latency or broker execution. NO_OBSERVED_CROSSING concerns supplied quotes, not all unobserved prices. Assessment reports must retain NOT_SIMULATED with null fill/PnL, and must not drive account settlement.
- Diagnostic issues cover the supplied revealed interval; an issue after an earlier observed crossing is not retroactive evidence of a different first crossing. Hidden future suffixes cannot alter assessment, references or hashes. Existing candle SL-first modelling remains separate from this unmounted evidence path and cannot be relabelled as tick truth.

### Immutable pipeline and provider boundary

`RAW → NORMALIZE → VALIDATE → VERSION → DERIVE → SERVE` remains a design, not an implemented pipeline. Provider adapter owns file/API peculiarities; canonical schema and dataset registry feed replay/research/execution consumers without vendor APIs in core engines. Keep source bytes immutable where licensed retention allows; write separate normalized/validated/derived artifacts and reports. Retention obligations override an unconditional archive promise. Reprocessing creates a new version rather than overwriting evidence.

Derive M1 bid and ask candles separately from valid ordered quotes, then derive higher timeframes reproducibly. Pin bucket boundaries, UTC/session calendar, empty-interval policy, side, precision, ordering, normalization/validator/aggregation versions and completion/availability rule. Retain provider-native candles as a separate cross-validation dataset. No filling market gaps, creating volume, shifting prices, blending vendors or changing historical feed labels. Preserve source event time and received/available time separately where supplied; strict replay consumes only server-authorized available events, including only the revealed portion of current buckets.

### Dataset Registry and Passport requirements

| Metadata group | Required research-capable fields |
| --- | --- |
| Identity | dataset_id, immutable dataset_version, provider, provider_product, provider_dataset_id if supplied, original_symbol, canonical_instrument, asset_class, feed_id; futures expiry/contract if applicable |
| Time/evidence | coverage_start/end with boundary semantics, explicit complete/partial/unknown intervals, source timezone/DST, UTC conversion rule, actual timestamp_resolution, granularity, bid/ask/last/mid availability, tick ordering/sequence confidence, source format |
| Reproducibility | acquisition/import timestamp, normalization_version, validator_version, aggregation_version, quality_status/report and gaps, raw-byte hashes, declared canonical-byte hash and encoding/schema version, derived-artifact identity, provenance references |
| Rights | license_classification plus independently evidenced permitted usage, audience, attribution, storage/cache/backup/archive, derived/display/raw API/export, commercial/user/region limits, validity/termination/deletion policy and private evidence reference |

Existing `backend/contracts/models.py:Passport` already has dataset_id/version/hash, instrument_id/feed_id and engine/execution/input provenance. Research proposes registry resolution of those fields, not a second Passport or a change to its frozen hash contract. Use exact decimal strings or reviewed scaled integers; preserve source precision and scale, not binary-float invented precision. Existing BTL-CJSON-1 forbids floats: metadata content identity must honor that encoding, while raw source hashes cover original bytes. Define new tick-artifact encoding separately before implementation.

Experiments pin immutable identity/version/hash. Migration A→B creates a new dataset and explicitly labelled rerun; previous results retain A. Rights withdrawal can require data deletion even when reproducibility would prefer retention: retain legally permitted metadata/audit hashes, mark the experiment unavailable for rerun, do not silently substitute B or promise permanent reproducibility against a deletion clause.

### Quality acceptance and procurement sample plan

The original research had no independently downloaded tick benchmark. The subsequent [personal HistData sample](PRODUCT_SYSTEM_ARCHITECTURE_BLUEPRINT.md#428-personal-histdata-sample-and-offline-parser-checkpoint) supplies three limited-window structural measurements and an offline parser; it does not certify fidelity or representative coverage. Provider claims are not measured quality scores. Extended rights-approved sampling must include normal sessions, market open/close, holidays/weekends, DST boundaries, volatility/spread stress, equal-time events and overlapping years. Ten-year coverage requires an interval inventory, not only first and last dates.

| Check | Required observation and treatment |
| --- | --- |
| Chronology | Count out-of-order and tied timestamps; preserve source bytes/ordinal, inspect source sequence. Never drop all ties or claim ties are ordered without evidence |
| Completeness | Missing files/ticks/bars, session calendar, gaps and staleness; distinguish planned closure from unexplained outage. A quiet period alone does not prove lost ticks |
| Quotes | Reject nonfinite/nonpositive hard-invalid prices; quarantine crossed bid>ask and malformed scaling; report zero spread, negative spread, spikes and wide spread without silently repairing authentic stress |
| Representation | Original timezone/UTC/DST conversion, decimal precision, price units, instrument/side and timestamp resolution; no futures/spot or bid/mid conflation |
| Revisions | Provider corrections, raw and filtered variants, immutable version/hash and documented differences; no replacement of prior experiment inputs |
| Transport | Retry/checksum integrity, rate/request-window/pagination limits, stable boundary and duplicate handling, download reliability and deterministic repeated output; actual rate and history availability remain measured gates |

Compare the same feed's tick-derived candles against provider-native M1 first. Cross-provider differences are diagnostic, not evidence that the cheaper feed must be shifted to the expensive one. Record each failed/incomplete criterion and measured counts; do not invent a numeric score before a benchmark. Rights/access approval is required before acquisition; this phase neither downloads new archives nor requests credentials.

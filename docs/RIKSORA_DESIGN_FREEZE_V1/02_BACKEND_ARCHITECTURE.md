# 02 — Backend Domain Architecture, State, Recovery and FX Contract

**Design state:** scoped contract extension proposals; NOT proof of runtime or 16-pair qualified execution. No duplicate financial engine. Preserve [frozen execution and evidence semantics](../V2_ALPHA_EXECUTION_FINANCIAL_CONTRACT.md), [Method/Session specification](../TRADING_METHOD_SESSION_SPEC.md), and [V2 canonical market data](../MARKET_DATA_STANDARD.md).

## Actual repo evidence vs design

Existing main `backend/ticks/storage_v2.py` is indexed SQLite/zlib canonical market store, NOT Parquet; `backend/ticks/timeline_v2.py` retains per-Session timeline/position logging. `backend/execution/historical.py` binds one accepted historical Exness XAUUSDm source; `backend/execution/research.py` and `postgres.py` implement Session/review/command receipt/events/checkpoints. `postgres.py` stores command results (including some replay content) and full checkpoint each revision; disk amplification unknown until measured. `backend/cloud/app.py`, `research.py`, and `workspaces.py` contain genuine FastAPI routes and ownership. Unmerged shared-source branches and public web UI are not proof of production Beta market serving.

## Proposed modular-monolith boundary

| Subsystem | Sole authority | Forbidden dependency/behavior |
| --- | --- | --- |
| Verified Identity/Workspace | actor, membership, roles, entitlement | self-asserted tenant or billing rights from browser |
| Research Method | immutable Free Style/Protocol rule identity | retroactively rewriting evidence Method |
| Session Registry | Session lineage, dataset/feed/execution pinned profile, cursor | creating user-specific market archive |
| Data Catalog/Reader | source manifest, raw/canonical hash, bid/ask, metadata, bounded indexed pages | creating simulated fills or modifying quotes |
| Replay Controller | virtual UTC clock, revealed cursor, Play/Step/Seek/Jump, causal clipping | exposing future market data to UI |
| Execution Reducer | orders, pending activation, SL/TP, commission, cash, unresolved state | importing database/Parquet, accepting browser cash |
| Durable Session Writer | idempotent command/event/ledger/cursor transaction | duplicating commit or dropping immutable audit |
| Checkpoint/Restore | compact state and hash tip, indexed suffix reconstruction | full market copy or one-year genesis scan as sole resume |
| Research Projections | Session/Instrument-in-Method/Method statistics | fabricating portfolio drawdown or price data |
| Worker/Queue | bounded jobs, cancellation/progress, resource protection | unbounded CPU/RAM/temp or fake success receipt |

### Stable ports (conform to existing V2 instead of replacing it)

- `DatasetRegistry.resolve(datasetId, version, feedId, symbol, profileId)`: immutable passport, eligibility and rights/quality; no silent latest-version substitution.
- `IndexedTickDataProvider.locate_v2(timeNs)`: indexed first complete timestamp group at/after time, preserving tied-row evidence.
- `IndexedTickDataProvider.read_page_v2(cursor, maxEvents)`: bounded deterministic canonical event page and continuation, cross-day groups not truncated incorrectly.
- `IndexedTickDataProvider.read_evidence_v2(request)`: controller-private bounded sidecars and causal diagnostics; no future data in browser surface.
- `ReplayController.advance(sessionPin, command, budget)`: produces candidate cursor, authorized tick groups, reviewable state and stop reason; stream bounded.
- `ExecutionReducer.apply(state, tickGroups, orderCommand, methodSnapshot, profile, optionalConversionProof)`: pure exact deterministic canonical event result; **same reducer** for normal play and Jump.
- `SessionStore.commit(commandId, expectedRevision, canonicalHash, events, state, cursor)`: atomic deduplicated durable receipt and event hash; recover after worker death.
- `ResearchProjector.compute(scope, ledgerTipHash, filters)`: bounded read-only statistical results, with denominator and excluded/unresolved evidence.

These are conceptual method boundaries, not preexisting Python signatures. Codex publishes actual signatures/schema diffs before coding.

## Session/command state machine

**Session:** CREATED → ACTIVE (authorized, verified market data) → PAUSED/RESUMABLE; UNRESOLVED (financially affected actions blocked as defined by frozen contract), ARCHIVED/TRASHED with separate retention/restore. Existing evidence never silently reset. Rewind after first financial event forks with immutable parent lineage and source/time pin.

**UI order draft:** DRAFT → server REVIEWED (immutable quote/profile/Method/revision) → user CONFIRM → COMMIT_PENDING → server COMMITTED/PENDING/FILLED or REFUSED/UNRESOLVED. An order can subsequently activate from PENDING; protect SL/TP and partial/full Free Style exit according to frozen execution rules. Visual draft is not a fill. Cancel an unfilled Protocol pending is allowed; active Protocol manual close/TP amend is refused.

**Writes:** unique command ID + expected revision and canonical payload hash. Same ID/same bytes returns original receipt; same ID/different bytes conflict; stale revision refuses. Durable transaction includes dedup identity, financial events, cash/positions, revision and cursor. Crash before commit none, after commit all. Async 202 job is admission, not financial success. Disconnected browser must reconcile before retry.

## UTC Jump 72h no hidden shortcut

One click; exactly 72 elapsed UTC hours after current cursor at most. Stop at earliest eligible pending activation or active protective exit; process concurrent independent orders in chronology and same-time causal group. No event reveals eligible candles through time bound at once and preserves every pending order (no OCO/auto-expiry). Stop at qualified source boundary, keep missing/uncertain data visible. A future-search accelerator is allowed only behind private causal controller with golden proof identical to tick-by-tick normal replay. Execution reducer **cannot** read hidden future prices.

## Durable storage: event vs checkpoint

For each Session durably retain: Method snapshot hash, one symbol/feed/dataset/version/profile, revision, current cursor and anchored prefix hash, accepted command dedup receipts, immutable order/fill/cash events, active order/position state, compact recovery snapshot, journal and drawings. **Never copy raw tick or one-year candles per user.**

Main `tick_commands` serialized replay result, `tick_checkpoints` snapshots and per-Session `timeline.sqlite` position/advance blocks require measured reduction. Define a new versioned receipt and two-level recovery scheme: compact atomic current state per committed command and periodic source-pinned indexed recovery snapshot (open orders, positions, exact balance, prefix hash, cursor/provider version, ledger tip). Restore checks all anchors and reprocesses only required suffix. Checkpoint payload remains <=2 MiB; cadence decided by real long-prefix benchmark. Existing receipts remain readable and hash-valid; new schema rather than reinterpret old immutable bytes. Orphans/cache GC only after audit/owner-approved reachability checks.

## Instrument model, 16 symbols and FX conversion

Target order from founder: `AUDUSD, EURGBP, NZDUSD, USDCHF, AUDJPY, CADJPY, EURUSD, GBPUSD, NZDJPY, USDCAD, CHFJPY, EURJPY, EURNZD, GBPJPY, USDJPY, XAUUSD`.

One principal symbol per Session; immutable instrument execution profile: base/quote, feed/raw symbol, provider version, tick size and exact scale, contract size, min/max/step lots, account USD, commission/slippage/latency model, eligible time calendar, quality and source/derivation hashes. P&L and risk are exact decimals/scaled ints; no universal gold or pip multiplier. For quote currency not USD, use independently pinned point-in-time conversion source with explicit bid/ask conversion side, freshness and max staleness; historical USDJPY/GBPUSD or other eligible cross-feed only if actually available/qualified. Unknown or causally ambiguous conversion is refused/unresolved, **never substituted with today's FX rate**.

Existing Alpha frozen financial contract supports only XAUUSD/USD and refuses FX conversion. Keep those historical bytes and tests untouched. The broader 16-symbol engine requires **explicit versioned profile/financial contract extension** with new golden scenarios and owner-reviewed change authorization; not a silent Alpha reinterpretation.

## Security / reliability / scale

- Verify actor and workspace membership on every read/write, jobs included. Secure explicit Google/password account linking, not email equality auto-link. Sessions cannot cross tenant.
- Free/Pro entitlement enforced server-side; no change to market/fill correctness by subscription; one calendar-month Free daily segment, max 5 saved Sessions, 30-day Trash, open-position extension from frozen spec.
- Keep PostgreSQL on same VPS initially with bounded connection pool and workers. Data may live local SSD or object storage via reader port. Source quality, host disk 80%, RAM 85%, queue and price licensing are hard gates.
- No new Redis, microservice, second compute VPS or uncontrolled full-year caching. No raw dataset uploads to GitHub. Off-node backup + isolated restore rehearsal are mandatory.
- Same canonical ledger supports Journal/Session/Method analytics; non-comparable account curves must not be pooled. AI future research can read evidence, not mutate it.

## Acceptance before integration

Versioned OpenAPI fixtures; existing XAUUSD financial goldens; tied timestamp/provenance, new FX/no-lookahead goldens; 0/100/500 trade and one-year no-trade disk delta; cold resume after full prefix; 72h Jump vs replay; exact crash/idempotency; auth/entitlement/tenant isolation; mobile/browser reconciliation; 1 VPS repeatable capacity and source-rights checks. **No claim of current completion.**

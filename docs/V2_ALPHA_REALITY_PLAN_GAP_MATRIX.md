# Backtest Lab v2 Alpha — Reality → Plan Gap Matrix

Status: **PLAN HARDENING / CODE-INFORMED**. This document records known runtime reality against the frozen Alpha journey. It does not authorize implementation.

## Rule

A known gap is closed at planning level only when it has: concrete runtime evidence, severity, frozen checkpoint owner, deterministic remediation direction, and measurable acceptance evidence. Runtime remains unimplemented until its checkpoint is authorized and passes.

| ID | Sev | Runtime reality / failure mode | Evidence surface | Frozen owner | Required acceptance evidence |
|---|---|---|---|---|---|
| GAP-001 | P1 | Legacy CSV import materializes whole input plus parsed/accepted/index-like collections; large files can exhaust RAM. | backend/engine/market_data/importer.py; backend/services/replay_service.py | M-2/M-3 | production v2 ingestion RSS bounded by configured chunk/worker budget; dataset-size growth does not imply full-dataset resident objects |
| GAP-002 | P1 | Legacy replay/state creates prefix-sized lists and long jumps return all newly revealed candles. | backend/engine/replay/replay_engine.py; backend/services/replay_service.py | M-4/M-7/I-5 | seek/resume returns bounded page/window; no full revealed prefix materialization |
| GAP-003 | P0 | Legacy candle trading settles from OHLC/mid and deterministic SL-first ambiguity; it is not precision truth. | backend/engine/trading/trading_engine.py; frontend/src/trading/simulator.js | X-1..X-4/I-1/I-3 | no v2 financial mutation can originate from OHLC; canonical tick bid/ask vectors and ambiguity refusal pass |
| GAP-004 | P1 | Legacy sessions/datasets are process memory; restart loses state and multiprocess instances do not share truth. | backend/services/replay_service.py | Q-1/Q-2/X-3 | kill/restart restores committed session exactly; no duplicate/lost financial event |
| GAP-005 | P1 | Production replay queue/admission controller is absent. | current API/ReplayService runtime | Q-3/H-4/H-5 | bounded queue/workers; overload rejects before heavy allocation with retry semantics; queue itself cannot grow unbounded |
| GAP-006 | P1 | Tick provider/timeline validation can retain dataset-scale identity/diagnostic state even when pages are bounded. | backend/ticks/provider.py; backend/ticks/timeline.py | M-3/M-4 | peak validation/timeline working memory bounded by configured window/index structures, not total event count; diagnostic storage bounded/durable |
| GAP-007 | P1 | Tick resume/read paths can reconstruct from origin, creating O(prefix) recovery/seek and restart thundering herd. | backend/ticks/timeline.py | M-4/Q-2/Q-3 | indexed checkpoint restore; random late-history resume meets seek SLO without origin scan; recovery obeys admission limits |
| GAP-008 | P1 | Browser replay arrays/history aggregation grow and copy with revealed history. | frontend/src/market/useReplayMarket.js; frontend/src/trading/replaySettlement.js | I-3/I-5/H-4 | browser receives bounded chart/lookback/projection windows; long replay does not retain full tick/history prefix |
| GAP-009 | P1 | Historical browser chunk cache/loading can amplify requests and has no certified memory eviction budget. | frontend/src/market/useGoldMarket.js | I-5/H-4 | bounded cache with eviction; request concurrency bounded; browser budget measured under max Alpha replay window |
| GAP-010 | P1 | PostgreSQL helpers open connections per operation; no certified production pool/budget on audited path. | backend/infrastructure/database.py; identity/workspace adapters | I-2/H-2/H-4 | explicit pool/max connections/reserved headroom; overload cannot create unbounded connection attempts |
| GAP-011 | P1 | Auth rate limiting itself writes/cleans PostgreSQL state, so a rush can pressure the protected dependency. | backend identity boundary | H-2/H-4/H-5 | outer cheap admission/rate boundary plus benchmark; abusive traffic remains bounded without DB exhaustion |
| GAP-012 | P1 | Durable intake has idempotency/locking, but current durable path explicitly records NO_EXECUTION; atomic financial settlement is not yet proven. | backend/application/service.py; backend/infrastructure/postgres.py/tests | X-3/X-4/Q-2/H-5 | injected failure at every financial commit stage yields ALL committed or NONE; duplicate command never double-settles |
| GAP-013 | P1 | Worker authorization could regress if queued work is addressed only by session id. | workspace/identity boundary + future Q-3 seam | Q-3/I-2/H-2 | durable job carries/verifies workspace authority; hostile cross-tenant queued job cannot read/write/execute |
| GAP-014 | P1 | Capacity telemetry needed to distinguish CPU/RAM/I/O/DB/browser/queue bottlenecks is not yet a runtime primitive. | current runtime | H-1/H-4/L-2..L-7 | metrics expose active/queued/rejected work, resource/session cost, DB pool, latency, throughput, deterministic mismatch and recovery without secrets |
| GAP-015 | P2 | Legacy account state has browser storage/record ceilings and multiple persistence technologies exist. | AccountPersistence/localStorage; drawings; news IndexedDB; PostgreSQL | I-3/I-5 | source-of-truth matrix enforced; legacy failure is explicit/non-destructive; canonical v2 financial state server-side |
| GAP-016 | P1 | Dataset provenance/version must remain pinned through active session and cutover; legacy visual/live sources can differ. | frontend market adapters; v2 tick contracts | M-7/Q-1/I-3 | active session cannot silently switch dataset/version; mixed legacy/live visual source never becomes execution evidence |
| GAP-017 | P2 | Backup/restore uses fixed operational timeout and has not been certified at grown Alpha DB size. | backend/infrastructure/database.py | H-3/H-4 | measured size-aware backup/restore drill meets frozen RPO/RTO or blocks release |
| GAP-018 | P2 | Reproducible production delivery/CI surface is incomplete in audited tree; backend loose requirements must not supersede lock. | backend/requirements.txt + lock; repository deployment surface | H-2/H-3/L-2 | release installs pinned lock; clean environment build/test/migrate/restore reproducible; CI/release gate executes required test families |
| GAP-019 | P1 | Gap/outlier/calendar quality in legacy importer is insufficient for precision eligibility. | backend/engine/market_data/importer.py | D-0/M-3/M-5 | quality report classifies chronology/duplicates/crossed/missing/gaps/calendar uncertainty; no silent repair; uncertain execution becomes UNRESOLVED |
| GAP-020 | P1 | State/trade responses can serialize unbounded trade history. | TradingEngine.state; ReplayService.state | M-7/I-2/I-5 | paginated/bounded projections; no ordinary API response grows with complete session history |
| GAP-021 | P1 | Recovery of many sessions can stampede disk/DB even if each restore is correct. | interaction of Q-2 with current origin-scan behavior | Q-2/Q-3/H-5 | mass-recovery workload is admitted through bounded recovery queue; resource ceilings remain intact |
| GAP-022 | P1 | Queue saturation can merely move DoS from workers into queue storage. | future Q-3 seam | Q-3/H-4/H-5 | global/per-user queue capacity fixed; excess gets 429/503 + Retry-After; no million-entry in-memory/DB queue |
| GAP-023 | P1 | Static tests cover important idempotency/tenant behavior, but financial kill points, disk-full, DB-loss and mass recovery are not runtime-proven. | backend/tests + missing integrated v2 execution | H-5 | deterministic failure-injection matrix executed against integrated v2 runtime with evidence artifacts |
| GAP-024 | P2 | Telemetry itself can become a resource/privacy liability on a small Alpha node. | future H-1 seam | H-1/H-4 | bounded-cardinality metrics/logging, retention/redaction, backpressure/drop policy; observability failure cannot block financial truth |

## Negative invariants

The v2 Alpha implementation MUST satisfy all of these:
1. No full-dataset materialization in production ingestion, validation, replay, seek or API projection.
2. No seek/resume complexity proportional to the complete historical prefix when an index/checkpoint can locate the target.
3. No unbounded in-memory duplicate, diagnostic, cache, history, queue or telemetry-cardinality structure.
4. No OHLC/candle path may commit v2 precision financial truth.
5. No heavy replay allocation occurs before admission.
6. No unbounded worker count, queue length, DB connection creation or browser historical state.
7. No queued/recovered worker gains authority from a naked session id.
8. No financial mutation is committed outside the frozen atomic transaction boundary.
9. No duplicate command creates a duplicate financial event or settlement.
10. No recovery stampede bypasses the same resource controls as normal work.
11. No active session silently changes dataset identity/version/profile.
12. No legacy/live visual source is promoted to execution evidence.
13. No ordinary state endpoint serializes complete unbounded history.
14. No protection mechanism (rate limiting, telemetry, recovery) may become an unbounded dependency load.
15. No external Alpha cohort starts without measured capacity, recovery, security, rights and deterministic evidence.

## Planning disposition

All known gaps above map to existing frozen journey checkpoints. They harden acceptance; they do not add product scope or authorize runtime. A new finding that cannot map to the frozen architecture must follow the Decision Register hard-invalidation/change-request protocol.

## Alpha implementation adversarial observations (2026-10-11)

These are concrete checkpoint findings, not the requested final post-implementation Alpha audit. Historical planning rows remain unchanged; no final release PASS is inferred.

| Finding | Severity | Reproduction / consequence | Existing owner | Disposition / evidence |
| --- | --- | --- | --- | --- |
| ALPHA-A01 | P2 | seekTarget(2025-02-30T12:00) returned March2; April31 and24:00 could normalize rather than reject the requested replay time | R-4/I-3 display boundary | Fixed exact UTC roundtrip; authored leap/century/invalid calendar/time vectors pass, empty browser seek refuses before command |
| ALPHA-A02 | P2 | Fixed420px mobile workspace height let chart/replay/limitations overlap the following order bar | R-4/I-3 responsive composition | Corrected intrinsic/min height; actual375px DOM bounds confirm detailsBottom≤orderTop and no horizontal overflow |
| ALPHA-A03 | P2 | A bare home link discarded Session/source query selection, making navigation return to an unselected workspace | R-4/I-3 navigation | Same-origin bounded pagePath preserves Session and synthetic/historical context; actual home return and authored route vectors pass |
| ALPHA-A04 | P2 | Introducing persisted24px terminal state revealed an unreopenable restoreHeight24 default | R-4 shared panel policy | Fixed minimum restored height144; golden keyboard test plus actual reload/Restore pass. Persistence preserves unsupported/foreign bytes and handles denied/quota failures |

Financial/tick contracts and actual Exness UNKNOWN/UNTRUSTED are unchanged. R-5 through release gates remain pending under the sole operational pointer. After implementation, re-audit tenant/session ownership, no-look-ahead, financial retries/recovery, journal/metrics/measurement, resource bounds, dependency security and complete browser journeys; unresolved severity1/2 issues block internal Alpha acceptance.

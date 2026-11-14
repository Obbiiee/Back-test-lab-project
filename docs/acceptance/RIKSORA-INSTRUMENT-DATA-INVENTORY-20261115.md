# RIKSORA — 16-instrument data inventory and product-engine audit (2026-11-15)

Status: **IMPLEMENTATION REGISTER, not an architecture authority.** Facts only; nothing here promotes a data right or invents a broker profile. Evidence: `docs/benchmarks/data-verification/verify_v2_16pairs_2026-11-14.jsonl` (544 verified datasets), `verify_prehistory_16pairs.jsonl`, `docs/benchmarks/financial-real-v2/`, code paths cited below.

## 1. What the product actually runs (engine audit)
| Layer | Implementation used by the hosted product | Evidence |
|---|---|---|
| API / auth / tenant | `backend/cloud/*`, `backend/identity/*` | route tests, tenant-isolation tests |
| Queue / worker | PostgreSQL `btl.research_jobs`, SKIP LOCKED, leases, native serve-mode worker `cloud/worker.py` | `tests/test_research_queue.py` 26/26 PASS on this run (includes process death after inner commit for replay and jump, rollback + exact result recovery, lease/heartbeat, cancel, fairness between actors, FIFO per actor, global slots, retry by job id) |
| Tick source | Monthly Parquet through `execution/` provider; the monthly selection is only admitted when `eligibility == 'SYNTHETIC'` (`cloud/research_routing.py:validate_source_selection`, error `REFUSED_SOURCE`) | code |
| Financial reducer | frozen reducer in `backend/execution/` (the baseline implementation). It is the only engine whose result becomes a receipt | frozen contracts |
| Claude v1 / v2 engines, compact tick v2, OHLC engine | `backend/tools/claude_exp/*`: **prototype / parity candidates, not wired into the product runtime** except the OHLC chart path (`cloud/chart_history.py`, `execution/claude_ohlc_seam.py`) | `docs/benchmarks/financial-real-v2/` parity: baseline = Claude v1 = Claude v2 on 18 single-month real slices and 6 cross-month slices (up to 256 fills); proven for private QA only |
So: no second financial engine exists in the product. Replacing or adding one is not done and not recommended before the rights question below is resolved.

## 2. Inventory by layer (the seven things that must not be conflated)
1. **Instrument specification** (what the instrument is). The launch catalog names 16 symbols (`docs/acceptance/RIKSORA-COMMERCIAL-V1-TARGETS.md` section 1). Only XAUUSD has a product execution profile (observed path) and the synthetic fixture has its own; the other 15 have NO contract/lot/commission/slippage/margin profile in the repository. **MISSING (owner or broker-spec input required; not invented).**
2. **Feed precision** (price digits in the source). From the verified datasets: priceScale 5 for AUDUSD, EURGBP, EURNZD, EURUSD, GBPUSD, NZDUSD, USDCAD, USDCHF; priceScale 3 for AUDJPY, CADJPY, CHFJPY, EURJPY, GBPJPY, NZDJPY, USDJPY and XAUUSD. **Proven by the verifier (all 544 OK).**
3. **Contract / lot sizing profile**: unknown for 15 of 16 (see 1). The profile fields exist in the frozen profile contract (tickSize, priceScale, contractSize, lotStep, minLot, maxLot, moneyScale, commissionModel, slippage, latency) but must come from a real, citable specification.
4. **Actual dataset coverage**: 16 pairs x 34 months (2024-01 .. 2026-10) of tick data = 544 datasets, 1,331,417,302 ticks, all verified; M1 BID prehistory 2020-11 .. 2023-12 for 16 pairs (derived display data only). The advertised 2023-01..2025-10 catalog window in the Commercial targets does not match what exists (2024-01..2026-10); the owner must restate the SKU window.
5. **Source integrity**: manifests/hashes verified, crossed-quote and ordering checks reported per dataset, 0 problems; compact tick v2 proven lossless against v1 on 60,017,476 EURUSD ticks.
6. **QA admission**: the product Monthly path refuses anything that is not `SYNTHETIC` eligibility. Real data therefore cannot reach the product worker today, by design.
7. **Commercial-use rights**: every dataset carries rights `UNKNOWN` (544 of 544). Per the owner's standing rule these are private QA only and cannot be presented as commercial evidence.

| Pair | Months | First | Last | Ticks | priceScale | Verifier problems |
|---|---|---|---|---|---|---|
| AUDJPY | 34 | 2024-01 | 2026-10 | 88,646,196 | 3 | 0 |
| AUDUSD | 34 | 2024-01 | 2026-10 | 48,647,805 | 5 | 0 |
| CADJPY | 34 | 2024-01 | 2026-10 | 73,092,810 | 3 | 0 |
| CHFJPY | 34 | 2024-01 | 2026-10 | 89,104,394 | 3 | 0 |
| EURGBP | 34 | 2024-01 | 2026-10 | 48,402,606 | 5 | 0 |
| EURJPY | 34 | 2024-01 | 2026-10 | 137,938,800 | 3 | 0 |
| EURNZD | 34 | 2024-01 | 2026-10 | 79,856,600 | 5 | 0 |
| EURUSD | 34 | 2024-01 | 2026-10 | 60,017,476 | 5 | 0 |
| GBPJPY | 34 | 2024-01 | 2026-10 | 119,710,850 | 3 | 0 |
| GBPUSD | 34 | 2024-01 | 2026-10 | 67,139,956 | 5 | 0 |
| NZDJPY | 34 | 2024-01 | 2026-10 | 69,331,691 | 3 | 0 |
| NZDUSD | 34 | 2024-01 | 2026-10 | 42,185,322 | 5 | 0 |
| USDCAD | 34 | 2024-01 | 2026-10 | 59,490,324 | 5 | 0 |
| USDCHF | 34 | 2024-01 | 2026-10 | 47,693,649 | 5 | 0 |
| USDJPY | 34 | 2024-01 | 2026-10 | 96,831,343 | 3 | 0 |
| XAUUSD | 34 | 2024-01 | 2026-10 | 203,327,480 | 3 | 0 |

## 3. Cross-month sessions
Product Sessions are bound to one monthly dataset (`startPeriod`), so the pending-order/open-position continuation across a month boundary (Free window rule) cannot yet be exercised on the product path with real months. The guard (`cloud/window_guard.py`) and its tests use the real reducer on the synthetic fixture with the boundary placed inside the dataset. A real cross-month product Session needs a provider that serves two adjacent months as one dataset: **NOT IMPLEMENTED**. Engine-level evidence exists outside the product: 6 cross-month parity slices (baseline = Claude v1 = Claude v2).

## 4. Real-data acceptance verdict
**BLOCKED** at admission (item 6/7): rights UNKNOWN, 15 instrument profiles missing, product path synthetic-only by design. Synthetic acceptance continues (queue/worker recovery 26/26, browser journey, entitlement, window guard, export). Required to unblock: (a) owner-approved data-use class for private QA sessions with explicit label; (b) citable instrument specifications for 15 instruments (or an owner decision to launch fewer instruments); (c) a restated SKU window; (d) a two-month provider if cross-month continuation is a Commercial V1 requirement.

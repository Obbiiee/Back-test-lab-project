# Dual Engine Challenge V1 — Claude candidate report

Branch `claude/dual-engine-v1-20261114`. Common baseline: PR #55 head `f941eba` (contains Codex integration `d8f5e12`). Codex's unpublished local commits were not visible
to this agent, so the final side-by-side is **BLOCKED**; this is the Claude side, measured against an independent oracle, ready to be compared.

## What was built (all under `backend/tools/claude_exp/`, nothing in production code changed)
| Part | Path |
|---|---|
| Independent oracle (pure Python, ints/Fractions, no shared aggregation code) | `ohlc/oracle.py` |
| Streaming nine-timeframe engine, exact int64 grid (MID = bid+ask per tick), immutable idempotent publish | `ohlc/engine.py` |
| Object-store port: local SIMULATION + S3/R2 adapter (stub-tested only) | `ohlc/store.py` |
| Cursor-bound authenticated chart API (HTTP) | `ohlc/service.py` |
| 13 golden tests, 13 service/attack tests | `ohlc/test_golden.py`, `ohlc/test_service.py` |
| Staged benchmark | `ohlc/bench.py`, raw result `docs/benchmarks/CLAUDE_OHLC_EURUSD_2026-05.json` |
| Baseline merge: one conflict (`contracts/canonical.py`); the baseline (Codex) version kept, my competing fast path dropped | commit `bf9cb94` |

Commands (from `backend/`, project-pinned Python 3.13, numpy 2.5.4, pyarrow 26.0.0):
`python -m unittest tools.claude_exp.ohlc.test_golden tools.claude_exp.ohlc.test_service` and
`python -m tools.claude_exp.ohlc.bench --src <compact dir> --repeats 5 --oracle-upto 1500000 --out <json>`.

Dataset (pinned): HistData-UTC EURUSD 2026-05, 1,444,646 ticks, compact manifest hash `c98162e2bfae997fc626e967e86a014e9bb2f003fa990b1b36247aea8163b252`. Rights: UNKNOWN.
Host: Windows 11, 8 logical CPUs, 7.8 GiB RAM (NOT the 6 vCPU / 16 GiB target).

## Measured results (5 repeats, median)
| Gate | Ticks | Wall s | CPU s | Peak RSS MB | Output bytes (9 TF) | Oracle equality |
|---|---:|---:|---:|---:|---:|---|
| G0 | 2,048 | 0.041 | 0.047 | 79 | 15,728 | IDENTICAL |
| G1 | 65,536 | 0.053 | 0.047 | 83 | 51,516 | IDENTICAL |
| G2 | 262,144 | 0.091 | 0.156 | 88 | 160,698 | IDENTICAL |
| G3 | 1,000,000 | 0.248 | 0.281 | 86 | 731,006 | IDENTICAL |
| G4 (1 real month) | 1,444,646 | 0.364 | 0.453 | 94 | 1,136,953 | IDENTICAL |

Each gate = 10 objects (9 timeframes + manifest), 10 PUTs. RSS includes about 50-80 MB interpreter and library baseline. The oracle needed 154 s for G4, which is why it is a
reference and not a candidate. G5 (multi-month) and G6 (one year) were **not run**.

Serving (loopback HTTP, local object-store simulation, 9 timeframes x first page 512 and page 1000):
| Phase | Requests | p50 ms | p95 ms | p99 ms | Mean payload B | Store GETs / bytes |
|---|---:|---:|---:|---:|---:|---|
| cold, late in month | 18 | 11.1 | 340.9 (first request, library warm-up) | 340.9 | 27,566 | 10 / 1.14 MB |
| warm, late in month | 360 | 3.37 | 4.17 | 4.54 | 27,566 | 0 |
| warm, one third from end | 360 | 5.57 | 6.74 | 7.39 | 25,169 | 0 |

First page (512 bars) is 1.9 KB (D1) to 27 KB (M30) of JSON. Latency here is server plus loopback only, not browser time-to-first-chart.

## Claims
**Proven (by tests in this branch, on this data):**
- Engine equals the independent oracle exactly for all nine timeframes: random sources, ties, gaps/weekends, month and year boundaries, row-group boundaries, BID/MID/ASK, extreme precision, single tick, empty source; G0-G4 on real data.
- MID is computed per tick; a test shows the "average of side highs" result differs.
- Corrupt order and non-positive prices are refused, never re-sorted. Publication is deterministic (byte-identical across stores), idempotent (no second PUT) and immutable (conflicting rewrite refused).
- Direct HTTP attacks: no token, forged token, foreign session (same 404 as unknown), malformed/hostile parameters, `before` in the future (refused, not clamped), session pins not overridable by the request, stale revision (409), cursor cannot move backwards, no-store header, no object key in any body.
- No-lookahead: for 8 cursors x 9 timeframes the completed bars and the forming bar equal the oracle built from ticks <= T; a canary future price never appears in any served byte before the cursor (and is detected once the cursor passes it).

**Hypothesis (not shown):** that these latencies and 1.1 MB/month hold at 16 instruments x 34 months; that R2 operation counts and cost match the estimate (about 10 objects per instrument-month, 544 x 10 = 5,440 objects); that a CDN or edge in front keeps the cursor guarantee (it must not cache cursor-bound pages).

**Prototype only:** the S3/R2 adapter (stub client, never a real bucket); the object store is a local-directory simulation, not an R2 PASS; HTTP layer uses a test bearer-token map, not the product identity; sessions are in-memory records, not PostgreSQL.

**Needs production-like acceptance (not done):** Postgres/worker/queue integration with the chart service; browser metrics (time-to-first-chart, switch latency, heap, fps); 1/2/5/10 trader load on a 6 vCPU / 16 GiB host; real R2 PUT/GET/LIST counts and egress; financial replay and Jump at the pinned gates (earlier Claude numbers are on different data: XAUUSD 20k/100k/1M ticks, parity with the reference reducer 24/24 plain and 12/12 archive); rights for real data; one-year G6; the OHLC-only 2021-2022 prehistory (no source exists here).

## Adoption matrix (Claude candidate, pending a Codex counterpart on the same oracle)
| Area | Verdict |
|---|---|
| Independent oracle and golden fixtures | ADOPT CLAUDE (use as the shared acceptance judge for both) |
| Nine-timeframe offline materialisation | REQUIRES PARITY (Codex's BID M1 generator must pass the same oracle, then choose on cost) |
| Cursor-bound chart delivery | COMBINE (keep product auth/identity; take the paging, active-candle and attack tests) |
| R2 adapter | REQUIRES CAPACITY TEST (needs real bucket and cost measurement) |
| Financial replay / Jump / compact source | REQUIRES PARITY on the pinned dataset, then capacity test |
| Product integration, Postgres, worker, load | BLOCKED (Linux needed; the product data layer uses POSIX-only calls) |

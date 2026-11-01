# CP6A-9 — Shared Canonical Source / One-Day Acceptance

**Result: PASS for the bounded one-day QA checkpoint.** This does not certify annual replay, production readiness, broker fills, or external data-use rights.

## Scope and source identity

The paired sessions used the same accepted H1 canonical XAUUSD source and the same January 2, 2024 order-decision schedule, financial kernel, Batch-256 advance setting, PostgreSQL isolation, and QA guardrails. The baseline uses the existing per-session timeline copy; the candidate uses `shared-source-v1`, retaining only a hash-chained advance/cursor log in the session timeline database and deriving quote positions from the immutable source.

| Binding | Value |
|---|---|
| Dataset ID | `local:hf-community:XAUUSD:2024:53011f22a5887999a2c883a2` |
| Dataset version / internal root | `87e3c3355dccc3afafef837a56d24046275dcf8ee6d1173a929a10279f14e743` |
| Original source manifest hash | `53011f22a5887999a2c883a20cf5702d011a9523cb50578979059f9f3c2bfc5a` |
| H1 archive SHA-256 | `b8f45551f408021514ab92599bd227eb4bfa9097c865d0084e0a91999c155b94` |
| Qualification receipt SHA-256 | `1ace74978391741f66078b8969a1784229a7c17f07b32f63b7e9e41e148cbb29` |

The candidate pins dataset ID/version, canonical root, index content hash, archive hash, and qualification receipt hash for the session. The source files and production state remained unchanged. Source rights remain `UNKNOWN`; execution eligibility remains `NOT_GRANTED`. The simulation label remains **EXPERIMENTAL — UNVERIFIED SOURCE — SIMULATED EXECUTION**. No broker-fill or redistribution claim is made.

## One-day financial and source result

Both runs completed the requested 2024-01-02 UTC interval using 137,108 source groups and the same first/last observed quotes. Independent source traversal matched 172/172 entry and exit fills. Both produced 86 closed simulated trades (65 SL, 21 TP), four cancelled orders, 777 events, ending balance `9976.38` from `10000`, and gross P&L `-23.62`. Commission model was `NONE`; no broker commission was inferred.

One `UNKNOWN_COVERAGE_GAP` lasting 3,602.483 seconds was recorded from `1704232798239000000` to `1704236400722000000`. No quotes or fills were synthesized during it. The first observed quote is 130 ms after UTC midnight, and the final observed quote is 809 ms before the requested interval end; coverage limitations remain explicit.

Independent comparisons passed for order lifecycle, normalized trade audit, fill prices/quantities/timestamps/reasons, Bid/Ask source groups, event counts/order, final balance, gross P&L, financial-state hash, and semantic financial-event hash. Session-specific event IDs make the trade-audit hashes differ. The event transcript, receipt-ledger, full final-state, and resume-state hashes also differ because the Session IDs and timeline checkpoint representation differ; each run's own chain was independently verified. These representation hashes are not presented as cross-format semantic hashes.

## Measured paired results

Allocated sizes below include each isolated QA runner's PostgreSQL cluster. The canonical H1 source is shared infrastructure and is excluded from per-session bytes.

| Measure | Baseline timeline copy | Shared canonical source | Change |
|---|---:|---:|---:|
| Per-session `timeline.sqlite` allocated | 84,520,960 B | 434,176 B | **99.486% less** |
| Total QA artifacts allocated | 160,935,936 B | 76,664,832 B | **52.363% less** |
| PostgreSQL database | 26,582,039 B | 26,401,815 B | Similar; small run variance |
| PostgreSQL cluster allocated | 76,185,600 B | 76,001,280 B | Similar; small run variance |
| End-to-end wall | 657.203 s | 632.123 s | 3.82% less in this pair |
| CPU | 596.573 s | 572.536 s | 4.03% less in this pair |
| Peak RAM (QA cap method) | 798,179,328 B | 796,413,952 B | Similar; both below 1 GiB |
| User-facing replay wall | 454.797 s | 431.921 s | 5.03% less in this pair |
| Independent verification wall | 72.846 s | 69.453 s | Separate stage |
| Cold-resume wall | 57.343 s | 56.584 s | Similar |
| ADVANCE command latency, 631 calls | p50 596.993 ms; p95 786.727 ms | p50 587.038 ms; p95 681.928 ms | Measured for this pair |
| First post-restart command | 16.678 s | 14.778 s | Reported separately from ADVANCE distribution |

The small runtime improvement is an observation from one paired run, not a general performance guarantee. The durable SQLite log still consumes 434,176 bytes for the candidate; it stores advance/checkpoint metadata, not a full quote timeline.

## Recovery and regression gates

- Baseline and shared-source one-day report: PASS; both cold-resumed the same Session after process restart and passed idempotent retry.
- Shared-source timeline tests: PASS, including replay reconstruction without position blocks, source-pin mismatch rejection, missing advance commitment rejection, and corrupted advance-chain rejection.
- Isolated PostgreSQL regressions: **13/13 PASS** in a private Unix-socket-only cluster, including rollback and shared-source SIGKILL-after-commit, idempotent retry, and cold resume. No production database was used.
- Tick storage, observed kernel, and source regression suite: **80/80 PASS**.
- Python compilation and `git diff --check`: PASS.
- Production changed: `false`. Canonical source changed: `false`.

## Qualified annual projection

CP6A-8 projected 56,208,511 annual groups and 38.93 GB artifacts using the per-session timeline-copy design, including 34.66 GB of timeline data. Scaling the measured candidate timeline allocation by annual groups gives about **178 MB** of per-session advance metadata. Keeping CP6A-8's separately measured non-timeline projection unchanged gives about **4.45 GB** before margin, or **5.56 GB** with a 25% margin. This is a linear projection, not an annual benchmark. The 22.93 GB H1 source remains stored once as shared infrastructure and is not added to per-session cost.

The annual runtime remains the CP6A-8 estimate of about **56.2 hours**; this checkpoint does not demonstrate annual speedup. Current free space is approximately 48.9 GB, above the 30 GiB reserve, but annual execution remains gated on an explicit supported annual order schedule (within cumulative-order policy), week/month recovery evidence, and a fresh resource preflight. No annual replay was started.

## Reproduction and evidence

Runner command template (use a **new empty evidence root** for every invocation):

```bash
PYTHONPATH=/tmp/riksora-beta-integration-current-20261028/backend \
BTL_QA_HISTORICAL_BATCH_GROUPS=256 \
BTL_HISTORICAL_QA_RUN_ID=UNIQUE_RUN_ID \
BTL_HISTORICAL_QA_ROOT=/home/riksora/riksora-qa-evidence/NEW_EMPTY_ROOT \
/tmp/riksora-vps-candidate-venv/bin/python -B -m tests.qa_historical_day_v2
```

Add `BTL_QA_SHARED_CANONICAL_SOURCE_V1=1` for the candidate; leave it unset for baseline. The runner creates its own private QA PostgreSQL cluster. Accepted run reports:

- Baseline: `/home/riksora/riksora-qa-evidence/cp6a9-xau-day-baseline-r5-20261101/report.json`
- Shared-source: `/home/riksora/riksora-qa-evidence/cp6a9-xau-day-shared-r3-20261101/report.json`
- Qualification: `/home/riksora/riksora-qa-evidence/beta-checkpoints-20261025-jtbqjj1o/xau-binary-recovery-20261026/resumable-parity/final-report.json`
- Machine-readable paired evidence: [CP6A-9 evidence JSON](CP6A-9-shared-source-evidence.json)

No full-year run was performed. The CP6A-8 inventory/report and all earlier evidence remain untouched.

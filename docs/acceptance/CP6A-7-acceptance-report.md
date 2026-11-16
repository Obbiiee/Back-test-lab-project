# CP6A-7 — 2,000 Completed Trade Acceptance

**Status: PASS for the bounded 2,000-trade QA checkpoint. This is not full-year acceptance.**

## Run and financial result

One continuous QA Session processed XAUUSD from **2024-01-02 00:00:00.130 UTC** through **2024-01-17 11:03:24.130 UTC** (16 calendar days), then stopped at the completed-trade target. It consumed **1,688,742 source timestamp groups**. It accepted 2,019 orders: 2,000 closed, 18 cancelled, 1 pending at stop; 2,018 terminal orders are archived and one pending order remains hot.

The independent trade audit verifies **2,000 unique completed orders**, each with entry and exit events tied to observed source groups. It matches 2,000 entry fills and 2,001 exit-fill rows (one partial close); all entry quantity is exited and every trade ends with zero remaining quantity. All 4,001 fill rows match observed source. Gross posted P&L is **-645.85**, reconciled from **10,000.00** to **9,354.15**. Commission model is `NONE` (zero), slippage is `NONE`, and latency is `ZERO`; no broker fees or actual broker fills are claimed.

Event-chain/source-order verification, financial reconciliation, receipt ledger, cold resume after day one, and idempotent retry all PASS. Production and source data were unchanged. The exact result, hashes, timings, resource readings, and limitations are in [machine-readable evidence](CP6A-7-acceptance-evidence.json).

## Regression gates

**39/39 targeted tests PASS** in a fresh private PostgreSQL 16 Unix-socket cluster: observed kernel, archive-v1, and the complete observed PostgreSQL regression suite, including QA archive integration, transaction/crash recovery, idempotency, concurrency, and legacy/session verification. The temporary test cluster was stopped and its test fixtures removed. `py_compile` and `git diff --check` PASS. The 2,000-trade workload was not rerun.

## Source identity and limits

The run's dataset ID/version match the accepted canonical XAUUSD 2024 intake identity: `local:hf-community:XAUUSD:2024:53011f22a5887999a2` / `87e3c3355dccc3afafef837a56d24046275dcf8ee6d1173a929a10279f14e743`. Its archive/snapshot SHA-256 (`b8f45551…c155b94`) matches the prior full-binary parity evidence, whose classification explicitly says **not financial admission**. The intake pin refers to `CarlosSilva1/xauusd-ticks` revision `d14fc64dc3b0452732e60662d94b500a6bb3d534`; its manifest labels the source `CC-BY-4.0`.

This confirms the run used the same internally accepted canonical dataset, not a synthetic fixture or a different test source. It does **not** establish broker origin, completeness of market coverage, legal advice, permission to redistribute commercially, or actual broker execution. The run records source rights as `UNKNOWN`, execution eligibility as `NOT_GRANTED`, and classification as **EXPERIMENTAL — UNVERIFIED SOURCE — SIMULATED EXECUTION**. There were 21 unknown coverage-gap events and 11 stale-quote events. The tick-quality/source identity gates passed for this simulation; external usage rights remain a separate review.

Private run evidence is at `/home/riksora/riksora-qa-evidence/cp6a7-real-xau-2024-20261031-trade2000-r1/`; report SHA-256 is `010695f6163f9fc299036c3bdedb8359fbc8fd0f361ec47821a9992e5aa0e066`. Canonical intake and binary parity evidence are under `/home/riksora/riksora-qa-evidence/beta-checkpoints-20261025-jtbqjj1o/`.

## Resources and full-year readiness

Measured run: **6,073.746 s wall** (1 h 41 m), **5,688.605 s CPU**, peak RAM **845,447,168 B** (<1 GiB), peak QA artifacts **1,171,181,568 B**, PostgreSQL database **76,069,911 B**, and final free disk **49,514,954,752 B**. Replay was 5,010.245 s, independent full verification 875.387 s, cold resume 191.458 s. A fresh read-only disk check after regression showed 49,461,407,744 B free.

Using the accepted annual count of 56,208,511 groups and measured 1,688,742-group run, a simple linear extrapolation is **33.28×**: about **56.2 h wall**, **52.6 h CPU**, and **38.93 GB** QA artifacts. With 25% artifact margin, budget about **48.66 GB**. This is a projection, not a benchmark. Current free space less the required 30 GiB reserve leaves only about **17.25 GB** spendable. Therefore **do not start annual replay on the current volume**. The minimum arithmetic shortfall is about 29.3 GiB; provision at least **40 GiB additional usable SSD** (or demonstrate a separately approved storage plan), then require a read-only preflight proving at least **30 GiB reserve + 45.3 GiB run budget** free before launch. Keep canonical sources and all existing evidence in place; use a new isolated QA output root.

The 2,000-trade grid rate would exceed the QA cumulative-order limit of 4,096 if copied across a full year. The annual run needs an explicitly bounded order-decision schedule that respects current policy; do not silently increase limits or reuse the short-run grid. No full-year replay, production change, or policy change occurred here.

## Git state

Tests were run against base `a85a7d57b3db9a8be7ffef37ba67825a26021040`; origin matched that base before publication. The QA runner changes are additive and the existing monthly runner remains in the same file. The report, evidence summary, and scoped implementation are published together; the resulting commit is reported with this checkpoint.

# CP6A-10 P0 Local Integration — 2026-11-06

Status: **PASS — isolated synthetic QA only**

Implementation branch: `codex/p0-local-integration-20261106`

Base: PR #39 branch `claude/product-frontend-v1`, SHA `274d592e06a9a8afc2a7b7e2efdf09498da36a34`
Scope: local QA API and PR #39 frontend contract. No merge, deployment, production auth change, annual replay, benchmark, multiworker run, historical eligibility, or financial reducer change.

## Implemented contracts

- `GET /api/v1/tick-alpha/sessions/{sessionId}/commands/{commandId}` returns versioned `BTL-TICK-COMMAND-STATUS-1`.
- `COMMITTED` requires the immutable, content-hash-validated transactional execution result, matching Session/command/review, command hash, and exactly the reviewed revision transition.
- `NOT_COMMITTED` requires a durable matching review, no command receipt or order, and a Session revision newer than the review's expected revision. Receipt absence alone returns `UNKNOWN`; a Session lock/in-flight confirmation remains `UNKNOWN`.
- Exact retry with the same review identity returns the same receipt. A changed command hash for the same command ID is refused by the existing durable idempotency check.
- Catalog availability schema v1 explicitly identifies its scope as `SESSION_START_MONTH_ONLY`. Synthetic QA reports a bounded `PARTIAL` instrument and one exact `AVAILABLE` start month, without claiming complete month coverage. Historical source rights remain `UNKNOWN`, eligibility `NOT_GRANTED`, and local API Session creation is refused.
- Create Session rechecks availability server-side. No financial reducer, engine, receipt writer, event writer, or canonical source code changed.

## Verification evidence

- Dedicated PostgreSQL 16 cluster: `/tmp/riksora-p0-local-integration-pg-20261106` (Unix socket only, `listen_addresses=''`, 32 MiB shared buffers, 16 connections). It was stopped cleanly after tests; the cluster files remain for inspection.
- Backend: 6 new P0 integration tests PASS; 9 existing PostgreSQL execution tests PASS; 13 existing research-session tests PASS; 1 focused historical local-API regression PASS. These cover the complete planned LIMIT order API journey, receipt and Journal, exact retry, changed-hash conflict, response loss after commit, UNKNOWN while a row lock is held, definitive stale-revision refusal, historical rights denial, and existing chart-only behavior.
- Frontend: period availability and confirm outcome tests PASS; ESLint PASS; Vite production build PASS.
- Browser (cached Chromium; local Vite + local API + isolated PostgreSQL only): **8/8 PASS**. Includes planned limit → review → confirm → durable receipt → Journal, 200 followed by refresh failure, committed response loss reconciled by receipt lookup, genuine 409 refusal, 503/timeout UNKNOWN without duplicate confirm, idempotency, double tap, Back/reload while pending, and stale-revision reconciliation.
- Combined existing backend suites initially reported one test harness configuration error because `BTL_PG_BIN` was unset; the PostgreSQL execution suite was rerun with `/usr/lib/postgresql/16/bin` and passed 9/9. No financial assertion failed.
- The original and rerun browser screenshots are in `screenshots/`; only screenshots from the final 8/8 passing run are retained here.

## Boundaries and remaining blockers

- This is not hosted authentication, public API, production readiness, source-rights clearance, or broker execution eligibility.
- Historical source rights remain `UNKNOWN`; no historical Session was created through the local API.
- Hosted authentication/API integration and any deployment/merge remain separate owner-approved checkpoints.
- Local QA PostgreSQL and API were stopped after verification. Temporary test data remains isolated under `/tmp`; no cleanup was performed.

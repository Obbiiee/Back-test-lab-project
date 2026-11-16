# CP6A-10 Product Integration — P0 Remediation Review

Date: 2026-11-07
Status: **HOLD — NOT ACCEPTED**
Branch: codex/product-integration-v1-20261106
Base HEAD: f68ba9d7e56fffd7a4be90f8da265ae6098c9a23
Working tree: modified and uncommitted; no commit, push, merge, or deployment performed.

## Scope and safety

This checkpoint preserved the existing local Method-versioning and frontend integration changes. No deterministic reducer, financial receipt contract, production service, historical dataset, Annual PASS evidence, or CP6A-8 evidence was changed. Annual verification report SHA-256 was rechecked at its protected path and remains:

cdc65e4c7fd7e65e85fac38726472c2ad92925c502afc2f08482a01b897fc831

Latest resource measurements:

| Gate | Measured | Required | Result |
|---|---:|---:|---|
| Free disk (/, bytes / GiB) | 36,131,262,464 bytes / 33.65 GiB | ≥36 GiB | HOLD |
| MemAvailable | 4,707,896 kB / 4.49 GiB | ≥10 GiB | HOLD |
| Swap | 0 | 0 | PASS |

PostgreSQL QA and browser acceptance were not run. The application PostgreSQL service was not used for test writes. No isolated QA PostgreSQL instance was created. A requirements.lock-matched isolated Python venv was prepared and used for non-database tests.

## Confirmed queue transport regression and correction

The hosted backend durably queues POST /sessions, Session view, bootstrap, chart-history, replay-to, and ADVANCE/SEEK replay operations. The account frontend previously supplied queue IDs only for a subset of reads and commands. A valid 202 QUEUED response for the remaining routes could be treated as a failed response, or the frontend could poll with no matching job identity.

The frontend now assigns a deterministic queue UUID from authenticated workspace/user scope, route, and stable request body. Exact retries therefore address the same durable queue row. It submits this identity on Session creation, replay-to, chart history, and existing queued operations. It polls only the matching returned job ID.

Mutating operation timeouts, lost responses, polling timeouts, and RECONCILE_REQUIRED results now remain explicitly UNKNOWN with the durable jobId. The frontend does not automatically cancel an uncertain mutation or claim that it failed. A retry of the same body reuses the same queue identity. Definitive HTTP refusals remain refusals, while an HTTP 5xx or transport timeout is treated as unknown. A queued response without a usable job ID fails closed. The database remains authoritative for queue idempotency, Session creation idempotency, and financial receipts.

## Confirmed observed-command dialect regression and correction

The shared frontend command builder previously always emitted BTL-TICK-EXECUTION-COMMAND-1. That is incompatible with an observed Session, whose frozen kernel expects BTL-OBSERVED-EXECUTION-COMMAND-1.

The frontend now selects the command wire format only from the Session artifact returned by the authenticated server. Local Sessions keep the legacy dialect; observed Sessions use the observed dialect; unknown metadata fails closed, and observed SEEK is refused because that kernel does not support it.

Queue admission now reads the Session payload within its authenticated workspace scope, verifies its canonical content hash, schema version, ID, and exact artifact, then validates the request using that persisted Session family. A client-supplied command tag cannot select the execution family. replay-to is likewise admitted only for a persisted observed Session. The worker's existing authoritative Session resolution and validation remain in place.

No engine kernel, deterministic reducer, or financial semantics changed.

## Method versioning acceptance candidate

The existing additive candidate remains in the working tree:

- Migration 022_product_method_versions.sql maps existing immutable Method rows to version 1 families without rewriting Method payloads, hashes, IDs, or Session pins.
- New versions append a new immutable Method payload and version mapping. Family revision and current-version changes use a locked, expected-revision compare-and-swap.
- Exact successor retries are idempotent; conflicting IDs/hashes and stale revisions fail closed.
- Archive/restore changes lifecycle metadata only. Archived Methods remain addressable by historical Sessions and are included on request.
- Existing catalog maximum of 128 rows is preserved. Every successor version consumes one slot because versions are immutable rows in tick_methods; archiving does not free capacity.
- The registered migration runner checks the migration filename/checksum and skips an already-applied matching version. The acceptance test now invokes it twice and checks no duplicate version mapping. The migration is additive and forward-only; a failed transaction rolls back atomically, and a later correction must use a new forward migration.

Tests were expanded for:

- Session pin preservation and original Method hash.
- Exact version retry without a duplicate.
- Two concurrent successors from the same expected revision: one winner, one stale response, and no partial version.
- Stale request, archive refusal for new Sessions, restore, legacy list visibility, and owner/foreign-workspace authorization.
- Member mutation refusal and revoked membership access.
- Official migration-runner rerun.

These PostgreSQL integration tests have not run. Therefore migration, trigger behavior, real concurrent CAS, tenant authorization, row counts, and Session pinning remain unaccepted until an eligible isolated PostgreSQL gate is available.

## Method analytics test coverage added

backend/tests/test_method_analytics_projection.py adds bounded synthetic projection cases for positive, negative, and breakeven completed positions across compatible Sessions; incompatible currency units; incomplete analytics; and the 4,096-event budget. It checks that account balances are not combined and cross-Session streak metrics are omitted.

The three unit cases pass. The aggregation-level fixture does not independently prove event persistence. A separate PostgreSQL-backed test now creates real synthetic Session commands and committed events for a win, loss, and breakeven, then checks the API projection. That database test remains unrun; the existing implementation reads committed event pages through _committed_analysis.

## Validation performed

| Check | Result |
|---|---|
| python3 -m py_compile on changed queue and backend test modules | PASS |
| git diff --check | PASS |
| npm run test:tick-alpha | PASS — queue transport outcomes, stable retries, unknown/reconciliation, and command dialect cases |
| npm run test:product-pages | PASS |
| npm run test:confirm-outcome | PASS |
| npm run test:phase18.8 | PASS |
| npm run lint | PASS |
| npm run build | PASS |
| Backend queue-contract unittest, pinned venv | PASS — 6/6 |
| Method analytics projection unit tests, pinned venv | PASS — 3/3; first run exposed an incomplete mocked Session artifact/hash, fixture corrected, rerun passed |
| Repository dependency lock check | PASS — 40/40 exact versions; pip check clean |
| Python syntax compilation of changed backend modules/tests | PASS |
| PostgreSQL migration/queue/Method/analytics acceptance | BLOCKED_RESOURCE_GATE — 33.65 GiB free and 4.47 GiB MemAvailable, below 36 GiB / 10 GiB |
| Hosted browser journey and six viewport screenshots | NOT RUN — PostgreSQL acceptance is blocked; no mocked screenshots substituted |

Annual SHA-256 and resource figures above were read directly from the local evidence path and host during this checkpoint. No financial command, replay, benchmark, deployment, or database QA write was performed.

## Working-tree delivery

The candidate remains uncommitted and unpushed because mandatory database and browser acceptance has not passed. Existing draft work is preserved. Changed candidate files include:

- Queue contract and server validation: backend/cloud/queue.py, backend/tests/test_research_queue_contract.py, backend/tests/test_research_queue.py.
- Method lifecycle acceptance tests: backend/tests/test_cloud_research.py, backend/tests/test_method_analytics_projection.py.
- Frontend queue and dialect handling: frontend/src/tickAlpha/client.js, frontend/tests/tick-alpha.test.mjs.
- Existing local Method-versioning candidate and frontend work remain intact.
- Protected untracked CP6A-8 files remain present and untouched.

## Decision

**HOLD — NOT ACCEPTED.**

The two P0 regressions have targeted frontend changes and mock regression coverage; queue backend contract tests pass 6/6 in the pinned venv. Method versioning and committed-event analytics acceptance still require a resource-eligible isolated PostgreSQL run; the hosted browser journey requires that backend gate plus real browser evidence. The exact PostgreSQL QA plan is recorded in CP6A-10-product-integration-pg-qa-plan-20261107.md. Account linking remains blocked by its separate owner decision. No source-rights classification was changed.

Next authorized gate: obtain a resource-eligible isolated QA PostgreSQL environment (≥36 GiB free disk, ≥10 GiB MemAvailable, swap 0), install/use the repository backend dependencies, and execute the queued backend, migration, Method-versioning, authorization, and analytics tests. Only after those pass should the hosted synthetic browser journey run.

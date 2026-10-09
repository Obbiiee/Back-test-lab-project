# Commands

V21-0 documentation/repository reconciliation: from backend run `python -m unittest tests.test_tick_timeline tests.test_tick_contract_spec tests.test_tick_storage_contract_spec tests.test_tick_evidence_access_contract_spec tests.test_precision tests.test_precision_policy tests.test_histdata_ticks tests.test_contracts -q` (88 existing methods); from root run `node backend/tests/verify_contract_vectors.mjs`; from frontend run `npm run test:repository`, `npm run test:ai-bundle`, `npm run ai:bundle` and `npm run ai:bundle:verify`. Verify preservation fingerprints, complete documentation-only diff, normal commit/push and actual GitHub equality/clean 0/0. Browser/product/build/database-service/full historical benchmark acceptance are not claimed by this readiness checkpoint. Future runtime work retains its applicable full gates; [existing Section 43](../docs/PRODUCT_SYSTEM_ARCHITECTURE_BLUEPRINT.md#v21-0-repository-reconciliation-and-fixture-first-readiness-evidence) owns readiness evidence.

Offline HistData tick seam: from backend run `python -m unittest tests.test_histdata_ticks tests.test_precision -v` (6 parser + 11 evaluator methods; authored fixtures only, no provider download). Full discovery with actual isolated PostgreSQL now includes 120 methods. Keep frontend/regression/lint/build/release, vectors and context/bundle gates; browser exempt while unmounted. Actual machine-local sample measurements belong to existing blueprint Section 42.8, not test fixtures or public raw data.

Local precision foundation: from backend run `python -m unittest tests.test_precision -v` (11 methods). Keep full backend discovery with isolated PostgreSQL, independent Node canonical vectors, frontend regression/lint/build/release and context/bundle gates. Browser exempt only while this module remains unmounted; [existing owner](../docs/PRODUCT_SYSTEM_ARCHITECTURE_BLUEPRINT.md#427-local-quote-evidence-foundation--implementation-checkpoint) records evidence and limitations.

Run in `frontend/`:

| Command | Protects |
| --- | --- |
| npm run build | Production compilation |
| npm run lint | Source lint/hook rules |
| npm run test:repository | Production/archive boundaries, compatibility/fixtures/config; single context authorities, phase gates, roadmap and bundle inclusion |
| npm run test:phase4 | Runtime retirement and legacy preservation |
| npm run test:phase5 | Manager/model/primitive/creation foundation |
| npm run test:phase6 | Selection/hit testing/drag/cancel/arbitration |
| npm run test:phase7 | Persistence/history/lock/visibility/storage safety |
| npm run test:phase8 | Core line/rectangle models, creation, geometry/editing, axis constraints, lifecycle, history and v1 restore |
| npm run test:phase9 | Fib levels/reversal, arrowhead, Text editing, Measure calculations, mixed history/v1 restore and interaction isolation |
| npm run test:phase10 | Indicator registry/config, revealed-only frozen input, normalized output, warmup, error isolation, replay/prepend/timeframe, series lifecycle and protected boundaries |
| npm run test:phase11 | SMA/EMA/Bollinger vectors, bounds, warmup, causality, multi-output isolation and lifecycle |
| npm run test:phase12 | Wilder/EMA/Stochastic vectors, warmup/causality, official pane/reindex/reference lifecycle and isolation |
| npm run test:phase13 | Exact chart/Volume/seven-indicator/account differential equality, cursor semantics, malformed hint/recovery fallback, hidden mutation causality and playback acknowledgement/cancellation |
| npm run bench:phase13 | Non-gating CPU timing for 5000 revealed bars/seven indicators/100 steps and chart/indicator API operation counts |
| npm run test:phase14 | Canonical partial-exit grouping/completeness, financial/drawdown vectors, legacy issues, reconciliation, CSV UTF-8 roundtrip/download lifecycle, reset guards and persistence/hidden-input independence |
| npm run bench:phase14 | Non-gating alternating Analysis closed/open CPU comparison; same 5000 bars/seven indicators/100 steps, 500 exits, dependency-check timing and projection counts |
| npm run test:trading-separation | Independent Risk/Reward ownership |
| npm run test:trading | Order/position simulation |
| npm run test:drawings | Existing geometry/math regressions |
| npm run test:market | Aggregation and entire decade validation |
| npm run test:ai-bundle | Generator determinism/safety/staleness |
| npm run ai:bundle | Generate disposable root AI_BUNDLE |
| npm run ai:bundle:verify | Read-only hash/config freshness check |

Run full regression in master, not the partial bundle. Browser verification is required for product interaction changes; Phase 7 evidence and limitations: `docs/PHASE7_DRAWING_PERSISTENCE.md`.

Economic news: `npm run test:phase14.5` checks import/time/strict invariance/index/context/marker/navigation; `npm run bench:phase14.5` reports non-gating 10k/100k indexing/query/heap observations. Test-only `/tests/phase14-5.html` exercises real IndexedDB, file import, primitive lifecycle, replay integration and browser benchmarks on an isolated origin. [News report](../docs/PHASE14_5_ECONOMIC_NEWS.md) records evidence/limits. Retain full earlier-phase regression, lint/build and bundle gates.

Phase 7.5 no-behavior-change verification is recorded in `docs/PHASE7_5_REPOSITORY_CLEANUP.md`; disposable captures are ignored under `frontend/tests/artifacts/`. Backend tests are a standalone Python workflow, not proof of active frontend features.

Documentation-control changes must run test:repository and test:ai-bundle plus regenerate/verify the bundle. Product changes retain the full regression/browser requirements in [workflow](06_WORKFLOW_RULES.md). Phase 7.6 changes only context, roadmap, tests and bundle config; browser verification is exempt because no product/runtime/build path is modified.

Phase 8 product/browser validation and scope evidence: [checkpoint report](../docs/PHASE8_CORE_DRAWING_TOOLS.md).

Phase 9 product/browser validation: [checkpoint report](../docs/PHASE9_ADVANCED_DRAWING_TOOLS.md).

Phase 10 product/browser validation: [checkpoint report](../docs/PHASE10_INDICATOR_ENGINE_FOUNDATION.md). Test-only browser harness: `/tests/phase10.html` on an isolated dev-server origin; reference indicator never enters production UI.

Phase 11 product/browser validation: [checkpoint report](../docs/PHASE11_OVERLAY_INDICATORS.md). Test-only /tests/phase11.html observes real official series on an isolated origin; production uses the same overlay registry and controls. Synthetic volume exists only in the fixture.

Phase 12 browser/product evidence: [checkpoint report](../docs/PHASE12_INDICATOR_PANES.md). Test-only /tests/phase12.html observes actual official pane/series/reference ownership and revealed endpoints; all calculators remain pure.

Phase 13 browser/product/performance evidence: [checkpoint report](../docs/PHASE13_REPLAY_OPTIMIZATION.md). Test-only /tests/phase13.html uses real replay/playback/trading/chart APIs and compares all series with reference output. Run tests with frontend as their working directory; legacy drawing SSR fixtures depend on that root.

`npm run test:regression` runs every registered `test:` command except itself, failing on the first failure. `npm run test:phase16` protects storage preservation/bounds/foreign-write detection, legacy identity, randomized strict-news cache equivalence, logarithmic marker lookup and bounded source-security heuristics. Lint/build/browser/bundle/Git verification remain separate required gates. For disposable cold-build browser storage checks only: build first, then `node tests/phase16-built-server.mjs` (localhost 5194; optional numeric port argument). `/__qa__` seeds only this isolated origin; never use it on user data or publish it. Evidence: [Phase 16 report](../docs/PHASE16_QA_HARDENING.md).

Local release distribution: run `npm run build` then `npm run audit:release`. This separate gate checks 1.0.0 package/lock identity, installed chart version, build/catalog availability, byte-preserved shipped license files and exclusion of disposable QA seed code. It is not a substitute for full regression, browser checks or actual GitHub equality.

`npm run test:phase18.6` protects terminal collapse/compact/expanded limits, narrow viewport budget, keyboard restore/Shift/toggle and design-token normal-text contrast. Actual browser resize/modal/chooser/responsive evidence: [Phase 18.6](../docs/PHASE18_6_UI_UX_DESIGN_SYSTEM.md).

`npm run test:phase18.8` protects isolated prototype Method creation, risk/instrument constraints, Quick/Planned, checklist ON/OFF evidence, bypass/stale refusal, confirmation dedup and lifecycle restrictions. Open `/?trading-ux=prototype` on an isolated origin for browser QA; all sample state is memory-only. Contracts/evidence: [existing Method/Session owner](../docs/TRADING_METHOD_SESSION_SPEC.md).

`npm run test:phase18.9` protects single frozen handoff ownership, prototype isolation/default v1, immutable Method/request observations, inherited Session, stale/bypass refusal and preservation of confirmed requests through exit amendment. It complements full regression and actual browser evidence, not a production integration certification.

Backend foundation: from `backend/`, run existing Python environment `python -m unittest discover -s tests -v` (Windows existing venv: `venv/Scripts/python.exe`); includes all legacy backend tests and `tests/test_contracts.py`. From repository root run `node backend/tests/verify_contract_vectors.mjs` for independent standard-library golden bytes/hash checks. Fixtures are durable acceptance evidence. Full frontend regression/lint/build/release plus repository/bundle generation/verification remain checkpoint gates; browser exemption applies only to this explicitly authorized unwired foundation, not later API/UI integration. [Existing architecture evidence](../docs/PRODUCT_SYSTEM_ARCHITECTURE_BLUEPRINT.md#387-authorized-foundation-checkpoint--implementation-evidence) owns limitations.

Application intake: from `backend/`, `python -m unittest tests.test_application tests.test_application_transport -v` runs 14 new methods with scoped/concurrent/atomicity/Protocol/strict-wire/temporal cases; full discovery now runs 77 methods. Keep independent Node vectors and all frontend/repository/bundle gates above. Test doubles live only in backend/tests; no server or storage needed for new tests. Browser exemption applies only while handlers are unmounted, per [existing evidence](../docs/PRODUCT_SYSTEM_ARCHITECTURE_BLUEPRINT.md#389-applicationapi-intake--implementation-evidence).

PostgreSQL gate: configure **isolated** BTL_TEST_DATABASE_URL and BTL_PG_BIN/PATH, then from backend run `python -m unittest tests.test_postgres -v` or full discovery. Nine methods include real concurrency, rollback, scoped queries/CAS, append-only, least privilege, migration checksum and native dump/restore; absent DB causes explicit skips and is **not a release PASS**. Run a real server restart and compare canonical bytes before reporting persistence acceptance. Existing [system owner/runbook](../docs/PRODUCT_SYSTEM_ARCHITECTURE_BLUEPRINT.md#391-implemented-persistence-and-acceptance-evidence) describes safe empty-target restore. Keep full frontend and bundle gates.

Identity gate: with isolated BTL_TEST_DATABASE_URL from backend run `python -m unittest tests.test_identity -v` (nine methods); full discovery includes 95 methods. Windows QA/server uses selector event loop as in tests/cloud.serve, per Psycopg requirements. QA SMTP sink never sends mail. Missing DB skips are not PASS. Keep real PostgreSQL restore tests, frontend/regression/lint/build/release and bundle controls. [Existing identity owner](../docs/PRODUCT_SYSTEM_ARCHITECTURE_BLUEPRINT.md#401-implemented-identity-and-validation) owns TLS/runtime-role composition.

Ownership gate: same isolated real DB configuration, `python -m unittest tests.test_workspace -v` (eight methods); full discovery includes 103 methods. Tests cover every resource kind, hostile ownership input, owner/member/creator rules, revocation races, immutable identity/CAS/archive, bounded pagination, legacy refusal, exact Passport scope, concurrent durable nonexecuting intake, least-privilege native restore and restored private access. No skip counts as release PASS. Run full backend/frontend gates and actual server restart byte comparison; [existing final audit](../docs/PRODUCT_SYSTEM_ARCHITECTURE_BLUEPRINT.md#411-implemented-ownership-and-final-journey-audit) owns acceptance and browser scope.

Local policy: from backend run python -m unittest tests.test_precision_policy -v (13 methods); full discovery now runs 133 methods with real isolated PostgreSQL and no release skips. Read-only audit: python -m precision.policy --artifact <private-local-artifact.json> --sha256 <expected-sha256>. Keep price-bearing reports private. Full frontend, canonical vectors and repository/bundle controls remain required; browser exempt only while unmounted, per blueprint Section 42.9.

Local Tick Review: from frontend run npm run test:tick-review (18 Python-authored report pairs, canonical golden parity and hostile/bounded/race cases), plus full regression/lint/build/release and repository/bundle controls. Browser: isolated localhost /?tick-review=local with explicit artifact/report file selection; test status/reasons, pagination, refusal/reset, narrow/keyboard access, preservation and default/prototype smoke. Never commit private quote reports or provider files. Existing Section 42.11 records acceptance. Backend precision/evaluator/parser 30 tests and Node vectors passed; DB/auth code unchanged and full DB rerun exempt here.


Local historical delivery: from backend run `python -m unittest tests.test_market_data tests.test_precision tests.test_precision_policy tests.test_histdata_ticks -v` (39 methods). Node canonical vectors and frontend full regression/lint/build/release plus repository/bundle gates remain required. Actual local startup/HTTP validation and replay/cloud boundaries: existing blueprint Section 42.13. No frontend integration or DB/auth modification; browser-adapter/full DB rerun exempt here, not a cloud release certificate.

Tick contract freeze: from backend run `python -m unittest tests.test_tick_contract_spec tests.test_precision tests.test_precision_policy -v`, plus independent Node golden vectors. The new harness validates the single blueprint 42.15 synthetic matrix and existing exact/canonical compatibility only; it does not test an implemented provider/timeline/settlement. Run repository/bundle tests and regenerate/verify the bundle. No browser/full-release rerun is claimed for documentation/test-only work; future implementation must add actual behavioral acceptance.

Tick timeline implementation: from backend run `python -m unittest tests.test_tick_timeline tests.test_tick_contract_spec tests.test_precision tests.test_precision_policy -v` and full discovery. Section 42.16 records 21 synthetic acceptance methods; PostgreSQL/identity/workspace skips are not PASS. Keep Node golden vectors, frontend regression/lint/build/release, repository/bundle generation/hash verification and Git gates. Browser exemption is limited to this unmounted pure infrastructure; later UI/API integration requires actual browser validation.

Scalable V2 contract freeze: from backend run `python -m unittest tests.test_tick_storage_contract_spec tests.test_tick_timeline tests.test_tick_contract_spec tests.test_precision tests.test_precision_policy tests.test_histdata_ticks tests.test_contracts -v` and full discovery, plus Node golden vectors. Section 42.17 owns normative V2 layout fixtures and measured validation results. Oracle is test-only, not a disk provider or scalability benchmark. Run repository/AI-bundle tests, generation and hash verification. Browser/frontend product/build/full-release/database-service rerun exempt for this documentation/test-only checkpoint; explicit backend DB skips remain SKIP. V1 runtime and existing 42.15 fixture bytes must remain unchanged.

V2 sidecar reconciliation: from backend run `python -m unittest tests.test_tick_evidence_access_contract_spec tests.test_tick_storage_contract_spec tests.test_tick_timeline tests.test_tick_contract_spec tests.test_precision tests.test_precision_policy tests.test_histdata_ticks tests.test_contracts -v`, plus independent Node vectors, repository/AI-bundle tests and bundle regeneration/hash verification. Existing blueprint 42.19 owns the new normative access fixture. This is planning-oracle validation, not runtime conformance or a completed Exness benchmark; runtime drafts stay byte-preserved and benchmark must not resume. Browser/frontend product/build/database-service rerun exempt for documentation/test-only changes. Clean checkpoint conflict must be reported before committing, never concealed by skipping untracked files or mixing the runtime draft into planning.

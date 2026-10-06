# PF-0 Devil's Advocate Audit — v2 Alpha Plan Freeze

> **Verdict: FAIL — NOT YET SAFE FOR AUTONOMOUS JOURNEY AUTHORIZATION.**
>
> This is intentionally adversarial. The goal is to find every place where a competent implementation agent could make two different reasonable decisions, where an acceptance gate cannot be falsified, or where an older frozen authority can conflict with the new plan.
>
> No runtime implementation is authorized by this audit.

## Executive finding

The plan is directionally strong but is **not yet a true “plan your trade, trade your plan” contract**. It currently freezes architecture intent while deferring several material product/execution/operational decisions into implementation checkpoints. That would create hidden design work during execution.

The plan must not receive whole-journey autonomous authorization until all P0/P1 findings below are either:
1. resolved and frozen before implementation; or
2. converted into deterministic decision procedures with objective inputs, thresholds and fallback branches.

## Severity model

- **P0 BLOCKER:** autonomous execution can produce materially different financial truth, corrupt/lose evidence, violate rights/security, or cannot proceed without human design choice.
- **P1 MAJOR:** different competent agents can make different architecture/product choices or a gate is not objectively pass/fail.
- **P2 MODERATE:** maintainability/operability ambiguity likely to cause drift or rework.
- **P3 MINOR:** clarity/documentation weakness with low immediate correctness risk.

## Findings

### PF0-001 — P0 — Execution semantics are not actually frozen
Frozen Spec explicitly defers the exact execution contract to X-1. Open decisions include exact market fill semantics on discrete quotes, limit price improvement, stop activation/fill semantics, gap behavior, same-timestamp activation vs exit ordering, partial-exit rules, cost timing, slippage model, command revision/idempotency details and unresolved-state behavior.

**Why fatal:** X-1 becomes an architecture/product-design checkpoint, not mechanical implementation. Two agents can implement different P&L from the same ticks.

**Required resolution before journey authorization:** create a frozen Execution Semantics v1 spec with complete state machine, side/trigger/fill tables, total ordering rules, gap rules, cost arithmetic, precision/rounding, idempotency and golden examples. X-1 then becomes contract verification, not design.

### PF0-002 — P0 — Existing frozen Trading UX contract can conflict with new generalized Protocol wording
`TRADING_METHOD_SESSION_SPEC.md` is already FROZEN and more specific: Protocol is Planned, pending-only, categorical restrictions, explicit checklist behavior, intervention restrictions and existing workflow semantics. New Frozen Spec summarizes Protocol more broadly and could be read as allowing combinations the old contract forbids.

**Why fatal:** two “frozen” authorities can produce incompatible UI/domain implementations.

**Required resolution:** explicit precedence/reconciliation matrix. Preserve existing validated semantics unless a human-approved revision intentionally supersedes them. The new plan must cite exact inherited rules rather than restate them loosely.

### PF0-003 — P0 — Full-journey autonomy conflicts with current operational authorization model
`04_CURRENT_PHASE.md` currently has no authorized implementation phase and workflow says human authorization controls implementation. The Decision Register says a whole frozen journey *may* be authorized, but no exact authority state/representation exists for “continue checkpoint-to-checkpoint without asking.”

**Why fatal:** Work either stops after every checkpoint or violates current governance.

**Required resolution:** define a machine-readable JOURNEY authorization mode, scope, start/end, allowed automatic checkpoint advancement, hard-stop classes and revocation semantics in the existing sole authority file/schema. Do not create a second status owner.

### PF0-004 — P0 — Data-rights dependency can make external Alpha impossible while the ledger keeps progressing
Launch dataset/provider/license is unresolved. The ledger puts the rights launch gate near the end.

**Why fatal:** substantial product work could target a data mode that cannot legally be shown to the 5-user cohort.

**Required resolution:** split rights gates:
- early **DATA-MODE GATE** before provider-specific production integration;
- final launch re-verification before external cohort.
Freeze fallback: if redistribution/display rights fail, choose a predefined permitted provider/product tier or remain internal; do not redesign data semantics.

### PF0-005 — P0 — “Observed quote crossing” vs simulated fill truth is under-specified
Market Data Standard correctly says quote crossing is not broker fill proof, but Alpha promise says deterministic tick-evidence-based execution “when evidence is sufficient.” The plan does not freeze the user-facing epistemic labels between observed quote path, simulated execution under a profile and actual broker fill.

**Risk:** product could overstate historical precision.

**Required resolution:** freeze result taxonomy, e.g. OBSERVED_FEED_EVENT, SIMULATED_FILL(profile/version), UNRESOLVED, LEGACY_MODELLED; never label simulated fill as observed broker execution.

### PF0-006 — P0 — Financial arithmetic contract is missing
No complete frozen contract for:
- price scale;
- quantity/lot scale;
- money scale;
- account currency;
- contract size;
- tick size/value;
- rounding direction;
- risk-size rounding;
- commission denomination/timing;
- realized/unrealized P&L;
- conversion rates if non-account currency;
- margin/leverage treatment.

**Why fatal:** identical trades can produce different balances/risk sizing.

**Resolution:** freeze Alpha Instrument + Execution Profile + Financial Arithmetic v1 before engine implementation. For Alpha, deliberately limit unsupported currency/conversion cases rather than inventing them.

### PF0-007 — P0 — Same-timestamp uncertainty has no complete propagation policy
Plan says do not guess when equal-time ordering can change outcome, but does not specify whether:
- whole trade becomes unresolved;
- only an event is unresolved;
- session may continue;
- account remains blocked;
- research excludes trade;
- user can inspect but not settle.

**Resolution:** freeze uncertainty propagation through execution → account → journal → Passport → research.

### PF0-008 — P0 — Session backward navigation/branching remains explicitly deferred
Frozen Spec says backward navigation with committed trades should require reset/new branch/session “according to eventual UI command contract.”

**Why fatal:** this is a user-facing state/evidence policy still left for later.

**Resolution:** freeze one behavior now. Recommended conservative Alpha: committed financial session cannot rewind; user must fork a new session from an eligible earlier checkpoint with a new identity/lineage, or reset and explicitly discard uncommitted session evidence. No silent undo.

### PF0-009 — P1 — STITCH gates contain subjective language
Terms such as “acceptable performance,” “bounded integration,” “net custom-maintenance reduction,” “at least as well,” and “demonstrated benefit” have no scoring formula.

**Why important:** DT-DRAW still requires judgment, so it is not deterministic.

**Resolution:** freeze a weighted/non-weighted decision rubric with MUST gates and tie-breaker. Prefer binary MUSTs plus deterministic tie-breaker: lowest migration surface → lowest runtime dependency → lowest maintained custom LOC → current implementation.

### PF0-010 — P1 — Performance gates have no target envelope
The plan requires p95/p99, RAM/I/O, etc. but has no acceptable values, reference hardware or workload timing target.

**Why important:** no objective PASS/FAIL means DT-PERFORMANCE cannot choose.

**Resolution:** establish Alpha SLO/capacity budget before implementation, or define a calibration checkpoint that produces the budget from named low-cost target hardware and then freezes it before architecture-sensitive work. Calibration cannot itself choose architecture.

### PF0-011 — P1 — Release cohorts lack observation/sample gates
“healthy observation window/sample” is undefined. Five users could advance after five minutes or five weeks.

**Resolution:** freeze minimum evidence per cohort: e.g. completed sessions/trades/replay-hours plus minimum elapsed window and zero unresolved severity threshold. Values must be chosen before journey authorization.

### PF0-012 — P1 — Severity-1/2 defects are referenced but not defined
Release gates mention severity without taxonomy.

**Resolution:** freeze severity definitions with examples for financial correctness, data integrity, security, data loss, availability and UX.

### PF0-013 — P1 — OSS versions/commits/licenses are not pinned in the frozen plan
STITCH-0 records repository-level observations, but autonomous execution can see a changed upstream HEAD.

**Resolution:** before each donor spike, provenance checkpoint may resolve exact current tag/commit under predefined rule, but the rule must say whether moving upstream is allowed. Freeze candidate major/version or exact commit at PF stage where possible.

### PF0-014 — P1 — OpenAlgo-first ordering may bias toward a much larger chart migration
Decision tree tests OpenAlgo first and can select it if it passes, even if OpenCharts/current solution has materially lower integration cost.

**Risk:** “first passing” is not “best for product.”

**Resolution:** evaluate all three against the same rubric before selection. Deterministic ranking should favor satisfying Alpha MUSTs with minimum authority/migration surface, not maximum features.

### PF0-015 — P1 — Indicator semantics are not fully pinned
Current seven have implementation-specific seeds/warmups. Frozen plan says authored vectors but does not make formula/version owner explicit in new authority.

**Resolution:** freeze formulas, seed/warmup, missing-value behavior, precision/tolerance and timeframe input semantics by reference to existing tested authority or a dedicated calculator contract.

### PF0-016 — P1 — Tick→candle aggregation semantics incomplete
Missing complete policy for:
- bid vs ask vs mid chart price;
- bucket boundaries;
- empty buckets;
- session/calendar;
- first/last incomplete bucket;
- timestamp label;
- timezone/DST;
- volume semantics.

**Resolution:** freeze Aggregation v1 before M-6.

### PF0-017 — P1 — Trading calendar/session semantics are under-defined
XAUUSD broker feeds have weekends, maintenance gaps and provider-specific sessions. “Gap” cannot be classified correctly without a calendar/feed policy.

**Resolution:** freeze provider calendar metadata semantics; unknown calendar means gap explanation UNKNOWN, not outage/closed market.

### PF0-018 — P1 — Dataset completeness threshold is not frozen
Market Data Standard says completeness may remain unknown, but launch eligibility does not define what quality state is acceptable.

**Resolution:** define Alpha dataset acceptance classes separately for charting, replay and precision execution. Precision mode must have explicit required evidence.

### PF0-019 — P1 — Migration from v1 local state to hosted v2 is not fully decided
Drawings, account, journal, replay date, news and prototype data have different stores. “Preserve/migrate/refuse” is repeated but exact Alpha migration promise is not fixed.

**Resolution:** freeze per-store migration matrix. Conservative option: import only explicitly supported artifacts; v1 remains readable/exportable; never silently migrate financial truth.

### PF0-020 — P1 — Canonical event log durability/transaction boundary is unspecified
Need exact relationship among execution event append, account projection, session revision and DB transaction/outbox/retry.

**Risk:** crash can duplicate or lose financial state.

**Resolution:** freeze transactional invariant and recovery model before X-3/Q-2. Event identity/idempotency must survive process restart.

### PF0-021 — P1 — Worker concurrency model lacks ordering ownership
If replay worker and API/session commands race, no frozen single-writer/serialization rule exists.

**Resolution:** freeze per-session command serialization/lease/revision model. One committed order of financial commands/events per session.

### PF0-022 — P1 — Monte Carlo statistical contract is underspecified
“seeded Monte Carlo” lacks resampling unit, replacement policy, number of runs, path construction, ruin threshold semantics and confidence summaries.

**Resolution:** freeze MC v1 semantics before R-8 or move Monte Carlo out of Alpha MUST. Do not let implementation choose statistics ad hoc.

### PF0-023 — P1 — MAE/MFE definition is underspecified
Need side-aware price, spread, interval, open/close boundary and unresolved path semantics.

**Resolution:** freeze metric definitions or defer them.

### PF0-024 — P1 — No exact Alpha deployment target/cost envelope
Single-node topology is frozen but provider/OS/CPU/RAM/storage/cost ceiling is not.

**Risk:** performance gates cannot be interpreted economically.

**Resolution:** freeze a reference deployment class and monthly cost ceiling; provider may vary if equivalent.

### PF0-025 — P1 — Backup/RPO/RTO targets deferred too late
Recovery cannot be accepted objectively without targets.

**Resolution:** freeze initial Alpha RPO/RTO and backup retention before H-3.

### PF0-026 — P1 — Telemetry/privacy retention is unspecified
Logs/metrics can leak user strategy/order data or grow unbounded.

**Resolution:** freeze telemetry classification, redaction, retention and no-secret/no-sensitive-payload policy.

### PF0-027 — P1 — Security threat model is too generic
“A cannot access B” is necessary but not sufficient. Need CSRF/session, auth recovery, enumeration, rate abuse, upload/parser bombs, path traversal, dataset object authorization, SSRF if URLs appear, supply-chain and admin/support access assumptions.

**Resolution:** freeze Alpha threat model and required tests.

### PF0-028 — P1 — Test-command authority does not yet cover future checkpoints
Ledger says new checkpoints extend 07_TEST_COMMANDS, but autonomous execution could invent test naming/coverage differently.

**Resolution:** define test-family naming/registration contract now; each checkpoint may add exact commands mechanically but cannot waive mandatory families.

### PF0-029 — P1 — “One checkpoint per commit” vs practical atomicity is unclear
Some checkpoints may need multiple safe commits; current wording can incentivize giant commits.

**Resolution:** checkpoint may contain multiple atomic commits, but only one checkpoint completion marker; every intermediate commit must keep protected baseline recoverable.

### PF0-030 — P1 — Whole-journey continuation after a failed checkpoint is ambiguous
Decision Register says repair/retry, but no retry ceiling or escalation rule exists.

**Resolution:** freeze retry policy: unlimited reasoned code fixes is unsafe; define when repeated failure becomes hard invalidation (e.g. acceptance impossible under frozen contract, not arbitrary attempt count). Require root-cause evidence.

### PF0-031 — P2 — “Core drawings” wording can drift
Frozen Spec says core drawings while current disposition names eight.

**Resolution:** explicitly state the eight current drawing types are Alpha minimum unless donor provides compatible superset.

### PF0-032 — P2 — Economic news is KEEP but its role in Alpha is unclear
Could accidentally become a release blocker.

**Resolution:** classify as preserved non-blocking v1 capability unless v2 integration explicitly enters MUST.

### PF0-033 — P2 — Advanced research ledger wording is inconsistent
Work Execution Plan includes D10/D11/D12; Frozen Spec says advanced research should not delay first cohort; Frozen Ledger R-9 says defer by default.

**Resolution:** frozen ledger should clearly mark these POST-ALPHA and remove them from pre-Alpha critical path.

### PF0-034 — P2 — “Six months is enough for product Alpha” can be misread as a fixed dataset requirement
It is a product-validation statement, not data-quality/right requirement.

**Resolution:** define launch history as a configured product constraint chosen after rights/coverage evidence, with six months a candidate minimum only if it meets product acceptance.

### PF0-035 — P2 — No explicit accessibility baseline
Prototype has keyboard/focus work but Alpha release gate lacks accessibility minimum.

**Resolution:** freeze modest Alpha baseline: keyboard critical flow, focus visibility/restoration, labels, no inaccessible modal trap; deeper certification can remain post-alpha.

### PF0-036 — P2 — Browser/device support matrix missing
Without it, UI acceptance can expand endlessly.

**Resolution:** freeze supported Alpha browsers/viewports. Mobile native is excluded; narrow web fallback can remain best-effort if explicitly stated.

### PF0-037 — P2 — Dependency update policy missing during long autonomous journey
Pinned dependencies can age/security drift; automatic upgrades can destabilize.

**Resolution:** freeze policy: no opportunistic major upgrades; security-critical patches via bounded change checkpoint; donor versions pinned per migration.

### PF0-038 — P2 — Feature flags/cutover lifecycle incomplete
v1/v2 flag exists conceptually, but removal conditions are not fixed.

**Resolution:** freeze stages: hidden v2 → internal default → cohort default → v1 rollback retention window → explicit retirement checkpoint after evidence.

## Cross-document contradictions / ambiguity summary

1. New Protocol summary vs existing FROZEN Trading UX contract.
2. “Frozen” plan vs execution contract still designed later at X-1.
3. “Autonomous journey” vs current human-per-checkpoint authorization semantics.
4. Advanced research appears in broad plan but is non-blocking/deferred in frozen ledger.
5. Rights gate is late relative to provider-specific integration.
6. Performance/release gates request measurements without pass thresholds.
7. Storage/drawing decision trees still contain subjective selection terms.

## What is already strong and should NOT be reopened

The audit does **not** recommend redesigning:
- React/Vite;
- FastAPI;
- PostgreSQL;
- tick-native target;
- no OHLC precision settlement;
- immutable dataset identity/version/hash;
- one execution authority;
- canonical event log direction;
- durable small sessions / replaceable workers;
- Method/Protocol/Passport concept;
- adapter-isolated OSS;
- simple single-node-first infrastructure;
- progressive closed Alpha;
- no Redis/Rust/Kubernetes without evidence.

These are coherent and reduce the search space.

## Required remediation before PF-0 can PASS

Create/freeze, in this order:

1. **Authority reconciliation map** — especially Trading UX/Protocol and journey authorization.
2. **Execution Semantics v1** — complete financial state machine and golden table.
3. **Financial Arithmetic + Instrument/Execution Profile v1**.
4. **Uncertainty/result taxonomy and propagation**.
5. **Session command/rewind/serialization semantics**.
6. **Tick→Candle Aggregation v1 + calendar semantics**.
7. **Dataset quality/rights launch-mode gate** moved early.
8. **Objective STITCH scoring rubric** evaluating all candidates, not first-pass winner.
9. **Alpha SLO/capacity/cost envelope**.
10. **Release evidence thresholds + severity taxonomy**.
11. **Per-store migration matrix + v1/v2 cutover lifecycle**.
12. **Event-log transactional/recovery invariant**.
13. **Research metric contracts (MAE/MFE/Monte Carlo) or explicit defer**.
14. **Security/privacy/threat model + RPO/RTO**.
15. **Supported browser/accessibility baseline**.
16. **Dependency/update policy**.
17. Update Frozen Spec, Decision Register and Ledger only after these are internally consistent.
18. Re-run PF-0 adversarial audit. PASS only if no P0 and no unresolved P1 requiring human design choice remains.

## Final adversarial verdict

**DO NOT authorize STITCH-1, B1/42.18, or the whole implementation journey yet.**

The current plan is much better than an ordinary roadmap, but calling it fully frozen would be false precision. It still contains hidden design checkpoints and non-falsifiable gates. Fixing these now is cheaper than discovering them inside the execution engine, migration, or first external Alpha.

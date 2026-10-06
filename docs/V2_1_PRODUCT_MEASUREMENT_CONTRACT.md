# Backtest Lab v2 -> v2.1 Product Measurement Contract

Status: **PLAN-FREEZE / planning only — runtime remains unauthorized by this document.**

## 1. Version boundary

### v2 — usable, trustworthy Alpha product
v2 must be usable by the owner and closed-alpha testers without depending on the v2.1 analytics stack. It owns:
- tick-evidence replay/execution and existing frozen financial semantics;
- identity/workspace/session durability;
- bounded admission, queue, workers, DB, browser state and recovery;
- journal/basic research required by the frozen v2 Alpha spec;
- deployment/security/rights/recovery/capacity gates;
- **minimum operational telemetry and vendor-neutral product-event hooks** needed to operate safely and permit later v2.1 measurement.

v2 does **not** need a product-analytics dashboard, survey builder, session recording, marketing attribution suite, experimentation platform or PMF scoring UI.

### v2.1 — measurement & product-intelligence release
v2.1 turns the hooks into an analysis-ready product dataset. It owns:
- versioned event taxonomy and schema registry;
- funnel, activation, completion and abandonment measurement;
- D1/D7/D30 retention and cohort analysis;
- feature adoption;
- pseudonymous linkage between product events, cohort membership and voluntary feedback;
- workload/cost correlation using bounded operational aggregates;
- questionnaire delivery/response storage or a replaceable external adapter;
- export/query/dashboard surfaces;
- privacy, consent where required, retention, deletion and access controls;
- measurement QA and decision reports for later product planning.

v2.1 is observational. It MUST NOT become execution truth, alter deterministic financial outcomes, or block the financial commit path.

## 2. v2 instrumentation seam

v2 MUST expose a replaceable event sink interface. Product code emits typed events to that interface; it does not import a particular analytics vendor into replay/execution domain logic.

Minimum envelope:
- event_id (idempotent);
- event_name + schema_version;
- occurred_at UTC;
- pseudonymous actor_id when applicable;
- workspace_id/session_id only when necessary and authorized;
- app_release;
- anonymous/known cohort tag where applicable;
- bounded properties object from an allowlist;
- correlation_id for operational tracing when safe.

The sink MUST support no-op/disabled operation. Failure, slowness or unavailability of analytics MUST NOT fail an order, mutate financial truth, change replay chronology or prevent safe logout/recovery.

## 3. Minimum v2 events

Freeze the semantic hook names before implementation; physical storage may vary:
- auth_succeeded / auth_failed (bounded reason class only);
- workspace_opened;
- session_created / session_restored / session_completed / session_abandoned;
- replay_started / replay_paused / replay_seeked / replay_completed / replay_failed;
- order_command_submitted / order_command_refused / order_outcome_committed / order_outcome_unresolved;
- analysis_opened;
- research_metric_requested;
- queue_admitted / queue_rejected / queue_timeout;
- recovery_started / recovery_completed / recovery_failed.

Feature-use events for drawings/indicators/order types may be represented as allowlisted category identifiers rather than arbitrary payloads.

## 4. v2.1 derived product measures

At minimum:
- signup/login -> first session -> first replay -> first order -> completed session -> analysis-opened funnel;
- activation rate and time-to-first-completed-backtest;
- session completion/abandonment and abandonment stage;
- D1/D7/D30 retention;
- sessions and completed backtests per active user;
- adoption of drawing, indicator, order-type and research feature families;
- replay range, timeframe and speed distributions using bounded categorical/bucketed values;
- error/reject/unresolved rates;
- queue wait/reject rates;
- aggregate compute/storage/network cost proxies by workload class;
- questionnaire response rate and feedback themes.

No metric may reinterpret a financial event. Financial/research truth continues to come from canonical v2 evidence and Passport-owned calculations.

## 5. Questionnaire plan

Questionnaire is a v2.1 capability and MUST NOT block v2 release.

Prefer short, event-triggered or cohort-triggered surveys after meaningful use, not immediately after signup. Initial research questions:
1. ease of use (1-5);
2. trust in backtest result (1-5);
3. most useful feature;
4. most confusing/frustrating point;
5. most wanted next capability;
6. willingness to consider a paid plan and optional price band;
7. "How disappointed would you be if Backtest Lab were no longer available?" with a fixed response scale.

Free text is optional, separately classified as sensitive user-generated research content, excluded from ordinary logs/telemetry and governed by explicit retention/deletion rules.

## 6. Privacy and minimization

MUST NOT enter product analytics by default:
- passwords, auth tokens, cookies or secrets;
- broker/provider credentials;
- raw private provider market files;
- journal free text;
- complete private strategy/Protocol bodies;
- complete order payloads when stable IDs/reason classes suffice;
- precise unnecessary personal data.

Use pseudonymous internal identifiers. Analytics access is workspace/admin-authorized. Define retention and deletion before external Alpha collection. High-cardinality labels are prohibited from infrastructure metrics.

## 7. Open-source reference audit

Repositories are references/adapters, not automatic dependencies.

- PostHog: strong reference for event analytics, funnels, retention, paths and lifecycle. Its self-hosted stack is not a v2 prerequisite; adopting it must pass resource/privacy/license/deployment evaluation.
- Umami: lighter privacy-oriented reference for traffic/event/conversion analytics; evaluate if simple web/product analytics is sufficient.
- Formbricks: strong survey/experience reference. Core licensing is AGPLv3 with separate enterprise areas; do not copy/embed server code into Backtest Lab without explicit license review. Prefer API/standalone integration or our own minimal survey storage if selected.
- OpenTelemetry Collector: reference for vendor-neutral operational telemetry export. Product analytics events remain logically separate from financial truth.

Selection rule for v2.1:
1. first prove the vendor-neutral internal event contract;
2. benchmark operational cost on the selected Alpha host;
3. evaluate privacy/data residency and license obligations;
4. choose internal PostgreSQL-only, external/cloud adapter, or self-hosted adapter based on evidence;
5. no vendor may become a hard dependency of execution.

## 8. Cohort measurement

Existing closed-Alpha cohort progression remains authoritative. Measurement depth increases with evidence:
- earliest cohort: qualitative usability + instrumentation correctness;
- middle cohorts: funnel/abandonment/feature adoption + capacity correlation;
- later Alpha cohorts: retention, repeat behavior, survey patterns and unit-cost evidence.

A cohort may be held if instrumentation is materially incomplete or misleading, but analytics sink failure alone never corrupts or rolls back canonical financial state.

## 9. Devil's-advocate failure cases

The implementation must explicitly defend against:
- analytics outage blocking trading;
- duplicate client retries double-counting events;
- client clock spoofing changing canonical financial timestamps;
- event schema drift making cohorts incomparable;
- raw IDs/free text causing privacy leaks;
- cardinality explosion increasing VPS cost;
- session recording capturing strategies or credentials;
- bots/test accounts contaminating product metrics;
- one power user dominating aggregate event counts;
- survivorship bias from surveying only retained users;
- questionnaire fatigue;
- telemetry loss being mistaken for user abandonment;
- vendor lock-in;
- analytics DB growth exhausting the trading database disk;
- deleting analytics accidentally deleting canonical financial evidence, or vice versa.

## 10. Acceptance gates

### v2 gate
PASS only if:
- typed event sink and no-op path exist;
- event emission cannot mutate/block financial truth;
- operational/capacity telemetry required by existing contracts is present;
- event volume/cardinality/storage are bounded;
- privacy denylist tests pass;
- canonical v2 operation remains correct with analytics disabled/unavailable.

### v2.1 gate
PASS only if:
- schema registry/versioning exists;
- funnel and D1/D7/D30 definitions are reproducible;
- feature adoption and abandonment are queryable;
- feedback/questionnaire data can be linked pseudonymously where consent/policy permits;
- bot/test/internal traffic can be excluded deterministically;
- export/query path exists;
- retention/deletion/access controls are tested;
- analytics resource budget is measured;
- product metrics are demonstrably non-authoritative for financial truth.

## 11. Roadmap mapping

This contract is cross-cutting and does not renumber or falsely complete ROADMAP phases.
- v2 minimum hooks/operational measurement map to existing H-1/H-4/L gates and relevant identity/session integration checkpoints.
- v2.1 product measurement is a post-v2 bounded release that should be authorized separately before implementation.
- Later ROADMAP usage/resource metering, experiment tracking, administration and AI research may consume this evidence, but they are not implicitly authorized.

## 12. Change control

This document narrows the newly agreed version boundary; it does not activate runtime. Operational authorization remains solely in AI_CONTEXT/04_CURRENT_PHASE.md. Any implementation that requires analytics to participate in execution semantics is a material conflict and must stop.

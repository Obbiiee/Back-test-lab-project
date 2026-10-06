# PF-3 — v2/v2.1 Measurement Readiness & OSS Adversarial Audit

Status: **PASS FOR PLANNING AFTER REMEDIATION — RUNTIME NOT AUTHORIZED**

## Question audited
Can Backtest Lab ship v2 as a usable product, then add v2.1 as a serious product-measurement/data-extraction release without discovering that the required evidence was never captured or that analytics contaminates deterministic trading truth?

## Repository finding
Before this audit, the repository had strong operational/capacity telemetry, bounded-cardinality/privacy rules, closed-Alpha cohort gates and deterministic financial evidence. It did **not** have one normative owner for the newly agreed product boundary:
- v2 = usable product;
- v2.1 = product-measurement intelligence.

That omission could cause two opposite failures:
1. over-scope v2 with dashboards/surveys/analytics infrastructure and delay usability; or
2. defer instrumentation entirely, making early Alpha behavior impossible to reconstruct later.

## Remediation
Created [V2_1_PRODUCT_MEASUREMENT_CONTRACT.md](V2_1_PRODUCT_MEASUREMENT_CONTRACT.md) and froze ADR-MEASUREMENT-001.

The contract requires v2 to ship a vendor-neutral typed event seam and minimum operational/product hooks while leaving funnels, retention, questionnaires, product dashboards and product-intelligence extraction to separately authorized v2.1.

## OSS reconnaissance

### PostHog
Useful reference for event-based product analytics, funnels, retention, paths/lifecycle and later dashboards. Do not make self-hosted PostHog a v2 prerequisite. It adds operational footprint and vendor semantics that the core engine does not need.

### Umami
Useful lighter reference for privacy-first traffic/event/conversion analytics. It may fit basic web analytics better than deep research-product analytics. Evaluate in v2.1, not now.

### Formbricks
Useful reference for in-app/link survey targeting and questionnaire UX. Its core has AGPLv3 obligations and enterprise-licensed areas. Do not copy server implementation into Backtest Lab without explicit license review. Standalone/API integration or a minimal native questionnaire are safer decision branches.

### OpenTelemetry Collector
Useful vendor-neutral operational telemetry/export reference. It is not a product analytics database and must not become financial truth.

## Devil's-advocate pre-mortem

### P0
- **Instrumentation added only in v2.1:** early Alpha behavior is permanently missing. **Closed** by mandatory v2 event seam.
- **Analytics participates in financial execution:** outage/drift changes trading result. **Closed** by non-authoritative/no-op invariant.
- **Sensitive strategy/journal/auth data leaks into analytics:** **Closed at plan level** by explicit denylist and privacy gate.

### P1
- Event schema drift breaks cohort comparability -> schema_version + registry in v2.1.
- Duplicate retries inflate metrics -> event_id/idempotency semantics.
- Bot/test/internal traffic contaminates metrics -> deterministic exclusion required.
- Telemetry loss looks like abandonment -> health/ingestion completeness must accompany product interpretation.
- One power user dominates totals -> user-level/cohort measures, not raw event counts alone.
- Analytics DB exhausts small VPS -> separate bounded storage/resource budget and drop/backpressure policy.
- Session recording captures private trading methods -> not required; default absent.
- Survey only reaches retained users -> include abandonment/exit sampling where feasible.
- Vendor lock-in -> typed internal event contract before adapter selection.

### P2
- Questionnaire fatigue -> short, triggered surveys with exposure limits.
- Metrics vanity trap -> activation/completion/retention and qualitative causes prioritized over page views.
- Premature PMF claims at tiny cohorts -> early cohorts qualitative; later cohorts directional, not population-level proof.

## Version acceptance

### v2
Usable product plus minimum sensor layer. No product analytics dashboard or questionnaire is required for v2 completion. v2 must remain correct with analytics disabled.

### v2.1
Measurement-ready release. It must make event schemas, funnel, retention, feature adoption, abandonment, feedback, workload/cost correlation and export/query reproducible and privacy-bounded.

## Repository consistency
- Existing H-1/H-4 capacity telemetry remains authoritative for operational readiness.
- Existing financial/evidence contracts remain authoritative for execution truth.
- Existing Alpha cohort gates are not weakened.
- No numbered ROADMAP phase is marked complete.
- No analytics vendor is mandated.
- No runtime authorization is granted.
- AI_CONTEXT/04_CURRENT_PHASE.md remains the sole operational pointer and must still be null unless separately authorized.

## Verdict
**PASS FOR PLANNING.** The v2 -> v2.1 boundary is now explicit enough that a future Work agent can build v2 without analytics scope creep while preserving the evidence seam required for v2.1.

Re-open this audit only if:
- v2 event-hook implementation cannot be made non-blocking/bounded;
- privacy/legal requirements materially change;
- selected analytics/survey vendor imposes incompatible licensing or resource requirements;
- the product decides to require session recording or personally identifiable behavioral profiling.

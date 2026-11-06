# Backtest Lab — Scaling, Data & AI Architecture Decisions

> **Status:** Living architecture decision memory  
> **Purpose:** Menyimpan keputusan lintas-phase mengenai scaling, portability data, deployment profiles, dan AI architecture.  
> **Authority:** Bukan implementation authorization dan tidak mengubah phase status.

## 1. Two Independent Axes

**Roadmap phase = what can the product do.**  
**Deployment profile = how much workload can infrastructure serve.**

Phase number must not automatically dictate infrastructure size.

> **Design for scale. Deploy for current demand. Scale from measured bottlenecks, not from phase number.**

## 2. Deployment Profiles

### Profile S — Single Node

    Internet
       ↓
    Reverse Proxy / TLS
       ↓
    Single Server
    ├── Web
    ├── API
    ├── Research Worker
    └── PostgreSQL
            ↓
          Backup

Cheap and operationally simple while measured workload remains safe.

### Profile M — Separated Workloads

    Web / API
        │
        ├──────── PostgreSQL
        └──────── Queue
                    ↓
              Research Workers
                    ↓
              Object Storage

Separate DB, research compute and bulk storage when measurements justify it.

### Profile L — Distributed Scale

    CDN / Edge
        ↓
    Load Balancer
        ↓
    API ─ API ─ API
        │
    Redis / Queue
        ↓
    Worker Pool
        │
    PostgreSQL
        │
    Object Storage

Add horizontal APIs, worker scaling, managed DB, pooling/replicas, cache and CDN only when required.

## 3. Scale Triggers

Measure P95/P99 API latency, CPU, memory, DB connection pressure, slow queries, queue depth, jobs/hour, failures, candle throughput, storage growth, backup/restore duration, concurrent replay sessions and cost per active user.

Exact thresholds must be benchmarked with real workloads.

## 4. Data Ownership

Shared/canonical candidates:
- historical candles;
- ticks later;
- economic events;
- instrument metadata;
- dataset versions.

User/workspace-owned candidates:
- strategies and versions;
- protocols;
- experiments;
- replay sessions;
- opportunities/trades;
- journal;
- persisted drawings/preferences;
- research results/reports.

Do not duplicate full canonical market datasets for every user unless a private-data use case requires it.

## 5. Data Portability & Seamless Scaling Contract

1. Stable IDs across migrations.
2. Critical truth must not live only in one application server's RAM.
3. Multiple compute instances use canonical persistence.
4. Database schema changes use versioned migrations.
5. Experiments remain linked to exact dataset versions.
6. Large data/artifacts use storage abstraction rather than permanent coupling to one VPS disk.
7. Backup plus tested restore.
8. Verify important migrations with integrity checks.
9. Target safe minimal-downtime migration before premature zero-downtime complexity.
10. Product identity/domain must not depend on one infrastructure vendor.

## 6. Infrastructure Evolution

Start:

    Server 1
    ├── Web
    ├── API
    ├── Worker
    └── PostgreSQL

Then separate database if needed:

    App Server → Database Server / PostgreSQL

Then separate research compute:

    App → Queue → Worker 1 / Worker 2 / Worker N

Then horizontally scale APIs if needed:

    Load Balancer → API 1 / API 2 / API N
                         ↓
                 PostgreSQL + Queue

Core research/trading engines should not require conceptual rewrites just because process/server count increases.

## 7. Migration Strategy

    Current Infrastructure
            ↓
    Backup / Replication
            ↓
    Restore / Sync New Infrastructure
            ↓
    Integrity Verification
            ↓
    Final Sync / Controlled Write Window
            ↓
    Application / DNS Cutover
            ↓
    Observe
            ↓
    Retire Old Infrastructure after confidence window

Exact migration mechanics depend on database size and availability requirements.

## 8. AI Architecture

AI is a separate interpretive/orchestration layer:

    User
      ↓
    Backtest Lab
      ↓
    Deterministic Research Engines
      ↓
    Research Context Builder
      ↓
    AI Gateway
      ↓
    AI Model
      ↓
    Explanation / Hypothesis / Next Experiment
      ↓
    Human Decision

> **Deterministic engines calculate evidence. AI interprets verified evidence.**

AI is not the canonical calculator for WR, P/L, PF, expectancy, drawdown, Monte Carlo, FDR, RR execution, regime classification or execution simulation.

## 9. AI Gateway

Backtest Lab should use its own AI abstraction instead of scattering provider-specific calls through product code.

Candidate responsibilities:
- provider/model routing;
- request templates;
- structured tool calls;
- context limits;
- usage metering;
- quotas;
- retry/fallback policy;
- observability;
- cost accounting.

Target abstraction:

    Backtest Lab
         ↓
    AI Gateway
     ├── Model/Provider A
     ├── Model/Provider B
     └── Local/Specialized model later

Multiple providers are not required at launch.

## 10. Research Context Builder

Do not send the entire database to AI. Construct the smallest relevant evidence package from Experiment Passport, protocol/strategy versions, dataset/execution versions, selected trade summaries, verified statistics, Monte Carlo, regime, robustness, OOS, Research Integrity and relevant journal context.

Benefits: lower cost, lower latency, less unnecessary data exposure, clearer grounding and easier auditing.

## 11. Tool-Based Research Copilot

Future flow:

    User question
        ↓
    AI Research Assistant
        ↓
    Get Experiment / Protocol
        ↓
    Read Verified Results
        ↓
    Optionally request authorized research jobs
        ↓
    Receive deterministic results
        ↓
    Explain to user

Heavy jobs remain asynchronous. AI does not bypass the research engine.

## 12. AI Scaling

AI workload should scale independently from chart/replay workload:

    Application
        ↓
    AI Gateway
        ↓
    AI Job Queue
     ├── AI Worker
     ├── AI Worker
     └── AI Worker
        ↓
    Provider API

This allows concurrency control, metering, quotas and provider rate-limit handling without freezing replay.

## 13. AI Data & Privacy Principles

- send only needed context;
- authorize workspace/user before context construction;
- never leak cross-tenant research data;
- never expose secrets in prompts;
- retain provenance of which results grounded an analysis;
- define provider/retention policies before production;
- core backtesting remains usable during AI outage.

## 14. Capacity Planning

Never claim a concurrent-user capacity before load testing representative chart/replay, candle delivery, save/resume, concurrent writes, analytics, imports, Monte Carlo, robustness and AI workloads.

## 15. Decision Summary

**Features:** Roadmap Phase 1 → 75.  
**Capacity:** Profile S → Profile M → Profile L, independently according to measured demand.

**Data:** Canonical Data + Stable IDs → Portable Persistence → Replaceable Compute → Infrastructure can scale/migrate while user/workspace/experiment identity remains stable.

**AI:** Research Engines → Verified Evidence → AI Context → AI Interpretation → Human Decision.

These principles should remain stable even when vendors, server sizes, queues or AI models change.


## 16. Infrastructure Upgradeability Principle

> **Start small, but never design ourselves into a corner.**

Backtest Lab may begin with inexpensive and simple infrastructure. A low-cost VPS, a single-node deployment and one PostgreSQL instance are acceptable when they match actual workload.

The constraint is architectural: simplicity today must not create a forced core rewrite tomorrow.

From the beginning, boundaries should allow these components to be separated or scaled independently when justified:

    Web
     │
    API
     │
     ├── PostgreSQL
     ├── Research Workers
     ├── Object Storage
     ├── AI Gateway / AI Workers
     └── External Integrations / CRM (e.g. Odoo)

Scaling may happen vertically first when that is the simplest and most economical choice, then horizontally when workload requires it.

User ID, Workspace ID, Experiment ID, dataset versions and Experiment Passport identity must not change merely because:
- server size changes;
- a component moves to another machine;
- additional workers/API instances are added;
- infrastructure provider changes;
- CRM/AI/storage providers change.

Before adopting an infrastructure component, ask:

> **If workload grows 10×, can this component be separated, replaced, or multiplied without a brutal migration or rewrite of the core product?**

This does not mean pre-building distributed infrastructure. It means preserving clean boundaries, portable data and replaceable compute while deploying only the capacity currently needed.

CRM systems such as Odoo should remain integration layers rather than the canonical store for Backtest Lab experiments, strategies, trades or research evidence.


## 17. Payment, Billing & Entitlement Architecture

Payment, billing, product access and CRM are separate responsibilities.

> **Payment collects money. Billing records commerce. Entitlements control access. CRM manages relationships. Core engines do research.**

Target boundary:

    User
      ↓
    Backtest Lab
      ├── Product Database
      │    ├── User / Workspace
      │    ├── Strategy / Experiment
      │    └── Research Evidence
      │
      ├── Billing & Entitlement Layer
      │          ↓
      │     Payment Gateway
      │
      └── Integration Layer
                 ↓
              CRM / Odoo

### Payment Flow

    User chooses an upgrade
            ↓
    Backtest Lab creates checkout
            ↓
    Payment Gateway processes payment
            ↓
    Gateway sends signed webhook/event
            ↓
    Backtest Lab verifies the event
            ↓
    Billing record is updated
            ↓
    Entitlements are recalculated
            ↓
    Authorized product capabilities unlock
            ↓
    CRM/Odoo receives relevant customer lifecycle event

The payment gateway confirms commerce events. It must not become the direct authorization mechanism for research features.

### Billing Records

Candidate billing data:
- internal customer/user/workspace reference;
- plan;
- subscription status;
- billing period;
- provider;
- provider customer/subscription/payment references;
- invoice/payment state where needed;
- timestamps;
- cancellation/renewal state;
- relevant webhook/event provenance.

Do not store raw card credentials in Backtest Lab.

### Entitlements

Product features should ask the internal entitlement layer whether access is allowed.

Conceptually:

    can(user_or_workspace, "monte_carlo")
    can(user_or_workspace, "rr_lab")
    can(user_or_workspace, "robustness")
    can(user_or_workspace, "extended_data")
    can(user_or_workspace, "ai_research")

Avoid coupling product code to questions such as:

    did_user_pay_using_specific_gateway_X()

This permits plans and access rules to evolve independently from a payment provider.

Potential entitlement sources may later include:
- Free;
- Pro;
- Research / Team;
- trial;
- promotion;
- admin-granted access;
- affiliate/coupon campaigns;
- other explicitly supported commercial states.

Exact plans, prices, quotas and commercial rules remain product decisions.

### Provider Portability

Payment integration should sit behind a provider adapter/billing boundary.

    Billing / Entitlement Layer
              │
       ┌──────┴──────┐
       ↓             ↓
    Gateway A     Gateway B

A future provider migration should not require rewriting Monte Carlo, RR Lab, Strategy Destruction, AI Research Assistant or other research engines.

### CRM / Odoo Boundary

Odoo/CRM may receive the business context needed for customer lifecycle, campaigns, support and relationship management.

Odoo must not be the canonical source of truth for:
- experiments;
- trades;
- strategies;
- research evidence;
- Experiment Passports;
- product authorization decisions.

If CRM is unavailable, core research and valid existing entitlements should not fail merely because CRM is down.

### Reliability & Security Principles

- verify payment-provider webhook signatures/authenticity;
- design webhook processing to be idempotent because events may be retried;
- keep an auditable event/billing history;
- never trust a browser redirect alone as proof of successful payment;
- use server-side authorization for paid capabilities;
- keep secrets outside source code;
- design reconciliation for missed/delayed provider events;
- define safe behavior for provider outages;
- test upgrade, renewal, failed payment, cancellation, refund and downgrade paths before production.

### Upgradeability Principle

Billing must obey the same infrastructure rule:

> **Start small, but never design ourselves into a corner.**

We may begin with one payment provider and a simple billing module. The boundary must still allow provider replacement, multiple plans, workspace/team billing and independent entitlement logic later without rewriting the research core.


## 18. Global Payment Provider Planning

> **Status:** Preferred planning direction, not implementation lock. Provider availability, pricing, supported jurisdictions and legal/compliance requirements must be re-verified before implementation or launch.

Backtest Lab should be designed for international SaaS distribution rather than coupling commerce to one Indonesian payment rail.

### Preferred Provider Direction

- **Global SaaS / subscription candidate:** Paddle, primarily because a Merchant-of-Record model can simplify international software sales, tax/VAT handling and subscription operations where supported.
- **Indonesia-local payment candidate:** Xendit as an optional secondary adapter when local rails such as QRIS, virtual accounts or local e-wallets materially improve conversion.
- **Future alternative:** Stripe or another international provider may be evaluated when availability, company structure, supported countries/currencies and economics make it appropriate.

These are provider candidates, not permanent architectural dependencies.

### Target Architecture

    Global User ──────→ Global Provider Adapter ──┐
                                                  │
    Indonesia User ──→ Local Provider Adapter ────┤
                                                  ↓
                                      Verified Commerce Events
                                                  ↓
                                           Billing State
                                                  ↓
                                        Entitlement Engine
                                                  ↓
                                      Backtest Lab Capabilities

The product must never ask a payment provider directly whether a research feature is authorized. Providers report commerce facts; Backtest Lab's internal entitlement layer decides product access.

### International-Scale Requirements

Before public paid launch, validate:
- merchant/company eligibility in the operating jurisdiction;
- supported customer countries and currencies;
- settlement currencies and payout mechanics;
- recurring subscription support;
- refunds, disputes and chargebacks;
- tax/VAT/GST responsibilities and Merchant-of-Record implications;
- invoice/receipt requirements;
- webhook authenticity and idempotency;
- subscription lifecycle semantics;
- payment failure/grace/downgrade behavior;
- reconciliation and audit trail;
- provider fees and FX costs;
- data-processing/privacy terms;
- prohibited/restricted business categories relevant to the actual Backtest Lab product and marketing claims.

### Provider Migration Contract

Internal billing records should preserve provider-neutral identifiers and state so that:

    Paddle → another provider

or

    Xendit → another local provider

does not require rewriting research engines, Experiment Passports, user workspaces or historical research evidence.

Provider-specific customer, subscription and transaction IDs should remain integration references rather than canonical product identity.

### Launch Principle

Start with the smallest provider set that serves the actual launch market. Do not implement multiple gateways merely for theoretical scale.

**Global-ready architecture does not mean global infrastructure on day one.**


## 19. Early Affiliate Placement & Ad-Free Entitlement

> **Status:** Monetization planning direction, not implementation authorization.

For the initial monetization stage, Backtest Lab may use a small first-party affiliate/sponsor placement for Free users instead of depending on a generic ad network.

### UX Principle

The trading/replay workspace is the product. Monetization must not obstruct it.

Candidate presentation:
- a compact native affiliate card/banner with an image and optional short copy;
- visible in a reserved, non-critical area of the Free workspace;
- no overlay on candles, drawings, order controls, replay controls, research results, or critical navigation;
- no pop-up/interstitial behavior during trading/replay;
- responsive placement must preserve usable chart space;
- clearly distinguish affiliate/sponsored content from product controls and research evidence.

### Entitlement Behavior

Conceptually:

```text
Free entitlement
      ↓
Affiliate placement may render

Paid / ad-free entitlement
      ↓
Affiliate placement does not render
```

The decision must come from Backtest Lab's internal entitlement layer rather than being hard-coded to a payment provider.

### Affiliate Link Model

Affiliate destinations should be managed as configuration/content rather than embedded throughout chart code. This permits partner/link/image/campaign changes without modifying the replay or research engine.

Track only the minimum analytics needed to evaluate placement performance, subject to the product's privacy/consent requirements.

### Research Independence

Commercial relationships must not alter:
- research calculations;
- backtest results;
- provider/broker comparisons;
- rankings or evidence presentation;
- Experiment Passport;
- research conclusions.

Affiliate/sponsored relationships should be disclosed clearly where applicable.

### Initial Commercial Strategy

At early scale, prioritize relevant direct affiliate/sponsor placements over building a complex advertising system. Generic ad-network inventory can be evaluated later from measured traffic and economics.

The intended exchange is simple:

**Free = core product access + unobtrusive affiliate/sponsor placement.**  
**Paid = deeper paid capabilities + ad-free workspace.**

Exact partner categories, creative dimensions, placement location, frequency, pricing and affiliate agreements remain future product/business decisions.


## 20. Odoo as Modular Business OS

> **Status:** Approved business-architecture direction, not implementation authorization.

Backtest Lab will use **Odoo as the preferred modular back-office / Business OS**, adopted only where it removes real operational work. The product must not become technically dependent on Odoo for research execution or real-time access control.

### Responsibility Boundary

```text
Payment Provider
      ↓ verified commerce event
Backtest Lab Billing
      ↓
Entitlement Engine ─────────→ Free / Pro capabilities
      ↓ asynchronous/integration boundary
Odoo Business OS
      ├─ Contacts / customer administration
      ├─ Invoicing / payment records
      ├─ Accounting / finance as edition and requirements permit
      ├─ CRM when useful
      └─ Additional back-office modules only when justified
```

Backtest Lab remains authoritative for:
- application identity/authentication;
- Free/Pro entitlements and capability authorization;
- usage metering;
- experiments, strategies, protocols and Experiment Passports;
- datasets/research state;
- replay and research engines.

Odoo must not become the source of truth for research evidence or be required synchronously to authorize an already-valid research session.

### Initial Adoption

Start small:
1. Contacts/customer administration;
2. Invoicing/payment records;
3. accounting/finance capability appropriate to the selected Odoo edition;
4. CRM only when customer lifecycle volume justifies it.

Do not enable HR, Inventory, Manufacturing, POS, Website, Marketing or other modules merely because they exist.

### Edition Decision

Odoo Community is the preferred low-cost starting candidate when its available capabilities are sufficient. **Do not assume Community contains the complete Odoo Accounting product.** At implementation time, re-check the current official Community vs Enterprise feature matrix, Indonesian localization/tax requirements, reporting needs, upgrade/maintenance burden and total cost.

If full accounting, localization, reporting, bank reconciliation, support or upgrade requirements make Enterprise materially safer or cheaper operationally, migration to Odoo Enterprise is allowed without changing Backtest Lab's product architecture.

Third-party/community accounting add-ons must pass license, maintenance, security and upgrade-compatibility review before production use.

### Integration Contract

Create an Odoo adapter/integration boundary rather than scattering Odoo-specific calls through the product.

Candidate synchronized business objects:
- customer/contact reference;
- invoice;
- payment/settlement record;
- refund/credit state;
- subscription/plan reference where useful;
- tax/fee information where appropriate;
- reconciliation references.

Synchronization should be idempotent, auditable, retryable and tolerant of temporary Odoo outages. Odoo downtime must not automatically revoke valid Pro access.

### Finance Principle

**Payment collects money. Billing records commerce. Entitlements control product access. Odoo operates the back office. Backtest Lab research engines produce evidence.**

Use Odoo aggressively where it saves commodity business-development work, but preserve replaceable integration boundaries around the unique Backtest Lab product.


## 21. RIKSORA Lean Execution & Unit-Economics Architecture — 2026-11-06

> **Status:** Owner-selected **planning direction** for a complete low-cost execution platform, consolidated here instead of creating a competing architecture file. **Not a production freeze, merge, deploy, schema migration, source license, or benchmark authorization.** `AGENTS.md`, frozen decisions, current-phase gates and the financial/data source contracts remain superior. Reviews of [Claude's PR #42](https://github.com/Obbiiee/Back-test-lab-project/pull/42) and Codex CP6A evidence inform this section. Items marked **RESEARCH/HOLD** are NOT adopted implementations.

### 21.1 Product architecture to build as one coherent backend

```text
Authenticated trader -> FastAPI modular API
   -> cheap read path (Session, chart, journal, job status)
   -> per-workspace admission -> PostgreSQL bounded durable research_jobs queue
   -> one replaceable QA worker initially (lease/heartbeat/recovery, per-Session ordering)
   -> immutable version-pinned Monthly Parquet market-data provider
      -> selectable DuckDB range/analytics and PyArrow bounded-batch adapters
      -> optional Arrow/NumPy trigger scanner [RESEARCH; exactness not assumed]
      -> existing causal controller + exact deterministic reducer [SOLE FINANCIAL AUTHORITY]
   -> atomic PostgreSQL command/receipt/event/current-state/checkpoint commit
   -> paginated journal/trade read models, observable job/usage meters
```

- **Keep:** existing React/Vite/Lightweight Charts, FastAPI, PostgreSQL, exact tick-native reducer and Bid/Ask, atomic timestamp groups, no look-ahead, quality/gap/UNRESOLVED gates, immutable ledger and identical idempotent confirm outcomes. Avoid replacing engine or adding Redis/Celery/Kubernetes/Rust/extra databases without demonstrated need.
- **Reuse:** existing `btl.research_jobs` and migration 008/009 queue schema as starting point; do not create a second incompatible queue. Lease/claim, bounded backlog, expiration, per-tenant fairness, progress/status, safe cancel and recovery must be added/validated. Financial effects are committed exactly once by durable dedup, despite at-least-once job delivery. Read-only journal/status requests do not wait for heavy replay jobs.
- **One source, multiple readers:** immutable **Monthly Parquet** under provider/feed/instrument/version/year/month is the owner-selected experiment layout, **not a production-performance winner**. The owner's requested DuckDB monthly read path can coexist with PyArrow/NumPy on the SAME Parquet files, without duplicated market data. Choose the operator based on workload and measurements, not library labels. No new history download/convert/publish for a source without the required rights/admission.
- **Parquet correctness contract:** preserve full precision, quality/diagnostics, source ordinal and original ordering TRUST; do not sort an untrusted provider order into a trusted one. Version manifest binds source, coverage, rights, file hashes, row-group bounds, encoding, schema, timezone and price scale. Stable tick identity and forensic proofs remain compatible with frozen canonical event IDs until an independently accepted migration. A row-group hash alone is NOT proven a drop-in replacement for per-event semantics.
- **Parquet performance candidate:** start with ZSTD and integer bid/ask/ts plus validated group statistics; ~128k row-group records is an *initial hypothesis*, not a universal optimum. Read bounded ranges with explicit timestamp + ordinal ordering, preserve equal-time groups across batch/month boundaries, never materialize a whole month per Session.
- **Vectorized fast path [RESEARCH/HOLD]:** index first potentially state-changing trigger, source-quality issue, gap, diagnostic or ambiguous tie; preserve all mandatory chain/evidence effects. Process every candidate boundary via existing controller/reducer, fall back to normal chronological evaluation whenever the no-change proof is incomplete. No fast path may skip events solely because prices do not touch SL/TP. Identical canonical events, receipts, finance, cursor and cold recovery are acceptance requirements; 0.04 s synthetic scanner or any thousands-fold speedup is NOT a RIKSORA SLA.
- **Data for chart:** derive shared candle tiles once per pinned dataset; serve only the Session-authorized revealed prefix. Do not publish future candles, raw quotes, complete historical day files or unrestricted CDN URLs simply because the date is in the past. Check data redistribution/display rights independently.
- **Storage:** keep immutable command+event identity, existing durable financial commits and source pins. Pursue **versioned compact receipts/deltas + indexed recovery checkpoints + current projection**, reusing CP6A-5 QA-v3 evidence; retain exact retry response, reconstructible fork-at-revision, corruption detection, bounded cold recovery, and dual-read legacy compatibility. No arbitrary deletion of old checkpoints or fixed every-50-command policy without proof. Journal/trades become paginated derived read models (never an alternative financial authority); remove 32-order/128-order product caps only through a bounded compatibility design.
- **One product backend candidate:** reconcile PR #41 and Claude PR #39 contracts and the appropriate existing beta candidate by pinned diff and dependency plan, rather than merging incompatible branches blindly. Add minimal CI and reproducible deploy process. Frontend Claude owns UI; backend Codex owns finance/data/queue/runtime. Source licenses remain an independent release gate.

### 21.2 Build complete pipeline first, measure real economics afterward

Build through small reversible code commits with local checks and relevant golden regression tests, **not** a giant untested code drop. Defer exhaustive reader sweeps and user-capacity benchmarking until the complete synthetic QA pipeline is integrated. No new heavy benchmark on the current development host until its resource preflight passes.

Record cost units during normal operations:
- CPU seconds, wall time, number of source groups, worker busy/idle, actual RAM peak and cache residency;
- read bytes versus disk-device I/O, row groups touched, temporary spill, per-Session queue waiting p50/p95/p99 and cancellation;
- PostgreSQL command bytes, event bytes, receipt bytes, checkpoint and WAL/index delta, journal/trade incremental bytes, backup/restore overhead;
- admitted, queued, running and completed virtual traders **separately**. Scenario mixes (light/medium/heavy) are assumptions until measured.

**Hardware normalization (owner-selected):** 6 vCPU : 16 GB RAM : 200 GB SSD nominal; 1-vCPU proportional planning slice = 2.667 GB nominal RAM and 33.333 GB nominal SSD, not a physical per-worker reservation. Actual GiB, OS/DB overhead and measured p95 latency constrain usable capacity. Prefer one isolated worker for the first complete-system experiment; subsequent 2/4/6-worker tests require distinct resource and correctness gates. Do not infer 100 concurrently computing users from 100 accepted queue entries.

**Observed RIKSORA evidence, not extrapolated benchmarks:**
- CP6A-10: 298,662 groups and 108 completed trades, five candidates PASS; PyArrow Single 1,330.3 s wall versus DuckDB Single 1,502.7 s and DuckDB Daily 1,548.4 s in this **two-day** run. Monthly has not been tested.
- CP6A-9: shared canonical source reduced per-Session timeline allocation 84,520,960 -> 434,176 bytes (~99.49%) on the bounded one-day workload; exact limitations and parity are in its report.
- CP6A-5: isolated compact QA-v3 PostgreSQL growth 7,741,440 -> 3,858,432 bytes (~50.16%) on a 513-command/256-order scenario, with recovery and relevant financial regressions. This does NOT certify a production schema.
- HFTBacktest public *Accelerated Backtesting* documents ~109 s full versus 0.416 s accelerated, but acknowledges changed fill/latency semantics. It **cannot** establish exact-event parity for RIKSORA.
- DuckDB's public Parquet row-group microbenchmark reports 8.77 s at row-group 960 versus 0.87 s at 122,880 on an aggregation workload. It is a size-selection clue, not a monthly tick replay benchmark.

### 21.3 Review decisions still required — do not silently adopt

1. **Canonical identity:** replacing the existing per-event canonical commitment with only `(file, row)` + hash of a row group is **NEEDS-CHANGE** pending a proof of unchanged semantic identities, original ordinal/trust, auditability, cold/fork/recovery and data migration. Keep canonical identity unless independently proved equivalent and owner-approved.
2. **Fast path:** large performance wins are plausible, but hftbacktest's accelerated example loses some fidelity. Adopt only an *optional exactly-equivalent proof-gated* scanner with fallback until representative RIKSORA parity and end-to-end CPU gains are measured; do not market 260×/40,000× as measured RIKSORA performance.
3. **Storage policy:** compact QA-v3 is promising; neither checkpoint pruning nor short command receipts may alter immutable recoverability or identical durable retry responses. Select cadence and delta/index policy by bounded restore/fork measurements, not a fixed N.
4. **Rights/public distribution:** commercial and even free beta access to data is separate from an internal owner decision. Keep `UNKNOWN/NOT_GRANTED` until a sufficient data-source agreement/rights review supports the actual uses; do not make unlicensed files globally cacheable. Public price assets require a deliberate legal/repository cleanup plan, not automatic history rewrite.
5. **Scaling/claims:** one-core/100-user synthetic acceptance and RAM <85% do not alone prove comfortable SaaS capacity. Set queue depth, per-user fairness, p95 request and queue-wait targets, recovery and error budgets and then measure the entire pipeline.

**Review references:**
- [Claude architecture/cost audit PR #42](https://github.com/Obbiiee/Back-test-lab-project/pull/42)
- [Compact storage QA CP6A-5](https://github.com/Obbiiee/Back-test-lab-project/blob/codex/parquet-one-day-duckdb-20261105/docs/CP6A5_COMPACT_STORAGE_PERFORMANCE_2026-10-31.md)
- [Shared-source QA CP6A-9](https://github.com/Obbiiee/Back-test-lab-project/blob/codex/parquet-one-day-duckdb-20261105/docs/acceptance/CP6A-9-shared-source-report.md)
- [DuckDB Parquet performance/row-group benchmark](https://duckdb.org/docs/current/guides/performance/file_formats)
- [HFTBacktest accelerated versus full comparison](https://hftbacktest.readthedocs.io/en/latest/tutorials/Accelerated%20Backtesting.html)
- [Parquet on-disk checksums/specification](https://github.com/apache/parquet-format)
- [RFC 6962 Merkle inclusion and consistency proofs](https://www.rfc-editor.org/rfc/rfc6962)
- [PostgreSQL `SKIP LOCKED` queue semantics](https://www.postgresql.org/docs/current/sql-select.html)
- [Dukascopy terms of use](https://www.dukascopy.com/swiss/english/legal-pages/terms-of-use/)

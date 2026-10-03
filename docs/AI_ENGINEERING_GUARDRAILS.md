# AI Engineering Guardrails — Backtest Lab Architecture & Code Contract

> **Status:** Repository engineering contract for AI-assisted implementation.  
> **Purpose:** Preserve architecture, correctness, security, maintainability, and research integrity while using AI to accelerate development.  
> **Authority:** This document constrains implementation quality. It does not authorize a phase or supersede `AI_CONTEXT/04_CURRENT_PHASE.md`, the roadmap, or workflow/Definition-of-Done authority.

## Core Philosophy

> **Start small, but never design ourselves into a corner.**

> **Complexity must be earned by evidence.**

> **AI may accelerate implementation. It does not lower the engineering standard.**

AI-generated code is production code once accepted. It receives no reduced standard because a model wrote it.

---

## 1. Architecture Boundaries & Domain Isolation

Backtest Lab follows a **Modular Monolith first** strategy unless measured evidence justifies extraction.

Separation of concerns is mandatory:
- presentation/UI;
- application/use cases;
- domain/business/research logic;
- infrastructure/data access/external providers.

Rules:
- UI MUST NOT execute raw database queries or contain canonical research mathematics.
- HTTP/API handlers are adapters/controllers: validate input, invoke application/domain services, and serialize responses.
- API handlers MUST NOT become the home of trading/research algorithms.
- Database/provider implementation details MUST NOT leak into domain contracts.
- Product Database, Research Compute, Billing/Entitlements, AI Gateway, and CRM/Integration remain logical boundaries even if initially deployed together.
- Future microservice extraction is an option, not a Day-1 objective.

## 2. Typing, Runtime Validation & Trust Boundaries

### TypeScript
- enable/maintain strict typing;
- avoid `any`; exceptions require explicit justification;
- prefer `unknown` for untrusted input until validated;
- do not bypass type safety with unsafe casts merely to silence the compiler.

### Python
- type hints are required for new/modified public function signatures and domain data structures where practical;
- schema/domain models should make invalid states difficult to represent.

### Runtime Validation

External/untrusted input MUST be validated at trust boundaries, including:
- HTTP payloads;
- query/path parameters;
- webhooks;
- file imports;
- external APIs;
- AI/tool structured arguments.

Use the project's approved schema-validation mechanism (for example Zod/Pydantic if/when adopted). Do not add a dependency solely because it is named in this document without checking existing project authority and dependencies.

Once validated and transformed into domain types, avoid redundant parsing throughout domain code.

## 3. Deterministic Research & Trading Invariants

Canonical research evidence MUST come from deterministic engines, not AI interpretation.

Implementation MUST preserve:
- no look-ahead;
- deterministic replay for identical dataset/protocol/seed/engine assumptions;
- reproducible research calculations;
- explicit execution assumptions;
- stable treatment of ambiguous intrabar cases according to the active model;
- Experiment Passport/version provenance;
- clear separation of observed results from statistical/model-based inference.

Never silently change a formula, execution assumption, seed behavior, dataset interpretation, or research definition.

Changes affecting research outputs require tests and explicit version/migration consideration.

## 4. No-Look-Ahead Contract

At simulated time `t`, trading/research logic may consume only information permitted by the active execution/replay model at `t`.

Forbidden examples:
- reading future candles to decide current fills;
- using completed higher-timeframe information before it was available;
- calculating indicators from future observations;
- selecting an episode using outcome information that the protocol says should be blinded;
- leaking future news/outcome labels into trading decisions.

Every new market/replay feature that can affect temporal information MUST include anti-look-ahead tests.

## 5. Database & Query Engineering

### Evidence-Based Indexing

Do NOT blindly index every `WHERE`, `JOIN`, or `ORDER BY` field.

> **Index from query patterns and EXPLAIN/benchmark evidence, not intuition alone.**

Indexes have write, memory, and storage costs.

### N+1 Prevention

AI-generated ORM/data-access code must be reviewed for N+1 behavior. Prefer explicit batching/eager-loading/join strategies when supported by measured access patterns.

### Scaling

Start with the simplest approved persistence architecture.

Do NOT introduce Redis, PgBouncer, read replicas, ClickHouse, TimescaleDB, Kafka, RabbitMQ, or equivalent infrastructure merely because future scale is imaginable.

Introduce infrastructure when:
1. a concrete workload requires it;
2. telemetry/benchmarking identifies the bottleneck;
3. simpler remedies are insufficient;
4. the operational cost is justified.

PostgreSQL/object storage remains valid until evidence says otherwise.

## 6. Heavy Compute, Async Jobs & Resource Limits

Expensive research workloads must not monopolize synchronous request handling.

Examples:
- large Monte Carlo runs;
- Strategy Destruction grids;
- robustness/parameter sweeps;
- large backtests/imports;
- portfolio simulations;
- report generation when expensive.

When such workloads exist, design them for appropriate async execution.

Heavy jobs MUST have appropriate:
- timeout/deadline;
- bounded concurrency;
- memory/resource limits where controllable;
- cancellation semantics;
- progress/state tracking where required;
- idempotency/retry semantics where applicable;
- protection against runaway loops and unbounded allocations.

Do not introduce a queue before there is a workload requiring one, but do not couple heavy compute so tightly to HTTP that later separation requires rewriting the research engine.

## 7. Error Handling

Do NOT blanket-wrap code in generic `try/catch` or `try/except`.

Prefer:
- typed/domain-specific errors;
- centralized boundary/middleware handling;
- actionable error messages;
- preservation of root cause for internal diagnostics;
- safe user-facing responses.

Examples of domain errors may include `InsufficientDataError` or `InvalidProtocolError`, but names should follow actual project conventions.

Never silently swallow exceptions.

Retries are allowed only when the operation is safe/retryable and retry behavior is bounded. Side-effecting retries require idempotency or equivalent protection.

## 8. Observability

Use structured, contextual logging appropriate to deployment maturity.

Useful context may include:
- trace/request ID;
- user/workspace ID when appropriate;
- experiment/job ID;
- operation;
- duration;
- outcome/error class.

Never log:
- passwords;
- session secrets;
- payment card data;
- API/provider secrets;
- raw credentials.

Measure before scaling. Candidate production signals include:
- p50/p95/p99 latency;
- error rate;
- worker queue delay;
- job duration/failure;
- memory/CPU;
- database query duration;
- connection pressure;
- cache hit rate if caching exists.

Specific vendors are implementation choices, not architecture requirements.

## 9. Security Contract

All implementation must comply with `docs/SECURITY_ARCHITECTURE.md`.

When multi-user resources are introduced:
- authorization is server-side;
- tenant isolation is deny-by-default;
- cross-tenant access tests are mandatory for protected resource paths;
- entitlement checks are server-side;
- AI tools cannot bypass authorization.

Security controls must protect the actual boundary, not merely hide UI.

## 10. Payment & Entitlement Boundary

Payment-provider state MUST NOT be treated as direct product authorization.

Flow remains conceptually:

    Payment Provider
          ↓ verified event
    Billing State
          ↓
    Entitlement Layer
          ↓
    Product Capability

Webhooks require authenticity verification and idempotent handling.

Research engines must not depend directly on a specific payment gateway.

## 11. AI Security & Research Boundary

AI may:
- explain evidence;
- summarize;
- compare;
- identify anomalies;
- propose follow-up experiments.

AI MUST NOT:
- become the canonical calculator when deterministic code exists;
- bypass tenant authorization;
- receive unnecessary secrets/private context;
- silently alter research results;
- convert model speculation into stored evidence.

> **AI may interpret evidence. AI must not be the source of truth for evidence.**

Treat model/tool output as untrusted until validated at the appropriate boundary.

## 12. Dependency Discipline

Before adding a dependency, the AI must:
1. check whether existing code/platform capabilities already solve the need;
2. explain why the dependency is needed;
3. consider maintenance/security/bundle/operational cost;
4. follow the current phase/workflow authority.

Do not install packages merely because they are popular or convenient.

Lock and review dependencies according to project tooling.

## 13. Backward Compatibility & Migration Discipline

Do not silently break persisted data or public/internal contracts.

Changes to:
- database schema;
- serialized experiment format;
- dataset metadata;
- Experiment Passport;
- API contracts;
- research-result schemas;
- billing/entitlement state

must consider migration and backward compatibility.

Migrations should be versioned, testable, and recoverable where appropriate.

Do not rewrite historical research provenance to make new code appear compatible.

## 14. Testing Contract

New/changed domain behavior requires tests proportional to risk.

Relevant layers:
- unit tests for deterministic math/domain logic;
- integration tests for boundaries/persistence;
- regression tests for previously fixed behavior;
- anti-look-ahead tests;
- security/tenant isolation tests when applicable;
- E2E tests for critical user flows;
- performance/benchmark tests where a performance claim or bottleneck is involved.

### Test Integrity Rule

**Never make a failing test pass by changing its expected result merely to match broken implementation.**

When a test fails:
1. determine whether implementation, specification, fixture, or test is wrong;
2. identify the authoritative expected behavior;
3. fix the correct layer;
4. document intentional behavior changes.

Changing expected values is valid only when the specification/authority intentionally changed and the change is explicit.

Do not delete, skip, weaken, or mock away meaningful tests merely to obtain a green suite.

## 15. Performance Claims Require Evidence

Do not claim a component is “scalable”, “fast”, “optimized”, or capable of a particular user count without relevant measurement.

Optimization workflow:

    Observe
      ↓
    Measure
      ↓
    Identify Bottleneck
      ↓
    Form Hypothesis
      ↓
    Change
      ↓
    Benchmark
      ↓
    Keep / Revert

> **Complexity must be earned by evidence.**

## 16. AI Code Execution Pipeline

All AI-generated implementation follows the repository's active workflow and phase authority.

Conceptual gate:

    AI CAN WRITE CODE
            ↓
    Architecture / Phase / Scope Contract
            ↓
    Strict Types + Runtime Validation
            ↓
    Deterministic & Security Invariants
            ↓
    Static Analysis / Lint
            ↓
    Unit / Integration / Regression Tests
            ↓
    Security / Performance Tests when relevant
            ↓
    Build / CI Gate
            ↓
    Required Review / Validation
            ↓
    Commit + Push according to repository workflow

A passing build does not override an architectural violation.

## 17. Direct Instructions for AI Coders

Before modifying code:
1. read the current phase/authority files;
2. read relevant architecture/security/research contracts;
3. inspect existing implementation before proposing replacement;
4. state/understand acceptance criteria;
5. preserve scope.

While coding:
1. respect module boundaries and existing folder authority;
2. do not duplicate an existing source of truth;
3. do not add dependencies without justification;
4. avoid `any`, unsafe casts, dead code, debug logging and hidden fallback behavior;
5. validate untrusted input;
6. preserve deterministic/no-look-ahead behavior;
7. write/update tests with implementation;
8. avoid unrelated refactors.

Before completion:
1. run the required test/regression suite;
2. run build/lint/static checks required by the repo;
3. inspect failures rather than masking them;
4. run security/performance checks when the change creates that risk;
5. verify working tree/scope;
6. commit and push validated work when required by the active repository workflow;
7. report baseline/final commit, files changed, tests performed, and known limitations.

## 18. No Silent Scope Expansion

AI must not use a feature request as permission to:
- migrate frameworks;
- replace the database;
- introduce microservices;
- rewrite unrelated modules;
- change product behavior;
- change research formulas;
- add infrastructure;
- redesign UI globally.

If an out-of-scope change is genuinely required, stop and surface the dependency/blocker for explicit authorization.

## 19. Refactoring Rules

Refactoring should preserve behavior unless behavior change is explicitly authorized.

For meaningful refactors:
- establish regression coverage first where practical;
- keep changes reviewable;
- avoid mixing broad cleanup with feature behavior;
- benchmark if performance is the reason;
- verify research outputs where domain code moves.

“Cleaner” is not permission to change scientific semantics.

## 20. Definition of AI-Assisted Engineering

Backtest Lab does not reject AI-assisted coding. It rejects **unverified coding**.

AI can increase implementation velocity dramatically. Human/product authority, deterministic tests, architecture contracts, security boundaries, and measured evidence determine whether that code belongs in the system.

The operating principle is:

> **Move fast through generation. Move carefully through validation.**

And the repository-wide standard remains:

> **Don't trust the claim. Test it.**

# Backtest Lab v2 Alpha — Capacity & Failure Hardening Contract v1

Status: **FROZEN PLAN CONTRACT**. Planning authority only; no implementation authorization.

## 1. Bounded work
Demand may exceed capacity; accepted heavy work may not. Expensive replay/data work passes rate boundary, authentication/scope, per-user quota and admission before entering a bounded durable queue and bounded worker pool. Queue saturation returns a stable 429/503 class response with retry guidance before heavy allocation.

## 2. Benchmark-derived capacity
H-4 certifies safe active replay count, worker count, global/per-user queue ceilings, DB connection budget/headroom, market-data cache budget, browser delivery budget and telemetry overhead. Production limits stay at or below measured safe capacity. A cheaper host requires its own benchmark and does not inherit the 4-vCPU/8-GiB result.

## 3. Memory invariants
Production memory is bounded by configured working sets, not total dataset/session-history size. No full v2 dataset object graph, dataset-scale in-memory duplicate/diagnostic collection, full revealed-prefix state response, unbounded browser history/cache, unbounded queue, or per-session dataset copy. Bounded pages, tie groups, indexed windows, small checkpoints and bounded caches are allowed.

## 4. Indexed resume and recovery
Session checkpoints bind immutable dataset identity/version/hash, execution/profile versions, cursor/index location, revision and lineage. Late-history resume/seek locates a bounded reconstruction point through index/checkpoint metadata and does not replay the complete prefix merely to position. Mass recovery uses bounded scheduling rather than simultaneous automatic resume.

## 5. Durable queue
The Alpha queue has global and per-user capacity, stable idempotent job identity, workspace/session scope binding, cancellation/timeout, exclusive worker ownership/lease or equivalent, crash recovery, fair scheduling, bounded durable representation and explicit lifecycle. A worker revalidates durable resource authority before protected execution; session id alone is never authority.

## 6. Database pressure
Use a bounded connection pool or equivalent manager, configured below PostgreSQL maximum with operational headroom. Rate limiting, telemetry, queue polling and recovery are included in load tests and may not create unbounded DB work.

## 7. Browser delivery
The browser is a bounded view/client, not the historical database or financial authority. Deliver bounded chart window/lookback, current projection, bounded event/trade pages and progress. Cache and request concurrency use explicit budgets and eviction/coalescing. Raw tick flood remains disabled by default.

## 8. Capacity telemetry
H-1 measures, with bounded cardinality: active/queued/rejected replay jobs and queue wait; worker/session CPU/wall/RSS where measurable; bytes/chunks read, cache hit/miss and events/sec; API latency/errors/timeouts/payload size; DB pool active/idle/waiting and query latency; node CPU/RAM/disk; deterministic mismatch and unresolved/refused counts; recovery outcome; browser delivery/window/performance proxy; privacy-safe cohort and cost measures.

Telemetry excludes authentication secrets, private raw provider files and journal free text by default. Its buffers and retention are bounded; non-critical telemetry degrades before financial truth.

## 9. Failure-injection matrix
H-5 verifies at least: process/worker loss around transaction boundaries; staged-write rollback; lost response followed by duplicate retry; two workers targeting one job/session; stale revision; DB unavailable/connection exhaustion; queue full; corrupt/missing market-data chunk or index/checkpoint; dataset-version mismatch; safe disk/permission pressure; interrupted publication; mass recovery; client cancellation; malformed/oversized input; telemetry sink unavailable.

Every case must result in fail-closed/no financial mutation, atomic rollback, idempotent prior-result recovery, bounded rejection, or deterministic restore. Partial financial commit and scope bypass are forbidden.

## 10. Financial crash atomicity
Dedup identity, canonical financial events, order/position/account projection, session revision/cursor and required evidence references obey the frozen transaction invariant. Failure injection at persistence stages proves only two durable outcomes: all required financial state committed, or none. Acknowledged committed financial truth retains the frozen RPO=0 requirement.

## 11. Dataset/provenance cutover
Active v2 sessions pin immutable dataset/version/hash and execution/instrument-profile identities. Replacement creates a new identity/session/fork as defined by frozen contracts; it never mutates evidence beneath an active session. Legacy visual/live/news sources cannot become v2 execution evidence through frontend composition.

## 12. Release gate
External Alpha requires applicable GAP-001..GAP-024 implementation evidence or justified N/A, zero open S0/S1/S2, H-4 capacity certification, H-5 failure matrix, H-3 restore drill, usable privacy-safe H-1 telemetry, and L-1 rights re-verification.

This hardens the existing ledger without selecting Redis, Kafka, Kubernetes, ClickHouse, microservices or other new infrastructure. Technology changes remain governed by the existing decision/change-control rules.

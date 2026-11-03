# 09 — Architecture Decision Register (ADRs) / No-Surprise Change Control

**Scope:** proposal for Design Freeze V1.0 review. Records decisions and rejects needless ambiguity, without claiming benchmark PASS. These decisions are subordinate to existing frozen product and financial authority.

## Locked decisions

| ADR | Decision (positive choice) | Rejected alternative / why | Proof / impact |
| --- | --- | --- | --- |
| ADR-001 | React+Vite + Lightweight Charts remains frontend for laptop, HP and PWA | Next.js rewrite or three separate frontend codebases | Existing repo integration preserved; responsive tests |
| ADR-002 | FastAPI **modular monolith** + PostgreSQL single financial write authority | microservices/Kubernetes/Redis first | Lower ops cost, atomic Session model, simpler recovery |
| ADR-003 | One canonical immutable tick dataset **shared across Sessions**; Session references dataset/version/manifest hash | full market copy to each trader, user-scoped OHLC/tick materialization | 0 dataset clones per user; disk delta measured |
| ADR-004 | Versioned `IndexedTickDataProvider` port between market storage and replay | reader-specific financial engine, PyArrow calls in reducer | Existing goldens unchanged across storage adapter |
| ADR-005 | Logical data partition per instrument/provider/version/UTC day; Parquet ZSTD priority candidate | unindexed one giant CSV, unbounded in-memory year | Day-v-month row-group physical benchmark decides |
| ADR-006 | One replay controller / one financial reducer for Play, Step, Seek and fixed 72h Jump | separate future-looking Jump executor and manual settlement | exact normal-vs-Jump event/ledger parity |
| ADR-007 | One Method to many single-instrument pinned Sessions; Free Style and Protocol inherited | separate trading-mode toggle per Session | existing canonical spec and UI flow |
| ADR-008 | Server Review then explicit Confirm for all accepted orders | clicking Buy/Sell instantly creates fill | refusal/stale/duplicate/idempotency test |
| ADR-009 | PostgreSQL immutable financial events + compact command receipt/current state + bounded recovery snapshots | storing replayed tick groups and per-tick positions per Session | old audit compatibility, session bytes per million ticks, cold restore |
| ADR-010 | Separate quote/account currency conversion feed pinned and point-in-time; do not broaden old Alpha XAUUSD wire | present-day FX conversion or treating JPY as USD | multi-FX goldens and historical feed refusal |
| ADR-011 | Free/Pro use identical price and financial truth; entitlement controls capacity | crippled Free engine or arbitrary session-trade limit | subscription negative/financial parity tests |
| ADR-012 | Versioned API/OpenAPI/fixtures and strict Codex backend vs Claude frontend ownership | undocumented API inference, shared silent edits | contract SHA pins, linked PR and E2E |
| ADR-013 | Single VPS until evidence proves saturation; cold cached partitions, bounded worker/pool | second VPS or 2TB purchase from guessed catalog footprint | one-VPS/S3 cost gate after real source benchmark |
| ADR-014 | Off-node encrypted backup, restore rehearsal, reachability-aware dataset/ledger retention | disk-only backup, deleting QA/source by rough GB | RPO/RTO and immutable hash restore evidence |
| ADR-015 | Installable PWA first; **Capacitor Android/iOS shell as the store-app packaging target after PWA parity** | rewrite React/financial logic in separate native mobile apps | mobile web/PWA QA then native lifecycle/deep-link/signing/store QA |
| ADR-016 | Point-in-time author-observed Opportunity Journal light fields; AI counterfactual later | pretending trade-only records capture every missed setup | no imaginary hypothetical fills |

## Ownership of physical choices (no rewrite permission)

These are **parameters**, not open-ended product requirements:

1. Parquet day vs month/row groups/ZSTD level: Codex selects from a **single pre-registered real-data benchmark**; result recorded as an ADR subdecision after passing canonical parity.
2. PyArrow reader vs DuckDB direct reader: select on real bounded random-seek/full-replay/RSS/latency/bytes. DuckDB may remain analytics-only; do not introduce a second market DB as a side effect.
3. Session snapshot cadence, codec and local cache/file-handle limits: measure actual bytes per Session and cold resume; tune without silently altering immutable ledger semantics.
4. SSD/local vs S3 remote canonical dataset: actual safe storage footprint, rights, restore, network and cost decide; interchangeable provider adapter. Second compute VPS remains a measured exception.
5. App store native shell: not part of installable PWA v1. A later packaging checkpoint decides based on distribution requirement and QA; all backend contracts remain stable.

## Design review explicit outstanding contracts

### A. Exact recovery snapshot and migration schema

Codex must define serializer version, stable source/cursor/event hash and prefix anchoring, post-commit atomic rollback, partial sessions, command-receipt compact form, checkpoint retention and old-session dual reader. Must show that `tick_commands` full replay result is not needed to reconstruct a lost market dataset and that idempotent exact command receipts still work. Benchmark chooses cadence, not semantic content. Test before changing existing stored bytes. **No full-year restart from genesis as the only recovery path.**

### B. 16-pair execution and historical currency conversion

Old XAUUSD Alpha contract remains frozen. Define versioned FX profile, feed/source hash, tick/lot/cost numeric semantics, conversion path to USD, quote-side policy, freshness, gaps, and time-bound quote lookup. Produce golden vectors for all quote currencies needed. Unsupported source yields visible refusal. No asset price/volatility assumptions.

### C. Canonical DataReader event/evidence parity

Adapter must preserve every existing V2 requirement: duplicate/tied events, metadata, source quality, sidecar evidence, bid/ask scale, time index/prefix hash and no future leak. A Parquet file smaller than SQLite is **not** proof of correctness or readiness. Published real source + original identity probes + same normal replay = required.

### D. Security, account linkage, distribution

Google/email account linking must require verified possession and prevent duplicates, with existing-user migration/explicit consent and threat model; production TLS and PWA update must prevent token caching. Paid release blocked until actual market-data licensing and payment idempotency are proved. These gates cannot be postponed merely because the UI looks ready.

## Versioning / migration contract

- Every source dataset has immutable version/manifest hash; correction publishes another version. Existing Session pins never silently switch.
- Every execution/profile/method revision changes through explicit version and new Method for material Protocol rule updates; no retroactive ledger rewrite. Schema migrations must be backward-readable, with backup and dry-run restore before cutover.
- API additive fields require versioned fixture and regenerated Claude client; breaking changes require new major route/schema, both-owner signoff and compatibility window. Deploy backend compatibility first, frontend reader second.
- Production data deletion/compaction requires restore and reachability audit and owner's explicit permission. An ordinary docs PR does not authorize migration/purchase/release.

## Change Request process — rare, explicit, evidenced

Only when a frozen invariant proves materially wrong or unsafe:
1. record failing real/canonical fixture and reproducible baseline commit;
2. classify safety, money, market quality, source-rights, performance, UX or cost;
3. enumerate one smallest compatible fix, one alternative and consequence of HOLD;
4. list all affected Method/Session/DataReader/API/UX/schema versions and migration/rollback;
5. name Codex and Claude reviewers, owner decision and new ADR version;
6. author regression tests and migration proof **before** changing runtime; submit linked PRs;
7. never silently redefine original event history.

Nonbreaking UI improvements and physical codec changes remain normal scoped PRs and do not require re-opening whole system design. Unknown unknowns are escalated through this process; they are not coded around speculatively.

## Formal signoff

`DESIGN_REVIEWED` requires README + 01–09, known source precedence, no contract conflicts, route-to-API coverage matrix, completeness review and owner approval. `IMPLEMENTATION_DONE`, `REAL_DATA_BENCHMARK_PASS`, `VPS_CAPACITY_PASS`, `PRODUCT_RELEASE_PASS` are separate later gates, never inherited from this document.

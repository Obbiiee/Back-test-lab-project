# CP6A-10 Product Integration V1 — Contract Map (working checkpoint)

Date: 2026-11-07 (updated)
Candidate branch: `codex/product-integration-v1-20261106`
Base: `codex/integrated-backend-v1-20261106` at `992ae61f6671814348b85f0c3e3d605f91f37de9`
Frontend input: PR #39 head `274d592e06a9a8afc2a7b7e2efdf09498da36a34`, based on PR #36 head `293c36b1209757e6ca79b736013aeeabffe18e5e`.
P0 frontend input: PR #41 head `eb66a646090a1b46253eebfa64ae6c0dabcdef06`, based on PR #39 head above.

This is a working acceptance map, not a production-readiness claim. PR #42 is advisory; PR #43 is architecture memory and neither overrides repository authority. The deterministic reducer, receipts, canonical source identity, and Annual PASS evidence remain unchanged.

## API and product flow

| Product area | Current contract / route | Status | Boundary or gap |
|---|---|---|---|
| Sign up, verify, password login/recovery | `/api/v1/auth/{register,login,me,verify,request-verify-token,forgot-password,reset-password,logout,logout-all,providers}` | IMPLEMENTED (fixture-backed) | SMTP delivery and hosted credentials/configuration are not live-verified here. Bearer token stays in frontend memory; frontend requires HTTPS. |
| Google sign-in and account linking | `/api/v1/auth/google/*` when all Google settings are configured | IMPLEMENTATION CANDIDATE; ACCEPTANCE PENDING | Link start requires an authenticated password account and fresh password proof; Google subject proof uses the existing OIDC/PKCE state. Matching email alone never links. Additive identity registry/migration and compatibility mirror are described in `CP6A-10-account-linking-contract-decision-20261106.md`; PostgreSQL migration/backfill, restricted-role and browser acceptance remain open. |
| Workspace | `/api/v1/workspaces`, `/api/v1/workspaces/{id}`, membership and resource routes | IMPLEMENTED | Server derives user and workspace scope; owner-only writes and member reads. |
| Workspace capability / entitlement status | `GET /api/v1/workspaces/{id}/capabilities` | IMPLEMENTED IN CANDIDATE | Authenticated DTO reports workspace role, role-gated product actions, configured providers, and NOT_CONFIGURED/SANDBOX_ONLY entitlement. Account UI displays the server status. It is informational; every operation rechecks authorization. No production entitlement is claimed. |
| Product shell / frontend route | PR #39 `AlphaProduct`, `AlphaShell`, `productRoute`, `TickAlpha`; PR #36 terminal/drawing/indicator modules | INTEGRATED SNAPSHOT | Candidate uses pinned PR snapshots; original Claude branches remain unchanged. |
| Method catalog/create | `GET /workspaces/{id}/research/catalog`, `POST .../methods` | IMPLEMENTED | Catalog is bounded to the existing 128-record catalog; Methods are immutable evidence. New family metadata binds a stable family ID to immutable versions without rewriting Method bytes or Session pins. |
| Method page/detail/version/lifecycle | `GET .../method-families?limit=&after=&includeArchived=`, `GET .../method-families/{familyId}`, `POST .../{familyId}/versions`, `POST .../{familyId}/lifecycle` | IMPLEMENTED IN CANDIDATE; DB ACCEPTANCE HOLD | Additive family/version catalog, immutable version rows, expectedRevision CAS, archive metadata and Session creation refusal for archived families. Old Methods are mapped to self-family v1. Existing `/methods` and Session wire pins remain supported. PostgreSQL migration and integration regression have not been run because current host is below the 36 GiB disk and 10 GiB MemAvailable QA gates. |
| Session create/replay/job | `POST .../sessions`, `POST .../sessions/{id}/commands`, replay/view/bootstrap/chart-history, `/jobs/{id}` and cancel | IMPLEMENTED IN CANDIDATE (synthetic build) | Queue is persistent, one worker. New tick and observed Sessions default to compact-v1; stored legacy/snapshot formats remain readable. Source remains server-pinned; historical rights UNKNOWN / execution NOT_GRANTED. Integrated compact-default regression remains pending. |
| Session list/detail/resume | `GET .../sessions?methodId=&limit=&after=`, `GET .../sessions/{id}`, `POST .../{id}/view` | IMPLEMENTED IN CANDIDATE | Hosted UI consumes cursor-bounded pages (hard 128-record ceiling); list returns metadata/revision and explicitly does not compute financial counts. Detail/view is the authoritative recovery path. No separate mutating resume action is required. |
| Instrument availability | Catalog `availability` v1 for synthetic-only source; observed catalog is server-owned source catalog | IMPLEMENTED WITH SOURCE LIMIT | Historical eligibility remains fail-closed. Unknown, incomplete, or rights-ungranted sources cannot be selected for execution. No fabricated 16-instrument availability. |
| Review / confirm / receipt | `POST .../reviews`, `POST .../sessions/{id}/confirm`, `GET .../sessions/{id}/commands/{commandId}` | IMPLEMENTED | Durable PostgreSQL receipt is authority. UNKNOWN stays UNKNOWN until receipt/status evidence resolves; retries do not create another command. |
| Journal | `GET .../sessions/{id}/journal/pages`, note POST | IMPLEMENTED | Bounded revision-pinned pages; financial projection is committed-event derived; notes remain separate mutable annotations. |
| Session analytics | Session detail/view analysis and `/summary` | IMPLEMENTED (bounded) | Read-only projections from committed events/state; exclusions and provenance remain explicit. |
| Method analytics | `GET .../methods/{methodId}/analytics` | IMPLEMENTED IN CANDIDATE (bounded projection) | Pools only completed committed positions with one identical profile/engine/currency unit and at most 4,096 total events. Never combines balances/equity or cross-Session streaks. Reports included/excluded Sessions; incompatible units or an over-budget sample return UNAVAILABLE. |
| Entitlements/capability | `/auth/providers`; optional sandbox billing routes only under explicit config | PARTIAL | No generally valid production entitlement/usage contract. Plan, quota and paid capabilities must remain unavailable unless the server publishes an authoritative DTO. |
| Multi-instrument source picker | Server-pinned single workspace/profile or admitted operator catalog | BLOCKED BY CONTRACT | `POST /sessions` does not accept a general instrument identity for the synthetic product flow. Do not offer a second instrument without versioned server contract and rights. |

## Changes made in this checkpoint

- Imported the PR #39 frontend snapshot and the PR #41 P0 frontend fixes onto the candidate branch only. No Claude branch was modified.
- Added authenticated, workspace-scoped Method list/detail and Session list routes. Pagination is capped at 50; the Session list includes metadata and revision only and marks financial counts `NOT_COMPUTED_ON_LIST`.
- Added an authenticated workspace capability DTO that explicitly reports no production entitlement unless only sandbox billing is configured.
- Updated hosted frontend loading to consume the paginated Method/Session routes with a 128-record fail-closed ceiling.
- Added bounded Method analytics over existing committed-event projections. Pooled trade metrics are server-derived; cross-Session balances/equity and streaks are intentionally not synthesized.
- The endpoint implementation does not mount a provider, execute replay, modify evidence, or calculate financial truth.

## Verification and remaining gates

### Account-linking candidate update — 2026-11-07

- The implementation candidate now includes additive migration `023_account_identities.sql`, verified-email/Google-subject backfill, explicit password-reauthenticated link start, authenticated identity-provider listing, and same-user Google login resolution. Full contract and rollback notes: `CP6A-10-account-linking-contract-decision-20261106.md`.
- `AlphaAccount` clears stale OAuth query parameters and in-memory credentials after a failed one-time exchange so the user can start again.
- New Session constructors and cloud factory fallbacks now select `compact-v1`; `snapshot-v1` remains an explicit server override, and persisted format dispatch keeps existing Sessions unchanged.
- Frontend `npm ci`, lint, production build, and the registered regression suite pass on the current workspace. Targeted observed-analysis unit tests pass 5/5; the changed backend journey test compiles. No PostgreSQL migration/backfill, role, concurrency, cold-recovery, or PostgreSQL-backed journey gate has run because the isolated PostgreSQL 16 binaries/cluster are unavailable. The Playwright product flow was updated to reconcile the exact durable receipt before Journal and Analytics, but was not run because its API/HTTPS test servers are unavailable.
- The database and browser gates in the Google row above remain open. This change is local candidate code; no production, hosted configuration, OAuth credentials, or annual/historical evidence was changed.

### Owner P0 implementation sequence — 2026-11-07

- P0-1: expanded `test_method_analytics_pools_positive_committed_synthetic_trades_only` into one authenticated HTTP/service journey covering Method, Session, review, durable receipt lookup, Journal, closed trade, and committed Method Analytics. The product Playwright runner now checks the receipt before navigating to Journal and Analytics. Both are implementation coverage only until the PostgreSQL/browser gates run.
- P0-2 is partial: the primary tick reducer bounds hot state to active orders; migration 024 adds an immutable, indexed, hash-chained terminal-order read model, committed atomically with events/checkpoints, plus order lookup and keyset page APIs. Synthetic 129-order projection and closed-fill detail regressions pass. PostgreSQL archive, retry, crash recovery, and observed-path production integration remain NOT RUN/open; the observed archive remains an isolated QA format.
- P0-3 is partial: new Sessions default to `compact-v1`; eligible observed sources now default to `shared-source-v2`. Durable monotonic frontier/recovery and periodic verified compact recovery bases still need integration and PostgreSQL acceptance.
- P0-4 remains open: Monthly Parquet is wired only through the server-pinned synthetic QA fixture, not a general rights-eligible source catalog/worker path.
- P0-5 is partial: observed statistics no longer reject offsets above 128, but the main tick analytics/journal 4,096-event limits and complete lifetime pagination/aggregation are not removed. Payment remains out of scope per owner direction.

- Frontend lint: PASS.
- Frontend production build: PASS.
- Targeted frontend tests for availability, confirm outcome, note drafts, TickAlpha transport, drawings, and indicators: PASS.
- Frontend full registered regression runner: PASS after creating the ignored local `backend/venv` from the repository's pinned `backend/requirements.txt`.
- Backend syntax compilation: PASS.
- New Methods/Session page PostgreSQL integration test: 1/1 PASS in a private PostgreSQL 16 cluster; pagination, membership isolation, bounded metadata and no financial counters on list were verified.
- Same private PostgreSQL test verifies Method analytics is authenticated, tenant-scoped, server projected, and does not combine balances; it is explicitly a zero-trade synthetic case.
- Private PostgreSQL auth/workspace tests verify capability DTO role semantics for owner/member and explicit `NOT_CONFIGURED` production entitlement.
- Hosted `tests.test_cloud_research`: 11/11 PASS in a private PostgreSQL 16 cluster, including the new page test, authenticated Session journey, durable receipt/idempotency, tenant isolation and bounded sequential synthetic cohort. The cluster stopped and the harness removed only its own temporary fixture.
- The first targeted run exposed a missing `Query` import; it was fixed before the passing reruns.
- Real browser account journey, six-viewport candidate screenshots, live SMTP/Google provider, account linking, Method lifecycle, and hosted operational configuration: NOT YET VERIFIED.
- Method analytics is implemented only for bounded, compatible synthetic Sessions; no positive-trade pooled fixture has yet been exercised through that endpoint.
- Candidate screenshots were not captured: the computer-use browser inventory was empty and the existing Firefox desktop process was left untouched after an isolated headless launch could not start. Vite QA server was stopped afterward.

Annual PASS and historical evidence were not opened for write and are outside this candidate diff. No benchmark, replay, deployment, or production service change was made.

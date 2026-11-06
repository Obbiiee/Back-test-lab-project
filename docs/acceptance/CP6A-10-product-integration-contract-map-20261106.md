# CP6A-10 Product Integration V1 — Contract Map (working checkpoint)

Date: 2026-11-06
Candidate branch: `codex/product-integration-v1-20261106`
Base: `codex/integrated-backend-v1-20261106` at `992ae61f6671814348b85f0c3e3d605f91f37de9`
Frontend input: PR #39 head `274d592e06a9a8afc2a7b7e2efdf09498da36a34`, based on PR #36 head `293c36b1209757e6ca79b736013aeeabffe18e5e`.
P0 frontend input: PR #41 head `eb66a646090a1b46253eebfa64ae6c0dabcdef06`, based on PR #39 head above.

This is a working acceptance map, not a production-readiness claim. PR #42 is advisory; PR #43 is architecture memory and neither overrides repository authority. The deterministic reducer, receipts, canonical source identity, and Annual PASS evidence remain unchanged.

## API and product flow

| Product area | Current contract / route | Status | Boundary or gap |
|---|---|---|---|
| Sign up, verify, password login/recovery | `/api/v1/auth/{register,login,me,verify,request-verify-token,forgot-password,reset-password,logout,logout-all,providers}` | IMPLEMENTED (fixture-backed) | SMTP delivery and hosted credentials/configuration are not live-verified here. Bearer token stays in frontend memory; frontend requires HTTPS. |
| Google sign-in | `/api/v1/auth/google/*` when all Google settings are configured | CONFIG-GATED | It is opt-in. Existing Google identity flow rejects email collision with a password account; authenticated account linking is not implemented. Do not enable a button as proof of provider readiness. |
| Workspace | `/api/v1/workspaces`, `/api/v1/workspaces/{id}`, membership and resource routes | IMPLEMENTED | Server derives user and workspace scope; owner-only writes and member reads. |
| Product shell / frontend route | PR #39 `AlphaProduct`, `AlphaShell`, `productRoute`, `TickAlpha`; PR #36 terminal/drawing/indicator modules | INTEGRATED SNAPSHOT | Candidate uses pinned PR snapshots; original Claude branches remain unchanged. |
| Method catalog/create | `GET /workspaces/{id}/research/catalog`, `POST .../methods` | IMPLEMENTED | Catalog is bounded to the existing 128-record catalog; Methods are immutable evidence. |
| Method page/detail | `GET .../methods?limit=&after=`, `GET .../methods/{methodId}` | IMPLEMENTED IN CANDIDATE | Read-only, cursor-bounded workspace endpoints. Hosted UI loads these pages with a hard 128-record ceiling. No edit/archive semantics yet: changing/deleting canonical Method evidence is forbidden by current DB contract. A version/successor and archive policy must be resolved before those routes are added. |
| Session create/replay/job | `POST .../sessions`, `POST .../sessions/{id}/commands`, replay/view/bootstrap/chart-history, `/jobs/{id}` and cancel | IMPLEMENTED (synthetic build) | Queue is persistent, one worker. Hosted source remains server-pinned; historical rights UNKNOWN / execution NOT_GRANTED. |
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
- Updated hosted frontend loading to consume the paginated Method/Session routes with a 128-record fail-closed ceiling.
- Added bounded Method analytics over existing committed-event projections. Pooled trade metrics are server-derived; cross-Session balances/equity and streaks are intentionally not synthesized.
- The endpoint implementation does not mount a provider, execute replay, modify evidence, or calculate financial truth.

## Verification and remaining gates

- Frontend lint: PASS.
- Frontend production build: PASS.
- Targeted frontend tests for availability, confirm outcome, note drafts, TickAlpha transport, drawings, and indicators: PASS.
- Frontend full registered regression runner: PASS after creating the ignored local `backend/venv` from the repository's pinned `backend/requirements.txt`.
- Backend syntax compilation: PASS.
- New Methods/Session page PostgreSQL integration test: 1/1 PASS in a private PostgreSQL 16 cluster; pagination, membership isolation, bounded metadata and no financial counters on list were verified.
- Same private PostgreSQL test verifies Method analytics is authenticated, tenant-scoped, server projected, and does not combine balances; it is explicitly a zero-trade synthetic case.
- Hosted `tests.test_cloud_research`: 11/11 PASS in a private PostgreSQL 16 cluster, including the new page test, authenticated Session journey, durable receipt/idempotency, tenant isolation and bounded sequential synthetic cohort. The cluster stopped and the harness removed only its own temporary fixture.
- The first targeted run exposed a missing `Query` import; it was fixed before the passing reruns.
- Real browser account journey, six-viewport candidate screenshots, live SMTP/Google provider, account linking, Method lifecycle, and hosted operational configuration: NOT YET VERIFIED.
- Method analytics is implemented only for bounded, compatible synthetic Sessions; no positive-trade pooled fixture has yet been exercised through that endpoint.
- Candidate screenshots were not captured: the computer-use browser inventory was empty and the existing Firefox desktop process was left untouched after an isolated headless launch could not start. Vite QA server was stopped afterward.

Annual PASS and historical evidence were not opened for write and are outside this candidate diff. No benchmark, replay, deployment, or production service change was made.

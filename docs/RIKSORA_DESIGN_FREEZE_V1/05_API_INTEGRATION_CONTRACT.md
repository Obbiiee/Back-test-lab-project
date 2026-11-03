# 05 — API / Frontend Integration Contract (Design-to-OpenAPI Handoff)

**Operational extension:** the detailed 19-endpoint backend ↔ Claude inventory, chart-object/indicator-instance CRUD/CAS, chart candles, error and QA fixtures is [17_CLAUDE_CODEX_API_ACCEPTANCE_MATRIX.md](17_CLAUDE_CODEX_API_ACCEPTANCE_MATRIX.md). Codex executes [B01](https://github.com/Obbiiee/Back-test-lab-project/issues/24) then [B08](https://github.com/Obbiiee/Back-test-lab-project/issues/31); Claude consumes the *actual generated OpenAPI SHA* in [Issue #21](https://github.com/Obbiiee/Back-test-lab-project/issues/21). No proposed endpoint is claimed existing without backend proof.

**Status:** contract blueprint for Codex+Claude. **Not** a generated OpenAPI file or claim that every planned endpoint exists. Existing operational authority and frozen domain/financial contracts control semantics. Codex must extract the real FastAPI OpenAPI from current composition, compare field-for-field, version DTOs and let Claude use exactly that schema.

## Existing verified route families in main (repo audit 2026-11-04)

- `backend/cloud/app.py`: `/api/v1/auth` (fastapi-users register/login/verify/reset, `GET /me`, `POST /logout-all`).
- `backend/cloud/workspaces.py`: `POST/GET /api/v1/workspaces`, `GET /{workspace_id}`, resource, membership and session review/confirmation routes.
- `backend/cloud/research.py`: `/api/v1/workspaces/{workspace_id}/research` with `GET /catalog`, `POST /methods`, `POST /sessions`, `POST /reviews`, `GET /sessions/{session_id}`, `GET /sessions/{session_id}/journal`, `POST /sessions/{session_id}/view|bootstrap|journal|confirm|commands`; `GET /jobs/{job_id}`, `POST /jobs/{job_id}/cancel`. Mutating ADVANCE/SEEK may be queued. They are not necessarily mounted/available on the production riksora.com instance.
- The isolated extended research-v2, Google and billing branches mentioned in architecture history **must be verified before assigning status**. No assumed `/api/v1/instruments` or `/api/v1/research` route.

## Integration contract decisions

1. Stable namespace `/api/v1`, exact object schemas with `schemaVersion` and immutable `contractVersion`/source/profile pins, HTTPS same-origin browser application.
2. Single verified identity, explicit workspace scope, server-authoritative role/entitlement/replay/profile/quotes/cash. Browser-provided financial totals, membership or dataset eligibility are not trusted.
3. All mutation requests use a generated `commandId` (UUID), `expectedRevision`, and canonical payload; exact retry returns original committed receipt, same commandId+different payload refused. User-initiated review is a **separate operation** from confirmation.
4. Never infer a failed financial commit from fetch timeout. `COMMIT_PENDING` and uncertain network outcomes demand inspect-by-command/job/session revision before allowing another submit.
5. Prefer bounded GET pages and restricted fields; a chart stream returns only candle history **already revealed by committed cursor** and authorized read-only context, never a public raw tick endpoint. Server honors body/page/cache ceilings from Alpha contract.
6. Time uses UTC ISO-8601 with explicit Z for display DTO, exact integer nanoseconds/string for matching quote source identity; numeric finance/tick/lot/amount use **canonical decimal strings or scaled integers**, not browser floats for truth.
7. Server errors provide machine `code`, plain `message`, current authoritative `revision` when safe, `requestId`, optional `retryAfterSeconds`/remediation and readable source availability. Error codes must not expose private tenancy/source internals.
8. Heavy work uses bounded `202 Accepted` Job receipt, explicit `GET job` state and `POST cancel`, no ghost spinner or uncontrolled client retry; backpressure 429 with Retry-After. Polling uses capped backoff and stops on logout/workspace switch.

## Proposed stable DTOs — write formal OpenAPI and golden JSON fixtures before UI coding

`Method`: `id`, `name`, `type: FREE_STYLE|PROTOCOL`, `rulesSnapshotHash`, `description`, `createdAt`, `archivedAt?`, `sessionCount`, `lastSessionId?`; Protocol includes immutable RR/risk/checklist/ON-OFF and refusal reasons.

`DatasetCard`: `symbol`, `status: AVAILABLE|PARTIAL|QA_BLOCKED|RIGHTS_BLOCKED|PLANNED`, `datasetId`, `version`, `feedId`, `coverageStartUtc`, `coverageEndUtc`, `eligibleIntervals`, `quality`, `executionEligibility`, `rightsDisclosure`, `profileId`; null/absent values never fabricated.

`Session`: `id`, `workspaceId`, `methodId`, `instrument`, `datasetId`, `datasetVersion`, `feedId`, `executionProfileVersion`, `initialBalance` decimal string, `accountCurrency: USD`, `revision`, `cursor`, `status`, `saveState`, `allowedWindow`, `pendingCount`, `openCount`, `closedCount`, `unresolvedCount`. No embedded full dataset or complete event history.

`OrderDraft`: `side: BUY|SELL`, `orderType: MARKET|LIMIT|STOP`, `plannedEntry`, `sl`, `tp`, `riskMode`, `riskValue`, `quantity`, `checklistObservations`, `methodRulesHash`. UI-only until server reviewed.

`ReviewReceipt`: `requestId`, `sessionId`, `expectedRevision`, `reviewHash`, `expiresAt`, `quoteTimestamp`, `sidePrice`, `profileVersion`, `resolvedQuantity`, `estimatedRiskAndCost`, `valid/REFUSED`; every edit invalidates the receipt. `ConfirmRequest`: original `reviewId` and `reviewHash`, plus `commandId` and expected revision.

`CommandReceipt`: `commandId`, `idempotencyHash`, `sessionRevision`, `result: COMMITTED|REFUSED|UNRESOLVED|QUEUED`, `cursor`, `events` bounded/links, `currentStateHash`, `sourceEvidenceRefs`. These are **target shapes** only; Codex maps them to existing BTL wire instead of silently replacing immutable receipts.

`Job`: `jobId`, `kind`, `state: QUEUED|RUNNING|SUCCEEDED|FAILED|CANCELLED`, `createdAt`, `progress?`, `resultRef?`, `errorCode?`. Do not interpret cancellation as rollback of a financial commit.

`AnalyticsSummary`: `scope`, `eligibleSessions`, `instrument`, `period`, `tradeCount`, `denominator`, `wins`, `losses`, `breakeven`, `unresolvedCount`, `winRate`, `expectancyR?`, `netRealized?`, `profitFactor?`, `maxDrawdown?`, `excludedReasons`, `comparabilityDisclosure`, `ledgerTipHash`. Valid null metrics are distinct from zero.

## Error/refusal matrix — Claude must present each honestly

| Condition | Contract action | User-visible UX |
| --- | --- | --- |
| 401 invalid/expired login | no financial action | redirect to login, keep local form draft only |
| 403 workspace/role/entitlement denied | do not expose existence of foreign resources | member/plan refusal with next allowed action |
| 404 private/nonexistent Session | no cross-tenant leak | session unavailable |
| 409 stale revision/idempotency conflict | inspect latest Session + command | "Session changed; review again" |
| 422 invalid geometry/precision/Protocol rules | no commit | field-specific correction |
| 429 queue capacity | Retry-After and bounded polling | queued/busy, no duplicate order |
| Dataset blocked / missing rights / missing FX feed | refuse or unresolved per existing contract | show exact evidence/availability limitation |
| Network timeout after mutation | **reconcile, not retry blindly** | "Checking whether the action completed" |
| 500/503 crash/outage | read-only safe state | preserve draft and report status |
| Same-time price ambiguity/gap | no invented fill | explicit research uncertainty |

## Frontend integration acceptance, in order

A. Codex exports actual versioned OpenAPI + error registry from the target backend branch; marks existing/missing endpoints; provides canonical JSON fixtures and immutable examples including refusal/queue. B. Claude generates typed client/mock from that pinned schema; no hand-coded invented endpoints/quotes. C. Independent contract suite tests required/optional schema fields, version mismatch and financial decimal precision. D. Browser runs full first Method → Session → Planned/Quick → Review → Confirm → Jump/Resume → Journal/Analytics; responsive viewports and duplicate/timeout/stale tests. E. Cross-account, logout/linked-identity and Free quota tests with actual isolated PostgreSQL and HTTPS. F. Pin exact commit and signed/hashed contract artifact in integration PR. Never auto-merge incompatible payload changes.

**OpenAPI filename to produce during implementation:** `docs/contracts/riksora-api-v1.openapi.yaml` via inspected actual FastAPI exporter; do not create speculative fake complete YAML in this design phase.

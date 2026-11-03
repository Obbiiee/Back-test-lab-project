# 06 — Codex & Claude Operating Agreement / GitHub Integration

**Objective:** one coordinated product, no parallel incompatible assumptions, no unsupervised production modifications. Founder is Product Owner; Codex is Backend/Data/QA implementer; Claude is Frontend/Responsive UX/PWA implementer. Independent reviewer verifies contracts and cross-system tests; nobody can silently override owner-approved Method/Session, finance or release gates.

## The four sources every AI must read FIRST

1. [this integrated design package](README.md) and current PR review; 2. [product design blueprint](../PRODUCT_DESIGN_BLUEPRINT.md), [frozen Method/Session](../TRADING_METHOD_SESSION_SPEC.md); 3. [financial/source/ops contracts](../V2_ALPHA_EXECUTION_FINANCIAL_CONTRACT.md), [market standard](../MARKET_DATA_STANDARD.md), [release gate](../V2_ALPHA_DATA_OPS_RELEASE_CONTRACT.md); 4. [current phase](../../AI_CONTEXT/04_CURRENT_PHASE.md), [workflow](../../AI_CONTEXT/06_WORKFLOW_RULES.md), [test commands](../../AI_CONTEXT/07_TEST_COMMANDS.md). Do not treat abandoned branches, stale chat quotes, unmerged Claude work or roadmap targets as deployed truth.

## Ownership and file fences

| Owner | Write scope | Read/review scope | Cannot do without joint approved CR |
| --- | --- | --- | --- |
| Codex | `backend/`, `deploy/` (scoped), server-side migration/test, docs/contracts provider-generated schema, QA receipts | `frontend/` for API needs | change Claude-owned visual/layout components or design tokens; rewrite existing financial reducer |
| Claude | `frontend/src/`, `frontend/tests/`, PWA manifest/worker/static assets within approved frontend path, UI storybook/mock/visual receipts | backend published OpenAPI/tests | change backend schemas, financial/execution rules, data sources, entitlement enforcement |
| Owner/reviewer | approve product/architecture changes and release/cost | all | no automatic PR merge or deletions without proof |
| Shared | `docs/RIKSORA_DESIGN_FREEZE_V1/`, versioned contracts, integration tests | read all | any update requires both owner-role approvals |

A change that touches both backend and frontend gets **two linked PRs** and an integration coordination ticket with exact dependency hashes. Source of truth for money is backend server only. Web or app never stores raw signed financial commands as offline replayable queue.

## Branch/PR convention

- Baseline: inspect branch, SHA, dirty/untracked files and preservation list; obtain up-to-date owner-approved base. No blind `git reset --hard`, checkout that overwrites worktree, rebasing others' unreviewed changes or force-push.
- Backend branch: `codex/<checkpoint>-<short-purpose>`; frontend: `claude/<checkpoint>-<short-purpose>`; design: `design/<purpose>`; QA: `qa/<purpose>`.
- One bounded implementation scope per PR. PR description contains **issue/goal**, applicable frozen authority, base/head SHA, changed-file allowlist, API schema version, source/dataset pins if used, actual commands and exit codes, screenshots at required device sizes, financial/hash parity, latency/RAM/disk numbers for performance claims, rollback, regressions, risks, reviewer and status.
- No direct push to `main` by agents for runtime. Owner/reviewer authorizes merge after green relevant gates. Every accepted checkpoint: separate normal commit/push, inspect exact remote equality and clean/known local state; no pretending CI equals real VPS proof.
- Keep failures, logs and source attribution; do not upload private raw tick files, licensed feeds, user data, secrets, production DB dumps or credentials to GitHub.

## Shared contract workflow (no conflicting concurrent edits)

1. **Contract first:** Codex publishes pinned OpenAPI DTO/error+revision fixtures or marks exact unavailable API as planned. Claude critiques use cases, mobile limitations and display requirements **before** runtime coding.
2. **Contract review:** freeze semantic interface; reject incompatible rounding, time, field optionality and error handling. Changes needing new fields use additive schema/version, deprecation window and old-Session migration proof.
3. **Parallel build:** Codex backend+DB/market adapter; Claude desktop+mobile+PWA against deterministic mock responses from Codex's canonical fixtures. Both reference same pinned contract commit.
4. **Integration branch/checkpoint:** Claude switches mock → live API client only after Codex publishes actual endpoint receipt and QA environment. Run all matching contract + user journey tests; negotiate a **new explicit contract revision** instead of patching one side silently.
5. **Review ownership:** Codex signs canonical finance/source and crash tests; Claude signs desktop/mobile/a11y/PWA; reviewer compares cross-boundary state and hidden assumptions; founder signs material product/cost/rights/release changes.
6. **Merge and release:** merge in dependency order, QA fixture then actual source, browser/device tests, VPS cost/capacity/restore; no release if rights/quality/security gates unresolved.

## Mandatory handoff message (from Codex to Claude)

```text
CHECKPOINT:
BRANCH / BASE_SHA / HEAD_SHA:
EXISTING VS NEW ENDPOINTS:
OPENAPI CONTRACT_SHA:
DATASET/PROFILE/QUALITY SUPPORTED:
METHOD/SESSION/PROTOCOL INVARIANTS:
EXAMPLE REQUEST/RESPONSE / ERROR_FIXTURES:
FINANCIAL GOLDEN RECEIPT HASH:
AUTH/ENTITLEMENT/OWNERSHIP:
KNOWN REFUSALS / UNCERTAINTY:
REGRESSION / DB / RECOVERY TEST COMMANDS:
FRONTEND INTEGRATION ACTION:
STOP/ROLLBACK CONDITIONS:
```

## Mandatory handoff message (from Claude to Codex)

```text
CHECKPOINT:
BRANCH / BASE_SHA / HEAD_SHA:
SITEMAP / ROUTE_IDS / SCREEN_STATE_VERSIONS:
ENDPOINT CONTRACT_SHA:
DESKTOP 1440/1024 and MOBILE 390/375/320, TABLET 768:
TOUCH/KEYBOARD/A11Y/PWA TESTS:
ORDER DRAFT/REVIEW/CONFIRM TRACE:
TIMEOUT/RECONCILIATION/RESUME TRACE:
FRONTEND TESTS / BUILD / BROWSER LOGS:
BACKEND API GAPS (field + reason, NOT demand to rewrite):
STOP/ROLLBACK CONDITIONS:
```

## Coordination guardrails

- GitHub PR/ticket = durable coordination; neither AI assumes another AI has seen chat. Every merge blocked when contract SHA differs from UI client fixture.
- Shared work is **document/contract-first, then PR discussion, then implementation**. One designated integration reviewer resolves any contract mismatch. A discovered non-causal UI issue is resolved in frontend; do not change backend money rules to match a mock.
- Unknown external sources/costs remain explicitly UNKNOWN with owner decision gates, never a chain of speculative "if" features.
- On error: stop, preserve exact failing fixture/report, issue concise blocker plus single minimal corrective step; no uncontrolled code-rewrite loop, no scope expansion and no background claims.
- AI is staff in this workflow, not an autonomous product owner or payment approver.

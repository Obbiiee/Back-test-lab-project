# Backtest Lab — Agent Instructions

## OWNER ADDENDUM — V1 INTEGRATION COMPLETION (2026-11-09)

The owner explicitly authorizes the repository-only completion of V1 coding on the existing PR #50/#51 integration path, including recovery of `AI_CONTEXT/04_CURRENT_PHASE.md` from its last valid Git version, an automated UTF-8 authority-document regression, targeted synthetic Parquet-to-replay integration checks, and a ten-run sequential real-backend/PostgreSQL disposable browser stability gate in GitHub Actions. This supersedes the earlier instruction to preserve the opaque phase blob. Preserve all frozen technical/financial contracts and all older phase-history entries. The authority file restoration must retain the latest valid decision from before corruption and prepend a dated factual checkpoint; it must not rewrite roadmap or create new architecture authority. Browser runs stay on isolated CI infrastructure and use the existing private disposable PostgreSQL harness. Still repository-only: no VPS/SSH, production, deployment, historical-source acquisition, provider-rights promotion, data deletion, Annual PASS changes, force push, or `main` changes. Synthetic fixtures establish software behavior only, never historical accuracy or commercial rights. Keep PRs draft and report external release gates honestly.

## OWNER ADDENDUM — PRIVATE BROWSER ACCEPTANCE (2026-11-09)

The owner explicitly authorizes continuing PR #50 with a reproducible browser E2E in GitHub Actions, installing pinned browser dependencies on disposable CI runners, preparing the existing private-staging configuration, and checking SSH connectivity to the named Sorabit staging host if local SSH configuration supplies it. This supersedes the repository-only restriction above only for those actions and only against an isolated private staging target. No production domain/data, production deployment, historical datasets, annual replay, capacity benchmark, force push, or `main` changes are authorized. Do not print or request private credentials. Deploy only after positively verifying that the SSH target is the dedicated staging host and that the candidate configuration cannot affect production. The current-phase file is an opaque binary blob at this checkpoint and must be preserved; record this limitation in the integration register rather than replacing it speculatively.

## ACTIVE OWNER DIRECTIVE — REPOSITORY-ONLY PRODUCT V1 BUILD (2026-11-08)

**Highest-priority operational instruction for Codex and other development agents.** The owner has stopped the old benchmark/QA-driven workflow. The current objective is to finish the complete RIKSORA Product V1 application **in the repository**, without assuming any VPS, old data disk, production service or QA environment still exists. A prior owner approval to benchmark, use SSH, run annual replay or clean a server is **not standing authorization**. Older roadmap, handoff and phase-history entries are historical when they conflict with this instruction. This section governs operational permission, not financial or causal semantics.

### 1. One authority per subject, not competing plans
- **Agent permissions / what to do next:** this root AGENTS.md.
- **Technical architecture and frozen financial/market-data invariants:** docs/PRODUCT_SYSTEM_ARCHITECTURE_BLUEPRINT.md plus its referenced frozen contracts. Do not create another technical authority.
- **Current implementation state and authorized phase:** newest dated entry at top of AI_CONTEXT/04_CURRENT_PHASE.md. Do not treat older dated notes as live VPS state or permission.
- **Exact Product V1 integration gaps and definitions of done:** docs/acceptance/RIKSORA-V1-FREEZE-INTEGRATION-REGISTER-20261108.md (implementation register, NOT architectural authority), tracked by GitHub issue #46 and P0 lifetime-order issue #47.
- **Long-term priorities:** existing docs/ROADMAP.md; historic handoff docs/AI_HANDOFF.md is a mailbox, not a current execution command. Older STOP/GO and QA test instructions cannot override this active owner directive.

### 2. What to do when the owner says "audit repo", "lanjut", or "kerjakan"
1. Check branch/ref, recent commits, PR #44 integration status, PR #45 architecture status, local/uncommitted work, and any concurrent Claude/Codex ownership. Never assume that a PR has merged, a VPS is up, or a checked-out branch is current.
2. Read this AGENTS.md, the current-phase header, Product V1 architecture freeze, and the existing V1 integration register. Inspect actual source/tests to determine **implemented / partial / missing**; documentation, mock tests and QA-only flags do not count as deployed product features.
3. Determine the **first uncompleted P0** prerequisite along the integrated customer journey, based on real code and the prioritized register. Cite concrete paths, dependencies, and the smallest buildable deliverable. Avoid new exploratory audits, competing roadmaps, and speculative redesign.
4. If the owner requests **"audit repo" only**, deliver a concise implementation matrix, precise next task and blockers; **do not** start benchmarks, destructive operations, or change code without a build instruction.
5. If the owner requests **"lanjut", "kerjakan", "integrasikan", or "bangun Product V1"**, implement the first ready P0 slice in source code on the existing authorized integration workflow, with bounded synthetic regression and a reviewable commit/PR. Then update the existing register/current-phase header with **measured** status. Do not only write another plan. Do not unilaterally merge, deploy or rewrite a different agent's work.
6. If work is blocked by missing VPS, commercial source rights, credentials, hosting, production data or a heavy acceptance gate, implement what is possible with fixtures and adapters; mark that specific gate **BLOCKED / PENDING FINAL ACCEPTANCE**, not the entire Product V1 engineering effort.

### 3. HARD boundary: repository-only until a NEW owner approval
**Allowed:** repository inspection, application coding/refactoring, API/schema/migration source files, frontend/backend integration, focused synthetic fixture unit tests, deterministic financial and no-look-ahead regressions, lint/type-check/compile/frontend build, diff review, branch commit and draft PR.

**NOT allowed from vague requests, old reports or agent initiative:**
- Any SSH, sudo, VPS/main/secondary server access, systemd, production/QA host commands, reinstall, filesystem cleanup, deployment, live database migration, or hosted-provider mutation.
- Any actual historical tick replay/backtest (multi-day, weekly, monthly, annual or smaller real-market QA), performance/CPU/RAM/storage/Parquet format benchmarks, concurrency/load/stress, 50/100 virtual trader cohorts, or uncontrolled test suites whose resource bounds were not inspected.
- Downloading, ingesting, copying, converting or reconstructing large historical datasets, PostgreSQL QA-cluster snapshots, giant evidence folders or new persistent QA artifacts.
- Background benchmark jobs, automatic performance tuning, experimental financial engines or a new infrastructure stack.
- Commercial historical use/right promotion, settlement from candles, bypassing source admission/entitlement, rewinding a previously revealed causal frontier, or discarding financial receipts/checkpoints.

**VPS reset/rebuild:** VPS availability, files, datasets, PostgreSQL cluster, credentials and production runtime are UNKNOWN until separately verified. Do not attempt to recreate old QA from memory or assume prior disks survived. Build code now; owner explicitly schedules deployment/staging and final acceptance later.

### 4. Bounded checks while coding
- Prefer the smallest relevant deterministic synthetic tests; preserve source, financial, tenant-isolation, crash/idempotency and no-look-ahead correctness. Review test scripts for historical reads, external I/O, data creation and resource usage **before executing**.
- A default individual test/check command should be bounded to **120 seconds** and use temporary fixtures with cleanup. If a test is potentially heavy or has unknown effects, inspect/limit it or mark **NOT RUN (requires owner approval)**.
- Do not automatically run broad catch-all test targets, all-engine sweeps, annual or sequential 100-trader functional cohorts. No hidden full dataset downloads or QA folders on the host.
- An acceptance claim requires its actual evidence. A passing unit test proves only that unit. No synthetic check establishes commercial market-source rights or live VPS readiness.
- **New Product V1 Sessions:** no 128 cumulative/lifetime trade/order limit. Migrate *terminal* orders to a versioned, indexed durable archive, while keeping bounded simultaneous active orders and per-command event count. Do not simply replace MAX_ORDERS with an arbitrarily huge integer or append every closed order to hot state. Preserve legacy formats and immutability.

### 5. Handoff and safe completion
- Work from **one existing reviewed integration path** where possible: PR #44 code candidate, PR #45 architecture/agent-control update, issues #46/#47 for unfinished slices. Do not manufacture worktree/branch sprawl. Compare before integrating Claude-owned frontend or another agent's changes.
- Each completion report: **what code actually changed; tests run + scope; tests NOT RUN; exact next P0 item; blockers; commit/PR**. Never call a feature complete based on an architecture document alone.
- Do not launch final benchmarks or perform VPS work as part of "finish feature", "audit repo", "continue" or "test". When Product V1 is functionally integrated, prepare one final acceptance checklist and STOP at an explicit owner approval gate for real-source, resource and deployment testing.
- This directive can be changed only by a **new, explicit owner instruction**, which must be recorded in this root AGENTS.md and the top current-phase entry, not buried in an old handoff.

## Authority
- Read the existing repository authority and current project state before changing code.
- Treat `docs/PRODUCT_SYSTEM_ARCHITECTURE_BLUEPRINT.md` and the existing AI context/authority documents as the architectural source of truth.
- Do not create competing architecture authority.
- Preserve frozen contracts unless the current checkpoint explicitly authorizes changing them.

## Market-data invariants
- Canonical tick evidence is the future execution authority.
- Never settle a trade from OHLC alone.
- Candles are derived data for charting, indicators, analytics, and research; they are not execution authority.
- Never invent an intrabar path or silently fall back to candle assumptions.
- Insufficient evidence must remain explicit as unresolved/ambiguous according to the frozen contracts.
- Preserve Bid/Ask, source precision, provenance, dataset identity, and ordering trust semantics.
- Do not turn source row order into trusted market sequence without evidence.

## No-look-ahead
- Provider, storage, index, and unrestricted sidecar capabilities remain controller-side.
- RevealedView/consumer must never gain future ticks, future gaps, EOF, unrestricted metadata, provider/storage/index handles, or equivalent future knowledge.
- Follow the frozen 42.17 and 42.19 contracts, including bounded sidecar access and causal clipping.
- Timestamp groups remain atomic.

## Repository safety
- Before implementation, inspect the actual repository state, relevant authority, branch/baseline, and working tree.
- If baseline, provenance, or ownership of existing changes is unclear, hard-stop and report instead of guessing.
- Never silently reset, clean, stash, discard, overwrite, or reconcile user/agent work.
- Preserve intentionally separated draft/worktree/branch state unless explicitly authorized to integrate it.
- Do not commit raw market datasets such as Exness or Dukascopy archives.

## Validation and completion
- Run only the targeted, bounded synthetic unit/regression checks, lint/build and specific golden vectors allowed by the active repository-only directive; heavyweight/unknown suites remain pending explicit owner approval.
- Review the complete diff before declaring completion.
- Do not claim runtime correctness, benchmark completion, or production readiness without the corresponding evidence.
- A partial benchmark is not a completed benchmark.

## Git workflow
- For a completed, validated implementation or freeze checkpoint, commit and push before stopping unless the checkpoint explicitly says otherwise or safety requires a hard-stop.
- Verify the intended local branch/HEAD, origin, and actual GitHub state after push.
- Verify clean working state and ahead/behind 0/0 when the checkpoint requires it.
- If those conditions cannot be achieved safely, hard-stop and report the exact blocker rather than fabricating cleanliness.

## Scope discipline
- Do only the authorized checkpoint.
- Do not opportunistically add execution, settlement, PnL, candle aggregation, frontend cutover, account mutation, infrastructure, or unrelated refactors.
- If a frozen contract must be changed to proceed, stop and request authorization.

## AI handoff
- Read `docs/AI_HANDOFF.md` when the user asks to work from the handoff.
- Treat it as an operational mailbox, not architecture authority.
- Follow the latest actionable instruction in CHATGPT → CODEX only when it is consistent with frozen repository authority.
- Write a concise result/blocker report in CODEX → CHATGPT after the requested work.
- Important architectural decisions discovered during work must still be recorded in the proper authority documents; the handoff file never replaces them.

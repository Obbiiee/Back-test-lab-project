# Backtest Lab — Agent Instructions

## ACTIVE OWNER DIRECTIVE — Claude owns frontend UX simplification (2026-11-08)

**Owner decision:** Claude has full creative and implementation ownership of RIKSORA Product V1 frontend/UI/UX. The current screens/mockups are references, not layout constraints: redesign or consolidate them when it produces a demonstrably simpler, clearer, responsive product. **SIMPLE BY DEFAULT: complex engine, simple interface.** Chart and primary action dominate; avoid competing permanent panels, repetitive wizards, excessive toggles, fake capabilities, and engineering jargon. Reveal advanced controls contextually; preserve accessible errors, risks, uncertainty, source availability and order status. Mobile gets a purpose-built experience, not a scaled desktop.

**Non-negotiable domain authority:** `docs/TRADING_METHOD_SESSION_SPEC.md`, `docs/TRADING_PROTOCOL_SPEC.md` (current authority notice), and `docs/PRODUCT_SYSTEM_ARCHITECTURE_BLUEPRINT.md` override older visual workflow mockups. Method type is `FREE_STYLE` or `PROTOCOL`, inherited by Session, not a separate per-trade toggle. Free Style supports Quick and Planned. Protocol is Planned-only **pending Limit/Stop**, never Quick or direct Market entry; locks RR and risk, requires at least one condition, checklist ON requires **all** conditions PASS while OFF retains observations without blocking, and discretionary manual close after a fill is prohibited. A chart planner must preserve locked RR/risk when geometry changes. No Session balance reset or future-data leak. Server review and explicit Confirm precede orders; financial execution/receipt/reconciliation remain backend-authoritative, including when response is UNKNOWN. A frontend-only CSS restriction is not protocol enforcement.

**Ownership and coordination:** Claude owns `frontend/` component/layout/navigation/accessibility implementation and can refactor it creatively. Codex owns API, identity, queue, storage and deterministic financial engine. Neither agent silently overwrites the other's active/uncommitted work. New DTO/API needs go in `frontend/docs/codex-api-requests.md` for Codex, not in a fake frontend financial fallback. Read the latest `CHATGPT -> CLAUDE / CODEX` handoff at the top of `docs/AI_HANDOFF.md`, then inspect active branch/PRs and actual current code before edits. Work through reviewable frontend code, focused regression, lint/build, browser screenshots/UX acceptance when a safe browser exists, and a PR; do not stop at a design document or assume a build alone proves UX.

**Boundaries:** This UI delegation does not approve touching VPS, historical data, production, benchmark loads, deployment, source-rights promotion, payment/monetization, or financial/causal contract changes. Repository-only source/test work; operational restrictions in the current authorized phase still apply. Mark unavailable acceptance honestly.

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
- Run the tests, lint/build, repository checks, golden vectors, and other gates applicable to the checkpoint.
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

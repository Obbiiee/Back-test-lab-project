# Backtest Lab — Agent Instructions

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

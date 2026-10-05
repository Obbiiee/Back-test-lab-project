# Backtest Lab — AI Handoff

This file is an operational mailbox between ChatGPT and Codex.
It is **not** architecture authority. Frozen decisions belong in the existing authority documents.

## STATUS

- Last known frozen contract: 42.19
- 42.19 main commit before creation of this mailbox: `6da3bdc4d3151942c6cfe38186f47b3bf50e070b`
- Preserved 42.18 draft reported locally on branch: `codex/preserve-42-18-draft`
- Preserved 42.18 draft commit reported: `a62fbd4161a3956544d4d9611056c67a1313e998`
- Reconciliation input snapshot reported: `2c65d2d043530605df2b43633e64dfe8e97dc303`
- Full Exness benchmark: NOT COMPLETE
- 700,000-row run: partial interrupted progress only
- Runtime conformity/security of the 42.19 sidecar path: not yet proven

Codex must verify actual local/GitHub state before relying on any status above.

## CHATGPT → CODEX

No implementation instruction is active yet.

When the user asks Codex to continue from this handoff:
1. Read `AGENTS.md`.
2. Read the existing architecture/project authority, especially frozen 42.17 + 42.19.
3. Verify actual repository/local state and preserved 42.18 draft provenance.
4. Do not resume implementation merely because this mailbox exists.
5. Report readiness/blockers in CODEX → CHATGPT and wait for an explicit implementation authorization.

## CODEX → CHATGPT

_No response yet._

When responding, replace this placeholder with a concise report containing:
- checkpoint/status
- repository/branch/commit state
- work performed
- validations/tests
- commit/push status
- blockers or ambiguity
- recommended next action

Do not use this section as a substitute for updating architectural authority when a real design decision is made.

## NEXT ACTION

Establish the handoff workflow first. The next implementation checkpoint is expected to resume the preserved 42.18 V2 draft against frozen 42.17 + 42.19, but it requires explicit authorization before execution.

# RIKSORA — Branch consolidation audit (2026-11-25)

Status: **IMPLEMENTATION REGISTER / AUDIT REPORT, not an architecture authority.** Method: read-only. For each remote branch with commits not in `main`, the files it changed since the branch point were compared with `main`: *unported* = the branch's version is not in `main` and `main` never touched that file since the branch point; *superseded* = `main` evolved that file further. Scripted, reproducible with `git merge-base`/`git diff --name-status`/`git cherry`.

## 1. GitHub vs VPS1 (item 2)
- The code running on VPS1 is release `ec79afd` (2026-11-20). It exists on GitHub (`origin/claude/dual-engine-v1-20261114`) and is an ancestor of local `main`. **Match: yes** for the running code. Local `main` is 586 commits ahead of `origin/main` (not yet pushed at the time of writing).
- Release `7fbb5cd` (adds the SEEK window fix) is prepared in `~/releases/` but not yet serving.

## 2. Branches with no unported code (docs-only, superseded, or contained) — safe to archive then delete on the remote
Count: 26. Their content is preserved in Git history / tags.

| Branch | unported files | unported code files | superseded files |
|---|---|---|---|
| `codex/p0-local-integration-20261106` | 67 | 0 | 29 |
| `claude/product-frontend-v1` | 58 | 0 | 27 |
| `claude/terminal-drawings-indicators-v1` | 58 | 0 | 11 |
| `design/riksora-integrated-freeze-v1-20261104` | 19 | 0 | 1 |
| `handoff/vps-staging-google-oauth-20261023` | 3 | 0 | 1 |
| `codex/cp6a10-postannual-handoff` | 3 | 0 | 0 |
| `docs/hybrid-precomputed-ohlc-r2-20261113` | 2 | 0 | 3 |
| `codex/cp6a10-annual-streaming-verifier-20261103` | 2 | 0 | 0 |
| `codex/beta-rc-20261028` | 1 | 0 | 3 |
| `claude/critique-replay-efficiency` | 1 | 0 | 1 |
| `planning/v22-precision-beta-20261009` | 1 | 0 | 0 |
| `docs/synthetic-tick-acceptance-v1-20261111` | 1 | 0 | 0 |
| `docs/session-storage-efficiency-20261105` | 1 | 0 | 0 |
| `docs/lean-engine-cost-architecture-20261106` | 1 | 0 | 0 |
| `docs/claude-audit-20261105` | 1 | 0 | 0 |
| `docs/architecture-cost-audit-20261106` | 1 | 0 | 0 |
| `codex/security-mainline-20261024` | 0 | 0 | 3 |
| `codex/timeline-prefix-cache-20261024` | 0 | 0 | 2 |
| `codex/pr15-live-vps-audit-20261024` | 0 | 0 | 2 |
| `codex/vps-source-lineage-20261024` | 0 | 0 | 1 |
| `codex/vps-preflight-20261024` | 0 | 0 | 1 |
| `codex/handoff-vps-archive-candidate-20261024` | 0 | 0 | 1 |
| `codex/handoff-source-rights-candidate-20261024` | 0 | 0 | 1 |
| `codex/handoff-full-backend-candidate-20261024` | 0 | 0 | 1 |
| `claude/owner-real-source-decision` | 0 | 0 | 1 |
| `codex/xau-intake-published-20261026` | 0 | 0 | 0 |

## 3. Held: HistData / real-source admission (data-gated, touches engine modules)
Eight branches carry the same Oct-2026 "admission v2" family (`histdata_source.py`, `admission_v2.py`, and edits to `kernel_v2.py`, `finance_v2.py`, `controller_v2.py`, ...). `main` never took these. They enable real HistData months, whose commercial rights are **UNKNOWN / deferred by the owner**, and they modify frozen-contract engine files. **Not consolidated.** Needs: owner decision on data rights, then a regression run of the financial goldens. Until then they stay as archived history.

| Branch | unported files | unported code files | superseded files |
|---|---|---|---|
| `codex/security-dependencies-20261024` | 24 | 13 | 18 |
| `codex/columnar-storage-probe-20261024` | 23 | 13 | 14 |
| `codex/functional-staging-foundations` | 21 | 13 | 14 |
| `claude/admission-one-command` | 21 | 13 | 14 |
| `claude/admitted-conversion` | 21 | 13 | 10 |
| `claude/admitted-session-route` | 20 | 12 | 10 |
| `claude/histdata-admission` | 18 | 11 | 9 |
| `claude/session-start-month` | 12 | 6 | 12 |

## 4. Candidate UI work (needs the owner to say "accepted")
Chart-first replay controls (scrubber, legend, trade toast, pending target). Not in `main`; nothing shows it was accepted for the live product. Adopting it needs a design decision and a browser E2E on desktop and mobile.

| Branch | unported files | unported code files | superseded files |
|---|---|---|---|
| `codex/riksora-commercial-v1-20261116` | 30 | 10 | 16 |
| `claude/chart-first-terminal-20261116` | 17 | 8 | 12 |
| `claude/chart-first-on-53-20261116` | 12 | 7 | 7 |

## 5. Other branches with unported code
| Branch | unported files | unported code files | superseded files |
|---|---|---|---|
| `codex/issue-37-terminal-preview` | 65 | 3 | 14 |
| `codex/exness-monthly-diagnostics-20261109` | 3 | 3 | 11 |
`codex/issue-37-terminal-preview` is an owner-gated design preview (`deploy/vps/install_terminal_preview.sh`); `codex/exness-monthly-diagnostics-20261109` touches Journal/Chart performance files that `main` has since rewritten.

## 6. Also not ported
`0b9fbc8` (position-block cache in `ticks/timeline_v2.py`, old `main`). Engine performance change; needs its own test. Read it with `git show archive/main-20261109`.

## 7. Test failures found and closed (item 4)
| Failure | Kind | Resolution |
|---|---|---|
| `test:repository`: 4 reachable modules missing from the AI-bundle config (`AccountPlan.jsx`, `accountPlan.js`, `MIWorkspace.jsx`, `miWorkspace.css`) | real, small | registered in `frontend/scripts/ai-bundle.config.json` |
| `test:period-availability`: regex predates multi-method (`methodIds:` in `onCreate`) | stale test | regex updated |
| `test:stitch-analytics`: needs `backend/venv/bin/python`, which is empty on VPS1 | environment | set `BTL_RESEARCH_PYTHON=~/tools/venv313/bin/python` (supported by the test; no code change) |
| `test:regression`: aggregate of the above | consequence | passes (32 s) |
| `deploy/site/v2_smoke.py` failed at `replay-run job` on the live release and on the new one | stale smoke script | first ADVANCE targeted 2020-01-30 and left a pending target; now starts at the first replay position (2020-01-01 00:30 UTC). **13/13 steps pass on the live release.** |

Measured 2026-11-25 on VPS1: frontend `test:*` 46/46, `lint` clean, `test_authority_documents` OK, CI financial/analytics block 55/55, CI PostgreSQL recovery block (incl. SIGKILL before/after commit) 13/13 + migration reconciliation, single-instrument Product V1 journey 1/1, production smoke 13/13, real-browser Play on riksora.com (replay time 00:30 to 00:33 in 12 s, no API errors). The PostgreSQL tests ran on a disposable PostgreSQL 17 cluster that was removed afterwards. Not run: the full browser gate (`riksora_browser_gate.py`) and the remaining backend suites outside the CI list.

## 8. Single authoritative branch (item 5)
`main` (local) is the trunk. It includes the old `main` history by an `ours` merge, so it fast-forwards onto `origin/main`. Pushing it and deleting remote branches are owner actions.

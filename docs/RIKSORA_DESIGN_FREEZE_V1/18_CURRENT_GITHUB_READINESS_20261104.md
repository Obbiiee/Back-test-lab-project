# 18 — RIKSORA factual GitHub readiness snapshot (2026-11-04, WIB)

**Purpose:** answer founder's "kita sudah di mana?" without fictitious percentages, assuming the GitHub repo as evidence. **This is not an inspection of live VPS, database, local Claude workspace, production riksora.com or a real 2024 published dataset.** Date recorded at snapshot time; refresh before implementation. No source status is promoted by chat or by planned GitHub issues.

## What was actually checked

1. Main GitHub tree contains backend V2 tick storage, indexed provider, timeline, execution and PostgreSQL financial store, FastAPI auth/workspace/research/queue modules and existing frontend React+Vite/Lightweight Charts. Specific code in `backend/ticks/storage_v2.py`, `timeline_v2.py`, `backend/execution/postgres.py`, `backend/cloud/research.py`, `frontend/src/tickAlpha/AlphaWorkspace.jsx`, `frontend/src/drawings/DrawingTypes.js`, `frontend/src/indicators/productionRegistry.js`.
2. `AI_CONTEXT/04_CURRENT_PHASE.md` on main still explicitly records Alpha readiness `CAPACITY_GATE_FAILED_FINAL_ACCEPTANCE_BLOCKED`: 20x/85% RAM/reference and HTTPS/live capacity certification unpassed at last recorded gate, even when many module tests previously passed. This is **historical operational pointer**, not a measured 2026-11-04 VPS result.
3. GitHub [Draft Design PR #20](https://github.com/Obbiiee/Back-test-lab-project/pull/20) remains open, unmerged, docs-only (now integration/product/desktop/mobile/tool/API and execution specifications). Its mere existence does not permit marking design formally reviewed or code implemented.
4. GitHub [Claude frontend Issue #21](https://github.com/Obbiiee/Back-test-lab-project/issues/21) exists and is open; at this snapshot it had no assignees and no implementation evidence in its issue thread. Existing frontend has **9 registered research drawings + 2 position planning tools**, **7 registered indicators**; owner target is much larger 50 core + 12 conditional indicators, professional draw props/geometry/mobile. Do not assert Claude has started from Issue creation alone.
5. GitHub [Codex backend Epic #22](https://github.com/Obbiiee/Back-test-lab-project/issues/22) and 13 detailed issues [#23–#35](https://github.com/Obbiiee/Back-test-lab-project/issues/23) created as sequential/parallel work tickets. Their checked boxes are deliberately **empty**; tickets are specifications, not code/test proof.
6. Actual VPS 2024 published-source hash/coverage, number/size/legal rights of all 16 ×5 qualified datasets, Parquet performance, RAM/disk on current host, source backup restore, and production OAuth/billing are **not verified this turn**. Legacy Exness 2015 reported source spans only Aug 10–Dec 31, not a full calendar year.
7. Candidate branches `codex/cp6a10-postannual-handoff`, `codex/columnar-storage-probe-20261024`, `codex/compact-writer-20261026` and `codex/beta-backend` exist; existence ≠ merged, certified or deployed. B00 must compare actual revisions/fixtures and preserve useful work instead of restart from scratch.

## Readiness board (meaningful, no guessed %)

| Area | Verified facts | Next PASS gate | Status label |
| --- | --- | --- | --- |
| Product rules / complete UX design handoff | 19 linked docs (README + 01–18) in Draft PR #20, user workflow and Claude tools spec | joint review/approval and no contract contradiction | **DESIGNED / DRAFT_REVIEW** |
| Backend basic V2 source/engine/Research/API | source modules on main and old test reports | B00 repo/VPS inventory + B01 actual OpenAPI snapshots | **EXISTING_BASELINE**, not finished final backend |
| Published full-year source 2024 | user discussion and candidate experiment only | B00 hash/rights/integrity and actual host evidence | **UNVERIFIED_LIVE** |
| Parquet daily/monthly storage and reader | benchmark plan, not production main V2 | B03 real-source benchmark then B04 V2 parity | **PLANNED** |
| Session per-tick storage elimination and cold recovery | main writes timeline/command/checkpoints; measurement pending | B05 restore/storage amplification tests | **PLANNED_OPTIMIZATION** |
| 16 symbols × five years admitted | exact owner list and catalog design | B02 source passports + B06 full FX goldens + rights per source | **TARGET, NOT ADMITTED** |
| Replay 72h Jump and advanced analytics | canonical design and old replay foundation | B07 + B09 golden and scenario tests | **NOT FINAL-CERTIFIED** |
| Cross-device drawing/indicator configuration API | API contract and B08 ticket exist | B08 new CRUD/version/CAS/tenant tests | **SPECIFIED, NOT IMPLEMENTED** |
| Claude advanced chart/50 indicators/mobile app | GitHub Issue #21 detailed implementation instruction | Claude branch+PR and each tool/indicator running test | **ASSIGNED_TASK_EXISTS**, not delivered |
| Secure account linking / Free entitlement / paid | basic verified identity modules exist; completeness unknown | B10 account/link/Free/paid-sandbox tests | **PARTIAL/UNVERIFIED** |
| One VPS end-to-end capacity | historical Alpha gate marked failed; new host not measured | B11 resource+backup+performance certificate | **NOT CERTIFIED** |
| Fully integrated laptop/HP/PWA/commercial release | specs exist, screenshots/CI of new delivery not executed | B12 plus joint API hashes/rights/owner approval | **HOLD** |

## Dependency-driven next actions — no unnecessary waiting

1. **Codex starts B00 (#23) read-only inventory** on actual GitHub/VPS. No destructive cleanup, no production migration. Result: actual existing vs candidate code/data/host baseline.
2. **Codex B01 (#24) produces actual versioned OpenAPI and typed fixture receipts**; Claude reads this SHA and can start React shell/UX implementation [#21](https://github.com/Obbiiee/Back-test-lab-project/issues/21) without waiting for Parquet.
3. **After B01, Codex B08 (#31) can run independently** to unblock cross-device drawing+indicator settings (stroke width, text Bold, Fib levels, pane Up/Down, CAS). Claude F01–F06 can develop mock-backed UI in parallel.
4. Codex B02→B03→B04→B05→B06→B07 process real shared source+reader+finance; B09 analytics and B10 identity/entitlement can proceed as applicable in parallel; B11 requires actual source/host capacity.
5. **B12 (#35) joins Claude and Codex** only when genuine PRs, tests, rights and host restore evidence exist. Procurement/riksora.com deployment is separate owner authorization.

## Evidence required for future status updates

For each issue update: issue status; branch pushed URL; PR and base/head commit; exact changed paths; test exits; source/financial golden hashes; OpenAPI SHA and Claude handoff where applicable; benchmark RAM/CPU/SSD and original source identity; rollback. Progress should be expressed as **completed checkpoints X/13 with independent PASS** and **frontend verified tool subsets**, not "backend 80%" guessed from docs or opened issues.

## Founder decision protection

The current task authorizes **planning and GitHub issue creation**; it did not modify source runtime/finance, datasets, VPS, object storage or production server, did not merge Draft PR #20, did not run a full-year replay or conclude a purchase verdict. Owner requested that worktree NOT be used; no worktree created here. Claude Issue #21 and Codex Issue #22 coordinate via GitHub, not assumptions from independent chats.

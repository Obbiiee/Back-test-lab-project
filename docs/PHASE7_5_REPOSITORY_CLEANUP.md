# Phase 7.5 — Repository cleanup and source-of-truth hardening

Baseline verified: `bbe2627db324a91c5cde39bcd75b1cb29358b582`, clean main, intended origin. Audit and deletion evidence were written before cleanup in PHASE7_5_REPOSITORY_AUDIT.md.

## Result

Removed ten unreachable source/asset copies, each byte-identical to its retained Phase 3 archive counterpart. No file moves, archive removal, evidence removal, runtime edits, dead-import refactors, data changes, dependency changes or behavioral refactors. The sole active source remains `frontend/src/`; the 41-file production graph and two intentional compatibility exports remain.

Updated root/frontend README, added docs index, marked initial ROADMAP historical. Existing phase reports retain their checkpoint descriptions; current AI_CONTEXT is authoritative. Existing linked evidence and test-dependent storage pairs stay tracked. New disposable artifacts use ignored `frontend/tests/artifacts/` or `docs/_generated/`; cache/coverage/browser-report/Windows-noise exclusions were added without ignoring source, fixtures or durable docs.

New `test:repository` protects the local import graph from archive/fixture imports, missing modules and unreviewed unreachable source, preserves compatibility/fixture references, validates task-specific bundle paths, package/lock agreement and required ignore rules. All original regression assertions are unchanged. No archived renderer was reactivated.

## Important tree

```text
repo/
  README.md, OPEN_SOURCE_NOTICES.md, .gitignore, .gitattributes
  AI_CONTEXT/                 tracked current context, eight ordered documents
  docs/                       durable reports, historical evidence and fixtures
    _generated/               ignored future disposable output
  frontend/
    index.html, package.json, package-lock.json, vite/eslint config
    src/                      sole production source
      main.jsx → FigmaWorkspace.jsx
      components/CandleChart.jsx
      market/                 candles/history/live/replay
      trading/                simulator, RiskReward, ticket/positions/journal
      chart/                  compatibility bridge and legacy storage protection
      drawings/               model/manager/primitive/interaction/persistence/history
    tests/                    regressions, repository checks, browser fixtures
      artifacts/              ignored disposable browser output
    scripts/                  data download and AI bundle tooling
    public/market/            tracked validated historical data
    legacy/phase3/            preserved reference and geometry test fixtures
    node_modules/, dist/, .npm-cache/, .history-downloads/   ignored
  legacy/                     preserved prototype and prior frontend snapshot
  backend/                    standalone backend reference/service and tests
  data/                       retained backend sample data/generator
  AI_BUNDLE/                  ignored generated task-specific reference
```

## Validation

PASS build, lint, test:repository, Phase 4/5/6/7, trading-separation, trading, drawings (88 checks), market (3,486,461 M1 candles across eleven timeframes) and AI infrastructure tests. Final build asset names/hashes match Phase 7: index-B2-XWXsq.css, CandleChart-BFWRl8Ji.js, index-dVzrLW3Q.js. Source diff additionally confirms no reachable production edits.

Real browser on isolated port 5183: app/chart load without missing modules; Trend Line creation/selection, endpoint/body drag with exact Undo/Redo restoration, locked drag unchanged, unlock/hide, hidden reload, Show, Delete/Undo/Redo, visible reload, M15↔H1, replay step, zoom/pan/resize. Canonical models matched saved JSON; all eight seeded legacy keys/backups remained byte-identical before intentional later Risk edits. Risk/Reward drag and Ctrl+Z changed/restored only Risk coordinates. Drawing lock/Undo left Risk coordinates unchanged. Risk-generated Buy Limit popup placed a simulated pending order; cancellation removed it and left Trend Line unchanged. Browser error list: empty.

Disposable local evidence (ignored): frontend/tests/artifacts/PHASE7_5_BROWSER_PROOF.json and PHASE7_5_PREVIEW.jpg; harness derived from existing Phase 7 fixture with isolated-port guard. Historical Phase 7 fixtures remain tracked. Main user preview storage was not touched.

## AI/Claude readiness

Bundle inclusion paths and generator unchanged; only current task text updated. Source allowlist: 25 files (8 context, 13 drawing implementation, 2 reference tests, 2 supporting). Output: 29 files including four wrappers, 83,628 bytes. Phase 7: 29 files / 78,164 bytes; increase 5,464 bytes from repository boundary/context/workflow documentation and added package test command. Phase 6.5 had 21 sources / 25 output files; Phase 7 added persistence/history/controls and one test. Exact historic Phase 6.5 byte total was not recorded in its report.

Major excluded directories: market datasets/public, node_modules/dist/caches, backend/data, archives, unrelated source/tests/docs/evidence. Bundle remains a small drawing-specific reference, not a full application. Repeated generation and verification are deterministic; original AI infrastructure tests cover byte equality, stale detection, edited-copy rejection, traversal/output safety and unchanged master sources.

Ready for manual secondary-AI workflow: master → AI_CONTEXT → task-specific bundle → narrow Claude patch → human/primary review → controlled integration → full master tests → Git checkpoint. No AI API or automatic application. Limitations: bundle is not runnable, omits dependencies/data/fixtures, current allowlist is drawing-specific, regeneration replaces generated edits so patches must be preserved first; hash checks validate expected files, not patch semantics or unlisted extra content. Review the full patch against fresh master hashes and do not run two independent writers on master.

Phase 8 is next in context but has NOT started. This phase ends after reviewed commit, normal origin/main push and remote/local HEAD verification. No force push or amendment of Phase 7.

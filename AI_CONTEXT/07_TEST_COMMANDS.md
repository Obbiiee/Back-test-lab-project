# Commands

Run in `frontend/`:

| Command | Protects |
| --- | --- |
| npm run build | Production compilation |
| npm run lint | Source lint/hook rules |
| npm run test:repository | Production/archive boundaries, compatibility/fixtures/config; single context authorities, phase gates, roadmap and bundle inclusion |
| npm run test:phase4 | Runtime retirement and legacy preservation |
| npm run test:phase5 | Manager/model/primitive/creation foundation |
| npm run test:phase6 | Selection/hit testing/drag/cancel/arbitration |
| npm run test:phase7 | Persistence/history/lock/visibility/storage safety |
| npm run test:phase8 | Core line/rectangle models, creation, geometry/editing, axis constraints, lifecycle, history and v1 restore |
| npm run test:phase9 | Fib levels/reversal, arrowhead, Text editing, Measure calculations, mixed history/v1 restore and interaction isolation |
| npm run test:phase10 | Indicator registry/config, revealed-only frozen input, normalized output, warmup, error isolation, replay/prepend/timeframe, series lifecycle and protected boundaries |
| npm run test:trading-separation | Independent Risk/Reward ownership |
| npm run test:trading | Order/position simulation |
| npm run test:drawings | Existing geometry/math regressions |
| npm run test:market | Aggregation and entire decade validation |
| npm run test:ai-bundle | Generator determinism/safety/staleness |
| npm run ai:bundle | Generate disposable root AI_BUNDLE |
| npm run ai:bundle:verify | Read-only hash/config freshness check |

Run full regression in master, not the partial bundle. Browser verification is required for product interaction changes; Phase 7 evidence and limitations: `docs/PHASE7_DRAWING_PERSISTENCE.md`.

Phase 7.5 no-behavior-change verification is recorded in `docs/PHASE7_5_REPOSITORY_CLEANUP.md`; disposable captures are ignored under `frontend/tests/artifacts/`. Backend tests are a standalone Python workflow, not proof of active frontend features.

Documentation-control changes must run test:repository and test:ai-bundle plus regenerate/verify the bundle. Product changes retain the full regression/browser requirements in [workflow](06_WORKFLOW_RULES.md). Phase 7.6 changes only context, roadmap, tests and bundle config; browser verification is exempt because no product/runtime/build path is modified.

Phase 8 product/browser validation and scope evidence: [checkpoint report](../docs/PHASE8_CORE_DRAWING_TOOLS.md).

Phase 9 product/browser validation: [checkpoint report](../docs/PHASE9_ADVANCED_DRAWING_TOOLS.md).

Phase 10 product/browser validation: [checkpoint report](../docs/PHASE10_INDICATOR_ENGINE_FOUNDATION.md). Test-only browser harness: `/tests/phase10.html` on an isolated dev-server origin; reference indicator never enters production UI.

# Operational phase authority

This is the sole operational phase pointer. String phase IDs preserve fractional checkpoints; null means no active/authorized implementation. Roadmap slots do not grant authorization.

```json
{
  "AUTHORITY": "current-phase",
  "LAST_COMPLETED_PHASE": "14",
  "CURRENT_IMPLEMENTATION_PHASE": null,
  "NEXT_PHASE": "14.5",
  "NEXT_PHASE_STATUS": "FINAL_SCOPE_PLANNED_AWAITING_IMPLEMENTATION_AUTHORIZATION",
  "AUTHORIZED_IMPLEMENTATION_PHASE": null,
  "TARGET_CHECKPOINT": "origin/main: Phase 14 Trading UX and Backtest Analysis",
  "FINAL_ROADMAP_PHASE": "75"
}
```

Phase 14 Trading UX and Backtest Analysis MUST scope remains validated. Phase 14.5 final scope incorporates the supplied human decisions in the [existing roadmap](../docs/ROADMAP.md#phase-145-final-implementation-scope): local canonical imports, explicit pilot coverage, provider-neutral data, USD/High defaults, configurable windows, derived-only research and strict availability. No unresolved product decision blocks foundation implementation; explicit implementation authorization is still required. No runtime implementation is active or authorized. Follow [workflow](06_WORKFLOW_RULES.md) and [history](03_PHASE_HISTORY.md). Planning is not a completed implementation phase; roadmap and generated prompts grant no permission. Stop after this planning checkpoint.

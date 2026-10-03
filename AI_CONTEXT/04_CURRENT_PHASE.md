# Operational phase authority

This is the sole operational phase pointer. String phase IDs preserve fractional checkpoints; null means no active/authorized implementation. Roadmap slots do not grant authorization.

```json
{
  "AUTHORITY": "current-phase",
  "LAST_COMPLETED_PHASE": "14",
  "CURRENT_IMPLEMENTATION_PHASE": null,
  "NEXT_PHASE": "14.5",
  "NEXT_PHASE_STATUS": "AWAITING_HUMAN_SCOPE_AND_AUTHORIZATION",
  "AUTHORIZED_IMPLEMENTATION_PHASE": null,
  "TARGET_CHECKPOINT": "origin/main: Phase 14 Trading UX and Backtest Analysis",
  "FINAL_ROADMAP_PHASE": "75"
}
```

Phase 14 Trading UX and Backtest Analysis MUST scope is validated under the submitted human implementation authorization. No implementation is active or authorized beyond this checkpoint. Follow [workflow](06_WORKFLOW_RULES.md); consult [roadmap](../docs/ROADMAP.md) for planning and [history](03_PHASE_HISTORY.md) for completed work. Phase 14.5 requires human scope definition/planning and separate implementation authorization; the roadmap and a generated next prompt grant no permission. Stop after this checkpoint.

# Operational phase authority

This is the sole operational phase pointer. String phase IDs preserve fractional checkpoints; null means no active/authorized implementation. Roadmap slots do not grant authorization.

```json
{
  "AUTHORITY": "current-phase",
  "LAST_COMPLETED_PHASE": "7.6",
  "CURRENT_IMPLEMENTATION_PHASE": null,
  "NEXT_PHASE": "8",
  "NEXT_PHASE_STATUS": "AWAITING_HUMAN_SCOPE_AND_AUTHORIZATION",
  "AUTHORIZED_IMPLEMENTATION_PHASE": null,
  "TARGET_CHECKPOINT": "origin/main: Phase 7.6 project-control hardening",
  "FINAL_ROADMAP_PHASE": "75"
}
```

The context/control infrastructure checkpoint is validated; no product implementation is active or pre-authorized. Follow [workflow](06_WORKFLOW_RULES.md); consult [roadmap](../docs/ROADMAP.md) for planning and [history](03_PHASE_HISTORY.md) for completed work. Stop after this checkpoint. A future request must supply the next phase's concrete scope and authorization.

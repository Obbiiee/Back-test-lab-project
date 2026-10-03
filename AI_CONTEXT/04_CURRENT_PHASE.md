# Operational phase authority

This is the sole operational phase pointer. String phase IDs preserve fractional checkpoints; null means no active/authorized implementation. Roadmap slots do not grant authorization.

```json
{
  "AUTHORITY": "current-phase",
  "LAST_COMPLETED_PHASE": "8",
  "CURRENT_IMPLEMENTATION_PHASE": null,
  "NEXT_PHASE": "9",
  "NEXT_PHASE_STATUS": "AWAITING_HUMAN_SCOPE_AND_AUTHORIZATION",
  "AUTHORIZED_IMPLEMENTATION_PHASE": null,
  "TARGET_CHECKPOINT": "origin/main: Phase 8 core drawing tools",
  "FINAL_ROADMAP_PHASE": "75"
}
```

Phase 8 core drawing tools are validated for the GitHub checkpoint. No implementation is active or pre-authorized. Follow [workflow](06_WORKFLOW_RULES.md); consult [roadmap](../docs/ROADMAP.md) for planning and [history](03_PHASE_HISTORY.md) for completed work. Stop after the validated Phase 8 checkpoint; Phase 9 requires separate human scope and authorization.

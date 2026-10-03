# Operational phase authority

This is the sole operational phase pointer. String phase IDs preserve fractional checkpoints; null means no active/authorized implementation. Roadmap slots do not grant authorization.

```json
{
  "AUTHORITY": "current-phase",
  "LAST_COMPLETED_PHASE": "11",
  "CURRENT_IMPLEMENTATION_PHASE": null,
  "NEXT_PHASE": "12",
  "NEXT_PHASE_STATUS": "AWAITING_HUMAN_SCOPE_AND_AUTHORIZATION",
  "AUTHORIZED_IMPLEMENTATION_PHASE": null,
  "TARGET_CHECKPOINT": "origin/main: Phase 11 Overlay Indicators",
  "FINAL_ROADMAP_PHASE": "75"
}
```

Phase 11 overlays are validated under the submitted human scope. No implementation is active or authorized beyond this checkpoint. Follow [workflow](06_WORKFLOW_RULES.md); consult [roadmap](../docs/ROADMAP.md) for planning and [history](03_PHASE_HISTORY.md) for completed work. Stop after this checkpoint. Phase 12 requires separate human scope and authorization; planning does not authorize implementation.

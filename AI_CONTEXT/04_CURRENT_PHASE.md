# Operational phase authority

This is the sole operational phase pointer. String phase IDs preserve fractional checkpoints; null means no active/authorized implementation. Roadmap slots do not grant authorization.

```json
{
  "AUTHORITY": "current-phase",
  "LAST_COMPLETED_PHASE": "13",
  "CURRENT_IMPLEMENTATION_PHASE": null,
  "NEXT_PHASE": "14",
  "NEXT_PHASE_STATUS": "AWAITING_HUMAN_SCOPE_AND_AUTHORIZATION",
  "AUTHORIZED_IMPLEMENTATION_PHASE": null,
  "TARGET_CHECKPOINT": "origin/main: Phase 13 Replay Optimization and Playback Controls",
  "FINAL_ROADMAP_PHASE": "75"
}
```

Phase 13 replay optimization and playback controls are validated under the submitted human scope. No implementation is active or authorized beyond this checkpoint. Follow [workflow](06_WORKFLOW_RULES.md); consult [roadmap](../docs/ROADMAP.md) for planning and [history](03_PHASE_HISTORY.md) for completed work. Phase 14 requires planning/scope definition and separate human implementation authorization; planning does not authorize implementation. Stop after this checkpoint.

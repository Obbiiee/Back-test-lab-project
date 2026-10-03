# Operational phase authority

This is the sole operational phase pointer. String phase IDs preserve fractional checkpoints; null means no active/authorized implementation. Roadmap slots do not grant authorization.

```json
{
  "AUTHORITY": "current-phase",
  "LAST_COMPLETED_PHASE": "10",
  "CURRENT_IMPLEMENTATION_PHASE": null,
  "NEXT_PHASE": "11",
  "NEXT_PHASE_STATUS": "AWAITING_HUMAN_SCOPE_AND_AUTHORIZATION",
  "AUTHORIZED_IMPLEMENTATION_PHASE": null,
  "TARGET_CHECKPOINT": "origin/main: Phase 10 Indicator Engine Foundation",
  "FINAL_ROADMAP_PHASE": "75"
}
```

Phase 10 foundation is validated for the GitHub checkpoint under the submitted human scope. No implementation is active or pre-authorized beyond this checkpoint. Follow [workflow](06_WORKFLOW_RULES.md); consult [roadmap](../docs/ROADMAP.md) for planning and [history](03_PHASE_HISTORY.md) for completed work. Stop after the validated Phase 10 checkpoint; Phase 11 requires separate human scope and authorization. No production overlay indicator was added.

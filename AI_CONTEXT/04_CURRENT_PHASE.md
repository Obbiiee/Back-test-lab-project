# Operational phase authority

This is the sole operational phase pointer. String phase IDs preserve fractional checkpoints; null means no active/authorized implementation. Roadmap slots do not grant authorization.

```json
{
  "AUTHORITY": "current-phase",
  "LAST_COMPLETED_PHASE": "18",
  "CURRENT_IMPLEMENTATION_PHASE": "18",
  "NEXT_PHASE": "19",
  "NEXT_PHASE_STATUS": "NOT_AUTHORIZED_POST_V1_0",
  "AUTHORIZED_IMPLEMENTATION_PHASE": "18",
  "AUTHORIZED_PHASE_SEQUENCE": ["14.5", "16", "15", "17", "18"],
  "EXECUTION_MODE": "HUMAN_AUTHORIZED_THROUGH_LOCAL_V1_0",
  "TARGET_CHECKPOINT": "Final Local v1.0 Acceptance / Release Audit",
  "FINAL_ROADMAP_PHASE": "75"
}
```

The human authorized baseline `388f54cc049f5333e2a619e0ba55b536871fc4e4` and execution through the sequence above, with individual validated GitHub checkpoints and a final full v1.0 acceptance audit. Phase 14.5, 16, 15 and 17 remote checkpoints are verified. Phase 18 local release identity/distribution gates passed; this status prepares its independent checkpoint. Full final regression/browser/release acceptance and final GitHub checkpoint remain authorized under Phase 18. Phase 19 is not authorized. Implement only MUST scope in the [existing roadmap](../docs/ROADMAP.md). Strategic blueprints remain preserved references; their presence does not widen v1.0 scope. Continue after successful checkpoints without duplicate authorization. Stop on material product conflicts/hard-stop conditions and before v2.0 implementation. Follow the sole [workflow](06_WORKFLOW_RULES.md) and [history](03_PHASE_HISTORY.md).

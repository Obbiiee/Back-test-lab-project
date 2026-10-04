# Operational phase authority

This is the sole operational phase pointer. String phase IDs preserve fractional checkpoints; null means no active/authorized implementation. Roadmap slots do not grant authorization.

The human separately authorized pre-v2 maintenance from verified `a613f49d09ade31fb1ea938e99b7a3f0e27bfc83`: remove only one old browser evidence JSON and three unused root-snapshot asset copies, retaining their Phase 3 counterparts and every KEEP/REVIEW item. Classification/results belong to the [existing repository audit](../docs/PHASE7_5_REPOSITORY_AUDIT.md). This is maintenance, not Phase 19 authorization; after validated commit/push and remote equality, STOP.

Post-release maintenance: the human authorized conservative v1.0 repository cleanup from verified `efe9553622cce95cb9bc2a6501bf9e168bbd7869`. Only an unreferenced template sprite was removed; runtime source, dependencies, data and protected knowledge remain intact. This maintenance authorization does not authorize Phase 19. Classification and validation belong to the [existing repository audit](../docs/PHASE7_5_REPOSITORY_AUDIT.md); commit/push/remote equality are required before reporting completion.

```json
{
  "AUTHORITY": "current-phase",
  "LAST_COMPLETED_PHASE": "18.6",
  "CURRENT_IMPLEMENTATION_PHASE": null,
  "NEXT_PHASE": "18.7",
  "NEXT_PHASE_STATUS": "NOT_AUTHORIZED_POST_V1_0",
  "AUTHORIZED_IMPLEMENTATION_PHASE": null,
  "AUTHORIZED_PHASE_SEQUENCE": ["18.6"],
  "EXECUTION_MODE": "HUMAN_AUTHORIZED_POST_V1_CLOSURE",
  "TARGET_CHECKPOINT": "18.6 completed; STOP before 18.7 and Phase 19",
  "FINAL_ROADMAP_PHASE": "75"
}
```

Phase 18.6 is completed: actual browser UI audit, single [design-system specification](../docs/PHASE18_6_UI_UX_DESIGN_SYSTEM.md), scoped tokens/chooser polish and terminal collapse/keyboard restore. Validation and limits belong to that report; completed facts belong to [history](03_PHASE_HISTORY.md). Phase 18 local v1 remains accepted. No active implementation remains. Next Phase 18.7 and 18.8–18.9/19 are NOT AUTHORIZED. Preserve protected contracts and follow the sole [workflow](06_WORKFLOW_RULES.md) and [roadmap](../docs/ROADMAP.md). Normal commit/push, remote equality and clean 0/0 must be verified before reporting completion, then STOP.

# Operational phase authority

This is the sole operational phase pointer. String phase IDs preserve fractional checkpoints; null means no active/authorized implementation. Roadmap slots do not grant authorization.

The human separately authorized pre-v2 maintenance from verified `a613f49d09ade31fb1ea938e99b7a3f0e27bfc83`: remove only one old browser evidence JSON and three unused root-snapshot asset copies, retaining their Phase 3 counterparts and every KEEP/REVIEW item. Classification/results belong to the [existing repository audit](../docs/PHASE7_5_REPOSITORY_AUDIT.md). This is maintenance, not Phase 19 authorization; after validated commit/push and remote equality, STOP.

Post-release maintenance: the human authorized conservative v1.0 repository cleanup from verified `efe9553622cce95cb9bc2a6501bf9e168bbd7869`. Only an unreferenced template sprite was removed; runtime source, dependencies, data and protected knowledge remain intact. This maintenance authorization does not authorize Phase 19. Classification and validation belong to the [existing repository audit](../docs/PHASE7_5_REPOSITORY_AUDIT.md); commit/push/remote equality are required before reporting completion.

```json
{
  "AUTHORITY": "current-phase",
  "LAST_COMPLETED_PHASE": "18.5",
  "CURRENT_IMPLEMENTATION_PHASE": null,
  "NEXT_PHASE": "18.6",
  "NEXT_PHASE_STATUS": "NOT_AUTHORIZED_POST_V1_0",
  "AUTHORIZED_IMPLEMENTATION_PHASE": null,
  "AUTHORIZED_PHASE_SEQUENCE": ["18.4", "18.5"],
  "EXECUTION_MODE": "HUMAN_AUTHORIZED_POST_V1_CLOSURE",
  "TARGET_CHECKPOINT": "18.4 and 18.5 completed; STOP before 18.6 and Phase 19",
  "FINAL_ROADMAP_PHASE": "75"
}
```

The human authorized joint documentation-only closure of 18.4 and 18.5 from verified af878addf7d250083ee61dbb7c6077182f6e51da, with a coherent normal GitHub checkpoint. Both are completed; Phase 18 local v1 remains accepted. No active implementation remains. Next 18.6 is NOT AUTHORIZED; 18.7–18.9 and Phase 19/v2 implementation are NOT AUTHORIZED. [Phase 18.5 architecture/reference audit](../docs/PHASE18_5_ARCHITECTURE_REFERENCE_AUDIT.md) owns findings and validation; [history](03_PHASE_HISTORY.md) owns completed facts. The [existing roadmap](../docs/ROADMAP.md) remains the sole long-term plan and [workflow](06_WORKFLOW_RULES.md) remains the sole Definition of Done/Git/next-prompt owner. Verify normal push, remote equality and clean 0/0 before reporting, then STOP.

# Operational phase authority

This is the sole operational phase pointer. String phase IDs preserve fractional checkpoints; null means no active/authorized implementation. Roadmap slots do not grant authorization.

The human separately authorized pre-v2 maintenance from verified `a613f49d09ade31fb1ea938e99b7a3f0e27bfc83`: remove only one old browser evidence JSON and three unused root-snapshot asset copies, retaining their Phase 3 counterparts and every KEEP/REVIEW item. Classification/results belong to the [existing repository audit](../docs/PHASE7_5_REPOSITORY_AUDIT.md). This is maintenance, not Phase 19 authorization; after validated commit/push and remote equality, STOP.

Post-release maintenance: the human authorized conservative v1.0 repository cleanup from verified `efe9553622cce95cb9bc2a6501bf9e168bbd7869`. Only an unreferenced template sprite was removed; runtime source, dependencies, data and protected knowledge remain intact. This maintenance authorization does not authorize Phase 19. Classification and validation belong to the [existing repository audit](../docs/PHASE7_5_REPOSITORY_AUDIT.md); commit/push/remote equality are required before reporting completion.

```json
{
  "AUTHORITY": "current-phase",
  "LAST_COMPLETED_PHASE": "18.8",
  "CURRENT_IMPLEMENTATION_PHASE": "18.9",
  "NEXT_PHASE": "18.9",
  "NEXT_PHASE_STATUS": "AUTHORIZED_SEQUENTIAL",
  "AUTHORIZED_IMPLEMENTATION_PHASE": "18.9",
  "AUTHORIZED_PHASE_SEQUENCE": ["18.7", "18.8", "18.9"],
  "EXECUTION_MODE": "HUMAN_AUTHORIZED_POST_V1_CLOSURE",
  "TARGET_CHECKPOINT": "Separate 18.7, 18.8, 18.9 checkpoints; STOP before Phase 19",
  "FINAL_ROADMAP_PHASE": "75"
}
```

The human explicitly authorizes sequential 18.7 → 18.8 → 18.9 with separate validated commit/push/remote-equality gates. Phase 18.7 extends the existing [Method/Session specification](../docs/TRADING_METHOD_SESSION_SPEC.md) with workflow, units, validation, confirmation and evidence contracts. Phase 18.8 prototype is validated; continue to authorized 18.9 validation/freeze after normal remote verification. No Phase 19/backend/cloud/auth/database authorization. Preserve the sole workflow/roadmap and protected boundaries.

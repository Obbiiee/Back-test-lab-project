# Operational phase authority

This is the sole operational phase pointer. String phase IDs preserve fractional checkpoints; null means no active/authorized implementation. Roadmap slots do not grant authorization.

The human separately authorized pre-v2 maintenance from verified `a613f49d09ade31fb1ea938e99b7a3f0e27bfc83`: remove only one old browser evidence JSON and three unused root-snapshot asset copies, retaining their Phase 3 counterparts and every KEEP/REVIEW item. Classification/results belong to the [existing repository audit](../docs/PHASE7_5_REPOSITORY_AUDIT.md). This is maintenance, not Phase 19 authorization; after validated commit/push and remote equality, STOP.

Post-release maintenance: the human authorized conservative v1.0 repository cleanup from verified `efe9553622cce95cb9bc2a6501bf9e168bbd7869`. Only an unreferenced template sprite was removed; runtime source, dependencies, data and protected knowledge remain intact. This maintenance authorization does not authorize Phase 19. Classification and validation belong to the [existing repository audit](../docs/PHASE7_5_REPOSITORY_AUDIT.md); commit/push/remote equality are required before reporting completion.

```json
{
  "AUTHORITY": "current-phase",
  "LAST_COMPLETED_PHASE": "18.9",
  "CURRENT_IMPLEMENTATION_PHASE": null,
  "NEXT_PHASE": "19",
  "NEXT_PHASE_STATUS": "NOT_AUTHORIZED_PLANNING_ONLY_NEXT",
  "AUTHORIZED_IMPLEMENTATION_PHASE": null,
  "AUTHORIZED_PHASE_SEQUENCE": ["18.7", "18.8", "18.9"],
  "EXECUTION_MODE": "HUMAN_AUTHORIZED_POST_V1_CLOSURE",
  "TARGET_CHECKPOINT": "18.7–18.9 validated; final checkpoint then STOP before Phase 19",
  "FINAL_ROADMAP_PHASE": "75"
}
```

The authorized sequential 18.7 → 18.8 → 18.9 journey is completed subject to final normal commit/push/equality verification. Phase 18 local v1 and 18.4–18.9 are complete; no active implementation remains. The existing [Method/Session owner](../docs/TRADING_METHOD_SESSION_SPEC.md) contains frozen Trading UX handoff v1, prototype evidence and future integration prerequisites. Phase 19 is NOT AUTHORIZED; a future human prompt may authorize planning only. No backend/cloud/auth/database or v2 implementation. Verify clean 0/0 and local/origin/actual GitHub equality, report, then STOP.

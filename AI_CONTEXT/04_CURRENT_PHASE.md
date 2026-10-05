# Operational phase authority

This is the sole operational phase pointer. String phase IDs preserve fractional checkpoints; null means no active/authorized implementation. Roadmap slots do not grant authorization.

The human separately authorized pre-v2 maintenance from verified `a613f49d09ade31fb1ea938e99b7a3f0e27bfc83`: remove only one old browser evidence JSON and three unused root-snapshot asset copies, retaining their Phase 3 counterparts and every KEEP/REVIEW item. Classification/results belong to the [existing repository audit](../docs/PHASE7_5_REPOSITORY_AUDIT.md). This is maintenance, not Phase 19 authorization; after validated commit/push and remote equality, STOP.

Post-release maintenance: the human authorized conservative v1.0 repository cleanup from verified `efe9553622cce95cb9bc2a6501bf9e168bbd7869`. Only an unreferenced template sprite was removed; runtime source, dependencies, data and protected knowledge remain intact. This maintenance authorization does not authorize Phase 19. Classification and validation belong to the [existing repository audit](../docs/PHASE7_5_REPOSITORY_AUDIT.md); commit/push/remote equality are required before reporting completion.

```json
{
  "AUTHORITY": "current-phase",
  "LAST_COMPLETED_PHASE": "20",
  "CURRENT_IMPLEMENTATION_PHASE": "21",
  "NEXT_PHASE": "21",
  "NEXT_PHASE_STATUS": "AUTHORIZED_AFTER_PHASE20_GIT_GATE",
  "AUTHORIZED_IMPLEMENTATION_PHASE": "21",
  "AUTHORIZED_PHASE_SEQUENCE": [
    "20",
    "21",
    "22"
  ],
  "EXECUTION_MODE": "AUTONOMOUS_BOUNDED_JOURNEY",
  "TARGET_CHECKPOINT": "Validated Phase 21 then Phase 22 checkpoints; STOP before Phase 23",
  "FINAL_ROADMAP_PHASE": "75"
}
```

The human authorizes Phase 20 → 21 → 22 from clean verified 32743428a16a0553dc6b5483b48767e28c26e6d4. PostgreSQL persistence gates PASS; [existing evidence/runbook](../docs/PRODUCT_SYSTEM_ARCHITECTURE_BLUEPRINT.md#391-implemented-persistence-and-acceptance-evidence) owns results. Normal Phase 20 commit/push/equality and clean 0/0 precede Phase 21 implementation. Use existing roadmap/security owners, separate validated checkpoints and automatic bounded continuation. No login preference reply arrived during independent Phase 20 work; minimum email/password with mature auth library is the stated implementation assumption, not external OAuth/cloud activation. STOP after Phase 22 or material unresolved security/product blocker; no Phase 23 or execution-authority switch.

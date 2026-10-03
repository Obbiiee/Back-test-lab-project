# Operational phase authority

This is the sole operational phase pointer. String phase IDs preserve fractional checkpoints; null means no active/authorized implementation. Roadmap slots do not grant authorization.

```json
{
  "AUTHORITY": "current-phase",
  "LAST_COMPLETED_PHASE": "14",
  "CURRENT_IMPLEMENTATION_PHASE": null,
  "NEXT_PHASE": "14.5",
  "NEXT_PHASE_STATUS": "PLANNING_REPORTED_AWAITING_HUMAN_DECISIONS_AND_IMPLEMENTATION_AUTHORIZATION",
  "AUTHORIZED_IMPLEMENTATION_PHASE": null,
  "TARGET_CHECKPOINT": "origin/main: Phase 14 Trading UX and Backtest Analysis",
  "FINAL_ROADMAP_PHASE": "75"
}
```

Phase 14 Trading UX and Backtest Analysis MUST scope is validated under the submitted human implementation authorization. Human-authorized Phase 14.5 Economic News Backtesting Engine audit/planning is reported in chat; no runtime implementation is active or authorized. Data source/licensing, coverage, categories, defaults, research windows and metadata decisions remain pending before separate implementation authorization. Follow [workflow](06_WORKFLOW_RULES.md); consult [roadmap](../docs/ROADMAP.md) for the human execution-order decision and [history](03_PHASE_HISTORY.md) for completed work. Planning is not a completed implementation phase. The roadmap and a generated next prompt grant no permission. Stop after this planning checkpoint.

# Phase 3 source snapshot — migration reference only

Captured before Phase 4 retirement on 2026-10-02. `src/` preserves the complete
Phase 1–3 frontend source, including the legacy tool registry, geometry, creation
paths, SMA/EMA calculation, old entry point, adapters and styles. It is outside
the active `frontend/src/main.jsx` import graph and excluded from production lint.
Do not use this snapshot as an application entry point.

`test:drawings` deliberately imports this snapshot's `drawings/tools.js` and
`components/DrawingGeometry.jsx`: the 88 legacy geometry fixtures remain useful
for interpreting old records; passing these tests does not enable their runtime.

The unused community adapters are retained as
`components/NativeDrawings.jsx.reference.txt` and `drawings/native.js.reference.txt`.
Their historical `lightweight-charts-drawing` imports are documentary references,
not executable dependencies. That community package was uninstalled in Phase 4.

## Data boundary

Keep `backtest-drawings-v2:<sessionId>` and the existing
`:before-trading-separation` backup. Legacy records use `id`, `type`, `points`
(numeric `time` and `price`) plus tool-specific optional fields, including text,
levels, color, hidden, locked and screenAnchor. Preserve fields and unknown types;
the archived registry is a reference, not an exhaustive data whitelist.

Active `src/chart/LegacyObjectPersistence.js` reads the same JSON, partitions
valid Long/Short objects from opaque records, retains interleaved record order,
and changes only accepted trading slots. Unchanged loads do not rewrite bytes.
Malformed JSON/non-array payloads disable saving. Existing backups are never
overwritten, and backup failure also prevents a write. No namespace or schema
migration has been performed. A future migration adapter can use this reader
and snapshot without activating the retired renderer.

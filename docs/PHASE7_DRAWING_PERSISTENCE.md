# Phase 7 — Drawing persistence, history, lock and visibility

Verified against Phase 6.5 baseline 374525e. Only the new Trend Line domain changes; trading, Risk/Reward, replay, market data and legacy engines remain separate.

## Architecture and contract

DrawingManager canonical TIME+PRICE models → committed snapshot events → DrawingHistory / DrawingPersistence → localStorage. Restoration validates through DrawingRegistry/model factories and reconstructs official Lightweight Charts primitives. No dependency or chart-engine replacement.

Storage key: `backtest-drawing-manager-v1:main%3AXAUUSD`. Document: `{version:1, workspace:"main:XAUUSD", drawings:[...]}`. Records contain id, type, points(time, price), options(color, lineWidth), visible, locked, metadata(createdOnTimeframe). Selection, hover, draft, pixels, controllers, chart and primitive references are excluded.

The current single XAUUSD workspace shares drawings across timeframe, live/historical/replay mode and replay cursor changes. No timestamp rounding during restore. A future multi-asset/layout implementation must supply explicit workspace identity.

Create/delete/property changes and completed changed drags commit once. Pointer previews never save or enter history. Cancel and no-op restore the original canonical state without a new action. Undo/Redo applies validated canonical snapshots and persists the resulting state; new actions clear redo. History is bounded to 100 actions and resets on reload; models persist.

Locked objects remain selectable and deletable, but endpoint/body geometry cannot change. Hidden objects do not render, hit-test or remain selected. Show hidden restores all hidden Trend Lines as one history action. Minimal controls preserve the existing layout. Keyboard history respects editable targets and drawing/trading ownership.

Malformed JSON, unsupported document/version/scope, unknown fields/types, invalid/partial records and duplicates never overwrite their original namespace. Valid records can restore from a mixed document, while the entire namespace stays read-only for that mount. The first valid duplicate ID wins. Warning text explains memory-only edits. Denied storage and quota errors preserve working in-memory rendering/history; failed writes do not imply persistence success.

## Verification

PASS: production build, lint, Phase 4/5/6/7, trading-separation, trading, drawings (88 checks), market (3,486,461 M1 candles and eleven timeframes), AI bundle infrastructure and generated bundle verification.

Browser checks used disposable origins 5182 (new drawing/legacy preservation) and 5181 (trading regression), without modifying the main 5173 preview. Verified creation/reload, endpoint A/B and body drag/reload, UI and keyboard Undo/Redo, Delete/Undo/Redo, lock/reload/unlock, hide/reload/show, M15↔H1 edit/persistence, 30m mixed and 3m malformed legacy scopes, replay step, zoom/pan/resize. Canonical DOM models matched persisted JSON.

Risk/Reward drag and its Ctrl+Z restored Risk coordinates without changing the new Trend Line. New drawing Undo/Redo left Risk coordinates unchanged. Existing Buy position/SL/TP remained present. Risk-generated Sell Stop popup created a simulated pending order and cancellation removed it without changing the Trend Line. Final fresh browser console error lists are empty.

Legacy before/after eight-key fixture snapshots have identical SHA256: `605590FE690E365FBED1F62BFD81082573AB5E4C200A36F0D1F9144313E195C3`. New adapter never reads/writes legacy keys or backups.

Evidence: PHASE7_PERSISTENCE_PROOF.json, PHASE7_LEGACY_BEFORE.json, PHASE7_LEGACY_AFTER.json, PHASE7_CONSOLE.json, PHASE7_HISTORY.jpg, PHASE7_LOCKED.jpg, PHASE7_HIDDEN.jpg, PHASE7_TIMEFRAME.jpg, PHASE7_FINAL_PREVIEW.jpg.

## Limits

Only new Trend Lines are persisted. History is session runtime state; no backend/cloud sync, cross-tab merge, new drawing types, object tree, properties panel, migration or automatic repair of protected malformed data. Browser storage is origin-specific. Archived legacy and historical fixture files remain intact. Phase 7.5 and Phase 8 have not started.

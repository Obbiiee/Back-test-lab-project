# Phase 14.5 — Economic News Backtesting Engine

Evidence report, not operational authority: completion/authorization belongs to [current phase](../AI_CONTEXT/04_CURRENT_PHASE.md); MUST scope belongs to the [sole roadmap](ROADMAP.md#phase-145-final-implementation-scope). Adopted baseline `388f54cc049f5333e2a619e0ba55b536871fc4e4` by fast-forward after auditing all 25 documentation-only commits. All strategic documents remain preserved. Their presence does not widen v1.0 scope.

## Boundaries and behavior

`frontend/src/news/` owns canonical validation, frozen field facts, strict/retrospective projection, availability timeline and bounded filter-view time indexes, separate native IndexedDB dataset/preferences storage, navigation requests and derived trade context. The existing News button opens the panel; an official Lightweight Charts series primitive projects eligible events into existing timeframe buckets and clusters overlaps. No chart replacement, autoscale contribution or trading-marker ownership. No simulator, replay settlement, indicator calculator or financial formula changes.

Strict selects each field independently at the revealed raw M1 endpoint. Unknown availability stays hidden. Actual/release information additionally requires eligible release-time evidence. Later schedule/impact/previous/forecast/actual revisions do not rewrite earlier knowledge. Date-only availability becomes next source-local midnight; date-only events stay list-only. Details display evidence/source timestamp/timezone/precision and hidden reasons. Retrospective research is labeled, separately cached, cannot navigate or change strict markers.

USD/High/all categories are initial defaults; Apply accepts other currencies/impacts/categories and persists validated preferences. Version-1 research windows preserve half-open boundaries; before/after UI uses minutes, during lead/lag seconds. Derived entry/each-exit context retains all overlaps and nearest-within-window only, signed delta, dataset SHA-256, query version and configuration SHA-256. Facts are evaluated as-of each trade timestamp capped by the cursor. Canonical account/grouping/metrics/notes/CSV contracts remain unchanged.

Previous moves viewport only. Next pauses playback and requests existing manual steps with one outstanding request, waiting for revision and canonical account lastTime acknowledgement. It reports the first endpoint at/beyond target and overshoot. Cancel preserves completed steps. Timeframe/dataset/filter/session/manual actions cancel; conflicting controls are disabled or cancel before acting. Normal chunk extension remains owned by the market hook. News writes no replay index/account state and resets no session.

## Canonical input and recovery

UTF-8 JSON schema version 1, up to 64 MiB, 100,000 occurrences and 1,000,000 field versions. Envelope: schemaVersion, datasetId, version, provenance (source/license/retrievedAt), coverage, definitions, occurrences. Coverage uses explicit-offset ISO from/to, complete/partial/unknown status, currencies/categories scopes (`*` for all) and evidence. Definitions have stable eventTypeId, preserved sourceName and variant. Occurrences have stable occurrenceId, eventTypeId, referencePeriod, releaseStage and field-version arrays in facts.

Field facts contain version, value, availableAtUtc (offset timestamp or null), evidence, sourceTimestamp, sourceTimezone and precision (second/millisecond/day). availabilityPrecision defaults second; date-only availability must explicitly set day. Numeric previous/forecast/actual require unit/rawText; optional referencePeriod retains period evidence. Schedule/release values are offset ISO timestamps, or YYYY-MM-DD for day precision. Milliseconds are retained. Missing facts stay hidden; null with known availability is explicitly unavailable. RetrievedAt never establishes historical availability. Offset-free/contradictory/unsupported timestamps reject.

Reproducible labeled sample: JSON.stringify(pilot(), null, 2), from `frontend/tests/phase14-5-fixtures.mjs`. Synthetic CPI/NFP/FOMC/PCE/GDP data is explicitly NOT economic history and never bundled into production. User imports must carry provenance/licensing; no third-party corpus or provider service ships here.

Native IndexedDB namespace `backtest-economic-news-v1`, version 1, stores source JSON, normalized-content/source-byte SHA-256 hashes, active/previous references and separate preferences. Validation/hash/index precede one atomic replacement transaction. Conflicting reused datasetId/version rejects. Reload verifies bytes and rebuilds indexes. Corrupt/future records remain preserved; Restore previous verifies the backup. Reimport a valid new version when a corrupted same-version record must remain preserved. Retain original source JSON: origin-local storage is not a portable backup. Trading/drawing namespaces remain intact.

## Validation evidence and limits

Full drawing/math, market (3,486,461 M1 candles), trading/separation, bundle/repository and Phase 4–14 regressions passed. News tests pass canonical hashing/order, malformed/duplicate inputs, DST gaps/folds/offset contradictions, date-only boundaries, strict future-field mutation and physical-truncation invariance, filters, same-time groups, coverage/windows/overlaps, marker gaps/lifecycle, single-request ordering and exact manual account equivalence at 1m/15m/1h. Deterministic tests cover chunk waiting/extension and cancellation. Lint and production build passed.

Actual in-app Chromium on isolated origin `127.0.0.1:5192`, test-only `/tests/phase14-5.html` and production `/`: file-chooser JSON import, pilot list/details, strict/retrospective restriction, invalid-import preservation, real IndexedDB replacement/reload/conflicting-version rejection/corrupt-hash rejection/backup recovery, timeframe, prepend, resize, pan/zoom, remount (old primitive detached, one active owner), actual marker click selection, main News integration, EUR/all-impact preferences surviving actual reload. No console/runtime errors observed in those checks. A browser-control timeout during reload resolved after loading; no application error. Recovery tests used a separate test-only database; no user-origin account was cleared.

15m navigation from 12:00 to synthetic 12:30 stopped at raw 12:44, the ordinary manual endpoint (14-minute overshoot, explicitly displayed). Account cursor matched raw endpoint.

Browser sparse synthetic ten-year observations, no CI timing thresholds:

| Events | Validate | Index | Initial view | 1,000 queries + availability | Tree visits | Projection + two frames |
|---|---:|---:|---:|---:|---:|---:|
| 10,000 | 380.8 ms | 43.2 ms | 82.2 ms | 13.6 ms | 37,922 | 15.2 ms / 11 events |
| 100,000 | 3,822.9 ms | 376.2 ms | 673.6 ms | 6.1 ms | 25,218 | 20.7 ms / 111 events |

Sparse schedule facts are not fully revised multi-field releases, sustained FPS or a hardware guarantee. Node benchmark separately reports query p95/heap. Import/initial filter view scan is separate from cursor queries: the time tree bounds range traversal, crossed availability IDs update existing views, cache is bounded to eight filter views per mode and UI lists/markers are bounded.

Final regression after Phase 15 remains required. Phase 16 owns broader reliability/security/resource checks. Real quota exhaustion/cross-tab blocking and live multi-chunk event navigation were not manually forced; failed version replacement and deterministic chunk controller tests cover those adjacent invariants. Real news acquisition/cloud/AI/final styling remain outside this phase.

During development, adding a hook while the Vite page was already mounted produced a Fast Refresh hook-order error and blank page. A full reload restored the unconditional hook tree; post-reload filter Apply, main-panel Next/Previous navigation and disabled-control restoration worked. This source-editing HMR incident is recorded separately from cold-start/runtime validation; final release audit must use the built static app. At 30m, main-panel Next reached raw 13:29 for the 13:00 event; Previous left the cursor unchanged.

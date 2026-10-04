# Local QA and hardening evidence

This checkpoint implements the local Phase 16 scope in the existing roadmap. Operational status and authorization remain in AI_CONTEXT/04_CURRENT_PHASE.md; workflow remains in 06_WORKFLOW_RULES.md. Strategic blueprints are retained references, not additional release requirements.

## Changes and boundaries

The existing account key/schema now has a separate lossless persistence adapter. Malformed, unsupported, unavailable and oversized records preserve stored bytes and use a clearly labeled temporary account. Quota/write failures remain in memory. Valid legacy metadata, Unicode notes, numeric identities and partial exits are retained. Writes compare previously read bytes before replacing them; foreign changes stop saving. This is best-effort conflict detection, not atomic multi-tab synchronization. Read/write limits match (8 MiB string length; 50,000 rows per collection).

Favorites receive safe bounded reads without overwriting malformed originals. Prototype-derived timeframe/tool names are rejected. Root render failures expose reload recovery without clearing storage; event-handler and asynchronous failures are outside React error-boundary coverage. Incomplete legacy journal rows render unknown/unavailable and do not invent calendar dates.

News exact anchor lookup is binary over sorted revealed candles, avoiding repeated full-history Set creation. The availability timeline has one global sort. Strict projection, chart-time anchoring and financial/replay semantics remain unchanged. No dependencies, cloud services, account migrations, indicator formulas or protected simulator/settlement/calculator changes were introduced.

## Validation

- All registered frontend regression commands passed, including full 3,486,461 M1 history, drawing/indicator/replay/trading/analysis/news and repository/bundle checks. Lint and production build passed.
- Phase 16 tests cover preserved malformed/future account bytes, valid legacy identity/metadata, oversized writes, unavailable/quota failures, subscription lifecycle, foreign-write detection and invalid favorites. A 100k-candle probe checks fewer than 100 anchor reads for one marker and zero for no markers. 150 randomized cursor/filter/rewind cases match direct strict projection across 300 revised occurrences.
- Active-source unsafe executable-input and high-signal embedded-credential heuristics passed. These are bounded checks, not a complete security audit. npm dependency audit on 2026-10-04 reported zero vulnerabilities; this is a point-in-time registry result.
- Actual cold production build on isolated localhost origins retained corrupt account/favorites bytes, fell back from invalid timeframe to 30m, and displayed storage warnings without a console error. Valid legacy balance/Unicode notes survived reload. Missing legacy side/time rendered unknown/unavailable; Journal and Calendar opened successfully. Real file import and 15m Next Economic Event reached raw replay 12:44 for a 12:30 event, with exact chart mapping and no console errors/warnings.

## Non-gating measurements and limits

Host CPU timing is observational, with concurrent QA and variable load. Phase 13 5k bars/seven indicators/100 steps: 15,816 ms, mean 158.16 ms, p95 371.75 ms; native candle API one full load plus 100 updates versus 101 reference full loads. Indicators still recompute fully (700 calculations). Phase 14 alternating closed/open/open/closed Analysis runs: 12,610 / 12,272 / 11,608 / 15,564 ms, with projection counts 0 / 1 / 1 / 0.

News 10k/100k synthetic occurrences: validation 494.21/8072.41 ms; indexing 70.8/486.72 ms; initial view 172.07/1640.35 ms; mean query 0.0315/0.0295 ms; p95 0.0436/0.0288 ms; heap delta 10.96/108.28 MiB. No FPS, playback-throughput, hardware-general or speedup claim follows from these runs. Earlier actual-browser news measurements and input/coverage limitations remain in the Phase 14.5 report.

Live cross-tab races, browser quota exhaustion, every OS/device and a deliberately forced React render crash were not manually exercised. Deterministic failure tests cover adjacent storage paths. Test-only seed/server files are outside the production import graph and production build; their origin contains disposable synthetic evidence and is not a user deployment. Final post-UI regression and v1.0 release acceptance remain separate gates.

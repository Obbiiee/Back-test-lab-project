# Phase 18.5 — architecture and reference audit

Audited 2026-10-04. Starting main/local/origin/actual GitHub baseline: `af878addf7d250083ee61dbb7c6077182f6e51da`, clean, ahead/behind 0/0. No incoming commits. Documentation-only closure jointly authorized with Phase 18.4; no runtime implementation, deletion, dependency change or data migration.

## Ownership and authority

The eight pre-existing AI_CONTEXT owners remain: 00 onboarding; 01 factual state; 02 actual architecture; 03 completed history; 04 operational authorization; 05 protected boundaries; 06 workflow/Definition of Done/Git/next prompt; 07 validation commands. [ROADMAP](ROADMAP.md) remains the sole long-term plan. [Trading Method specification](TRADING_METHOD_SESSION_SPEC.md) remains the sole Method/Session contract. This report owns this dated source/reference audit, not a new roadmap or live status tracker.

A new focused report is necessary because the existing official chart audit is a historical Phase 1 migration snapshot, and the repository cleanup audit owns file classification rather than cross-subsystem architecture/reference decisions. Both remain preserved and linked. No second workflow, phase tracker or design system was created.

## Phase 18.4 normalization and hygiene recognition

The four-file cleanup is already completed at the baseline; results belong to [repository audit](PHASE7_5_REPOSITORY_AUDIT.md). No repeat deletion sweep. All KEEP/REVIEW, archives, fixtures, datasets, licenses and strategic knowledge remain.

| Occurrence group | Classification | Resolution |
| --- | --- | --- |
| Method spec optional retention of checklist OFF; method-version risk phrase | CURRENT | Required evidence retention; immutable Method definition; internal schema provenance distinguished |
| Roadmap open checklist decision, future Protocol Quick journey, final Trading Mode diagram | CURRENT | Resolved from explicit human contract; permitted journeys and refusal cases; inherited Method |
| Trading/rules specification two independent dimensions and old 18.7 planning | HISTORICAL | Original draft retained in explicitly superseded details sections; active projection delegates to Method owner |
| Design/system blueprints and thesis version/mode terminology | AMBIGUOUS | Precedence notices distinguish preserved strategic/research wording from current domain authority |
| Initial official chart audit missing panes/legacy runtime | HISTORICAL | Dated checkpoint retained; current audit linked |
| Idea backlog, technical dataset/security provenance versions, Phase 13 reset evidence | IRRELEVANT to competing domain authority | Preserved; technical versions and actual v1 reset guards are not removed |

Canonical contract: `FREE_STYLE | PROTOCOL` belongs to Trading Method; Session inherits it. Free Style supports Quick + Planned with no protocol checklist. Protocol locks RR/risk and requires at least one condition; Planned pending Limit/Stop only, no direct Market or discretionary manual close. ON requires every condition PASS; OFF retains definition/available state and enforcement evidence without blocking or forced interaction. Unknown/not-assessed evidence is not invented PASS. Material changes create a new immutable Method. Session creation requires Method/name/instrument/immutable feed/balance/start period, with switchable timeframe and default/advanced execution configuration. Research Maturity does not require cross-pair coverage. These are future product contracts, not a claim of implemented v1 enforcement.

## Actual architecture and state flow

Production entry is [main](../frontend/src/main.jsx) → [FigmaWorkspace](../frontend/src/FigmaWorkspace.jsx) → lazy [CandleChart](../frontend/src/components/CandleChart.jsx). React 19/Vite 8; installed Lightweight Charts 5.2.1. Dependency manifest/lock unchanged. Backend is separate and not the active local frontend execution owner.

| Subsystem | Actual canonical owner and flow | Preserve / adaptation boundary |
| --- | --- | --- |
| Chart | CandleChart creates/removes chart, price candles/native Volume, ResizeObserver; adapters manage annotations/indicators/drawings | Keep official chart; UI commands translate through adapters, not direct account mutation |
| Market | market/history.js, candles.js, useGoldMarket.js progressively load/aggregate decade data; live quotes separately | Keep dataset identity and deterministic aggregation; provider identity in future Session requires a specification |
| Replay | useReplayMarket → revealed raw prefix + aggregated visible bars/revisions; useReplayPlayback + PlaybackScheduler acknowledge committed revisions | Keep loading/step/cancel/ack ownership; do not drive settlement from UI pixels or clock-only ticks |
| Drawing | DrawingManager → DrawingRegistry → immutable models → official primitives; TrendLineCreation and DrawingInteractionController; shared projectGeometry/hitTesting/timeCoordinates | Sufficient extension foundation for richer properties/object UI; no engine rewrite justified |
| Indicators | IndicatorRegistry/productionRegistry → IndicatorEngine validates frozen revealed input/output → IndicatorSeriesAdapter owns line/histogram series and dedicated panes | Seven production types, warmup/error isolation; no shared trading storage; full recalculation remains reference behavior |
| Trading | useTrading owns canonical account; validates requests, calls simulator; replaySettlement processes revealed raw candles with verified transition fallback | Preserve financial contracts and order/position/exit distinction; future Protocol validation is absent, not retroactively claimed |
| Position planning | RiskRewardController/Geometry/Layer/Settings and riskReward.js, separate from new drawing domain; ChartObjectBridge integrates legacy storage | Planning quantity/geometry are previews; conversion to ticket is explicit and needs future instrument-aware spec |
| News | useNews orchestrates eventValidation, eventRepository, EventIndex, timeIndex, NewsNavigationController; NewsMarkerAdapter and researchContext | Strict field availability; retrospective labeled and derived-only; separate IndexedDB, no settlement authority |
| Analysis | backtestAnalysis.js derives completed positions/partial exits/metrics from account; BacktestAnalysis.jsx renders | Preserve exact realized calculations, issue flags and memoization independent of cursor-only movement |
| Journal | Journal.jsx reads trades, useTrading.setNotes changes canonical notes | No second journal financial store; unknown legacy evidence remains unknown |
| CSV | backtestExport.js exports raw/grouped derived account evidence | Preserve UTF-8/escaping/group identity and download lifecycle |
| Workspace | FigmaWorkspace routes tools/order/news/replay callbacks and local presentation state; workspacePreferences; usePanelResize; WorkspaceModal/usePopupFocus | Adapt orchestration deliberately; existing six-dot keyboard/pointer resize and chart-accessible nonmodal panels remain valuable |

Tracing key paths: drawing creation/drag commits canonical model snapshots → DrawingHistory and DrawingPersistence subscriptions; transient drafts do not become account operations. Replay transition hints are checked against revealed arrays before chart updates or settlement suffix optimization, otherwise reference full scanning remains. useTrading chooses replay.raw when replay is active; visible aggregated timeframe candles do not replace raw settlement. IndicatorEngine receives visible/revealed chart input and clears failed output. News navigation uses acknowledged steps rather than arbitrary account rewind.

## Protected contracts and strengths

[Protected systems](../AI_CONTEXT/05_PROTECTED_SYSTEMS.md) remains authoritative. Keep TIME + PRICE drawing geometry across pan/zoom/resize/timeframe; isolated drawing vs Risk/Reward histories; immutable models; lock/hide; no-look-ahead; deterministic replay acknowledgements/cancellation; raw settlement and conservative ambiguous fills; account evidence identity/partial exits; exact realized Analysis/CSV; strict news field availability; byte-preserving corrupt/future storage recovery; all archived/fixture/data/license boundaries.

DrawingRegistry already centralizes models/primitives and can support additional types without replacing validated core. Creation and pointer arbitration are separated from financial execution. Existing history handles committed actions, while transient interactions can cancel. Indicator calculators are pure with separate official rendering/pane ownership. News is research context, not an execution signal. Financial projections remain derived from the account. These are strengths, not debt merely because future UX will be larger.

## Lightweight Charts capability audit

Installed `frontend/node_modules/lightweight-charts/dist/typings.d.ts`, not next/latest docs, establishes 5.2.1 API availability. Currently used: createChart/addSeries with Candlestick/Histogram/Line, official series primitives, time/price conversion and logical ranges, crosshair/click subscriptions, native markers/price lines, dedicated indicator addPane/removePane lifecycle, chart resize/disposal and guarded updates. Exact ownership is above and in [architecture](../AI_CONTEXT/02_ARCHITECTURE.md).

Available but not broadly used in the active UX: pane primitives (`IPanePrimitive`), `swapPanes`, `subscribeDblClick`, `setCrosshairPosition`, richer custom-series/primitive hit-test contracts. These enable future adapters; they do not automatically supply object persistence, undo/history, Protocol validation, order planning, financial risk rules, full toolbars or a professional workspace. Retain custom drawing serialization/interaction, Risk/Reward domain calculations, account simulator and replay. Pane reorder needs stable instance-to-pane mapping and lifecycle tests; context menus must respect chart/pointer arbitration; time conversion must preserve sparse/out-of-range anchor semantics. A chart engine upgrade/replacement is not justified by this audit.

## Trading-domain boundary map

| Concept | Existing owner / status | Required later specification or prototype |
| --- | --- | --- |
| Trading Method | Future conceptual authority in Method spec; no runtime Method repository | 18.7 immutable identity, validation and evidence boundary |
| Session | Future conceptual container; current replay/date/account are not equivalent | 18.7 inheritance/feed/continuation ownership; later authorized persistence implementation |
| Trading Plan | Preview object + ticket seed, not canonical durable domain entity | 18.7 plan/request mapping; 18.8 explicit confirmation UX |
| Position Tool | RiskReward* planning/visualization, not executable intent | 18.8 locked geometry/risk preview with no automatic execution |
| Order Ticket | OrderTicket.jsx form; FigmaWorkspace.openTicket/fromDrawing prepare seed | 18.7 canonical request constraints; 18.8 review/Place Order boundary |
| Order | account.orders via simulator/placeOrder | Retain financial owner; policy validates before mutation |
| Position | account.positions via simulator | Preserve pending-trigger and risk/exit lifecycle |
| Execution | simulator/processCandle + replaySettlement | Current local simulated fills; no full immutable event-ledger claim |
| Exit | account.trades partial/terminal records | Preserve positionId/grouping; do not equate every exit to a complete position |
| Trade Evidence | Existing account trade rows and notes + derived news context; metadata can be incomplete | Future Method/Session/checklist provenance needs explicit contract; never infer missing evidence |
| Analysis | Derived from canonical account | No independent financial store |
| Journal | Canonical trade notes rendered in Journal | Future projections must reference same evidence identity |

Current `fromDrawing` → `riskRewardOrderSeed` → `openTicket` prepares fields; only ticket submission calls `trading.place`. `riskRewardOrderSeed` may choose Market near current price and uses legacy quantity-to-lot conversion. That is valid existing local v1 behavior; it is not future Protocol compliance. Changing it now would exceed scope. Phase 18.7 must define instrument/tick/lot/cost constraints, single validation boundary, idempotent confirmation and blocked-action evidence; Phase 18.8 prototypes only after authorization. TRACK_VIOLATION cannot authorize prohibited Protocol Quick/Market/manual close.

## Persistence map and future migration precautions

| Data | Owner / schema | Corruption and recovery | Future considerations |
| --- | --- | --- | --- |
| Account | AccountPersistence; backtest-paper-account-v1; accepts legacy absent schemaVersion or 1 | Validates bounds/types, preserves unknown metadata; malformed/future original retained, temporary in-memory account/warning; foreign-write guard; quota failure warning | Session ownership cannot be inferred; retain original bytes, explicit versioned migration and rollback |
| Eight drawings | DrawingPersistence; backtest-drawing-manager-v1 workspace namespace; envelope version 1/workspace/drawings | Strict records; valid subset restored read-only if damaged; unsupported originals not overwritten | Workspace namespace is not automatically Session identity; preserve TIME + PRICE and existing unknown bytes |
| Legacy Risk/Reward/objects | LegacyObjectPersistence / ChartObjectBridge; backtest-drawings-v2 namespaces and before-trading-separation backups | Unknown records preserved; no silent migration | New planner must not drop legacy opaque records or merge histories |
| Favorites | workspacePreferences, backtest-favorites-v1 | Validated, malformed originals preserved with warning | UI preference, not research evidence |
| Timeframe/replay date | Workspace timeframe key backtest-workspace-interval-v1; useReplayMarket replay-time-v1 | Best-effort restoration/fallback; no account-grade durable recovery guarantee | Low-impact preference; distinguish from persistent Session provenance |
| News | eventRepository / IndexedDB backtest-economic-news-v1 DB 1; record schemaVersion 1, dataset ID/version/hash | Transactional replace, preserve old dataset pointer; revalidate hashes; restore previous/reimport; blocked/versionchange handling | Keep strict/retrospective projections separate; no cloud migration here |
| Indicators/history | Indicator configs and drawing Undo/Redo in memory; history bounded to 100 | Reload does not restore these; drawings themselves persist | Future persistence requires explicit schema/ownership; current limitation, not unexplained data loss |

No DB/backend/auth/cloud work. A future migration must map proven identities, snapshot original bytes, validate new envelope, recover safely and never invent Method/Session/evidence metadata.

## Open-source/reference decisions

Primary upstream repositories/docs inspected on 2026-10-04. Recommendations are architecture assessments, not permission to install. No dependencies added. Activity risk is qualitative: public docs/source/license availability was verified; no claim of exhaustive security or maintenance SLA. Pin a specific compatible release and recheck license/provenance before later adoption. Integration cost includes tests, pointer/focus ownership and persistence.

| Candidate / provenance | Area and intended value | License / activity risk | Cost and fit | Decision |
| --- | --- | --- | --- | --- |
| [TradingView Lightweight Charts v5.2.1](https://github.com/tradingview/lightweight-charts/tree/v5.2.1) | Chart, panes, primitives, annotations | Apache-2.0 + NOTICE/attribution; installed version audited | Low incremental adapter cost, strong existing fit | ADOPT: retain installed official foundation |
| [Official plugin patterns](https://tradingview.github.io/lightweight-charts/docs/5.1/plugins/intro) | Primitive lifecycle/hit testing, annotation architecture | Official API documentation; example source license must follow upstream before copying; adjacent-version docs not a substitute for installed typings | Low/medium; retain local domain wrappers | ADAPT: API patterns, no proprietary implementation |
| [deepentropy drawing](https://github.com/deepentropy/lightweight-charts-drawing) | Rich tools, projection, placement, serialization | MIT; smaller project, upstream documents a breaking 0.1→0.2 API | High swap/migration and regression cost; current public v5 API differs from historical local 0.2.5 assessment | LEARN: possible future isolated spike; REJECT immediate replacement of validated manager |
| [react-resizable-panels](https://github.com/bvaughn/react-resizable-panels) | Split terminal/workspace resizing | MIT; documented React API, release API changes require pinning | Medium; useful only if multi-panel requirements exceed current hook | ADAPT: conditional later selection, preserve current behavior |
| [Dockview](https://github.com/dockview/dockview) | Dock/tab/floating layouts | MIT for core/React; dockview-enterprise is commercial and excluded; package-specific LICENCE.md must be checked; larger layout surface needs lifecycle review | High; not justified for one vertical resizer; mount/reparent chart risks | LEARN: layout patterns; REJECT immediate full docking migration |
| [TanStack Table](https://github.com/TanStack/table) | Headless terminal/Analysis tables | MIT; broad API requires version choice | Medium; presentation adapter over existing derived rows, no new financial store | ADAPT: if sorting/filtering/large-table requirements justify |
| [Radix Primitives](https://github.com/radix-ui/primitives) | Design primitives, menus/dialogs, focus | MIT/WorkOS; documented accessibility-oriented primitives | Medium; incremental wrapper with existing styling and chart access | ADAPT: evaluate modal/nonmodal focus contract, not whole UI redesign |
| [cmdk](https://github.com/dip/cmdk) | Searchable command/menu patterns | MIT; unstyled React component, upstream owner redirect recorded | Medium; commands must route through existing owners; palette itself is not authorized | LEARN: menu patterns, defer dependency |
| [XState](https://github.com/statelyai/xstate) | Explicit plan/confirm/pending/position statecharts | MIT; actor/state-machine API adds learning/migration cost | High replacement cost, possible bounded workflow fit | LEARN: specification diagrams; do not replace replay scheduler |
| Existing RiskReward + OrderTicket / [Method contract](TRADING_METHOD_SESSION_SPEC.md) | Position planning/order review | Repository-native source and product authority, no new third-party permission claim | Low/medium incremental adaptation; validated separation | ADAPT: existing previews/request boundary before external planner |
| Proprietary TradingView implementations / visual imitation | Trading UX comparison | No open-source permission established for proprietary code/assets | Unacceptable copying cost/provenance; visual similarity is not a license | REJECT code/assets copying; public behavior can inform original design only |

The modern drawing README advertises v5 and a host-owned undo/storage/UI boundary. This does not invalidate the historical removal of the old installed package or prove compatibility with our schema/controllers. No unsupported v4 incompatibility claim is carried forward. MIT candidates require retention of license/copyright when distributed; Apache-2.0 needs corresponding license/NOTICE handling. Existing installed notices/distribution assets remain authoritative in [open-source notices](../OPEN_SOURCE_NOTICES.md). No code copied or new distribution obligations introduced by this report.

## Verified debt and future UX risks

These are source-observed integration concerns or documented limits, not evidence that validated v1 is broken. No BLOCKER was found for this documentation audit or for starting a separately authorized 18.6 audit.

| ID / subsystem | Evidence / severity | Impact | Blocks 18.6 / 18.7 / 18.8 | Action and recommended phase |
| --- | --- | --- | --- | --- |
| D1 workspace orchestration | FigmaWorkspace owns ticket seed, chart picking, replay/reset/news dialogs and several UI state collections; MEDIUM | A later layout move can accidentally change interaction/cancel order | No / No / integration must honor ownership | 18.6 map surfaces; 18.7 define commands/cancellation; 18.8 prototype via adapters, avoid opportunistic extraction now |
| D2 planner/request units | riskRewardOrderSeed permits near-price Market, legacy /100 conversion; no Method validation in useTrading; HIGH future Protocol gap | Reusing v1 seed unchanged would violate future Protocol/instrument constraints | No / must specify / future compliant integration blocked until specified | 18.7 request/risk/instrument contract; 18.8 blocked Protocol states; retain valid v1 behavior now |
| D3 persistence identity | Account/drawing workspace keys do not encode canonical future Method/Session; MEDIUM | Automatic remapping would invent research provenance | No / ownership specification needed / durable integration gated | 18.7 define identity; later explicitly authorized migration, no schema change now |
| D4 focus composition | usePopupFocus traps modal Tab via local element query/Escape; no centralized nested-modal/inert background ownership; MEDIUM | Future stacked dialogs can compete with chart keys/focus | No / No / overlapping modal prototype needs defined focus contract | 18.6 audit keyboard/modal inventory; 18.8 test nested/portal/focus-return if introduced; consider Radix adapter |
| D5 indicator continuity | Indicator instances/pane configuration runtime-only, as documented | LOW; reload loses selected indicator setup, not account/drawing evidence | No / No / No | 18.6 disclose persistence expectations; later authorized versioned configuration if required |
| D6 drawing properties extensibility | Registry/model supports fixed style; eight tools/minimal controls, no full object tree/multi-selection/magnet | LOW bounded feature gap; rich UX requires explicit models and interaction arbitration | No / No / extra feature implementation not implied | 18.6 inventory; later drawing phase adapters, not engine replacement |
| D7 license source pinning | Existing notices disclose fancy-canvas/tslib upstream license provenance from moving branches | LOW reproducibility concern, current release validation passes | No / No / No | Next authorized distribution maintenance: pin verified upstream revisions without altering installed license bytes |

Do not call full indicator recomputation a blocker: reference correctness and benchmark baseline exist; optimize only if measured budget demands it. Live market hook remains mounted during replay, but trading chooses revealed replay raw; this is an observed lifecycle optimization opportunity, not proven look-ahead or an audit blocker. New docking/remounts, native pane reorder, duplicate shortcuts, or direct planner execution are prospective risks requiring targeted tests when actually authorized.

## Regression baseline and validation

Use existing [test commands](../AI_CONTEXT/07_TEST_COMMANDS.md), not a second framework. Registered coverage: market decade/aggregation; trading simulator/separation; Phase 5–9 drawing geometry/interaction/history/storage; Phase 10–12 seven indicators/causality/panes; Phase 13 exact replay differential/ack/cancellation; Phase 14 Analysis/CSV/reset; Phase 14.5 strict news/navigation; Phase 16 storage/identity/cache hardening; repository/archive authority and AI bundle controls. Build/lint/distribution are separate gates. [V1 release](V1_RELEASE.md) and historical browser reports retain prior actual browser evidence.

Fresh closure checks PASS: all registered regression tests, repository/AI bundle controls, lint, production build and release/distribution audit. The dedicated documentation check verified 85 relative links in changed documents, canonical Method contract markers, absence of obsolete semantics outside explicitly historical details, and idle phase boundaries. Bundle generation/freshness is verified after final documentation updates. No new browser smoke is claimed: no runtime/product/build path changed, so the existing workflow's documentation-only exemption applies. Standalone backend tests are not an active local frontend release gate and backend is untouched.

## Blockers and next recommendations

No material product authority conflict remains: conflicting earlier semantics are labeled/delegated to the single Method owner; actual v1 reset/manual trading stays protected and future Method/Session rules are not retroactively imposed. Licensing candidates are recommendations only; no uncertain license is being shipped. No runtime change is necessary to complete this audit.

Recommend human review then separately authorize **18.6 UI/UX Audit & Design System**: map page/panel/modal surfaces, focus/keyboard/touch and chart obstruction, existing tokens/components and low-complexity resizing. No design-system implementation was performed here. For a separately authorized 18.7, specify immutable Method/Session/plan/request/evidence ownership, locked RR/risk and ON/OFF evidence semantics, explicit confirmation and refusal journeys, instrument units and cancellation. Keep simulator/replay/drawing/indicator/news ownership. 18.8/18.9 prototypes/freeze and Phase 19 remain unstarted. Recommendations are not authorization.

## Change inventory

Extended existing AI_CONTEXT/01_PROJECT_STATE.md, 02_ARCHITECTURE.md, 03_PHASE_HISTORY.md and 04_CURRENT_PHASE.md; docs/ROADMAP.md, DOCUMENT_MAP.md, TRADING_METHOD_SESSION_SPEC.md, TRADING_PROTOCOL_SPEC.md, PRODUCT_DESIGN_BLUEPRINT.md, PRODUCT_SYSTEM_ARCHITECTURE_BLUEPRINT.md, BACKTEST_LAB_RESEARCH_THESIS.md and OFFICIAL_LIGHTWEIGHT_CHARTS_AUDIT.md. Added this one focused report. Updated only frontend/scripts/ai-bundle.config.json allowlist to include the Method authority and this report. No files deleted. No runtime, dependency/lock, test source, dataset, archive or release evidence removed/modified. Git final SHA/equality belongs to the final checkpoint report rather than a self-referential SHA here.

# Backtest Lab — master roadmap

```json
{"AUTHORITY":"roadmap","FINAL_PHASE":"75"}
```

This existing roadmap is the sole long-term plan. It was normalized in Phase 7.6 rather than creating a competing AI_CONTEXT roadmap. [Current phase/authorization](../AI_CONTEXT/04_CURRENT_PHASE.md) controls work; [completed history](../AI_CONTEXT/03_PHASE_HISTORY.md) controls historical facts; [workflow/Definition of Done](../AI_CONTEXT/06_WORKFLOW_RULES.md) controls execution. Do not maintain a second current-phase tracker here.

The human has defined the high-level planning scopes below through Phase 75, including 14.5. These are intended architectural/product capabilities, not detailed acceptance criteria or permission to implement. Every future phase remains PLANNED and requires separate human scope definition and authorization. Known Phase 1–3 records remain grouped historically. Completed facts belong to history; operational authorization belongs only to the current-phase pointer. Preserve fractional IDs as strings.

| Phase | Milestone / planning scope | Status source / planning state |
| --- | --- | --- |
| 1 | Trading/drawing separation foundation | Recorded in completed history |
| 2 | Trading/drawing protection (historical Phase 1–3 group) | Recorded in completed history |
| 3 | Trading/drawing protection (historical Phase 1–3 group) | Recorded in completed history |
| 4 | Retire legacy drawing/indicator runtime | Recorded in completed history |
| 5 | Official primitive Trend Line foundation | Recorded in completed history |
| 6 | Selection and canonical drag interaction | Recorded in completed history |
| 6.5 | Multi-AI context/bundle infrastructure | Recorded in completed history |
| 7 | Canonical persistence/history/lock/visibility | Recorded in completed history |
| 7.5 | Repository cleanup/source-of-truth hardening | Recorded in completed history |
| 7.6 | Extend existing project-control authorities | Operational pointer determines checkpoint status |
| 8 | CORE DRAWING TOOLS | Recorded in completed history |
| 9 | ADVANCED DRAWING TOOLS | Recorded in completed history |
| 10 | INDICATOR ENGINE FOUNDATION | Recorded in completed history |
| 11 | OVERLAY INDICATORS | Recorded in completed history |
| 12 | INDICATOR PANES | Recorded in completed history |
| 13 | REPLAY ENGINE OPTIMIZATION & PLAYBACK CONTROLS | PLANNED; separate human authorization required |
| 14 | TRADING UX & BACKTEST ANALYSIS | PLANNED; separate human authorization required |
| 14.5 | ECONOMIC NEWS BACKTESTING ENGINE | PLANNED; separate human authorization required |
| 15 | FINAL FIGMA / UI-UX IMPLEMENTATION | PLANNED; separate human authorization required |
| 16 | FULL QA, PERFORMANCE & HARDENING | PLANNED; separate human authorization required |
| 17 | v1 RELEASE CANDIDATE | PLANNED; separate human authorization required |
| 18 | v1.0 STABLE LOCAL RELEASE | PLANNED; separate human authorization required |
| 19 | BACKEND ARCHITECTURE | PLANNED; separate human authorization required |
| 20 | PRODUCTION DATABASE | PLANNED; separate human authorization required |
| 21 | AUTHENTICATION & IDENTITY | PLANNED; separate human authorization required |
| 22 | USER & WORKSPACE MODEL | PLANNED; separate human authorization required |
| 23 | CLOUD MARKET DATA SERVICE | PLANNED; separate human authorization required |
| 24 | MARKET DATA PIPELINE | PLANNED; separate human authorization required |
| 25 | CLOUD BACKTEST SESSIONS | PLANNED; separate human authorization required |
| 26 | CROSS-DEVICE SYNCHRONIZATION | PLANNED; separate human authorization required |
| 27 | USER DASHBOARD | PLANNED; separate human authorization required |
| 28 | CLOUD OBJECT PERSISTENCE | PLANNED; separate human authorization required |
| 29 | MULTI-TENANT SECURITY | PLANNED; separate human authorization required |
| 30 | CLOUD QA & MIGRATION | PLANNED; separate human authorization required |
| 31 | STRATEGY LIBRARY & VERSIONING | PLANNED; separate human authorization required |
| 32 | PROFESSIONAL TRADING JOURNAL | PLANNED; separate human authorization required |
| 33 | ADVANCED PERFORMANCE ANALYTICS | PLANNED; separate human authorization required |
| 34 | MAE/MFE ANALYTICS | PLANNED; separate human authorization required |
| 35 | TIME, SESSION & ECONOMIC EVENT ANALYTICS | PLANNED; separate human authorization required |
| 36 | MARKET REGIME ANALYTICS | PLANNED; separate human authorization required |
| 37 | STRATEGY COMPARISON ENGINE | PLANNED; separate human authorization required |
| 38 | PORTFOLIO BACKTESTING | PLANNED; separate human authorization required |
| 39 | MONTE CARLO RESEARCH | PLANNED; separate human authorization required |
| 40 | PROFESSIONAL REPORTING | PLANNED; separate human authorization required |
| 41 | MARKET ENGINE v2 | PLANNED; separate human authorization required |
| 42 | TICK DATA ARCHITECTURE | PLANNED; separate human authorization required |
| 43 | TICK STORAGE & STREAMING | PLANNED; separate human authorization required |
| 44 | BID/ASK SIMULATION | PLANNED; separate human authorization required |
| 45 | SPREAD ENGINE | PLANNED; separate human authorization required |
| 46 | TRADING COST ENGINE | PLANNED; separate human authorization required |
| 47 | SLIPPAGE SIMULATION | PLANNED; separate human authorization required |
| 48 | INTRABAR EXECUTION ENGINE | PLANNED; separate human authorization required |
| 49 | EXECUTION ASSUMPTION FRAMEWORK | PLANNED; separate human authorization required |
| 50 | CANDLE VS TICK VALIDATION | PLANNED; separate human authorization required |
| 51 | SUBSCRIPTION ARCHITECTURE | PLANNED; separate human authorization required |
| 52 | BILLING & PAYMENT | PLANNED; separate human authorization required |
| 53 | USAGE & RESOURCE METERING | PLANNED; separate human authorization required |
| 54 | TEAM WORKSPACES | PLANNED; separate human authorization required |
| 55 | ROLE-BASED ACCESS CONTROL | PLANNED; separate human authorization required |
| 56 | SHARED STRATEGY MANAGEMENT | PLANNED; separate human authorization required |
| 57 | COLLABORATIVE RESEARCH | PLANNED; separate human authorization required |
| 58 | AUDIT & VERSION HISTORY | PLANNED; separate human authorization required |
| 59 | ADMINISTRATION & OPERATIONS PLATFORM | PLANNED; separate human authorization required |
| 60 | SaaS SECURITY & RELIABILITY AUDIT | PLANNED; separate human authorization required |
| 61 | RESEARCH DATASET ARCHITECTURE | PLANNED; separate human authorization required |
| 62 | EXPERIMENT TRACKING | PLANNED; separate human authorization required |
| 63 | PARAMETER RESEARCH ENGINE | PLANNED; separate human authorization required |
| 64 | WALK-FORWARD FRAMEWORK | PLANNED; separate human authorization required |
| 65 | ROBUSTNESS & OVERFITTING ANALYSIS | PLANNED; separate human authorization required |
| 66 | STRATEGY REGIME RESEARCH | PLANNED; separate human authorization required |
| 67 | AI RESEARCH ASSISTANT | PLANNED; separate human authorization required |
| 68 | RESEARCH AUTOMATION PIPELINE | PLANNED; separate human authorization required |
| 69 | EXTERNAL MARKET/BROKER INTEGRATION LAYER | PLANNED; separate human authorization required |
| 70 | LIVE MARKET DATA ENGINE | PLANNED; separate human authorization required |
| 71 | PROFESSIONAL PAPER TRADING | PLANNED; separate human authorization required |
| 72 | STRATEGY SIGNAL ENGINE | PLANNED; separate human authorization required |
| 73 | LIVE FORWARD TESTING | PLANNED; separate human authorization required |
| 74 | PRODUCTION RELIABILITY & RISK INFRASTRUCTURE | PLANNED; separate human authorization required |
| 75 | ALGORITHMIC-TRADING READINESS VALIDATION | PLANNED; separate human authorization required |

## Planned version release gates

These are planned release gates, not claims of released capability. Detailed acceptance criteria will be defined through separately authorized planning.

| Version | Release-gate phase | Target identity |
| --- | --- | --- |
| v1.0 | Phase 18 | Professional local/manual trading backtesting and research platform; no production multi-user cloud requirement |
| v2.0 | Phase 30 | Cloud multi-user backtesting platform |
| v3.0 | Phase 40 | Professional strategy research and management platform |
| v4.0 | Phase 50 | High-fidelity market simulation platform |
| v5.0 | Phase 60 | Professional SaaS with users, teams, permissions and administration |
| v6.0 | Phase 68 | Computer-assisted quantitative research platform |
| v7.0 | Phase 75 | Algorithmic-trading-ready research infrastructure |

## v1.0 — CORE BACKTESTING PLATFORM

Phases 1–7.6 retain their existing repository-supported descriptions above.

### Phase 8 — CORE DRAWING TOOLS

Planned scope:

- Horizontal Line

- Vertical Line

- Rectangle

These use the existing:
DrawingManager
DrawingRegistry
model
primitive
interaction
persistence/history architecture.

Completed evidence belongs to [phase history](../AI_CONTEXT/03_PHASE_HISTORY.md). This entry does not authorize additional implementation.

### Phase 9 — ADVANCED DRAWING TOOLS

Scoped tools: Fibonacci Retracement, Arrow, Text and Measure, through the existing drawing architecture. Completed evidence belongs to [phase history](../AI_CONTEXT/03_PHASE_HISTORY.md). This entry does not authorize additional drawing tools or future implementation.

### Phase 10 — INDICATOR ENGINE FOUNDATION

Scoped foundation: revealed candles → validated pure calculation → normalized TIME + VALUE output → official Lightweight Charts series adapter. Registry/instance/parameters, warmup/error isolation, replay-safe synchronization and minimal React/chart lifecycle are implemented. Production registry is empty; the reference close-line is test-only. Native Volume remains separate and legacy runtime retired. Completed evidence belongs to [phase history](../AI_CONTEXT/03_PHASE_HISTORY.md). This does not authorize Phase 11/12 indicators or panes.

### Phase 11 — OVERLAY INDICATORS

Completed authorized scope: exactly SMA, EMA and Bollinger Bands through the existing engine, compatible named multi-output, three official Bollinger lines and runtime-only multiple-instance controls. SMA-seeded EMA and population standard deviation are explicit contracts. Completed evidence belongs to [phase history](../AI_CONTEXT/03_PHASE_HISTORY.md). No panes, indicator persistence or additional products are authorized by this entry.

### Phase 12 — INDICATOR PANES

Completed authorized scope: exactly RSI, MACD, ATR and Stochastic in official Lightweight Charts panes through the existing engine/adapter. One dedicated pane per instance; runtime pane ownership/reindex, native resizing, reference-line lifecycle and minimal existing controls. Overlay indicators remain on price pane. Completed evidence belongs to [phase history](../AI_CONTEXT/03_PHASE_HISTORY.md). This entry does not authorize persistence, extra indicators or Phase 13.

### Phase 13 — REPLAY ENGINE OPTIMIZATION & PLAYBACK CONTROLS (PLANNED)

Planned direction:
Improve replay architecture/performance and professional playback
controls while preserving market/trading correctness.

### Phase 14 — TRADING UX & BACKTEST ANALYSIS (PLANNED)

Planned direction:
Improve simulated trading workflow, trade visualization, backtest
analysis and related trading UX.

### Phase 14.5 — ECONOMIC NEWS BACKTESTING ENGINE (PLANNED)

This is an explicit fractional roadmap milestone.

Planned foundation:

- historical economic-event data

- canonical event timestamps

- timezone normalization

- currency

- event name/category

- impact

- previous

- forecast

- actual

- historical news markers on chart

- filtering by impact

- filtering by currency

- filtering by event

- next/previous economic-event navigation

- dedicated news-backtesting workflow

- relationship between trades and nearby economic events

- pre-news / during-news / post-news research windows

- news-aware trade metadata

Intended research use includes events such as:

- CPI

- NFP

- FOMC

- PCE

- GDP

and instruments such as XAUUSD.

This phase must be treated as a real data/research subsystem,
not merely decorative chart icons.

Do not implement it now.

### Phase 15 — FINAL FIGMA / UI-UX IMPLEMENTATION (PLANNED)

Planned direction:
Apply the final professional visual/interaction design after the
core engines are sufficiently stable.

UI redesign must not casually rewrite validated engines.

### Phase 16 — FULL QA, PERFORMANCE & HARDENING (PLANNED)

Planned direction:
System-wide regression, performance, reliability and compatibility
hardening before release candidate.

### Phase 17 — v1 RELEASE CANDIDATE (PLANNED)

Planned direction:
Feature freeze, release validation, bug fixing and documentation.

### Phase 18 — v1.0 STABLE LOCAL RELEASE (PLANNED)

CHECKPOINT:
Backtest Lab v1.0

Target identity:
Professional local/manual trading backtesting and research platform.

No requirement for production multi-user cloud architecture at v1.0.

## v2.0 — CLOUD & MULTI-USER

### Phase 19 — BACKEND ARCHITECTURE (PLANNED)

Plan:
Establish production-oriented backend/service/API boundaries.

### Phase 20 — PRODUCTION DATABASE (PLANNED)

Plan:
PostgreSQL-oriented production persistence, migrations, indexing,
backup/restore and schema lifecycle.

### Phase 21 — AUTHENTICATION & IDENTITY (PLANNED)

Plan:
Secure user identity, authentication, session/token lifecycle,
recovery and supported login methods.

### Phase 22 — USER & WORKSPACE MODEL (PLANNED)

Plan:
Formal user/workspace ownership model for Backtest Lab resources.

Conceptual relationship may include:

User
→ Workspace
→ Backtests
→ Strategies
→ Drawings
→ Indicators
→ Preferences

This is conceptual planning, not a locked database schema.

### Phase 23 — CLOUD MARKET DATA SERVICE (PLANNED)

Plan:
Serve historical market data through cloud infrastructure.

### Phase 24 — MARKET DATA PIPELINE (PLANNED)

Plan:
Ingestion
→ validation
→ normalization
→ aggregation
→ storage
→ delivery.

Maintain consistent source relationships such as M1 to higher
timeframes where applicable.

### Phase 25 — CLOUD BACKTEST SESSIONS (PLANNED)

Plan:
Server-backed creation/save/resume of backtest sessions.

### Phase 26 — CROSS-DEVICE SYNCHRONIZATION (PLANNED)

Plan:
Allow a user's validated workspace/session state to move across
supported devices.

### Phase 27 — USER DASHBOARD (PLANNED)

Plan:
Professional user-facing management of strategies, sessions,
activity, statistics and workspace resources.

### Phase 28 — CLOUD OBJECT PERSISTENCE (PLANNED)

Plan:
Cloud persistence for appropriate drawings, indicators, layouts and
configuration.

### Phase 29 — MULTI-TENANT SECURITY (PLANNED)

Plan:
Tenant isolation, authorization, validation, rate limiting and
related security boundaries.

### Phase 30 — CLOUD QA & MIGRATION (PLANNED)

Plan:
Validate migration from local-oriented architecture toward the
multi-user cloud architecture, including concurrency and recovery.

CHECKPOINT:
Backtest Lab v2.0
Cloud multi-user backtesting platform.

## v3.0 — PROFESSIONAL RESEARCH & STRATEGY MANAGEMENT

### Phase 31 — STRATEGY LIBRARY & VERSIONING (PLANNED)

Plan:
Make strategy definitions first-class research objects with appropriate
metadata and version history.

### Phase 32 — PROFESSIONAL TRADING JOURNAL (PLANNED)

Plan:
Research-oriented journal tied to backtest trades, setups and notes.

### Phase 33 — ADVANCED PERFORMANCE ANALYTICS (PLANNED)

Planned metrics/research may include:

- expectancy

- profit factor

- average R

- drawdown

- recovery

- streaks

- equity behavior

- return distributions

- context-appropriate risk-adjusted statistics

Metrics must use transparent definitions.

### Phase 34 — MAE/MFE ANALYTICS (PLANNED)

Plan:
Maximum Adverse Excursion / Maximum Favorable Excursion research.

### Phase 35 — TIME, SESSION & ECONOMIC EVENT ANALYTICS (PLANNED)

Plan:
Analyze performance by:

- time

- day

- month

- trading session

- economic-event context

Build on the Phase 14.5 economic-event foundation.

### Phase 36 — MARKET REGIME ANALYTICS (PLANNED)

Plan:
Research behavior across defined market regimes such as trend/range
and volatility conditions.

### Phase 37 — STRATEGY COMPARISON ENGINE (PLANNED)

Plan:
Consistent comparison of strategies, versions and relevant parameters.

### Phase 38 — PORTFOLIO BACKTESTING (PLANNED)

Plan:
Research multiple strategies/instruments in portfolio context.

### Phase 39 — MONTE CARLO RESEARCH (PLANNED)

Plan:
Sequence randomization/distribution research, drawdown behavior,
robustness and transparent risk assumptions.

### Phase 40 — PROFESSIONAL REPORTING (PLANNED)

Plan:
Professional research/equity/strategy reporting and appropriate
export/share capabilities.

CHECKPOINT:
Backtest Lab v3.0
Professional strategy research and management platform.

## v4.0 — HIGH-FIDELITY MARKET SIMULATION

### Phase 41 — MARKET ENGINE v2 (PLANNED)

Plan explicit abstraction between:

- Candle Mode

- Intrabar / Tick Mode

### Phase 42 — TICK DATA ARCHITECTURE (PLANNED)

Plan schema/ingestion/indexing for high-resolution market data.

### Phase 43 — TICK STORAGE & STREAMING (PLANNED)

Plan scalable chunking, compression, caching and progressive delivery.

### Phase 44 — BID/ASK SIMULATION (PLANNED)

Plan explicit bid/ask-aware market simulation.

### Phase 45 — SPREAD ENGINE (PLANNED)

Plan fixed and variable/historical spread assumptions.

### Phase 46 — TRADING COST ENGINE (PLANNED)

Plan configurable:

- commission

- swap/funding

- appropriate execution costs

### Phase 47 — SLIPPAGE SIMULATION (PLANNED)

Plan deterministic/configurable/testable slippage assumptions.

### Phase 48 — INTRABAR EXECUTION ENGINE (PLANNED)

Plan higher-resolution execution sequencing where adequate data exists.

### Phase 49 — EXECUTION ASSUMPTION FRAMEWORK (PLANNED)

Research results should eventually record applicable assumptions such as:

- spread

- slippage

- commission

- tick availability

- fill assumptions

- intrabar resolution

### Phase 50 — CANDLE VS TICK VALIDATION (PLANNED)

Plan sensitivity/comparison tooling for candle-mode versus
higher-fidelity execution assumptions.

CHECKPOINT:
Backtest Lab v4.0
High-fidelity market simulation platform.

## v5.0 — PROFESSIONAL SaaS & ORGANIZATION MANAGEMENT

### Phase 51 — SUBSCRIPTION ARCHITECTURE (PLANNED)

Plan centralized product entitlements for future plan tiers.

### Phase 52 — BILLING & PAYMENT (PLANNED)

Plan subscription/payment lifecycle and entitlement synchronization.

### Phase 53 — USAGE & RESOURCE METERING (PLANNED)

Plan measurement/quotas for relevant compute, storage, market-data and
research-job resources.

### Phase 54 — TEAM WORKSPACES (PLANNED)

Plan organization/team-oriented multi-user workspaces.

### Phase 55 — ROLE-BASED ACCESS CONTROL (PLANNED)

Planned role concepts may include:

- Owner

- Admin

- Researcher

- Analyst

- Viewer

Exact permissions will be defined before implementation.

### Phase 56 — SHARED STRATEGY MANAGEMENT (PLANNED)

Plan organization-owned/shared strategy workflows.

### Phase 57 — COLLABORATIVE RESEARCH (PLANNED)

Plan comments, notes, annotations and review workflows.

### Phase 58 — AUDIT & VERSION HISTORY (PLANNED)

Plan durable accountability:
who changed what, when, and from which version.

### Phase 59 — ADMINISTRATION & OPERATIONS PLATFORM (PLANNED)

Plan internal management of users, organizations, subscriptions,
data jobs, incidents and relevant resources.

### Phase 60 — SaaS SECURITY & RELIABILITY AUDIT (PLANNED)

Plan system-level review of:

- authorization

- abuse resistance

- billing integrity

- tenant isolation

- backup/recovery

- operational reliability

CHECKPOINT:
Backtest Lab v5.0
Professional SaaS with users, teams, permissions and administration.

## v6.0 — QUANTITATIVE RESEARCH & STRATEGY INTELLIGENCE

### Phase 61 — RESEARCH DATASET ARCHITECTURE (PLANNED)

Plan structured/reproducible datasets for quantitative experiments.

### Phase 62 — EXPERIMENT TRACKING (PLANNED)

Conceptual reproducibility chain:

Strategy Version
+ Parameters
+ Dataset Version
+ Execution Assumptions
→ Experiment
→ Results

### Phase 63 — PARAMETER RESEARCH ENGINE (PLANNED)

Plan controlled batch parameter experiments.

Do not treat the best in-sample result as proof of strategy validity.

### Phase 64 — WALK-FORWARD FRAMEWORK (PLANNED)

Plan rolling optimization/training and out-of-sample validation
workflows.

### Phase 65 — ROBUSTNESS & OVERFITTING ANALYSIS (PLANNED)

Plan parameter sensitivity, neighboring parameter behavior,
out-of-sample degradation and related diagnostics.

### Phase 66 — STRATEGY REGIME RESEARCH (PLANNED)

Plan systematic study of strategy behavior across market regimes.

### Phase 67 — AI RESEARCH ASSISTANT (PLANNED)

Plan AI assistance for:

- reading experiment results

- identifying anomalies

- summarizing research

- generating hypotheses

AI has NO live-money trading authority.

### Phase 68 — RESEARCH AUTOMATION PIPELINE (PLANNED)

Plan:

- queued experiments

- workers

- reproducible runs

- automated comparisons

- scheduled research jobs

CHECKPOINT:
Backtest Lab v6.0
Computer-assisted quantitative research platform.

## v7.0 — LIVE RESEARCH & PRE-ALGORITHMIC INFRASTRUCTURE

### Phase 69 — EXTERNAL MARKET/BROKER INTEGRATION LAYER (PLANNED)

Plan provider abstraction for market/account interoperability.

Initial intent is integration infrastructure, not permission for
automatic real-money execution.

### Phase 70 — LIVE MARKET DATA ENGINE (PLANNED)

Plan:

- realtime quotes

- candles/ticks where supported

- reconnect

- sequence validation

- gap handling

### Phase 71 — PROFESSIONAL PAPER TRADING (PLANNED)

Plan live-market virtual execution including appropriate:

- orders

- fills

- SL/TP

- spread

- slippage

- commission

- positions

- P&L

### Phase 72 — STRATEGY SIGNAL ENGINE (PLANNED)

Plan structured strategy outputs such as:

LONG
SHORT
EXIT
Entry
Stop
Target
Risk parameters
Reason/context

A strategy signal is NOT automatically a broker order.

### Phase 73 — LIVE FORWARD TESTING (PLANNED)

Plan continuous strategy evaluation using live data and paper execution.

Support research comparison between:
historical
→ walk-forward
→ live forward results.

### Phase 74 — PRODUCTION RELIABILITY & RISK INFRASTRUCTURE (PLANNED)

Plan:

- orchestration

- worker recovery

- monitoring

- alerting

- logging

- metrics

- backups

- redundancy where justified

- incident handling

- system-level risk controls

### Phase 75 — ALGORITHMIC-TRADING READINESS VALIDATION (PLANNED)

Final planned audit of the complete research chain:

Strategy
→ Historical Backtest
→ High-Fidelity Simulation
→ Robustness Analysis
→ Walk Forward
→ Paper Trading
→ Live Forward Testing
→ Signal Engine
→ Risk Controls
→ Monitoring
→ STOP

CHECKPOINT:
Backtest Lab v7.0

Target identity:
Algorithmic-trading-ready research infrastructure.

## Hard boundary after Phase 75

The approved master roadmap ENDS at Phase 75. Do NOT create Phase 76. Algorithmic-trading readiness does not authorize automatic live trading. Autonomous live broker order placement, unattended real-money execution, and automatic conversion of strategy signals into live-money positions remain OUT OF SCOPE unless separately decided and authorized by the human in the future.

This normalization is planning/documentation only. No product/runtime/build path changes; browser verification is exempt under the existing workflow. Operational status is unchanged: planning is not implementation authorization.

## Historical prototype/backend roadmap — preserved verbatim

The following initial roadmap is historical evidence, not a second authority. Its old phase numbering and feature statements describe the prototype/backend checkpoint and are not mapped automatically onto the current phase sequence.

> HISTORICAL: roadmap prototipe/backend awal. Penomoran dan status di bawah bukan status produk saat ini. Lihat AI_CONTEXT/01_PROJECT_STATE.md dan 04_CURRENT_PHASE.md untuk kondisi aktual serta izin fase.

# Backtest Lab — Roadmap

## Hasil inspeksi kode yang ada (index.html v0.3)

**Sudah berfungsi (prototipe satu file):** chart candle, BUY/SELL, SL/TP, spread, komisi,
slippage, lot dari risiko %, kurva ekuitas, riwayat trade, Play/Next/Previous.

**Utang teknis yang harus diselesaikan:**
- Semua candle (termasuk masa depan) berada di memori browser, jadi belum bebas look-ahead.
- Data acak (80 candle), belum ada impor CSV.
- Logika trading ada di JavaScript frontend, padahal seharusnya di engine backend.
- Tombol PREVIOUS tidak membatalkan trade yang sudah tertutup, hasil bisa tidak konsisten.
- Slippage pada TP dikurangkan dengan cara yang sama seperti pada SL; perlu ditinjau ulang.
- Belum ada tes otomatis.

**Yang bisa dipakai ulang:** rumus lot dari risiko, konsep mode eksekusi SL-first/TP-first,
gaya tampilan (Poppins), susunan panel statistik dan riwayat.

## Fase 1 — Fondasi replay (sedang dikerjakan)
- [x] Model candle ternormalisasi (UTC)
- [x] Impor + validasi CSV (tidak ada perbaikan diam-diam)
- [x] Replay engine + tes anti look-ahead
- [x] Service dan API FastAPI
- [x] Data contoh XAUUSD 1 jam (simulasi)
- [x] Frontend: chart, kontrol replay, dialog impor terhubung ke API
- [x] Uji alur API lokal: impor CSV, mulai replay, dan maju satu candle

## Fase 2 — Order dan eksekusi
Market order, limit/stop, SL/TP dengan kebijakan intrabar yang terdokumentasi, spread,
slippage, komisi, position sizing (engine backend + tes).

**Kemajuan awal:** engine market order backend sudah dibuat dan dites: BUY/SELL, ukuran posisi
dari risiko, spread/slippage/komisi, SL/TP, gap melewati SL, penutupan manual, dan reset.
Jika satu candle menyentuh SL dan TP, SL diproses lebih dulu. Harga OHLC dianggap harga tengah;
jarak SL/TP dihitung dari harga entry aktual. Pengaturan akun default: saldo 10.000, kontrak
100 unit, biaya 0; semua nilai dapat diatur saat memulai replay. Frontend kini memiliki panel
BUY/SELL, risiko dan jarak SL/TP, penutupan manual, riwayat trade, serta marker entry/exit dan
garis harga posisi. Pending order dapat dibatalkan, pemicunya hanya diperiksa saat replay
maju, dan pengisian yang langsung menyentuh SL/TP mengikuti kebijakan SL-first. Analytics kini
menampilkan equity realized dari trade tertutup; floating P&L dan equity akun live masih perlu dibuat.

**Chart:** chart memakai TradingView Lightweight Charts (Apache-2.0). Overlay SMA 20, EMA 20,
dan EMA 50 dapat dinyalakan atau dimatikan langsung pada chart. Indikator dihitung dari candle
yang sudah terlihat di replay agar tidak membaca data masa depan. Tersedia garis harga sekali
klik, trendline dua titik, hapus garis gambar, serta pemilihan harga pending order dari chart
untuk dikonfirmasi di panel trading. Fitur berikutnya: RSI/volume dan pengelolaan order penuh
langsung dari chart.

**Position tool workflow:** Cursor, Long Position, dan Short Position tersedia. Klik chart untuk
membuat proyeksi posisi; Entry, stop, dan target dapat disesuaikan dengan handle. Proyeksi ini
hanya gambar rencana dan tidak mengirim order. Tiket order tetap dikonfirmasi secara terpisah.

**Chart UX — Phase 1 Shell:** top bar, left vertical tool groups, area chart utama, panel kanan,
dan kontrol replay bawah mulai dipisahkan. Dropdown timeframe pada shell hanya demo tampilan;
dataset candle tetap memakai timeframe saat impor. Interaction drawing yang lebih lengkap
menyusul di fase berikutnya.

## Fase 3 — Akun dan P&L
Balance realized dan riwayat trade terhubung ke replay. Berikutnya: floating P&L, equity live
saat posisi masih terbuka, dan batas risiko akun.

## Fase 4 — Jurnal dan analitik
- [x] Analytics posisi tertutup: P&L, saldo, win rate, expectancy, profit factor, average R, winners/losers, performa BUY/SELL, dan hasil harian.
- [x] Kurva equity realized, drawdown maksimum, ekspor CSV trade, dan simulasi target RR berbasis hasil R historis.
- [ ] Jurnal dengan tag/catatan per trade, filter tanggal/aset/arah, dan kalender performa.
- [ ] Statistik sesi dan metrik durasi pemulihan drawdown.

## Fase 5 — Fitur lanjutan
Multi-timeframe (agregasi OHLC), alat gambar, Monte Carlo, simulator prop firm.

## Fase 6 — Produksi
Login, PostgreSQL, penyimpanan cloud, deployment.

## Asumsi yang berlaku sekarang
- Semua waktu disimpan dalam UTC. Timestamp CSV tanpa offset dianggap berada di zona waktu yang dipilih saat impor.
- Gap data (akhir pekan, libur) hanya peringatan; data dengan error ditolak seluruhnya.
- Replay default mulai di candle ke-101 supaya ada riwayat 100 candle di belakang titik mulai.
- Previous hanya menggeser tampilan; kemajuan baru dilacak oleh `high_water`.

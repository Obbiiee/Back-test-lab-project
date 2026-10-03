# Backtest Lab — Product Design Blueprint

> **Status:** Living product-design memory / planning document  
> **Purpose:** Menyimpan keputusan UX, product language, information architecture, monetization experience, dan AI Research Assistant agar ide tidak hilang.  
> **Authority:** Dokumen ini bukan implementation authorization dan tidak menggantikan ROADMAP atau AI_CONTEXT/04_CURRENT_PHASE.md.

## Product Identity

Backtest Lab adalah **laboratorium penelitian trading**, bukan sekadar chart replay dengan statistik tambahan.

- **Chart = meja kerja**
- **Experiment = objek penelitian**
- **Basic Results = observasi**
- **Benchmark = pembanding**
- **Research Labs = instrumen penelitian**
- **Experiment Passport = catatan laboratorium**
- **AI = research assistant**
- **User = decision-maker**

> **Backtest Lab does not tell traders how they must trade. It shows the statistical consequences of how they choose to trade.**

> **Don't trust the claim. Test it.**

UX: **Freedom First → Evidence Second → Guardrails Optional.**  
Behavior: **Observe quietly → Analyze deeply → Warn selectively → Never force.**

## Product Journey

IDEA → TEST → VALIDATE → DESTROY → SIZE → REPLICATE → FORWARD/LIVE → AUDIT → IMPROVE

## Main Surfaces

1. **Chart Workspace** — chart, replay, drawings, indicators, trading, news, journal, Analysis.
2. **Lab Protocol** — hypothesis, Strategy Rules (the single canonical Inclusion/Exclusion rule set), RR/risk, planned N/stopping rule, optional execution checklist, blind settings, and execution assumptions.
3. **Research Results Workspace** — post-experiment evidence dashboard.
4. **Research Labs** — Statistical Evidence, RR Lab, Monte Carlo, Survival, Strategy Destruction, Regime, Robustness, OOS/Walk Forward, Research Integrity, Portfolio, Behavioral Audit.
5. **Experiment Passport** — reproducibility/provenance.
6. **AI Research Assistant** — grounded in verified experiment results.
7. **Dashboard/Workspace** — cloud management of strategies, experiments, sessions and reports.

## Lab Protocol v1 — Controlled Experiment Contract

Lab Protocol is available as a research mode rather than a premium-only methodology. It should preserve chart usability while preventing silent post-result rule changes.

### Protocol Setup

Before the experiment is committed, define:
- hypothesis / research question;
- **Strategy Rules = Inclusion / Exclusion Rules** — one canonical rule set, not separate duplicated concepts;
- entry definition;
- exit model;
- risk;
- planned sample / stopping rule;
- optional execution checklist;
- blind/randomization settings where used;
- execution assumptions.

### Strategy Rules & Execution Checklist

Strategy Rules contain the conditions that qualify or disqualify an opportunity. If **Execution Checklist = ON**, these same Strategy Rules are surfaced before execution; the user must not maintain a second duplicate checklist definition.

Checklist behavior:
- ON or OFF is chosen as part of the protocol;
- if ON, at least one rule must be marked **Required**;
- rules may be Required or Optional/Observation where appropriate;
- if OFF, protocol recording, Experiment Passport and no-look-ahead remain active;
- checklist state is recorded in the protocol.

### Workspace Freedom, Temporal Strictness

**Lock the hypothesis, not the workspace.**

A primary/decision timeframe does not lock the chart to that timeframe. During an experiment the user may switch among available timeframes, zoom, inspect prior candles, use drawings and perform multi-timeframe analysis.

All views share one canonical replay time. Switching timeframe must never expose future information. An unfinished higher-timeframe candle may expose only information actually available at replay time, never its future final OHLC.

### Exit Contract

For a **Fixed-RR Protocol**:
- RR is committed before the experiment and remains constant for every qualifying trade;
- SL distance may vary according to the committed strategy/entry logic, and TP is derived from the fixed RR;
- after entry, the trade resolves through the committed SL/TP execution model;
- no discretionary early close;
- no discretionary partial close;
- no moving SL or TP;
- no mid-experiment RR change.

If the strategy genuinely uses a variable or structural exit, it must use a **Rule-Based Exit Protocol** whose exit rule is committed before the experiment. Planned behavior such as a predefined partial exit may therefore be researched, but spontaneous intervention after observing a live trade is not part of a Fixed-RR experiment.

A desired change such as RR 1:1.25 → 1:2, excluding a newly noticed condition, or introducing early-close logic creates a new Strategy/Protocol version and a new experiment rather than rewriting the committed experiment.

### Experiment Lifecycle

Conceptual lifecycle:

```text
DEFINE
  ↓
COMMIT
  ↓
BLIND / REPLAY
  ↓
EXECUTE
  ↓
RECORD
  ↓
ANALYZE
  ↓
REPLICATE
```

Commit creates/version-locks the Experiment Passport. The running experiment should remain relatively quiet about interim performance so that temporary results do not unnecessarily influence execution.

The central principle is:

> **Lab Protocol does not remove the trader's freedom to read the market. It removes the freedom to silently change the experiment after learning from its results.**

## Research Results Workspace

Illustrative layout:

    EXPERIMENT #...                         LAB PROTOCOL ✓
    XAUUSD • M15 • Strategy v3 • N=428 • RR 1:1.25
    ---------------------------------------------------
    BASIC RESULTS             RESEARCH BENCHMARK
    Win Rate   48.6%          Break-even WR 44.4%
    Net P/L    +31.2R         Delta baseline +4.2pp
    Expectancy +0.073R        Sample 428
    PF          1.17
    Max DD     -8.4R
    ---------------------------------------------------
    EQUITY / DRAWDOWN / DISTRIBUTION
    ---------------------------------------------------
    BASIC ANALYSIS            ADVANCED RESEARCH — PRO 🔒
    Trade distribution        Statistical Evidence
    Average R                 Monte Carlo
    Historical DD             Survival Analysis
    Actual streaks            Strategy Destruction
    Journal                    RR Lab / Regime / OOS

Numbers above are UI examples, not product claims.

## Benchmark-First Design

A raw metric should be paired with relevant context whenever scientifically defensible.

Observed WR, break-even WR, difference, N, RR, expectancy and historical drawdown form a useful basic evidence card. Benchmark does not automatically prove edge; uncertainty, multiple testing, robustness and OOS belong to deeper evidence.

## Free vs Paid

### FREE — Test the idea
- Free Backtest
- Lab Protocol
- currently defined free historical-data window
- basic descriptive results
- break-even benchmark
- equity curve and historical drawdown
- actual streaks
- trade journal
- basic AI explanation if commercially viable

### PRO — Investigate the evidence
- extended historical data
- Statistical Evidence
- RR Laboratory
- Monte Carlo / Survival
- Strategy Destruction
- Regime Analysis
- Robustness
- OOS / Walk Forward
- Research Integrity / multiple testing
- Portfolio / Correlation
- Behavioral / Live Audit
- deeper AI workflows
- full research report

> **Do not sell freedom. Sell more data and deeper evidence.**

Pricing, quotas and final plan names remain undecided.

## Locked Research Cards

Locked modules should show what they measure rather than becoming empty paywall boxes.

Example:

    MONTE CARLO LAB                       PRO 🔒
    10,000 simulated paths
    Median MaxDD                🔒
    95th percentile MaxDD       🔒
    Worst simulated streak      🔒
    P(MaxDD > threshold)        🔒
    [ Unlock Research Analysis ]

Do not fabricate hidden values. Avoid disruptive upgrade popups.

## Research Lab Questions

- **Statistical Evidence:** How strong is the evidence?
- **Monte Carlo Lab:** What could different trade sequences do?
- **Strategy Destruction Lab:** What happens when assumptions get worse?
- **RR Laboratory:** How sensitive is the strategy to RR?
- **Market Regime Lab:** Where does the strategy behave differently?
- **Robustness Lab:** Do small changes destroy the result?
- **OOS / Walk Forward:** Does evidence survive fresh data?
- **Research Integrity:** Was exploration mistaken for confirmation?

## AI Research Assistant UX

AI is not a generic chatbot or trading guru. It consumes verified context: Experiment Passport, protocol, dataset/execution versions, statistics, Monte Carlo, regime, robustness, OOS and Research Integrity results.

AI may explain, summarize, compare, identify anomalies, expose uncertainty, propose next experiments and answer questions about experiments.

AI must not invent canonical statistics, silently alter protocols/results, produce universal GOOD/BAD strategy scores, promise profitability, or replace deterministic research engines.

Flow:

    VERIFIED ENGINE RESULTS
              ↓
    RESEARCH CONTEXT BUILDER
              ↓
    AI RESEARCH ASSISTANT
              ↓
    Explanation / Hypothesis / Next Experiment
              ↓
         HUMAN DECISION

## Information Hierarchy

1. What happened? → Basic Results
2. Compared with what? → Benchmark
3. How uncertain is it? → Statistical Evidence
4. What if sequence changes? → Monte Carlo
5. What if assumptions worsen? → Strategy Destruction
6. Where does it behave differently? → Regime
7. Does it survive small changes? → Robustness
8. Does it survive fresh data? → OOS / Walk Forward
9. Did research choices inflate evidence? → Research Integrity
10. Am I executing what I tested? → Behavioral / Live Audit

## Experiment Passport UX

Show Experiment ID/hash, strategy/protocol versions, dataset version, instrument/timeframe/period, RR/risk, planned vs actual N, seed, regime version, execution assumptions, engine version and exploratory/confirmatory status.

The Passport answers: **Exactly what produced this result?**

## Behavioral Design

Use measurable behavior, not psychological labels. Prefer “median risk after losing trades increased from X to Y” over “revenge trading detected.”

## Mobile / Desktop

Desktop is the primary high-density research workspace. Mobile should prioritize dashboard, experiment status, reports/results, AI Research Assistant, journal review and lightweight session management. Do not force a cramped desktop clone.

## Open Design Questions

Do not prematurely lock exact pricing, AI quotas, final navigation, final visual system, mobile chart scope, report format, team UX, or exact free-data limits if commercial testing later changes them.

## Design North Star

> **Backtest Lab should make sophisticated research understandable without pretending uncertainty is simple.**

The UI must distinguish observed facts, benchmarks, statistical inference, exploratory findings, validated/OOS evidence and AI interpretation.

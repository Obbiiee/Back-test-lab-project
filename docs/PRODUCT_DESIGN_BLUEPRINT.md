# Backtest Lab — Product Design Blueprint

> **Domain precedence (Phase 18.4):** [Trading Method & Session specification](TRADING_METHOD_SESSION_SPEC.md) owns current Method/Session semantics. Older mode/version language below is historical design/research terminology where it conflicts: Session inherits its Method, Protocol is Planned-only, checklist OFF retains evidence, and cross-pair coverage is not a maturity requirement. Technical version/hash provenance remains useful; it is not a mandatory user-facing Method-version workflow. These blueprints preserve strategic knowledge and do not authorize runtime changes.

> **Status:** Living product-design memory / planning document  
> **Purpose:** Menyimpan keputusan UX, product language, information architecture, monetization experience, dan AI Research Assistant agar ide tidak hilang.  
> **Authority:** Dokumen ini bukan implementation authorization dan tidak menggantikan ROADMAP atau AI_CONTEXT/04_CURRENT_PHASE.md.

## Alpha screen acceptance (2026-10-10)

This extends the existing design owner under [the Alpha scope amendment](V2_ALPHA_FROZEN_SPEC.md#0a-human-approved-alpha-product-closure-amendment-2026-10-10). The existing `UI_FIGMA_PREVIEW.jpg`, Phase 15 Figma UI and Phase 18.6 design tokens are the visual baseline. Do not substitute a donor demo/dashboard as the product design. The Method/Session contract continues to own product semantics.

| Screen ID | Required interaction and visible outcome |
| --- | --- |
| workspace | Chart dominates; left tool icons have labels/tooltips; strategy and saved Session are visible; instrument is XAUUSD with unobtrusive Exness source credit; timeframe/indicators/replay are grouped; Order opens on action; News opens from its control; bottom terminal has six-dot drag, keyboard resize/collapse/restore and persisted safe bounds |
| method_session | First use explains strategy and Session in familiar language; choose/create Method once, inherit its type; user names Session, chooses available start period and initial balance only at creation; restore retains balance/evidence; do not seed product-facing names such as Method Exness 2015 or Session Exness |
| order_review | Quick or Long/Short plan opens ticket; exact Entry/SL/TP/risk/size/RR and costs assumptions are readable; Protocol restrictions visible; immutable review before explicit Confirm; cancel/Escape returns focus without submitting; repeated confirmation does not duplicate orders |
| journal_analysis | Pending/positions/history/journal/analysis use the same canonical identities; notes do not change account; unresolved and unavailable measures have readable explanations; export retains provenance |
| source_details | Opening source credit shows provider feed identity, actual available period and quality/ordering limits; credits express thanks, not broker endorsement or redistribution permission; no technical dataset hash/path in routine creation flow |
| feedback | Optional short survey after meaningful replay/order/Analysis use; can dismiss; no modal on every load or trade; response save/error/retry explicit; failure never interrupts trading |
| identity_workspace | Hosted path has real login/verification/recovery/logout and private workspace; local path identified as private/local; no fake login; access denial and expired identity preserve work safely |

Browser acceptance must exercise the actual product at desktop and 780/375px widths, with no overflow hiding essential actions. Dialog Tab/Escape/focus recovery, empty/loading/error/reconnect states and six-dot interaction are required. Verify screenshot composition against the existing design reference; automated financial tests alone do not certify UI quality. Use a new QA Method/Session and isolated annotation namespace, not the user's saved evidence. Source uncertainty remains accessible without overwhelming the chart.

Product wording: **strategi → sesi → replay → rencanakan order → konfirmasi → jurnal → analisis**. Session is a continuing research context; leaving/reopening a workspace is a usage milestone, not a product Finish state. Exness identifies data, never the user's strategy. Keep one workspace with an explicit legacy rollback; fixture routes are engineering tools rather than separate products.

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


## SEO & Organic Growth Architecture

> **Status:** Growth planning direction, not implementation authorization. Exact keywords, volumes and priorities must be validated with current search data before execution.

### Objective

SEO exists to acquire traders with a real research problem and move them through:

```text
SEARCH / SOCIAL
      ↓
Useful Evidence / Education / Free Tool
      ↓
Free Backtest or Lab Protocol
      ↓
Activated Research User
      ↓
Deeper Research Need
      ↓
PRO
```

Optimize for qualified activation and eventual retained research usage, not pageviews alone.

### Search Intent Architecture

**Commercial / product intent**
- backtesting software;
- trading backtest tool;
- forex backtesting software;
- XAUUSD/gold backtesting;
- chart replay/backtesting alternatives;
- strategy testing/research software.

**Problem / research intent**
- how many trades are enough for a backtest;
- break-even win rate;
- risk-reward ratio;
- maximum drawdown;
- losing streak probability;
- Monte Carlo for trading;
- backtest overfitting;
- out-of-sample testing;
- walk-forward testing;
- slippage/spread impact;
- backtest vs live performance.

**Free-tool intent**
Candidate indexable utilities:
- Break-even Win Rate Calculator;
- Risk/Reward Calculator;
- drawdown/risk preview tools;
- backtest sample-size/evidence explainer;
- Monte Carlo preview where scientifically defensible.

Tools should provide genuine utility and naturally connect to Backtest Lab research workflows.

### Public Information Architecture

Candidate public routes:

```text
/
 /backtesting
 /forex-backtesting
 /xauusd-backtesting
 /tools/<tool>
 /learn/<topic>
 /research/<topic>
 /pricing
```

Exact slugs remain subject to keyword research and information-architecture review. Private workspace, account, experiment-management and other non-public application surfaces should not be indexed merely to increase page count.

### Content Engine

One strong research idea should be reusable across channels:

```text
Research Question
   ├─ Long-form article
   ├─ YouTube episode
   ├─ Reels/Shorts
   ├─ Carousel
   ├─ Free calculator/tool
   └─ Product CTA / experiment template
```

Example: **“Risk 1% itu datang dari mana?”** can become an educational article, short video, risk calculator and entry point to Survival/Find Your Risk.

Content should lead with trader problems and evidence questions rather than feature announcements.

### Technical SEO Requirements

When public pages are implemented, plan for:
- indexable server-rendered/static public content where appropriate;
- unique descriptive title, H1 and metadata;
- canonical URLs;
- XML sitemap;
- robots directives;
- Open Graph/social metadata;
- semantic HTML and descriptive image alt text;
- breadcrumb/internal-link architecture;
- deliberate redirects and 404 behavior;
- mobile usability;
- strong Core Web Vitals/performance budgets;
- structured data only when it truthfully matches visible content;
- clear index/noindex separation between public acquisition pages and private app surfaces;
- multilingual/hreflang only when real localized content exists.

SEO requirements must not make the latency-sensitive chart/replay workspace heavier.

### Content Quality & Programmatic SEO Guardrail

Do not mass-produce thin pages by combining instrument/timeframe/RR keywords. A page should exist because it provides distinct user value such as original explanation, calculator, methodology, research visualization, benchmark, or evidence.

AI may assist drafting and repurposing, but publication requires factual/research review. Do not manufacture performance claims, fake statistics, fake testimonials or implied guaranteed profitability.

### Internal Linking

Build topic clusters around:
- Backtesting Fundamentals;
- Edge & Statistical Evidence;
- Risk & Survival;
- Execution Reality;
- Robustness & Overfitting;
- OOS / Walk Forward;
- Trading Research Methodology.

Educational pages should link to the most relevant tool, experiment workflow or product capability rather than forcing every page directly to checkout.

### Measurement

Track the funnel rather than rankings alone:

```text
Organic Impression
→ Search Click
→ Useful Content/Tool Engagement
→ Signup
→ First Replay/Experiment
→ Completed Experiment
→ Repeat Research
→ Pro Conversion
```

Candidate metrics include non-brand organic clicks, qualified landing sessions, tool usage, signup conversion, activation rate, completed experiments from organic acquisition, retained organic cohorts and paid conversion. Search rankings are diagnostic metrics, not the North Star.

### Rollout

**Stage 0 — Before public launch**
- keyword/competitor research;
- public IA;
- technical SEO baseline;
- homepage/product positioning;
- initial cornerstone content;
- 2–4 genuinely useful free tools/calculators.

**Stage 1 — Launch**
- commercial landing pages;
- research/education clusters;
- sitemap/canonical/indexation QA;
- connect social/YouTube content to corresponding searchable resources;
- measure search → activation.

**Stage 2 — Evidence-led growth**
- expand topics from real search/user questions;
- publish original Backtest Lab research where scientifically appropriate;
- improve pages using Search Console/product analytics evidence;
- build legitimate references/backlinks through useful research/tools rather than spam.

**Stage 3 — International growth**
- expand English-first/global topics as product/data rights support them;
- add localized content only when maintained as genuine localization;
- build market/instrument landing pages only when they provide unique product or research value.

### SEO Principle

> **Do not optimize Backtest Lab to attract the most visitors. Optimize it to become the most useful answer for traders trying to test a claim.**

Brand bridge:

**Don't Trust the Claim. Test It.**


## Website Product Surface Plan

> **Status:** Approved website/product planning scope. This is a design plan, not implementation authorization and does not change the current implementation phase.

Backtest Lab should be designed as a complete web product rather than only a chart application. Public acquisition, activation, education, trust, support and product feedback surfaces are part of the intended website experience.

### 1. Public Website

The public website should eventually include:
- homepage with clear problem, positioning, evidence-oriented differentiation and primary CTA;
- product/backtesting overview;
- Lab Protocol explanation;
- Research Labs/capability overview;
- pricing and Free vs Pro comparison;
- public methodology/research-integrity explanation;
- public tools/calculators;
- Learn/Academy and research content;
- documentation/help center;
- changelog/release notes;
- trust/security/methodology area;
- system status entry point;
- contact/support entry point;
- required legal/disclosure pages.

Public pages should be fast, indexable where appropriate, accessible, mobile-friendly and separated architecturally from the latency-sensitive research workspace.

### 2. Signup, Onboarding & Activation

Do not treat account creation as activation.

Target journey:

```text
Landing
→ Try / Sign Up
→ Choose Free Backtest or Lab Protocol
→ Load sample/import eligible data
→ First replay action
→ First trade/observation
→ Complete first experiment/backtest
→ Understand result
→ Save/return
```

Provide:
- short product orientation;
- sample/demo path that avoids an empty-chart dead end;
- contextual guidance rather than a mandatory long tour;
- progress/resume where appropriate;
- clear first-success moment;
- contextual explanation of Free vs Pro without blocking core understanding.

Primary activation candidate: **first completed meaningful backtest/experiment**, not merely registration. Exact activation definition must be validated from product analytics.

### 3. Help Center & Backtest Lab Academy

Create an educational layer explaining both product usage and research concepts.

Candidate content:
- getting started;
- chart/replay/import workflows;
- Free Backtest vs Lab Protocol;
- Strategy Rules and Experiment Passport;
- RR, expectancy and break-even win rate;
- drawdown and losing streaks;
- Monte Carlo and survival;
- robustness/overfitting;
- OOS and walk-forward;
- execution assumptions, spread and slippage;
- methodology definitions;
- troubleshooting and FAQs.

Contextual **What does this mean?** links should connect complex metrics to concise explanations without cluttering the research workspace.

Academy/help content should reuse the SEO architecture where useful, but documentation accuracy takes priority over keyword optimization.

### 4. Trust & Transparency Center

Because the brand asks users to test claims, Backtest Lab should expose how its own evidence is produced.

Candidate public trust surfaces:
- methodology and metric definitions;
- no-look-ahead principles;
- execution-model assumptions;
- Experiment Passport/provenance explanation;
- data-source/coverage disclosure where licensing permits;
- security/privacy overview;
- research-integrity principles;
- AI role and limitations;
- affiliate/sponsored-content disclosure;
- service status and incident communication entry point;
- changelog/version transparency.

Do not expose secrets, internal security details that increase attack surface, private datasets, or information prohibited by data/provider agreements.

### 5. Support & Feedback Experience

Plan first-class flows for:
- bug reports;
- product questions;
- billing/account issues;
- data/import issues;
- feature requests;
- research/methodology questions;
- abuse/reporting when public/community content eventually exists.

Support should capture useful context such as app version, experiment ID or sanitized diagnostics where appropriate, with user awareness and privacy safeguards.

Feedback should be classifiable and measurable rather than living only in founder DMs.

### 6. Product Analytics & Experimentation

Instrument the product funnel with privacy-conscious first-party event semantics.

Core funnel:

```text
Visitor
→ Signup
→ First Replay
→ First Experiment
→ Completed Experiment
→ Return / Repeat Research
→ Pro Conversion
→ Retention / Churn
```

Measure feature adoption and failure points, not only pageviews. Candidate measures include activation, experiment completion, repeat research, retention cohorts, Free→Pro conversion, tool/content→product conversion, import failures, abandoned workflows and support burden.

Analytics must not alter deterministic research results or become a hidden dependency of replay/research functionality. Exact vendor is deferred.

### 7. In-Product Communication

Plan restrained product communication:
- notifications center;
- release/changelog announcements;
- relevant experiment/job completion notices;
- billing/account notices;
- optional educational/product guidance;
- user-controlled communication preferences.

Avoid interruptive growth mechanics inside active replay/research sessions.

### 8. Account & User Control Center

Eventually provide coherent controls for:
- profile;
- plan and entitlement visibility;
- billing/subscription entry points;
- usage/data allowance visibility;
- preferences;
- privacy;
- security/session controls as supported;
- data export/deletion/request flows as required;
- notification preferences;
- public-profile controls if Community is later enabled.

### 9. Reliability & Status Experience

Public SaaS should eventually provide a user-facing way to understand service health and incidents.

Plan:
- status surface/page;
- incident communication;
- maintenance notices where needed;
- clear degraded-state UX;
- retry/recovery guidance;
- preservation of user work where architecture permits.

Do not claim uptime/SLA targets until they are actually supported and measured.

### 10. Accessibility, Responsive UX & Performance

Website quality requirements should include:
- keyboard accessibility for appropriate controls;
- semantic structure and accessible labels;
- readable contrast and focus states;
- responsive public/account/help surfaces;
- explicit mobile scope for the research workspace;
- performance budgets and measurement;
- graceful loading/error/empty states;
- localization-ready text architecture without prematurely translating everything.

Accessibility and performance are product-quality requirements, not final cosmetic polish.

### 11. Website Information Architecture

Candidate top-level model:

```text
PUBLIC
├── Home
├── Product
├── Backtesting
├── Lab Protocol
├── Research
├── Tools
├── Learn / Academy
├── Pricing
├── Trust
├── Docs / Help
└── Login / Start Free

APP
├── Workspace
├── Experiments
├── Results / Research Labs
├── Journal
├── Data
├── Dashboard
├── Notifications
└── Account / Billing / Settings

LATER
└── Community
    ├── Feed
    ├── Analysis
    ├── Public Experiments
    ├── Profiles
    └── Fork / Replicate
```

Final navigation labels remain subject to UX testing.

### 12. Website Success Model

The website should optimize for a chain of real user value:

**Discover → Understand → Trust → Try → Complete Research → Return → Upgrade → Advocate.**

Do not optimize one stage at the expense of research integrity. Traffic without activation is not success; signup without completed research is not success; conversion obtained through misleading claims is not success.

### Website Planning Priority

These website surfaces are approved as intended scope, but should be implemented only when their roadmap dependencies are ready. Near-term work remains governed by the current phase authorization. Community remains deferred to the post-roadmap option already recorded in the master roadmap.


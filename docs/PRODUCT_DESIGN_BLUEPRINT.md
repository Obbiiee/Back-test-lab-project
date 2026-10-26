# Backtest Lab — Product Design Blueprint

> **Domain precedence (Phase 18.4):** [Trading Method & Session specification](TRADING_METHOD_SESSION_SPEC.md) owns current Method/Session semantics. Older mode/version language below is historical design/research terminology where it conflicts: Session inherits its Method, Protocol is Planned-only, checklist OFF retains evidence, and cross-pair coverage is not a maturity requirement. Technical version/hash provenance remains useful; it is not a mandatory user-facing Method-version workflow. These blueprints preserve strategic knowledge and do not authorize runtime changes.

> **Status:** Living product-design memory / planning document  
> **Purpose:** Menyimpan keputusan UX, product language, information architecture, monetization experience, dan AI Research Assistant agar ide tidak hilang.  
> **Authority:** Dokumen ini bukan implementation authorization dan tidak menggantikan ROADMAP atau AI_CONTEXT/04_CURRENT_PHASE.md.

## Alpha screen acceptance (2026-10-10)

This extends the existing design owner under [the Alpha scope amendment](V2_ALPHA_FROZEN_SPEC.md#0a-human-approved-alpha-product-closure-amendment-2026-10-10). The existing `UI_FIGMA_PREVIEW.jpg`, Phase 15 Figma UI and Phase 18.6 design tokens are the visual baseline. Do not substitute a donor demo/dashboard as the product design. The Method/Session contract continues to own product semantics.

| Screen ID | Required interaction and visible outcome |
| --- | --- |
| research_home | One local informational home linked to the existing workspace, original clean research/math/data-science design, readable responsive navigation, no invented performance/customer claims or hard selling; no API/data loading from the home |
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


## Alpha strategy/source composition evidence (2026-10-11)

From clean/equal `92ddcaaaee35ace8b6b24f929f3cb101ab87edab`, a bounded R-4A product-language slice reuses current components/tokens, without a visual-layout change. New strategy opens the existing immutable Method form; newly saved strategy becomes the default for the next Session, while reopening another Session selects its own Method. First use explains strategy → Session → replay → orders → results. No old Method/Session is renamed or automatically migrated. Creation still posts the same fields/identities; no account mutation or Session Finish state was introduced.

XAUUSD shows an Exness text credit button for historical mode (not a fabricated brand logo). It opens the existing modal with thanks, selected start month, already-revealed cursor time and explicit unverified quality/equal-time ordering/unresolved/display-only/rights limits. Synthetic mode identifies an authored fixture without Exness credit. No provider, dataset-size/EOF/future windows or unrestricted metadata is fetched. Raw source disclosure remains available on demand instead of being the workspace banner. Backend eligibility and financial truth are unchanged.

Actual5173 checks: source dialog shows the selected December period and acknowledged2015-12-01T00:30:02Z only; Tab reaches disclosure, wraps to Close and Escape restores the credit opener. Initial focus trap skipped the native summary; explicit tabindex0 integrates it into the existing modal policy. New Alpha onboarding verification QA strategy automatically selected in Create Session; Cancel restored opener and did not submit. Existing QA Session retained10000/revision0/Ray. Initial build/HMR reported a missing stamp export; shared existing formatter was moved into display and imported by terminal/source, then final lint/build/distribution succeeded. Earlier failed logs remain recorded rather than called a clean cumulative dev console.

Full registered frontend regression PASS, including source escaping/immutability and rejection of rendering extra futureTicks/EOF fields. Final125-module production build and license distribution PASS. Fresh production5196 QA Session/source panel has zero captured warning/error logs, reaches Source disclosure by Tab and restores the opener on Escape. At375x780 the existing source dialog has375px client/scroll width; viewport reset afterward. Ignored production screenshot: frontend/tests/artifacts/alpha-source-production-20261011.jpg. Repository/bundle/golden gates and preserved42.18/42.20 fingerprints PASS. Backend is unchanged; prior292actual-PG zero-skip evidence remains applicable. This does not certify the complete screen checklist, visual Figma match, News/order layout, hosted identity, advanced metrics, survey/cost or internal Alpha acceptance.

Visual implementation requires a real Figma Make URL or node-specific Design URL under the loaded figma-design-to-code skill (high-fidelity get_design_context plus screenshot). Repository and read-only local Figma Make snapshot contain source and preview but no file/node URL; none was guessed and no replacement Figma file created. Requested the missing link asynchronously and completed the independent product-language/source slice. Operational status and remaining work remain solely in04_CURRENT_PHASE. The existing accepted multi-checkpoint grant persists; no new product authorization is requested merely for receiving the design reference.

## Approved Riksora visual refinement plan (2026-10-12)

Human approved the Riksora Labs concept board ("ya acc design") and requested planning before closing V2.2. This section owns the visual requirements; operational permission/status remains in04_CURRENT_PHASE and sequencing in the existing Alpha ledger. It is a refinement of existing R-4 surfaces, not another roadmap or execution contract. Earlier composition evidence below remains historical.

### Brand and tokens

Use the supplied original metallic R, never an AI-redrawn substitute. Source: `Logo R Metalik Minimalis.png`, SHA256 `08f9dae81b9ee6bb7c798e1b67aeb2991b5b1e6aedef095fa9ca99de4f20bd1a`. The approved generated board is a layout/style reference only; numbers, dates, data ranges and controls are illustrative, not product evidence.

Palette: midnight navy `#06162E`, electric blue `#0965FF`, ice white `#F5F8FC`, silver `#C8D1DE`, amber `#FFC83D`, muted text `#64748B`. Amber is reserved for important evidence/warning states. Positive/negative financial colors retain semantic contrast. Use existing local/system sans typography, tabular numbers,14px readable body and12px minimum secondary text where practical; avoid new remote font requests. White research home, dark navy analytical workspace, restrained8px corners, subtle coordinate geometry only on informational surfaces. Logo header is compact; no heavy metallic textures behind data.

### Implementation mapping and order

| Existing surface | Planned refinement | Existing files / boundary |
| --- | --- | --- |
| Research home | Riksora identity, approved "Don't trust the claim. Test it." message, hypothesis/test/evidence diagram, clear workspace link and getting-started sequence | `AlphaHome.jsx`, `tickAlpha.css`; preserve pagePath query/source/Session context; no invented results or new catalog fetch on informational home |
| Workspace shell and empty/loading/error states | Compact brand/header, descriptive strategy/Session controls, XAUUSD and existing source credit, clear next action | `TickAlpha.jsx`, `AlphaAccount.jsx`, shared scoped CSS; no default-route change, account mutation or fake login functionality |
| Chart/replay | Navy chrome, readable toolbar hierarchy, grouped existing timeframe/replay controls | `AlphaWorkspace.jsx`; keep CandleChart/Lightweight Charts, drawings TIME+PRICE, indicator inputs, callbacks and replay scheduling |
| Order and source/news surfaces | Order appears on user action with compact right-side layout; preserve price picking, review/confirm, Protocol restrictions and explicit uncertainty | `AlphaOrderPresentation.jsx`, existing TickAlpha order form/modal and `AlphaSourceDetails.jsx`; no new news ingestion or fictitious News terminal tab |
| Terminal/journal/analysis | Restyle existing six-dot resize grip, tabs, tables and empty states; retain existing functional tab inventory | `AlphaTerminal.jsx`, `AlphaJournal.jsx`, `AlphaBootstrap.jsx`; no changes to calculations, trade grouping, exports, resize persistence or evidence scope |

First implement brand/home, then shell/chart presentation, then order/terminal presentation. Use separate validated Git checkpoints within existing R-4 refinement; keep changes small, no large-file rewrite, dependency upgrade or new UI framework. A small shared brand component/asset is justified only if multiple current headers use it; update the existing bundle allowlist when needed. Copy only the original approved logo asset for runtime; social feed posters and full concept board remain references, not large app backgrounds. Image editing/cropping requires the image tool unless explicitly authorized otherwise; prefer original-file display with CSS sizing.

The chart-first workspace remains the default. Informational home remains the existing explicit home route; do not silently redirect existing Sessions to a new dashboard. A live saved-research table belongs to the existing catalog-backed workspace until an independently reviewed reuse is implemented; never populate it with mock sessions.

### Acceptance before local product closure

Verify1280px desktop and375px narrow layout, keyboard focus/Escape/return, terminal pointer and keyboard resizing/collapse/restore, actual source credit, drawing create/select/edit/history/timeframe, order review/confirmation and unchanged canonical state, saved Session reload, unsupported/unavailable states, and clean console. Run registered frontend regression, lint/build/distribution, repository/bundle and independent contract vectors; backend regression only if backend/runtime contract code changes. No existing test expectations may be weakened for visual PASS. Audit as an adversarial reviewer after implementation, with reproducible findings.

HTTPS/account-browser acceptance remains human-deferred to VPS. UI completion does not close20x, RAM/reference-host, rights or final Alpha gates. No subscription/pricing/payment, external deployment, new source data, future evidence, fabricated fill or v2.3 feature is part of this plan.

## Alpha workspace/home composition evidence (2026-10-11)

The human explicitly resolved the missing design input: retain the existing local Figma chart UI/source and originally design other surfaces in a clean professional research/math/data-science direction without hard selling. This supersedes the earlier link dependency for this scope; no direct Figma matching claim. Informational research_home shares the same private entry/router and preserves Session/source query context, without fetching market data or inventing performance/customer claims. Existing default workspace and legacy rollback remain.

R-4 retains chart/drawing/indicator/order/replay/financial owners and adds a compact right action rail for Order/News/source, grouped replay/seek, on-demand display limitations, responsive sizing and guarded terminal UI persistence isolated by dataset version/Session. News explicitly has no connected point-in-time dataset; no present-day news is substituted. Terminal unknown/future/foreign bytes remain read-only; quota/denied storage falls back to memory with status. No backend/dependency/financial command/evidence trust or raw dataset change.

Actual5173 QA Session cf95b50b: News and Order open only on actions; Escape restores each opener. Invalid empty seek refuses before a command. Home navigation returns to the same Session/source; cash10000 and acknowledged2015-12-01T00:30:02Z remain unchanged. Six-dot drag144→224 works; Home24 persists across reload and Restore reopens144. At375x780, workspace scrollWidth370≤375 and the limitation panel ends before the order bar; viewport reset. Initial mobile height caused overlap and was corrected before acceptance. Existing saved Ray remains rendered in its dev-origin namespace.

Fresh production5196 home→same QA Session→News/Escape passes with zero captured warn/error logs and unchanged cash. Ignored proof images: frontend/tests/artifacts/alpha-home-production-20261011.jpg and alpha-workspace-production-20261011.jpg. Production namespaces are separate; no drawing restore claim is transferred across origins. Full registered frontend regression, lint,126-module build, release/license audit, independent Node6x3 and protected42.18/42.20 fingerprint comparison PASS. Repository/bundle/diff/Git closure is required before R-5. This is R-4 presentation acceptance, not full Alpha, hosted identity, research metrics, survey/cost, final recovery/capacity or post-implementation adversarial release acceptance.

### Alpha optional feedback screen evidence — 2026-10-11

Existing WorkspaceModal and native form controls provide a requested, dismissible seven-choice survey from Analysis after observed entered/unresolved order history; no automatic modal or preselected opinion. Opt-in notice states local/private/internal purpose,30-day access-based expiry, public-metric exclusion, response limit, disable/export/remove controls and stated-interest distinction. Human-readable price/choice labels retain fixed machine values. Existing Product Measurement Contract owns semantics/storage/privacy/limits; no survey builder or second product design authority.

Actual production browser confirms dismiss/reopen, opt-in, explicit authored QA answers, saved status/disabled duplicate save, cold persisted response explanation, parsed export review, disable and Escape/opener focus. The initial key press on a nonfocusable dialog timed out; Escape on its real button succeeds. Cash9995.5 and canonical research remain unchanged, console no warning/error. Ignored alpha-feedback-production-20261011.jpg and alpha-feedback-final-production-20261011.jpg record this internal QA, not an external user's opinion. Export prepares bounded JSON before an explicit download link, with a review fallback and canceled optional network request on timeout/unmount. Unknown hosted cost is null, not a fabricated estimate. This does not complete identity, public measurement/privacy rollout, final readiness or the requested final Alpha audit.

### Riksora brand/home implementation evidence — 2026-10-12

First approved presentation slice fromab57c8d: AlphaHome now uses the supplied original metallic R, RIKSORA LABS identity, blue/navy/ice palette, hypothesis/test/evidence geometry and the approved headline. Home remains an explicit pagePath route, performs no catalog/network fetch, and retains source/Session query semantics and uncertainty/provenance disclosures. Former home-only CSS moved into lazy AlphaHome-owned alphaHome.css; the chart stylesheet no longer owns landing styles. Narrow bundle allowlist adds only the CSS and original asset. Logo bytes match08f9dae81b9ee6bb7c798e1b67aeb2991b5b1e6aedef095fa9ca99de4f20bd1a; original1,229,337bytes retained rather than silently editing the artwork. No posters, sample profits, invented catalog entries, dependency or execution changes.

Validation: all registered frontend regression PASS, lint PASS, production134modules/build PASS, distribution audit PASS, bundle generation/verification257files PASS, independent Node6goldens×3 PASS. Restricted Windows run initially failed SSR/realpath access; identical regression/bundle run with required filesystem access passed without changing tests. Production localhost home1280 and375responsive DOM reviewed, logo loaded, mobile main370/scroll370px (no horizontal overflow), keyboard focus outline visible, home→workspace navigation PASS, warning/error console empty. Saved screenshot is ignored frontend/tests/artifacts/riksora-ui/home-desktop.jpg. Backend rerun exempt: this slice changes presentation/asset only, no backend/domain/schema/transport code. Remaining scope is workspace/order/terminal visual refinement and final adversarial/regression acceptance; capacity/reference gates remain OPEN and HTTPS remains deferred to separately authorized VPS.

### Riksora workspace/header implementation evidence — 2026-10-12

Second approved slice from7c0bc06: shared small AlphaBrand reuses original mark for workspace/account headers; account header now owns its layout independently of lazy home CSS. Alpha-scoped palette overrides leave legacy tokens untouched. CandleChart uses official applyOptions for research-only background/grid/text/borders after the existing chart mounts, with no recreation/series/data/coordinate/interaction changes; non-research colors remain unchanged. Existing contracts, callbacks and account HTTPS requirement preserved. Bundle allowlist adds only brand JSX/CSS.

All registered frontend regression/lint/build136modules/distribution/bundle259files/independent Node6goldens×3 PASS. Saved Alpha drawing journey reopened at$10000, same2015-12-01T00:30:02acknowledged cursor;1m→3m displayed25→9revealed bars without cursor/balance change. Grid off/on, Fit and home→workspace Session-query roundtrip PASS. Production5196 saved-session/brand render,375px main370/scroll370(no horizontal overflow), empty error/warn console PASS. Existing horizontal drawing remained visible across chart presentation change. Desktop screenshot ignored riksora-ui/workspace-desktop.jpg. Backend exempt for presentation-only changes; no execution/schema/financial/provider/storage or private/draft changes. Third remaining approved visual slice is action-triggered order/terminal refinement; final adversarial acceptance and capacity/reference gates remain open, HTTPS deferred.

### Riksora order/terminal visual refinement and bounded adversarial review — 2026-10-12

Third approved slice fromfd55a79 changes only Alpha CSS:420px action-triggered right order drawer (full width on narrow screens), readable controls/exact quote typography, existing six-dot terminal grip, underlined view selectors and sticky table header. Modal semantics/focus hook, financial callbacks, server review/confirmation, time/price picking, quantity/risk and execution remain unchanged. News still explicitly states no point-in-time dataset is connected; no fabricated events. Final CSS adds drawer scroll containment/safe-area padding and balanced home headings/anchor scroll margin.

All registered frontend regression PASS, lint/build136modules/distribution PASS; final CSS-only corrections revalidated lint/build/distribution. Bundle259files and independent Node6goldens×3 PASS before final documentation refresh. Browser review: click and keyboard open Order, desktop1280drawer left860/right1280/width420,375screen panel374/client scroll374(no horizontal overflow), Shift+Tab traps focus, server review quotes exact Ask1065.17/quantity0.1/risk basis10000/no planned-stop R0, Cancel and Escape return New order focus; no Confirm order was submitted and saved cash remains10000. Terminal224→234→224 via arrows, Home collapse/Enter restores224, Pending empty-state, news unavailable disclosure and production order/terminal render/console PASS. Ignored evidence riksora-ui/order-desktop.jpg and workspace-desktop.jpg. Backend rerun exempt for CSS-only changes; full financial/concurrency/security acceptance is not replaced by these UI checks.

Bounded adversarial findings (not final Alpha release acceptance):
- frontend/src/tickAlpha/tickAlpha.css:77 — drawer originally lacked scroll containment/notch padding; corrected and production computed overscroll=contain verified.
- frontend/src/tickAlpha/AlphaAccount.jsx:45 — prior shared home-header styles depended on home CSS; workspace slice gave account its own header and verified HTTP refusal. HTTPS login acceptance still human-deferred, not passed.
- frontend/src/assets/riksora-mark.png:1 — original1.23MB is large for a small mark; retained byte-identical under approved original-artwork rule. Public asset optimization remains a disclosed performance follow-up, not a claim of failure-free public delivery.
- No observed financial mutation from presentation/review/cancel, no invented News/data/profit, no new dependency or execution-authority change. Existing frozen exact decimal/UTC presentation is retained rather than applying generic locale suggestions that could obscure evidence.
- Capacity20x/reference host/85%-RAM and final end-to-end Alpha acceptance remain OPEN; last actual probe17.219946x/highest sampled host92% is not a passing capacity certificate. HTTPS remains deferred to separately authorized VPS. No full new backend benchmark/security/production-readiness PASS is claimed.

UI review used the current Vercel Web Interface Guidelines: https://raw.githubusercontent.com/vercel-labs/web-interface-guidelines/main/command.md. This is a guidance reference, not a competing product/architecture authority. Existing approved visual slices are implemented; resume only existing readiness/acceptance scope before declaring V2.2 complete.

### Human chart-presentation correction — 2026-10-12

Human clarified that current workspace functionality is good but wants original local Figma/FX Replay-inspired chart appearance. This supersedes strong navy workspace colors above, not approved home or historical evidence. Reference: existing UI_FIGMA_PREVIEW.jpg; no proprietary source copied. Chart #101216, chrome #171a20, controls #20242c, border #2c313a, text #e8ebf0/#adb5c2 and restrained accent #6da5ff. Smaller header/four-pixel corners/quiet toolbar retain controls, callbacks, routes and financial/causal boundaries. Only Alpha CSS and official research-only chart colors change; no engine, home, dependency, dataset or draft changes.

Actual375px browser reproduced replay controls intercepting New order: elementFromPoint at button center returned alpha-replay-controls. Fixed420px mobile workspace was shorter than wrapped controls. Intrinsic mobile workspace height with bounded360px chart body fixes overlap without altering order logic. Rebuilt production375px actual click opens Plan an order; main370/scroll370, drawer374/scroll374, containment retained. Development terminal312→322→312, modal Escape/opener focus, timeframe1m→3m→1m (28→10→28bars) and Fit verified. Saved cursor2015-08-10T00:30:00.000Z, Bid1089.843/Ask1090.264 and cash10000 unchanged; no order confirmed. Production1280px main1280/scroll1280, empty warn/error console. Ignored proof: riksora-ui/fx-workspace-desktop.jpg and fx-workspace-order-mobile.jpg.

Full registered frontend regression PASS; final CSS fix lint/build136modules/distribution PASS; Node6goldens×3 PASS. Backend rerun exempt for presentation-only code; retained backend evidence is historical, not new release acceptance. Capacity/reference/final acceptance remain open; HTTPS deferred. No new roadmap/status authority.

### Senior workspace UX critique, correction and first-user walkthrough — 2026-10-12

Starting clean baseline aaaf416bea8cd5f0eaebe997dd171d0041c90fa6, freshly verified against origin/main and actual GitHub main. Human explicitly requested senior UX critique, fixing/rechecking observed issues and an actual first-user backtest walkthrough. Existing R-4 owner remains authoritative; this is bounded UI work, not capacity remediation, new architecture or final Alpha acceptance. Impeccable and UI UX Pro Max informed the review. Two independent read-only assessments separated design judgment from detector/code evidence; the parent performed actual browser verification. No extra product/roadmap authority was created. Further interview questions were skipped because the human explicitly requested applying and rechecking the findings.

Reference observed: official public FX Replay backtest page https://fxreplay.com/campaigns/backtest and its replay screenshot, plus existing local Figma reference. No authenticated FX Replay workspace was tested, proprietary source copied, or exact parity claimed. The chosen direction retains the approved neutral dark chart, quiet rails and current product functions.

Findings and corrections:
- P1: terminal tabs were buried beneath duplicate headings/account explanation. Existing six tabs now lead the panel; redundant visible headings remain available to assistive technology, account values remain exact, explanation becomes an accessible disclosure.
- P1: order validation lived in the footer behind the modal. Errors now appear inside the order ticket, INVALID_INPUT has recovery guidance, and opening a ticket clears stale notices. Actual second review caught a stale reopen message inside the new alert and corrected it.
- P1: time/technical wording obscured replay state. Current acknowledged UTC and forming-candle status lead an expandable evidence summary; next requested boundary is visible with complete ISO tooltip. Seek UTC initializes from the current revealed cursor when opened, preserving user typing while open. Financial/replay callbacks and intervals are unchanged.
- P2: no clear empty-workspace primary action. Contextual create-strategy/Session action and concise Free Style/Protocol explanation reuse existing creation behavior. Copy avoids claiming every returning user is creating their first Session.
- P2: partial-close controls remained available after a Session ended, unlike full close. They now follow the same ended-state refusal; no reducer/execution behavior changed.
- P2: long requests disabled controls without useful feedback. Existing live status now explains processing. Mobile drawing/rail/view targets are at least44px; browser scrollbars/caret/selection follow the neutral theme.
- Recheck: Evidence now explains unresolved execution in plain language without assigning an invented root cause or fill.

Actual walkthrough used a separately named local QA Session, UI UX first-user QA 2026-10-12, session:6db95337-0a97-4182-bbac-b7cdede0e352, existing Alpha onboarding verification Free Style strategy, August2015, balance10000. No user Session was replayed/reset. Creation was saved and independently reopened from the catalog. Quantity0 yielded INVALID_INPUT visibly inside the ticket; quantity0.1 produced exact Ask1090.264 review. Confirm accepted the intent; one4-second replay interval yielded acknowledged2015-08-10T00:30:04 and honest UNRESOLVED, not a fabricated execution. Journal reported no entry/exit fill, Analysis0completed/1unresolved, committed cash10000/net0. Cold reload preserved the cursor, unresolved order and cash. Seek opening held exact2015-08-10T00:30:04;3m timeframe and Fit preserved acknowledged cursor/cash. Terminal keyboard144→154→144, News explicit unavailability and mobile modal checks completed. Existing user's Session remains untouched. The QA record is intentionally retained as evidence, not silently deleted.

Responsive recheck:1280×900 page width1280, all six terminal selectors visible at y758; Final spacing/disclosure correction increases chart plot341→385px with compact144px terminal; collapsing the existing terminal gives505px. This preserves discoverable terminal tabs while providing an explicit larger-chart mode rather than hiding controls.375×812 page width375; replay ends before the order bar starts (no overlap); narrow layout uses vertical scrolling rather than squeezing the full desktop workspace. Final mobile replay bottom908.8px/order top958.15px. Source/history/context chrome is still dense on phones; desktop remains the stronger research experience. Ignored screenshots: frontend/tests/artifacts/riksora-ui/senior-ux-desktop.jpg and senior-ux-mobile.jpg.

Validation: all registered frontend regression passed after the primary UI edits; final notice/busy/evidence refinements passed lint,136-module production build, release/distribution audit and focused tick-alpha/stitch-trading tests. Independent Node6vectors×3 passed. Detector on final four files emitted exactly one stylistic warning: overused-font, existing Inter at tickAlpha.css:1. Retained for the approved incumbent workspace; no rule suppression or clean-detector claim. Browser warning/error console empty on QA reload and production5196 saved-state render. Backend rerun exempt: no backend/schema/transport/provider/evidence/financial code changed; prior343zero-skip backend result remains historical evidence, not a fresh release claim.

Remaining blockers: opening the older December Alpha drawing journey during this review hit the existing30-second read deadline. This is retained failed performance evidence; neither increasing deadlines nor capacity-engine changes is in this UI checkpoint. Ambiguous historical execution prevents a completed-trade success story for this QA order. The latest capacity/reference status remains in04_CURRENT_PHASE; HTTPS stays human-deferred to separately authorized VPS. UI changes do not certify defect-free software, full mobile equivalence, broker fills, public readiness or V2.2 completion.

### Approved local FX Replay-inspired workspace composition — 2026-10-12

Human supplied C:\Users\kuchi\OneDrive\Dokumen\contoh design, confirmed it as inspiration, then explicitly requested UI only. Starting clean local/origin/actual GitHub main9ec82c8539f068316e6eb662ae20e710a3f6fba3,0/0. Source zip SHA256627561eb501e83c471de86ff57d839eb74c87ef6897730c67364382db04d31f7 contains a React Figma Make prototype and supplied FX Replay screenshots. Inspected as design evidence only: its simulated candles, unimplemented tool catalogue and custom drawing logic were not imported, executed or treated as production evidence. No external Figma link was required for this explicitly approved local reference.

Bounded adaptation changes only TickAlpha.jsx and tickAlpha.css: existing Method/Session controls remain available in native Session settings disclosure; quiet source/Session strip remains; desktop replay controls float above the existing chart; Order/News/Journal/Source controls form a labeled floating action group. Journal popup reuses the existing AlphaJournal and WorkspaceModal, with existing canonical transport, draft/save/refusal semantics and focus trap, rather than a second journal engine. Mobile keeps controls docked and the icon rail accessible to avoid floating overlap. Six-dot terminal drag/keyboard resize is unchanged. Replay overlay is positioned, not falsely represented as draggable. Original brand/home, underlying chart, candles, ticks, drawing/indicators, financial callbacks, review/confirmation and source semantics remain intact. No dependency/data/backend/contract change. The requested pre-Session one-month candle history is a separate pending requirement and was not implemented by this UI-only grant.

Validation: all registered frontend regression PASS; lint PASS; production136modules/build and release/distribution audit PASS; independent Node6goldens×3 PASS. Final detector reports exactly the existing Inter stylistic warning at tickAlpha.css:1, not an accessibility/error finding or clean-detector certificate. No typography/ignore-rule change was used to hide the warning. Backend rerun exempt for presentation/composition-only changes; historical backend evidence remains historical.

Actual isolated QA browser:1440×900 and production1280×900 width=scrollWidth, plot467px with144px terminal (previous385px in the same900px height). Native Session settings exposes current strategy/create/reopen/reload, New strategy opens existing modal, Cancel preserves state. Journal popup fetches committed revision2/unresolved/no-fill state, Escape restores Open journal panel focus; no journal note or financial command submitted. Terminal144→154→144.375×812 width=scrollWidth375; menu left38/right348/width310, journal panel/scroll375 (subpixel375.2border box), replay bottom759.3/order top808.65 (no overlap). News remains explicitly unavailable; production console error/warn empty. Ignored proof: frontend/tests/artifacts/riksora-ui/local-reference-desktop.jpg and local-reference-mobile.jpg. Existing QA balance10000/cursor2015-08-10T00:30:04/unresolved state unchanged. User's Session not replayed/reset. Separate capacity/reference/HTTPS/final Alpha acceptance limitations remain owned by04_CURRENT_PHASE; this presentation checkpoint does not close them.

### Live FX Replay reference: bounded workspace refinement — 2026-10-12

Human authorized implementation after direct account exploration; starting clean local/origin/actual GitHub main5f5edb6959a61a375a416da0a8b6608146018d50. Reference supplied interaction evidence, not copied proprietary code. AlphaWorkspace groups the existing nine drawing types and Long/Short into accessible native disclosures, retains original selection callbacks, and defaults replay to the bottom with opt-in drag/keyboard float. TickAlpha moves the actual action rail to the chart edge and adds a position-drawing object panel using existing onDrawingStateChange/object commands. This panel is deliberately limited to existing bridge objects: native primitive drawings retain their on-chart editing controls; it is not claimed as a unified tree. WorkspaceModal adds opt-in movable presentation only for Order/Journal/News; review/confirmation and all other modal callers remain unchanged. Six-dot terminal, exact price presentation, engine, API, data, contracts and home branding are preserved; no dependencies added.

Browser1280x720: Lines submenu selects actual Trend Line mode and closes; replay float/keyboard/dock plus pointer drag produced40px/30px offset. Order float/keyboard and mouse movement, dock, Escape/opener focus verified.375x812 panel/document widths375 with no horizontal overflow; mobile stays docked and hides unsupported floating controls. Journal loaded canonical revision0 and empty-order state without overflow; News retains explicit unavailable-data disclosure; position-tree empty state verified. Server review LONG/MARKET Ask1138.031/0.1lots/risk basis10000 preserved, confirmation cancelled without submitting an order; cash10000/cursor2015-09-01T00:30:00 unchanged. Timeframe3m and terminal arrow resize/restoration144 verified. Production5196 actual Session render and empty error/warn console verified. Ignored screenshot: frontend/tests/artifacts/riksora-ui/live-reference-refinement.jpg.

Full registered frontend regression, lint, build136modules, distribution release audit, independent Node6goldens x3 PASS. Existing AI bundle/repository gates run for the final documentation snapshot. Backend rerun exempt for presentation-only code: no backend/execution/schema/provider change and no new financial correctness claim. Initial missing JSX delimiter caught by lint/build and corrected; sandbox runner module failure did not count as PASS, normal-environment regression rerun passed. Second critique corrected keyboard movement bounds before final build. No assertion of defect-free UX, every drawing's browser acceptance, complete-trade simulation or V2.2 release readiness. Existing capacity/reference blockers, deferred HTTPS, pre-Session candle history and prior December read timeout remain open.

Final focus review: shared usePopupFocus now chooses the first visible enabled control; hidden desktop-only float controls must not receive initial focus on mobile. Focus remained inside the375px dialog during browser verification. Revalidated lint/build/release and refreshed bundle after this UI-only correction.

### Unified Objects and earlier candle context — 2026-10-12

Human authorized items4/5 only, from clean/equal2dac65b. Existing Objects now routes native primitives and Long/Short planning drawings to their original managers; storage/history domains remain separate, with no migration or engine replacement. Browser verified Trend Line create/select/resize and exact Undo/Redo, Text edit/delete, Long Position hide/lock/delete/Undo, reload/timeframe persistence, zoom/pan anchor equality and375px containment. Production independently verified Horizontal Line and Short Position edit/hide/lock and empty error/warn console. Representative checks are not exhaustive acceptance of every tool.

December Session loaded28435November M1 candles, first1446418800/last1448927940, strictly ordered and entirely before December. Session inspection before/after pagination matched exactly; cash10000, cursor2015-12-01T00:30:06 and unresolved order retained. Browser verified1m/5m prior context without advancing replay. UNKNOWN coverage and executionAuthority=false remain explicit. July is absent, so August correctly lacks preceding candles. Personal context is local-only, not an account/cloud feed.

Cold November preparation took approximately28minutes on this laptop alongside regression; warm pagination9.428seconds. Neither is a certified SLA/capacity result. Cache is process-local; restart rebuilds it. Durable derived-candle preparation remains future work. Expanded disclosure initially squeezed chart height; bounded popover fixed that. Backend349PASS/zero skips558.749seconds; frontend regression/lint/build136/distribution and independent Node6vectors x3 PASS. Ignored proof under frontend/tests/artifacts/riksora-ui. Capacity/reference gates remain open; HTTPS human-deferred. V2.2 is not complete.

## RIKSORA Drive brand token sync — 2026-10-17

The human accepted syncing Backtest Lab to the newer RIKSORA Master Blueprint brand system (Google Drive, updated 2026-10-16) and asked to finish UI/UX. That Drive document owns brand colors/typography; this section owns only the application mapping. It supersedes the 2026-10-12 token values above (#06162E/#0965FF/#F5F8FC/#FFC83D, system fonts) for home, brand, identity and workspace accent surfaces. The human chart-presentation correction (neutral dark chart/chrome #101216/#171a20) remains in force.

Tokens live in `frontend/src/tickAlpha/riksoraBrand.css`: navy #061A3C, electric blue #1378F5, white, ice #D9EAFE, yellow #FFCE55 for rare emphasis only, coral #FF7373 only for genuine risk/error. Derived shades exist only for WCAG AA: #0F67D8 for filled controls and links on white (white text 5.31:1), #0B55B8 pressed, #5A9DF8 accent text on dark (6.8:1 on #101216). Brand blue on white is 4.17:1, so it is used for large display text and non-text marks only. Typography is Inter (variable) and IBM Plex Mono, self-hosted latin woff2 from Fontsource 5.3.0 under OFL-1.1 (licenses in `frontend/public/licenses`); no remote font request. The logo is the existing `riksora-mark.png` (same byte size as the Drive "LOGO FIX - RIKSORA LABS.png"); not redrawn.

Applied: home palette and mono labels; shared brand component; workspace tokens (accent, selection #12305E, error to coral, warning to yellow, UI/data fonts); filled actions (New order, Review order, primary actions) use #0F67D8; Create strategy/Session dialog Save buttons now use the existing primary action style; identity/account pages use navy/ice with an AA link color (the previous link was low-contrast); chart toolbar label "Pilih harga order" became "Pick order price" for language consistency; at 375px the replay disclosure no longer widens the page (pre-existing scrollWidth 408, now 375). No engine, financial, drawing, chart series/data, API, schema or package dependency change. The repository reachability test now follows stylesheet `url()` assets and asserts they exist.

Evidence (cloud QA session, not the owner's laptop): eslint PASS; vite build PASS; every registered regression test PASS except `test:market`, which needs the 280MB decade catalog that was not copied into the QA environment (same result on the unchanged baseline); `audit:release` blocked by the same missing catalog. Isolated PostgreSQL 16 with `execution.local_api` synthetic fixture on 127.0.0.1:5196: create strategy, create Session, step replay, open New order by keyboard and Escape back to the opener at 1280px and 375px; computed fonts are Inter Variable and IBM Plex Mono; console warning/error empty apart from one environment proxy request also present on baseline. Before/after screenshots compared with a build of baseline b531ea2. In headless Chromium the chart canvas drew only its background for both baseline and change, so candle rendering was not verified here and must be checked in the owner's browser. Real Exness data, HTTPS and capacity gates were not touched; V2.2/Alpha readiness is unchanged.

## Testing hub and navy landing — 2026-10-17

The owner asked for a navy base on the landing page and for the first FX Replay-parity step (a Sessions overview). The FX Replay study notes live in the claude.ai Project document "fxreplay-gap-analysis-2026-10-17"; they describe flows to match, not visuals to copy.

Landing: same layout and copy, now on brand navy #061A3C with white/ice text, #5A9DF8 for eyebrows, the accent headline word and card numbers (6.2:1 on navy), muted text #A9BDDB (9.0:1), deeper navy panels #08204A/#0A2149, and the existing #0F67D8 primary button (white text 5.31:1; button against navy 3.24:1).

Testing hub (`frontend/src/tickAlpha/AlphaSessions.jsx`): replaces the "Start a backtest session" empty state whenever no Session is open. It shows a Sessions heading, New Session / New strategy / Data source actions, a four-step getting-started strip when no Session exists yet, search and strategy filters with a live count, Session cards (instrument, starting balance, start month, strategy, source, Open), and a strategy list with Session counts. It reads only the existing catalog: no per-Session view, replay or financial request, so it adds no capacity load. Cards show the starting balance, not the current balance; current balance and P&L per card need a bounded summary endpoint and are future work. The workspace header gets an "All Sessions" link (`sessionsPath()` in client.js) that returns to the hub without the session parameter. Session creation, reopening, the financial contract and the engine are unchanged.

Evidence (cloud QA, isolated PostgreSQL 16 + synthetic local_api on 127.0.0.1:5196): hub with two Sessions and with an empty database; search filters 2→1 with the live count; Open loads the chosen Session; All Sessions returns to the hub; 1280px and 375px without horizontal page overflow; console clean apart from the environment proxy request seen on baseline. eslint and build PASS; every registered frontend test PASS except test:market (missing decade catalog in QA, same as baseline). The AI bundle allowlist now includes AlphaSessions.jsx.

## FX Replay-parity trading UX — 2026-10-17

The owner asked to continue UI/UX toward the FX Replay-style workflow observed in the owner's FX Replay account (study notes in the claude.ai Project), while capacity work stays with the separate engineering track. Presentation only; the server review and confirmation remain mandatory and authoritative.

- Order bar: Sell (Bid) and Buy (Ask) buttons with live quote. They open the ticket with that side preselected; they never submit. New order remains.
- Ticket: Quick mode explains that it sends a market order without stop or target and offers "Add stop & target", which switches to Planned Market with entry at the side's quote. Planned Free Style adds TP 1R/1.5R/2R/3R buttons (target placed on the Session tick grid), risk presets 0.5/1/2/3% plus the existing Risk % field, and a live estimate: Est. loss, Est. profit, R:R, approximate lots, and stop/target distance in ticks. `orderEstimate.js` mirrors the server `risk_quantity` rule with exact decimal arithmetic (lots floored to the lot step; commission per side included). It is labelled as an estimate; the review shows the exact values. Browser checks: estimate 0.40 and 0.39 lots matched the server review exactly at 1280px and 375px.
- Replay shortcuts: Space plays/pauses and Shift+→ steps. They are ignored while typing, on focused controls, or when a dialog is open. Buttons expose aria-keyshortcuts and titles.
- Analysis tab: headline tiles (net cash change, win rate, profit factor, max cash drawdown, completed trades) and a single-series committed-balance line with a dashed start baseline, crosshair hover and low/high labels. It uses the existing committed equity projection; the posting table remains below as the accessible data view.
- Legacy `FigmaWorkspace.css` no longer imports Google Fonts at runtime (it loaded on every page); it now imports the self-hosted brand stylesheet, which also registers the "Inter" family.

Validation: eslint and build PASS; every registered frontend test PASS except test:market (decade catalog missing in the QA environment, same as baseline); new `test:order-estimate` covers long/short/commission/invalid-side/target-on-grid cases. Browser QA used headed Chromium under Xvfb against isolated PostgreSQL plus the synthetic local_api. Headless Chromium does not size Lightweight Charts canvases (300×150 backing store); headed rendering draws candles, markers, SL and fills correctly. Earlier "candles not verified" notes from this date are therefore an environment artifact.


## Local Playful preview integration - 2026-10-18

Human explicitly requested applying the handed-over Claude design and opening the local website. Preserve existing Claude landing/inline logo/font/estimate/Session/analysis patch; extend Sessions hub and header with approved navy/ice/yellow palette, rounded controls and reduced-motion support. Chart canvas/financial server contract remain unchanged. No prices, quotas, source coverage or fill results invented. This checkpoint integrates the existing local UI patch on main only; backend branch518e8c4 remains separate and has not been merged.

Validation: all registered frontend regression including market and order-estimate PASS; lint,141-module build, release audit, repository/bundle generation/verification and independent Node6vectors x3 PASS. Browser Chrome localhost5174 landing at1536px and375px shows no horizontal overflow; navigation to workspace correctly reports missing local service. No existing DB config was assumed, no user Session modified, and chart/replay/Session browser acceptance was not rerun here. Claude's earlier synthetic browser evidence remains historical. Detector flags existing Inter font as common; preserve explicit approved self-hosted Inter per brief. No full backend rerun, account/payment mount, Exness acceptance, complete P3-P6 redesign or Beta readiness claim.

Preview: http://127.0.0.1:5174/?page=home (loopback Vite process). Local backend5188 is not active/configured in this preview; workspace truthfully refuses connection. Earlier sandboxed launch failed socket access; approved loopback-only host process serves successfully. Scope is a visual preview, not completion of all UI/backend integration.


## HTTPS browser journey and chart minimum-size correction — 2026-10-19

Human requests testing login through backtest/statistics, then continuing toward a VPS candidate with data population later. Current main UI and codex/beta-backend518e8c4 remain deliberately separate; no silent merge or paid-Beta claim. A fresh isolated SCRAM PostgreSQL cluster ran13 identity/cloud-research tests, zero skips,69.664seconds PASS (wall75.983). Tests use HTTPS ASGI and authored email delivery, never application databases or real email. Unchanged full backend was not rerun.

Actual Chrome trusted HTTPS loopback journey PASS: verified generated QA account login → create own workspace → create Free Style strategy → create synthetic XAUUSD Session with10000USD → QUICK Buy0.1lot → server review/confirm → replay → fill Ask2006.05 → reviewed manual close → replay → exit Bid2005.75. Exact(2005.75−2006.05)*100*0.1=-3USD, commission0, balance9997. Analysis displays1 completed trade,0/1/0 wins/losses/BE,0%win rate, average loss/expectancy−3, profit factor0, cash drawdown3USD/0.03%, unresolved0. Missing pre-entry stop correctly excludes R instead of inventing it. Read-only server inspection independently matches browser and durable evidence. Logout/login/open saved Session and hard browser reload/relogin/open retain9997 and the same statistics; browser error log empty.375px document width375/no horizontal overflow PASS. This is existing v1 synthetic account flow, not newly mounted v2/multipair/Google/payment acceptance or market-data certification.

Browser resizing exposed chart body shrinking to34px with a311px terminal, allowing canvas to overlap replay controls. CSS now ensures desktop workspace/chart minimum300px and chart body/host180px with vertical scrolling. Confirmed desktop chart body183.4px/workspace300px, no financial/causal API change. Full registered frontend regression, lint,141-module production build and release audit PASS after correction. Bundle/Git closure remains required.

Human explicitly approved a localhost QA CA in CurrentUser Root. It expires2026-10-25T16:36:19Z, SHA1 thumbprint E418B3FB694B05A62C478C81D7B68EA722DB6961. Critical name constraints allow only localhost/127.0.0.1/::1; root signing key never persisted. Leaf certificate expires after3days. No public binding or TLS bypass. Operator may remove this exact QA root with certutil -user -delstore Root E418B3FB694B05A62C478C81D7B68EA722DB6961 when preview is no longer needed. QA artifacts/credentials/key and local database stay ignored/private, never committed. https://localhost:5443/?page=account serves current build and existing account API. Existing design preview remains http://127.0.0.1:5174/?page=home; separate synthetic local QA uses5173/5188. Native cluster remains running for the explicitly requested local preview; not a recovery/capacity/prod certificate.

Remaining launch prerequisites include controlled UI/backend branch integration, v2 product wiring and cross-version commercial quota, durable merchant orders/reconciliation/entitlements, actual Google/merchant/SMTP configuration, container/Linux/domain/HTTPS/capacity/recovery/rights/cohort acceptance. Data population later does not waive these gates. Minimal two-year causal OHLC prehistory is intended analysis context, not tick execution evidence or a claim of current dataset coverage.


### Opt-in Beta browser workspace - 2026-10-19

The human authorizes mounting the existing v2 transport and Free/Pro policy in the handed-over UI. The explicit `/?page=beta` route is separate from `/?page=account` and private HTTP source routes. The existing adapter now lives at frontend/src/beta/betaClient.js; frontend/integration/betaClient.js remains a compatibility re-export. Same-origin HTTPS, verified memory-only bearer, account/workspace generation guards, exact string values, fixed v2 endpoints, bounded responses and uncertain-write reconciliation remain authoritative. No new backend, database schema, financial reducer, settlement model or provider activation is introduced.

The screen uses the server catalogue for16 pairs, Free Style strategy/Session creation, server access counts/tier/reset timezone, activate/replay/review/hash/confirm/current-state reload, scoped chart drawings, orders/exit/cancellation, committed Analysis, journal CAS and recoverable Trash/restore. Review displays exact server quantity, entry, stops, targets and pinned planned risk/budget. Confirmed receipts are never rendered as current state; inspect separately. An uncertain write locks mutation controls until explicit evidence reload. Read-only workspace roles cannot mutate. Protocol order entry is explicitly unavailable on this first v2 screen; old Protocol UI remains separate. Chart stays at the server's1m projection, with manual replay stepping; no hidden v1 journal/bootstrap/chart-history transport is mounted.

Free includes trading, five saved v2 sandbox Sessions and one monthly-window activation per UTC day; an already activated Session remains usable. Pro is a server-issued sandbox grant, never a browser switch. No funds are collected and checkout is disabled. Authored96-timestamp demos are disclosed as short synthetic sequences, not acquired monthly data. Earlier two-year chart history is explicitly unavailable here. This checkpoint does not waive historical coverage, licensing, actual Google/merchant, Linux/VPS/capacity or paid external Beta acceptance.


### Functional Beta controls continuation - 2026-10-19

Human defers design to Claude and authorizes functionality that can be completed locally before VPS provisioning. Extend the opt-in v2 screen with Protocol creation/checklist review, planned orders, full/partial CLOSE review, playback pause/backpressure and1/4/16 interval stepping, and all existing chart timeframes. Reuse existing immutable MethodPolicy, v2 review/hash/receipt and controller execution semantics. Never calculate settlement, planned quantity or Protocol targets in the browser. Unassessed conditions remain unassessed; server policy alone accepts/rejects. Pausing prevents subsequent requests, while a command already admitted may finish. Replay stops after a refusal, no newly revealed group, Session end, or unmount; no future quote/EOF capability is added.

Add POST `/api/v1/workspaces/{workspace_id}/research-v2/sessions/{session_id}/view` with exactly `{timeframe}` for the existing nine display resolutions. It dispatches scoped read-only inspect, never a financial command, and cannot change revision, cash, cursor, Method or quota. Unknown fields/timeframes refuse; the existing query/source-override boundary, verified membership and bounded admission remain. The old GET view keeps1m compatibility. This exposes the existing causal display projection; no new aggregation, provider, index, stored candle or execution contract.

Google's existing server callback `/?auth=google` now enters Beta identity UI. One deferred, cancellation-guarded mount consumes the HttpOnly handoff through the existing same-origin exchange, removes the callback flag and keeps the resulting bearer only in the existing client closure. Provider availability controls the Google link; absent operator configuration remains explicitly unavailable. No actual owned Google consent/provider acceptance, merchant/data activation or external launch is supplied.

Claude owns later visual redesign. Keep working functions/server authority, opaque identity and state persistence when reskinning this screen; a static mock is not a replacement. Existing v1/local routes remain separate. Payments, two-year licensed historical OHLC and host-specific deployment/capacity acceptance remain independent dependent workstreams, not completed by these controls.


### Local payment UI and deployment configuration - 2026-10-20

Human requests locally possible work, with historical data deferred and visual redesign left to Claude. Mount BetaBilling on verified Beta account/workspace chooser only when the server advertises billingConfigured. Existing memory-only identity client gains fixed account-scoped plan/orders/access/checkout/resume/reconcile calls. Server tier is displayed without interpreting return URLs, browser clocks or payment status as entitlement. No bearer, provider key or payment return state is persisted in browser storage. Saved order lookup supports hard reload/sign-in recovery. Listing is bounded to50 deterministic order IDs (not represented as chronological history), discloses truncation and blocks new UI checkout if truncated. An open/uncertain payment blocks new UI checkout until explicit saved-state reconciliation. CREATED alone supports resuming its one-shot admission. Submitted checkout is never retried by a UI timer. Hosted URLs are HTTPS sandbox-only, credential/query/fragment-free and validated before rendering a separate-tab link; no card inputs or embedded payment SDK are added.

Add exact authenticated billing orders/access and CREATED resume endpoints to the existing prefix; JSON body overrides still refuse. Existing SQL ledger/migrations and financial/tick/causal contracts remain unchanged. All-or-none six-key server configuration (worker DSN, sandbox key, merchant, plan version, whole-IDR amount, duration) has no guessed price/duration/key. It requires UTC and refuses production keys. The explicit deployment operator optionally grants a separate restricted btl_billing worker and billing SELECT to btl_app; app/owner/worker membership mixing refuses. Private runtime JSON remains the only deployment secret input. Environment with no billing config remains disabled. Google/SMTP settings reuse their existing owners and remain operator supplied; no owned accounts or actual provider consent/delivery is fabricated.

Acceptance distinguishes authored provider responses -> actual HTTPS browser/API/PostgreSQL from actual Midtrans hosted-card/provider acceptance, which is absent without merchant credentials. No production charge, data download, VPS provisioning, automatic host backup scheduler, visual redesign or sale-ready claim. Existing recovery commands and operator runbook remain the host deployment path. Local UI must preserve uncertain-write lockout, persisted payment recovery, server expiry/refund access and account isolation when Claude reskins it.


## Claude presentation integration into Google staging (2026-10-23)

Owner authorized executing the preceding audit plan. Reviewed donor local branch `claude/ui-p1-sessions-hub-account-nav` at b2018d607d0ae443b5d1062f4a468a57216c1894 and its handoff/workflow. Source remains preserved. BetaWorkspace, BetaNewSession and beta.css were unchanged from donor base11f399f in the integration branch, permitting bounded presentation import without overwriting concurrent changes. Imported Sessions cards, Quick review strip, grouped positions, server-derived Statistics/balance line, Journal tag/filter UI, mobile order sheet and system states. Integration additionally disables writes during browser offline state.

The separate Google staging entry reuses the existing brand mark and navy component styles, adds workspace cards and account sign-out/all-device sign-out through existing canonical endpoints, and removes the workspace picker from the active practice view. Password/billing/support/admin routes stay closed; no backend/financial contract or source eligibility change. Draft prices/private operations theme are not activated. Landing remains untouched.

This is a partial implementation of the private canvas: exact exported canvas comparison and real desktop/phone UI acceptance remain separate gates. Chart tool rails/floating replay, R:R planning geometry, landing canvas alignment and backend-dependent cross-session aggregates are outstanding. No five-year data, complete visual fidelity or production readiness claim.


### Repository account composition restored for Google staging (2026-10-23)

Owner explicitly requests using the existing repository application rather than a separate workspace-only implementation. Imported remaining Claude presentation files BetaAccount/BetaBilling/BetaSupport from preserved b2018d6 after confirming unchanged11f399f originals. Staging entry now mounts the same maintained BetaAccount with explicit googleOnly and /login/ callback cleanup; no duplicate account/workspace JSX owner. Reuses existing avatar menu, Account & plan, workspaces, Sessions/Journal/Statistics components. Google-only composition does not mount email/password auth, payment checkout or support submission. Generic app defaults remain available for separately configured environments. Added uncertain workspace-create lock requiring explicit list reconciliation. Synthetic disclosure remains.

Static-only pinned installer is independent of API/data migrations: validates source/hash/allowlisted ZIP, preserves landing and old assets, takes private pointer rollback record, atomically switches static symlink, verifies public login bytes and restores pointer on check failure. No service restart/config/database operation. Browser/canvas acceptance remains unverified; no route/data eligibility waiver. HistData local sample audit found XAUUSD timestamp regressions and ties; source is not execution accepted. The frozen v2 real-source refusal remains intact.


### Public repository feature access (2026-10-23)

Owner explicitly requests public access to product previews and repository-to-host parity, with final blockers reported honestly. Existing AlphaHome now accepts explicit hostedPreview presentation so its repository landing links to Google staging and public feature directory without promising real-data history. Generic local default is preserved. Public feature directory and authored memory-only trading/R:R playground are accessible without identity through explicit /login/?view=features and view=prototype; Google callback always wins over preview selection. Local Tick Review/history API, old local runtime and private Odoo/CRM/finance surfaces stay isolated. Public preview is not permission to expose private source files, database or privileged operations.

Signed-in Sessions/Strategies/Journal/Statistics navigation is active. Strategies lists canonical definitions and reuses existing New Session creation. Journal/Statistics choose a saved Session; no cross-session aggregates invented. Navigation stops the replay loop. Added the existing IndicatorControls/IndicatorPreferences lifecycle to hosted chart, scoped by identity/workspace/Session, maximum16 validated instances, original bad/foreign-tab preferences preserved. Existing DrawingSpecs supplies every registered canonical drawing mode, rather than the previous six-entry subset. Indicators consume only the existing revealed chart bars; missing historical context stays warmup.

Static-only installer requires separate --replace-home to replace landing, validates every referenced HTML asset and actual public artifact bytes, and rolls back pointer on verification failure. No API/database changes. This delivers access to implemented hosted features and labelled previews, not 1:1 acceptance of local/private runtimes, unseen canvas or frozen real-source contracts.


### Correction: follow repository workflow instead of invented entry points (2026-10-23)

Owner rejects invented workflow and explicitly requires the repo workflow. Restored the existing Claude `docs/design/RIKSORA_WORKFLOW.md` verbatim from preserved b2018d6 donor as the same-path repository workflow copy; its LIVE/PATCH/PLAN legend is historically against11f399f, not a new production-status claim. Architecture and Method/Session authority retain precedence.

Remove Codex-created public feature-directory page and cross-session shortcut/library presentation from40b8945. Header follows Claude: Sessions navigation plus explicitly unavailable cross-Session Strategies/Journal/Statistics, while actual Journal/Statistics remain working tabs inside an opened Session. Keep existing canonical indicators/drawings (presentation capabilities, not workflow replacement). Avatar Account/Support retain selected workspace context; returning Sessions uses that workspace, and the workspace picker alone omits main nav. Public design prototype retains repository's explicit trading-ux=prototype opt-in and never becomes a mandatory step in saved research.

Canonical supported journey: Landing → sign-in → Workspaces → Sessions hub → New Session(pair,balance,strategy created inline if needed; no start date) → Session workspace locked → Activate replay window → Play/Step → Quick or Planned order → review → Confirm → eligible tick → Journal/Statistics tabs at any time → Sessions hub. Original email registration/verification, onboarding and incomplete Plan R:R remain honestly unavailable/PLAN under Google-only staging. No new financial/API or eligibility contract. Prior40b8945 operator helper is superseded so it cannot silently deploy the rejected workflow.

## Beta chart price-format compatibility — 2026-10-24

Actual desktop/mobile QA found that the shared candle renderer's fixed three-decimal format collapsed EURUSD axis labels to `1.100` while the server preserved five-decimal quotes. Beta now supplies the committed Session profile's `priceScale` and `tickSize` to the existing [Lightweight Charts priceFormat API](https://tradingview.github.io/lightweight-charts/docs/api/interfaces/PriceFormatBuiltIn). All16 authored profile vectors cover FX five decimals, JPY three and synthetic XAU two; unsupported formatting is refused rather than inferred from a symbol/quote. Other chart callers retain the existing default. This is display geometry/labeling only: canonical strings, tick ordering, reviews, receipts, fills, ledger and financial contracts are unchanged.

The isolated HTTPS Chromium journey checks actual five-decimal canvas labels, pending-before-tick confirmation, next-tick fill/exit and exact10000.03USD balance, Statistics, journal/timeframe, desktop1440/mobile375 no document overflow, cold reload/relogin and server logout revocation. Authored synthetic data and a QA certificate with browser verification bypass were used; no real Google/provider, production rollout, exact private-Claude-canvas parity or historical coverage is certified.

## Beta workspace toolbar, rail and keyboard alignment — 2026-10-24

Bounded implementation of the existing repository Claude workflow/Playful plan: symbol/timeframe and Fit/settings toolbar; existing nine drawing tools on a desktop left toolbar and narrow horizontal strip; Order/Objects/Settings/Journal/Statistics rail with honest disabled News; Session-scoped object selection/hide/lock/delete through existing CandleChart commands. Reused WorkspaceIcon, DrawingManager, CandleChart and indicator persistence. No chart/order engine was replaced. Settings change grid/crosshair only. Escape returns focus to the panel opener. The mobile order sheet now receives focus, cycles Tab/Shift+Tab, closes with Escape and returns to its actual opener. Space toggles replay and Shift+ArrowRight steps only outside inputs/controls/dialogs, using the existing guarded replay loop.

Actual versioned browser gate:12 stages PASS23.524s, including drawing/Objects/settings with zero financial requests; exact pending→next-tick entry/exit and10000.03 cash; Statistics/journal; five-decimal chart;1440/375 without document overflow; mobile focus trap/Escape; typing Space does not play; keyboard play/pause prevents subsequent scheduled commands; Shift+ArrowRight uses server replay; cold reload/note recovery and logout revocation. Initial single-candle drawing test could not resolve an off-bar time; it now waits for a second genuinely revealed candle, without inventing future data. No private-canvas pixel parity, planned R:R order wiring, cross-Session screens, historical-data admission or paid-release completion is claimed.


### Supported Beta Plan/R:R workflow — isolated evidence (2026-10-25)

Existing Claude workflow now connects Free Style Long/Short planning geometry to a draft ticket using current chart/controller and exact-decimal planning helpers. Draft copy never submits orders. Risk presets0.5/1/2/3 and RR1/1.25/1.5/2/3/manual feed existing server review; server-sized risk sends quantity null. Exact Bid/Ask comparison proposes MARKET/LIMIT/STOP; explicit review/confirm and next eligible tick stay mandatory. Protocol keeps server-owned risk/quantity/target, checklist and LIMIT/STOP. Drawings show geometry only; non-USD conversion and manual-lot exact risk defer to server rather than guessed values. Desktop ticket scroll/mobile focus remain scoped to presentation.

Versioned13-stage real Chromium QA verifies drawing→draft without financial writes, risk2% planned server review2lots/TP1.102 and Back without mutation, alongside prior exact pending/next-tick/cash10000.03, journal/statistics, desktop/mobile/focus/keyboard/reload/logout. Full frontend gates and independent vectors pass; no private-canvas pixel parity, historical-source admission, full capacity or paid-release certification. Existing written workflow remains the design reference, not rewritten to manufacture completion.


### Account recovery browser evidence and truthful data copy (2026-10-25)

Existing BetaAuth recovery UI now has versioned actual-browser coverage: invalid reset message, one-use valid reset, separately authenticated old bearer revocation, old password refusal, new login and saved Session/journal preservation. Existing14-stage gate retains trading/drawing/mobile/focus/keyboard assertions; local QA delivery only, no real SMTP/Google acceptance. Signed-out hero no longer promises16 instruments or historical data before catalog/source acceptance; Claude layout remains intact. Full private-canvas parity and historical/paid readiness stay unproven.

### Claude customer navigation, brand mark and wording corrections (2026-10-25)

Owner assigned Claude ownership of customer UI/UX, product workflow and the Odoo Community management UI. Separate branch `claude/customer-ui-odoo-20261025` from `f51b9cd`; main, Codex branches/worktrees and the handoff mailbox are untouched. Reference: `docs/design/RIKSORA_WORKFLOW.md` (owner decisions 2026-10-23) and `RIKSORA_PLAYFUL_UI_PLAN.md`; the private canvas was not available, so no pixel-parity claim.

Presentation only: Account and Support had no way back when no workspace was open (main nav Sessions disabled, avatar menu without a return item). Both now show Back to workspaces / Back to Sessions, and the header Sessions item is always enabled and returns to the picker or the open workspace. The favicon was the Vite default and the staging pages had no icon link; `public/favicon.svg` is now product mark C (geometry identical to `docs/design/logo/C-ribbon-R_app-icon.svg`) and both staging pages link it. Hosted landing step 3 says Statistics (Words rule); the local Alpha keeps its Analysis wording. New Session step 2 reads Balance (no start date). Header/back/public/footer links meet the 44px touch-target guardrail; the stray separator after Home is removed. No financial, review/confirm, data, API, payment, deployment or Odoo addon change.

Evidence: lint, full registered frontend regression, main build 150 modules, staging build 107 modules, release audit, AI bundle generate/verify, deploy package tests and Google staging tests on a private PostgreSQL cluster PASS. Existing versioned 14-stage synthetic browser gate PASS on the changed tree. A separate scratchpad Chromium journey (same isolated server setup) PASS: picker without main nav, Account→Back to workspaces by keyboard, Support→Sessions, Account→Back to Sessions with an open workspace, 375px Account without horizontal overflow, 44px controls, no page errors. Synthetic QA only; not production, historical-data or paid-Beta acceptance.

Still open against the design: Sessions hub cards (balance/P&L/progress/Continue replay) and Account usage/security/preferences need backend summary/storage; Free/Pro cards and Plans need billing plan options; header plan badge appears only after a workspace loads its access; "Activate trading window" wording kept because versioned QA uses that accessible name; Sell uses a coral-derived colour although coral is reserved for risk (owner decision); wordmark "riks▶ra" and the Hidden Candle Ops Odoo theme lack an available visual reference. Odoo addon changes were not made: no Odoo runtime is available on this host for the required isolated install/upgrade gate.

### Landing plans, Account sections and sign-in Google state (2026-10-25)

Owner asked to match the written Claude workflow and UI/UX, including sign-in. Presentation only, same branch.

- 03 Landing shows the same Free/Pro cards as 17 Plans (`frontend/src/beta/BetaPlans.jsx`, shared with Account): Free Rp0, 5 saved Sessions, 1 replay window a day reset 00:00 UTC; Pro Rp139.000/month or Rp1.668.000/year. Pro is labelled "Draft price · not on sale" with the open term/renewal/refund/tax note; no checkout or buy control. Only the hosted landing shows plans; the local Alpha has no accounts.
- 07 Account follows profile, usage, plan summary, security, preferences. Without sandbox checkout, usage meters show the last server access seen in this sign-in (otherwise "open a workspace"), never estimated. Security has Sign out and Sign out on all devices (existing API); password change and Bahasa Indonesia are disabled "soon" (no route/setting yet). With checkout configured the existing BetaBilling usage/offer/history stays.
- 04 Sign in shows a disabled "Continue with Google" button with the existing explanation when Google is not configured, per the playful plan.

Evidence: lint, full registered regression, main 152 / staging 109 modules, release audit, repository, AI bundle, deploy package and Google staging (private PostgreSQL) PASS; versioned 14-stage browser gate PASS. Scratchpad Chromium journey 8/8 PASS adds Account sections/meters/"Your plan", disabled Google button, and landing Plans at 1440 and 375 without overflow. Remaining gaps listed in the previous section are unchanged.

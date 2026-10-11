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

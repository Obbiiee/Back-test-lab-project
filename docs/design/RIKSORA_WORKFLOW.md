# RIKSORA Backtest Lab — workflow (one source of truth)

Repository copy of canvas artboard **00w · Workflow** in the private design canvas "RIKSORA Backtest Lab — Design" (owner's claude.ai account). Owner decisions of 2026-10-23 are recorded here. Statuses were corrected the same day after Codex's audit of the PDF exports.

When this file and the canvas differ, change the canvas first, then this file. Screen numbers refer to canvas artboards. The screen map with code status is artboard **00 · Design map & status**.

This file describes user-facing flow and presentation only. Architecture, financial and causal contracts stay in `docs/PRODUCT_SYSTEM_ARCHITECTURE_BLUEPRINT.md` and the frozen contracts, which win over anything here.

## One screen per job (owner decision 2026-10-23)

| Job | The one screen | Merged into it |
|---|---|---|
| Screen map and status | 00 | 00b inventory |
| Page-to-page flow | 00w (and this file) | — |
| Account: profile, usage, plan summary, security, preferences | 07 Account | 22 Settings |
| Prices and checkout | 17 Plans (03 Landing shows the same Free/Pro cards) | plan tables on 07 |
| Order flow, Quick and Plan | 13 Order flow | 11 Execution, 12 R:R tool |
| Limit states (Sessions full, window used) | 24 System & limit states | window-used card on 09 |
| Contact and problem reports | 30 Support center | feedback form on 29 |
| Evidence and legal | 29 Evidence & legal | — |

## Owner decisions (2026-10-23)

- **Logo:** C (Ribbon R) is the product mark for the app header, favicon and emails. The social avatar is still open (28).
- **Plans:** only Free and Pro.
  - Free is Rp0: 5 saved Sessions and 1 replay window a day, reset 00:00 UTC.
  - Pro is **Rp139.000 / month** or **Rp1.668.000 / year** (139.000 × 12).
  - Term, renewal, refund, tax and promo are still to decide.
  - Checkout amounts always come from the server. Today checkout is the sandbox only.
- **Orders have two modes**, the same on desktop (10) and phone (20):
  - **Quick:** Sell / Buy under the chart (phone: on the chart screen) with a lots box. Market order, no stop or target.
  - **Plan:** the Plan tab or the Long / Short tool draws an R:R box on the chart.
    - R:R presets are **1:1, 1:1.25, 1:1.5, 1:2, 1:3**, or **Manual**. Risk 0.5 / 1 / 2 / 3 % sizes the lots.
    - Drag entry, stop and target, then Place order.
    - The order becomes Market, Limit or Stop according to the entry price.
  - **Protocol strategy:** a Plan order with locks. Risk, R:R and order type come from the strategy, lots from the server. Every checklist condition must be assessed, and manual exits are locked. Quick is not available for Protocol.
- **Header:** one header on every signed-in page. Brand C, nav Sessions / Strategies / Journal / Statistics, plan badge, and an avatar menu with Account, Support, Sign out and Sign out on all devices. The workspace picker (06) shows no main nav.
- **Private screens use a full ninja theme, "Hidden Candle Ops"** (隠れ蝋燭の里). The owner asked for Naruto, more strongly, on 2026-10-23.
  - Applies to Odoo 31–38, Local Tick Review 39 and internal tools 40. The theme reference is P0.
  - Palette: orange jumpsuit #F57C00 with black text, night navy #1B2A49, headband steel, scroll paper, chakra blue, seal red.
  - Every header carries a forehead-protector steel plate with rivets and the village emblem. The emblem is original: a trading candle with a swirling flame.
  - Kanji under menu labels; shinobi ranks for roles (Kage = owner, Jōnin = Finance, Chūnin = CRM, Genin = Importer). Support tickets get mission ranks D/C/B/A/S by age, as decoration only. A red 封 seal marks immutable records.
  - Official characters and the Konoha symbol are not reproduced; original equivalents are used instead.
  - Real Odoo labels, states and amounts stay unchanged next to the flavour, and status colours keep their meaning.
  - Odoo build: one SCSS asset in btl_business (`web.assets_backend`), no core edits. Customer screens keep the RIKSORA navy look.
- **Words:** "replay window" (never "research window"), "Statistics" (never "Stats" or "Analysis" in navigation), "16 demo pairs", and "balance line" (never "equity curve" while unrealized value is excluded). New Session has no start date.

## Status legend (against the website candidate codex/beta-backend 11f399f)

Every step carries one of these:
- **LIVE**: runs in 11f399f.
- **PARTIAL**: runs, but not as drawn.
- **PATCH**: only in Claude patches 0001–0006 (0001–0011 on branch `claude/ui-p1-sessions-hub-account-nav`, not merged).
- **PLAN**: design only.

Rows A–H are journeys. Rows I–J are hubs: destinations by role, with no required order.

## Journeys

**A · First visit to first Session**
1. 03 Landing [PARTIAL: the earlier landing design is live].
2. 04 Create account [LIVE].
3. 05 Check inbox → verify [PARTIAL: verification by code works; email link delivery is not validated].
4. 04 Sign in [LIVE].
5. 23 Onboarding [PLAN].
6. 06 Workspaces [LIVE].
7. 08 Sessions hub [LIVE: an empty hub shows the New Session form].

**B · Start a Session** (order as the code runs)
1. 08 Sessions hub [PARTIAL: plain list; cards are PATCH].
2. 09 New Session: pair, balance, strategy; 16 strategy inline [LIVE].
3. Create Session [LIVE].
4. 10 Workspace opens with trading locked [LIVE].
5. Activate window [LIVE]. On Free with today's window unused, a dialog offers "Start window & play" or "Just look around".
6. Play / Step replay [LIVE].

**C · Trade, Quick (market)**
1. 10 Market order [PARTIAL: panel Market is LIVE; the Sell/Buy strip is PATCH].
2. 13 Review [LIVE].
3. **Confirm** [LIVE].
4. Accepted, waiting for the next eligible tick [LIVE].
5. Filled: a buy fills at Ask, a sell at Bid [LIVE].
6. 18 Manual close or partial close: review → Confirm → next tick [LIVE].

**D · Trade, Plan (Limit / Stop)** (Protocol adds locks)
1. 10 Planned order: type entry, SL and TP in the panel [LIVE].
2. 13 R:R box on chart with presets 1:1, 1:1.25, 1:1.5, 1:2, 1:3, Manual [PLAN].
3. Review → Confirm [LIVE]. Protocol: lots from the server and a checklist.
4. Pending until a tick reaches entry [LIVE].
5. Filled [LIVE].
6. 18 SL / TP trigger automatically [LIVE].

**E · Results** (any time, tabs inside the Session)
1. 15 Statistics [PARTIAL: Analysis tab; KPI tiles, balance line and closed-trade table are PATCH 0008].
2. 14 Journal [PARTIAL: notes per order; filters, editor and tag editing are PATCH 0008; rating is PLAN].
3. 18 Session ended [PARTIAL].
4. Back to 08 [PARTIAL].

**F · Limits and upgrade** (sandbox)
1. 24 Limit reached [PARTIAL: text notice live; cards with a way back are PATCH 0010].
2. 17 Plans [PARTIAL: one sandbox plan in the API; monthly / annual Pro are owner draft prices, PLAN].
3. Midtrans sandbox checkout [LIVE].
4. Check payment status [LIVE].
5. Pro granted only after the server confirms [LIVE].

**G · Help**
1. Support form below the workspace picker [LIVE].
2. 30 Support center page from the avatar menu [PATCH].
3. Send request, saved and listed [LIVE].
4. 33 Odoo staff ticket on the next sync [PARTIAL].

**H · Account**
1. Avatar menu on every page [PATCH].
2. 07 Account & plan [PATCH].
3. Security and preferences [PLAN].
4. Sign out [LIVE: this device; sign out on all devices is PATCH].

**I · Operator hub** (Odoo, staff only, any order)
- 31 Overview [PLAN: dashboard].
- 32 Customers, 38 CRM pipeline, 33 Support, 34 Sandbox payments, 35 Payout, 36 Cashbook, 37 Costs & import [PARTIAL].
- One menu: Overview 本部 · Customers 顧客 · CRM pipeline 縁 · Sandbox payments 試験 · Support 任務 · Finance ▾ 金庫 · Import 巻物.

**J · Owner tools hub** (private, any order)
- 40 Internal tools index page [PLAN].
- 39 Local Tick Review [LIVE].
- Daily checks (`OPERATIONS.md`) [LIVE].
- Backup and recovery (`recovery.py`) [LIVE].
- P0 ninja theme [PLAN].

## Execution rules

- **New orders and manual exits** (close, partial close, cancel pending): server review → Confirm → happen on the next eligible tick.
- **Stop loss and take profit** trigger automatically on an eligible tick, and a buy exits at Bid. There is no new review or Confirm when they trigger.
- Accepted is not filled. Candles never settle a trade. Missing ticks stay unresolved and are never guessed.
- An uncertain response means: reload saved evidence before sending anything again, with no blind retry.
- Plan, quota, price and access come from the server.
- Odoo is staff-only. An Odoo outage never blocks sign-in, billing or replay.

## Retired screen numbers

| Retired | Merged into |
|---|---|
| 00b | 00 |
| 11 Execution, 12 R:R tool | 13 |
| 22 Settings | 07 |
| Feedback form on 29 | 30 |
| Window-used card on 09 | 24 |

## Known gaps behind these journeys (backend, for Codex)

1. Sessions hub cards and "Continue replay" need a per-Session summary: balance, P&L, progress, ended, last opened, trashedAt.
2. The Plan mode R:R box on the chart, the R:R presets and risk-% sizing for Free Style are design only in code today.
3. Monthly and annual Pro offers need plan options in the billing API. Today there is one sandbox plan.
4. Account display name, in-app password change and preferences need storage and routes.
5. Support topic, staff status and replies are not stored or synced to the app.
6. Strategy list/edit, workspace invites, onboarding progress and jump-to-date have no API yet.
7. Private side:
   - No btl.customer ↔ crm.lead link and no plan field on CRM cards (38 shows them as proposed).
   - The Hidden Candle Ops SCSS asset is not in the addon yet.
   - The internal tools index page (40) does not exist; tools open by URL.
   - Local Tick Review copy is Indonesian in code, while the design is English.

# RIKSORA Backtest Lab — Playful UI plan

Owner-approved design direction, 2026-10-18. Design owner: Claude (UI/UX). Engineering owner: Codex (engine, API, backend).
Source mockups: private Claude Design canvas "RIKSORA — Akun & Navigasi" (11 artboards, owner access). This file is the repository copy of the plan. Brand assets live in `docs/design/logo/`.

## 1. Owner decisions

- **Flow and button placement match FX Replay**, with RIKSORA's own visual design, code and copy. No copied FX Replay branding, assets or pixel layouts.
- **Visual tone: playful, not rigid.** Rounded shapes, pill buttons, chunky "pressable" buttons, bold colour blocks, friendly copy, small celebrations.
- **Chart stays neutral dark** (owner correction, 2026-10-17). Playfulness lives in the chrome around the chart, not on it.
- **Landing page: navy base, playful, not stiff.**
- **Logo:** the owner likes all three playful marks (A Play R, B Candle R, C Ribbon R). Social media uses the boxless marks. Product default proposed: C for the app header and favicon, A for social avatars. Final pick still open.
- **Work order:** implement locally on the laptop working tree first; publish to the GitHub repository afterwards.

## 2. Brand tokens (unchanged canonical colours)

| Token | Value | Use |
|---|---|---|
| Navy | `#061A3C` | Base background, text on light |
| Electric blue | `#1378F5` | Accent, fills with dark text or large white text |
| Blue strong | `#0F67D8` | Filled buttons and bands with white body text (AA 5.3:1) |
| White / Ice | `#FFFFFF` / `#D9EAFE` / `#F3F8FF` | Text on dark, light cards |
| Yellow | `#FFCE55` | Highlights, celebration, "selected" chips, stickers |
| Coral | `#FF7373` | Risk, loss, stop loss only |
| Fonts | Inter (UI, 800–900 for headlines), IBM Plex Mono (numbers, prices) | self-hosted, OFL |

Playful additions (no new hues): radius scale 12 / 20 / 28 / 36 / pill; "press" shadow `0 5px 0 <darker shade>`; slight rotations (±1–4°) on stickers and hero cards only; decorative circles/rounded squares in brand colours. No gradient washes, no emoji.

Accessibility guardrails: white body text never on `#1378F5` (use `#0F67D8`); 44px touch targets; real buttons/links; profit/loss always carries a sign and label, not colour only; reduced-motion users get no confetti/bounce.

## 3. Screens

| # | Screen | Key elements | Backend dependency |
|---|---|---|---|
| 1 | Landing (public) | Hero "Practice trading on yesterday's market", tilted product preview with fill and "Target hit" stickers; 3-step "How it works"; colour-block feature cards; plans teaser; CTA band | None (plans need prices from owner) |
| 2 | Sign in | Google button (disabled until client ID), email/password, honest error state | Google/password auth (codex/beta-backend) |
| 3 | App header | Pill nav Sessions / Strategies / Journal / Statistics, quota chip "4 / 5 Sessions", FREE badge, avatar menu (Account, Trash, Upgrade, Sign out) | Account + quota API |
| 4 | Sessions hub | Welcome band with Continue replay; Session cards: instrument avatar, balance, P&L pill, sparkline, replay progress bar, action; "+ New Session" dashed card with slots left | Session summary API |
| 5 | Account & plan | Profile, sign-out, Sessions and daily-window meters, Free vs Pro cards, Midtrans hand-off note | Entitlement + payment (sandbox) |
| 6 | Trading workspace | FX Replay-equivalent placement (section 4) | Existing Alpha engine; v2 API later |
| 7 | Trade moments | Review popover, "filling on next tick", "You're in!" fill toast, "Target hit +2.00R" celebration card, calm stop-loss card with journal prompt, illustrated empty states | Receipt/fill/exit events |

## 4. Workspace layout (FX Replay-equivalent placement)

- **Top bar:** back to Sessions, symbol search, compare (+, soon), interval, chart type, Indicators, Analytics, Session name (centre), chart settings, fullscreen.
- **Left toolbar:** crosshair, trend line, Fibonacci, pattern (soon), long/short position, brush, text, measure, zoom, magnet, keep drawing, lock, hide all, remove all.
- **Right icon rail:** Order, Object tree, Watchlist (soon), Journal, News (soon), Settings.
- **Order panel:** Sell/Buy toggle with Bid/Ask; risk basis Initial/Current; risk 0.5 / 1 / 2 / 3 % / Custom; live estimate (loss, profit, R:R); Market / Limit / Stop; units; entry; SL and TP each by Price / Pips / $; Add partial (soon); Auto breakeven (Pro, soon); tags; "Open journal after placing"; **Place order**.
- **Chart:** draft order chip (side, lots, Draft · Market), SL chip in $ risk, TP chip in $ target, "+ TP"; floating replay bar (speed, previous candle (soon), play, next candle, step timeframe, go to, replay time).
- **Below chart:** ranges 1D…All, go to date, UTC, % / log / auto; one-click Sell · lots · Buy; balance chip with open P&L; hide balances.
- **Terminal:** Open positions / Pending orders / Closed positions (asset, side, size, entry, TP, SL, unrealized, realized, action).
- Controls without backend support render disabled with a "soon" label; never faked.

## 5. Execution flows

**Quick (execute now):** one-click Buy/Sell (or Market in the panel) → review popover (server returns exact lots and money) → Confirm → "accepted, filling on the next tick" → fill toast at Ask (buy) / Bid (sell) → position line with live P&L.

**Planned (R:R tool):** pick Long/Short position tool → click chart → drag entry/SL/TP handles; lots from risk %, R:R and $ live → tool shows the order it will become (Market at price; Limit or Stop by side of current price) → Place order → review → Confirm → Limit/Stop wait in Pending until a tick reaches entry. An unplaced tool stays a drawing.

**Exits:** SL/TP trigger on real ticks (a buy closes on Bid); manual close also goes through review; missing ticks produce "unresolved", never a guess.

Rules that stay mandatory: server review → confirm, exact decimal strings, no chart-drag settlement, no local MODIFY until the backend contract exists.

Open questions to Codex are in `docs/AI_HANDOFF.md` (workspace execution UX entry, 2026-10-18). Open owner decisions: skip-review option for one-click, Pro price/period, final logo pick.

## 6. Logo assets (`docs/design/logo/`)

- `A-play-R_*`, `B-candle-R_*`, `C-ribbon-R_*` — boxless marks, `for-dark` and `for-light`, SVG + transparent 1024px PNG (social media).
- `*_app-icon.svg` — boxed rounded-square versions for app icon / favicon.
- Wordmark: lowercase heavy "riks▶ra" with a Play-button "o" plus "BACKTEST LAB"; built in code, not an image.
- The previous `frontend/src/assets/riksora-mark.png` stays in the repository until the owner confirms the final mark.

## 7. Implementation plan (local first, then repository)

| Checkpoint | Scope | Files (Claude-owned, frontend) |
|---|---|---|
| P1 | Playful landing + SVG brand mark | `tickAlpha/AlphaHome.jsx`, `alphaHome.css`, `AlphaBrand.jsx`, `alphaBrand.css` |
| P2 | Playful Sessions hub + header chrome | `AlphaSessions.jsx`, `tickAlpha.css` |
| P3 | Order panel restyle (FX Replay placement) + trade-moment toasts | `TickAlpha.jsx`, `AlphaTicketEstimate.jsx`, `tickAlpha.css` |
| P4 | Workspace chrome: top bar, right rail, replay bar, bottom strip | workspace components, `tickAlpha.css` |
| P5 | R:R tool → Place order | after Codex answers the execution contract questions |
| P6 | Sign in, account, plans, checkout status | after betaClient mount by Codex |

Each checkpoint: build, frontend regression, desktop 1440px + mobile 375px browser check, keyboard check, then a handoff note. Shared files (`package.json`, lockfile, bundle config, notices) are touched only after coordination with Codex.

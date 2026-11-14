# Local Trader (prototype)

Manual trading on real local ticks, driven by the Claude engine (verified compact source + the reference reducer). QA/prototype:
single user, no PostgreSQL, observed quotes only (no slippage, no commission). XAUUSD and USD-quote FX only.

```
cd backend
# XAUUSD (Dukascopy monthly zip)
python tools/claude_exp/local_trader/server.py --zip <DUKASCOPY_XAUUSD_Txxxxxx.zip> --ticks 400000 --offset 0
# FX (HistData-UTC monthly zip): EURUSD | GBPUSD | AUDUSD | NZDUSD
python tools/claude_exp/local_trader/server.py --zip <HISTDATA_UTC_EURUSD_T202605.zip> --pair EURUSD --ticks 300000
```
Open http://127.0.0.1:8765. Needs numpy + pyarrow (the anaconda Python here has both). The first start converts the ticks once (cached in the temp folder).
Sessions are saved after every action. A restart resumes the latest session after verifying its hash chain and financial state;
`--fresh` starts a new one; the "Sesi" menu lists and opens saved sessions or creates a new one (balance + method).

## Method and order modes (docs/TRADING_METHOD_SESSION_SPEC.md, docs/design/RIKSORA_WORKFLOW.md)

A session inherits one immutable Method (its hash is part of the session identity).

| | Free Style | Protocol |
|---|---|---|
| Quick (market, no SL/TP, lots box) | yes | no |
| Plan (Entry/SL/TP, order becomes Market / Limit / Stop from the entry price) | yes | pending Limit/Stop only |
| R:R presets 1:1, 1:1.25, 1:1.5, 1:2, 1:3, Manual; risk 0.5/1/2/3 % or lots | free | locked R:R and risk, TP and lots derived |
| Checklist | none | min. 1 condition, ON = every condition must be PASS, OFF = recorded, not blocking |
| Manual / partial close, amend SL/TP | yes | refused (exit only by the planned SL/TP) |
| Cancel a pending order | yes | yes |

Every order goes through Review -> Confirm (the review is bound to the current price: if the price moved, the confirm is
refused as stale; confirming the same review twice returns the first result). Refusals are stored as evidence in the "Penolakan"
panel, they are not trades. The rules are NOT re-implemented in the UI or this server: `domain.py` builds the draft and dry-runs it
through `execution.contracts.open_payload` / `risk_quantity`, and the kernel re-checks everything when the order is applied
(`validate_action` for closes), so a request that bypasses the UI still fails.

## Jump to next event

"Event berikutnya" asks the source for the first tick group at which a live order could change (pending entry touched, SL/TP
touched, an exit request, or a data gap over the silence guard). Everything before it is skipped without per-tick work, that group is
processed by the reference rules, and the log shows what happened. With no live order it says so and does not move.
"Ke akhir" is a separate, explicit button. Play stops by itself at the next event (checkbox).

## Behaviour worth knowing

- A market order and a manual close fill on the NEXT revealed quote. SL/TP fill at the first observed quote that crosses the level (the fill can be worse).
- Silence guard: XAUUSD keeps the frozen 60 s. For FX the guard defaults to 300 s (`--silence-seconds`, QA setting in the prototype
  FX profile; needs owner approval before any product use) because FX feeds publish only changes and quiet minutes are normal.
  Longer silence with a live order makes the session UNRESOLVED (the reducer's rule, never guessed).
- Closed orders leave the live order list (order archive); they appear in "Riwayat trade". Order archiving keeps command latency flat.
- The browser only receives ticks/candles up to the session cursor (no look-ahead). Timeframes M1 M3 M5 M15 M30 H1 H2 H4 D1 are built server-side from revealed ticks.

## Test

```
python tools/claude_exp/local_trader/e2e_test.py --zip <HISTDATA_UTC_EURUSD_T202605.zip>
```
Starts its own server and drives it over HTTP: Quick, Plan (Market/Limit/Stop), review/confirm, stale and duplicate confirm, jump,
partial/manual close, SL/TP exit, cancel, every Protocol lock, checklist ON/OFF, tick-grid refusal, accounting identity, restart/resume, and an
independent full replay of each saved session (byte-identical state). 49 checks, all passing on the EURUSD 2026-05 sample.

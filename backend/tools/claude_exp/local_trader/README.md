# Local Trader (prototype)

Manual trading on real local ticks, driven by the Claude engine (verified compact source + reference reducer). QA/prototype:
single user, no PostgreSQL, XAUUSD profile only, observed quotes only (no slippage, no commission).

```
cd backend
# FX (HistData-UTC month zip): add  --pair EURUSD|GBPUSD|AUDUSD|NZDUSD
python tools/claude_exp/local_trader/server.py --zip <DUKASCOPY_XAUUSD_Txxxxxx.zip> --ticks 400000 --offset 0
```
Open http://127.0.0.1:8765. Needs numpy + pyarrow. First start converts the ticks once (cached in the temp folder).
Restart resumes the saved session after verifying its hash chain and financial state; `--fresh` starts over.

Behaviour worth knowing: market orders fill on the NEXT revealed quote; a manual close likewise; SL/TP fill at the first
observed quote that crosses the level (so the fill can be worse than the level); a data gap over 60 s while an order is live
makes the session UNRESOLVED (the reference reducer's rule). The browser only receives ticks/candles up to the session cursor.

Order archiving is enabled: command latency stays flat (6 / 18 / 15 ms at the 1st / 60th / 120th order on 150k real ticks; without archiving it grew from 13 to 140 ms). Closed trades are listed in the "Riwayat trade" panel.

FX pairs (EURUSD, GBPUSD, AUDUSD, NZDUSD) use `--pair` with a HistData-UTC zip (prototype FX profile, see docs/CLAUDE_ENGINE_ARCHITECTURE.md). Pairs not quoted in USD are not supported.

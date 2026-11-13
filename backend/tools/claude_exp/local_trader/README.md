# Local Trader (prototype)

Manual trading on real local ticks, driven by the Claude engine (verified compact source + reference reducer). QA/prototype:
single user, no PostgreSQL, XAUUSD profile only, observed quotes only (no slippage, no commission).

```
cd backend
python tools/claude_exp/local_trader/server.py --zip <DUKASCOPY_XAUUSD_Txxxxxx.zip> --ticks 400000 --offset 0
```
Open http://127.0.0.1:8765. Needs numpy + pyarrow. First start converts the ticks once (cached in the temp folder).
Restart resumes the saved session after verifying its hash chain and financial state; `--fresh` starts over.

Behaviour worth knowing: market orders fill on the NEXT revealed quote; a manual close likewise; SL/TP fill at the first
observed quote that crosses the level (so the fill can be worse than the level); a data gap over 60 s while an order is live
makes the session UNRESOLVED (the reference reducer's rule). The browser only receives ticks/candles up to the session cursor.

Measured responsiveness (150k real ticks, scripted open/close cycles): opening an order took ~13 ms with 1 order in the session,
~100 ms with 60 and ~140 ms with 120, i.e. roughly +1.1 ms per retained order (the reference reducer re-validates every retained order
on each command). Comfortable for manual trading; a session with many hundreds of orders will feel slower. Order archiving is the fix and is not integrated.

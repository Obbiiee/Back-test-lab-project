# Claude engine architecture experiment (RIKSORA) — prototype, measured on real XAUUSD ticks

Status: EXPERIMENT on branch `claude/engine-architecture-20261113`. Nothing here changes a frozen contract, golden vector,
production path or the Codex branch. Every contract change it implies is listed as a PROPOSAL (section 10) and needs owner
approval. Code: `backend/tools/claude_exp/`. All numbers are from this desktop (one machine, other work running at times),
real Dukascopy XAUUSD ticks (2024-01, local copy, never committed). No PostgreSQL was available, so the durable worker path
is NOT measured.

## 1. Choice: keep the financial reducer, replace source + cursor + scan

Three candidates, judged on what was measured:

| Candidate | What it changes | Evidence | Verdict |
|---|---|---|---|
| A. Optimize Codex engine | faster canonical walk, zlib log | 20-35% faster advance/resume (measured, parity identical) | Worth keeping, small ceiling: the reducer still takes one canonical frame per group and checks a per-group prefix hash |
| B. Codex timeline + compact data provider | storage reads only | NOT BUILT. Upper bound from profile: storage `_load` is ~45% of timeline advance, ~25-30% of total; per-tick frame validation, prefix hash and kernel checks remain | Weak: removes one cost, keeps the structural one |
| C. New source/cursor/scan layer, SAME reducer code | compact verified source, pinned cursor, indexed jump | 100,000 real ticks: 152.5 CPU-s (Codex) vs 7.3 CPU-s (C, measured in the parity run; 5.1 s after later validation changes). Identical fills, balance, orders, 24/24 fuzz seeds | Recommended direction |

C does not rewrite money math: `_fills`, `emit`, `_unresolved`, `can_change`, `exit_amount`, `apply` (OPEN/CLOSE/CANCEL/END) are imported from
`execution.observed_kernel`. There is one financial source of truth. Only the source, the cursor and the scan are new.

## 2. Data flow

```
raw source file (CSV zip)  --SHA-256-->  admission validation (once)
        |                                   - order/timestamps, precision (tickSize), crossed flags, ties, gaps
        v                                   - canonical reconstruction rule checked tick-by-tick against canonical store
verified compact parquet  (ts, bid, ask, ordinal, is_crossed [+group_id])   16 B/tick
        |  files pinned by SHA-256 in compact.json; manifest hash pinned by the session
        v
AdmittedSource (numpy arrays, group index, per-256-group min/max of bid and ask)
        |
        v
ClaudeSession.advance_through(target)
   exact groups (crossed, equal-time/different quote, gap > silence guard, order trigger) -> same per-group body as the kernel
   proven-quiet spans -> JUMP (only last group's quote basis is materialised)
        |                                   -> `_fills`/`emit` (reference code) for anything financial
        v
hash-chained durable log: advance + command records, each binding the financial-state hash
        |  recovery: chain check (ms) or full deterministic replay (seconds)
        v
PostgreSQL events/receipts/journal (UNCHANGED, not exercised here)
```

## 3. Integrity (what is proven, what is not)

Tested on 12,000 real ticks, all must be refused, none may be silently accepted:

| Attack / failure | Result |
|---|---|
| one flipped byte inside a parquet file | refused (`CHILD_HASH_MISMATCH`) |
| edited manifest | refused |
| session pinned to a different manifest hash | refused (`SOURCE_PIN_CHANGED`) |
| advance log record edited / log truncated | refused (`RECOVERY_CHAIN_MISMATCH`) |
| saved balance edited | refused (`RECOVERY_STATE_HASH_MISMATCH`) and by replay |
| saved lastObserved / quote basis edited | refused |
| one tick quote changed in the compact source | admission verification finds the altered group |
| worker restart mid-session | recovered state, chain and the next advance byte-identical to the uninterrupted run |

A real bug was found by this: the first design bound the chain to the cursor but not to the financial state, so an edited balance was
accepted. Fixed by binding a financial-state hash into every record (cached on pure-jump advances), plus replay verification.

Ambiguous order (equal timestamp, different quotes) is never skipped; it takes the exact path and the kernel marks it
`UNRESOLVED_EQUAL_TIME_ORDER` or `CHRONOLOGY_LIMITATION` exactly as before (parity fuzz includes this).

Answer to "18 canonical columns or 5?": five columns plus an admission record suffice FOR THIS SOURCE SHAPE. The other 13 fields are
constants pinned once (provider, feed, instrument, source id, member hash, dataset id/version, resolution, quality template)
or deterministic functions of ordinal and time (`eventId`, `originalTimestamp`). Proof: the reconstruction equals the canonical
engine group for every group (0 mismatches in 20,000 and 100,000 ticks), and the altered-quote case is detected. Not proven: sources with per-tick varying
quality, evidence, trusted sequence or diagnostics. Admission refuses those (they need extra columns or the canonical path).

## 4. Benchmarks (identical input; real ticks; mix = market/limit/stop/close/cancel trader, 5-minute steps)

| Stage | 20,000 ticks | 100,000 ticks |
|---|---|---|
| Canonical ingest (Codex pipeline) | 13.5 s | 75.3 s |
| Compact write | 1.4 s | 1.9 s (1,000,000: 6.6 s) |
| Dataset verification, file hashes | <0.1 s | 0.02 s (1M deep: 0.25 CPU-s) |
| Admission reconstruction check (one-time) | 2.8 s | 13.1 s |
| Pure reader throughput | 8.6 M ticks/s | 9.7 M ticks/s (1M: 12.9 M) |
| **Full financial execution, Codex baseline** | **28.9 CPU-s / 29.4 wall** | **152.5 CPU-s / 157.4 wall** |
| **Full financial execution, Claude path** | **1.0 CPU-s** | **7.3 CPU-s** (5.1 after the validation change) |
| Financial parity | identical | identical (151 fills, balance 9975.04) |
| Cold recovery, Codex timeline resume | 17.7 CPU-s | 95.3 CPU-s |
| Cold recovery, Claude chain check / full replay | 0.016 s / 1.1 s | 0.06 s / 6.4 s |
| Storage (data) | compact 0.32 MB vs canonical store 6.2 MB | 1.6 MB vs 30.7 MB (16 vs 307 B/tick) |
| Session log | Codex raw timeline 12.3 MB (zlib-1: ~10x smaller) | Codex raw 61.7 MB vs Claude log 56 KB |
| Peak RSS | 186 MB (both engines in one process) | 1M Claude-only: 468 MB (arrays + Python row list; not minimised) |

1,000,000 real ticks, Claude path only (the Codex baseline was not run: at its measured rate it would take about 25 min of CPU plus about 11 min ingest and several GB of RAM,
and no authorization was given for that): 7.5 CPU-s for a swing trader (189 fills; the session became `unresolved` at a real market gap, as the reference would).

Not measured: PostgreSQL, durable worker, multi-session cache sharing, browser/R2 candles. `fill_event_canonical_bytes_avg` is 1,316 B
(ENTRY/EXIT fill); a trade is roughly three events, so about 3.5-4 KB canonical before PostgreSQL row/index overhead (unmeasured proxy).

### Scalper profile (head-to-head, same input, identical result)
30,000 real ticks, 20 s steps, TP 0.15 / SL 0.10, mixed order types: Codex baseline **363.5 CPU-s (387 s wall)**, Claude path **82.0 CPU-s (83 s wall)**,
4.4x faster; 146 fills each, identical balance, events and orders (parity true, 0 reconstruction mismatches).
Earlier text in this experiment said the scalper case was "no faster than Codex"; that was wrong: I compared Claude's rate with the swing-profile baseline rate, not with the baseline measured on the scalper input.
The gain is smaller than for swing (21-30x) because both engines pay the same kernel cost: profile shows ~90% of the Claude path in `validate_state`, which re-validates
every retained order on every command (O(orders) per command, quadratic over a session; 263k `open_payload` calls at 50k ticks). Jump cannot remove it;
the repo's order-archive state mode is the intended mitigation and was not integrated here. After the tick reader is fast, THIS is the next bottleneck.

### Order archiving integrated (repo's QA archive state, both engines)
Both sides run the reference archive mode (`qa_order_archive_v1`, retention V4: 4,096 cumulative orders; the non-archive reducer caps a session at 128 cumulative orders, which is why earlier scalper runs stopped at 146 fills).
Scalper, 30,000 real ticks, 20 s steps: Codex+archive **142.1 CPU-s**, Claude+archive **12.4 CPU-s** (11.5x), 892 fills, identical events, balance and orders (766 orders archived).
Mixed trader 8,000 ticks: 32.8 vs 2.0 CPU-s (16x), identical. Integrity suite (restart, tamper cases) passes in archive mode; archive-mode fuzz 12/12 parity.
Local app command latency with archiving stays flat: 6 / 18 / 15 ms at the 1st / 60th / 120th order (was 13 / 101 / 141 ms without it); same final balance.

## 5. Jump to next event
Exact integer thresholds (scaled by 1000) against per-256-group min/max blocks, per order type: pending MARKET (next group), LIMIT/STOP (ask or bid vs entry), ACTIVE SL/TP, exit request.
Gap guard and crossed/equal-time groups are always exact. If a price is not an exact scaled integer the search returns "scan exactly".
Result: 151 of 100,000 groups processed exactly (99.85% skipped); 189 of 1,000,000. Correctness: 24/24 fuzz runs on random real-tick windows with random ties,
gaps (70-400 s), step sizes 60/300/900 s and two trader styles (including pending orders, manual close and cancel), plus clean/tie/gap runs. Same events, balance, orders, last observed, group count, quote basis.
Not covered: trailing stops and margin stop-out (the reference kernel has neither; nothing to prove), partial closes, crossed quotes (admission refuses; they would need diagnostics),
multi-symbol, any commission or slippage model other than NONE.

A bug the fuzz found: my first version omitted the reference's tail-of-advance `UNRESOLVED_OBSERVED_SILENCE` branch; parity failed 5/10 until added. The fuzz is what makes the claim credible, not the clean runs.

## 6. Python vs Rust
Measured: the scan is vectorised numpy (12 M ticks/s reading; 99.9% of groups skipped). Remaining cost is Python `Fraction`/`Decimal` validation in the reducer. Rust for the scan would add deployment complexity for nothing measurable.
Rust could help the reducer's exact-money validation, but would have to re-prove parity with the frozen reducer; high risk, low priority. Keep Python + PyArrow/numpy; revisit only if scalper latency (section 4) matters after the order-archive fix.

## 7. Scale and cost (assumptions explicit)
- CPU: 100k ticks ≈ 5-7 CPU-s, 1M ≈ 7.5 CPU-s for a swing trader on this desktop; scalper 82 CPU-s per 30k ticks (Codex 363) until validation is fixed. Do not extrapolate traders per server from this.
- RAM per active session: 468 MB measured for 1M ticks with whole-array load (not tuned); loading per-month blocks would cut it. Shared compact files can be cached once across sessions of one dataset (read-only arrays); nothing here tests that.
- One worker can serve many sessions serially: recovery by chain check costs milliseconds; state is rebuilt from the log. Not load-tested.
- Storage per million ticks: compact 15.4 MB; Codex canonical store ~307 MB.

## 8. Critique of Codex design
A. Keep: canonical contract, hash-chained events, reducer semantics, cold-recovery discipline, shared-source direction, order-archive mode.
B. Too costly: re-canonicalising each immutable tick several times per read (`storage_v2._load`, `_validate`, frame hash), per-group prefix hash, O(orders) `validate_state` per command.
C. Eliminate: per-tick validation of already-verified immutable data; `REPLAY_ADVANCED` as a persisted event (progress is not financial).
D. Rewrite (as layers, not the reducer): source access, cursor/prefix commitment, next-event scan.
E. End-to-end faster? Yes: swing-style 21-30x (100k ticks), scalper-style 4.4x (30k ticks), parity identical in both. The scalper gain is capped by the shared `validate_state` cost.
F. Migration risks: a second cursor/commitment format; owner approval for the proposals below; replay-equivalence must be proven per source type; two engines must never both be authoritative.

## 9. If building from scratch today (16 instruments, years of history, budget server)
Verified compact columnar files per instrument-month as the only hot source (immutable, hash-pinned, SSD), admission once, canonical store kept only as cold evidence for exceptions.
Sessions keep a pinned cursor and a hash-chained advance/command log; recovery by chain check, with deterministic replay as the independent proof (affordable because replay is seconds).
Jump scan with exact fallback. Reducer stays the audited Python implementation, with order archiving from day one. PostgreSQL for state, receipts, journal. This is the shape measured here, not a claim about the unmeasured parts.

## 10. Proposals needing owner approval (nothing applied)
1. Pinned-source cursor and per-advance chain instead of per-group `visiblePrefixHash` (changes the reveal-frame contract, like the shared-source direction).
2. Stop persisting `REPLAY_ADVANCED`; keep progress in the advance log.
3. Compact derived dataset as an admitted execution source (rights remain UNKNOWN for HistData; Dukascopy used here for the test).
4. Light validation on pure-jump advances (full `validate_state` when anything financial changed) plus full validation at recovery/replay.
5. Order archiving in the sessions that use the new path.

## 11. Not proven
PostgreSQL/worker path and bytes per trade; multi-session cache; browser candles/R2; sources with per-tick evidence; crossed-quote handling; margin/trailing logic; behaviour at yearly scale (largest run 1M ticks, Claude path only);
the middle candidate (B) was not built, only bounded; one machine, no repeated runs for timing variance beyond the figures quoted.

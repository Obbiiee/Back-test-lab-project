# Session timeline log: default physical codec for NEW logs

Status: candidate change for comparison. It is a physical-encoding default only. Logical block bytes, block hashes,
cursor/checkpoint calculations, causal clipping and no-look-ahead are unchanged; no frozen contract is edited and no
migration runs. It is not an architecture authority and does not claim the 500 MB annual Session target.

## Change
`execution.historical.new_session_log_codec(folder)` chooses the codec when a Session log is created:

- An explicit `BTL_QA_TIMELINE_LOG_CODEC` always wins (unchanged behaviour).
- Otherwise a NEW private log (no `timeline.sqlite` yet) uses `zlib-1`; this codec already existed and was opt-in.
- An existing archive is opened with `None`, so it keeps the layout it was written with (raw or tagged). Archives are
  never migrated and mixed layouts are still refused (covered by a test).

`delta-dict-zlib-1` is NOT enabled: it saves about 15% more but made reads slower (below).

## Local measurement (real ticks, n=1, not a benchmark claim)
Real XAUUSD ticks (private local data, none stored here) imported through the existing Dukascopy CSV adapter; 15,000
ticks, 2,048 timestamp groups advanced, one machine that was also running other jobs.

| Codec | Block bytes/group | SQLite files bytes/group | Resume | `read_revealed(64)` median |
| --- | ---: | ---: | ---: | ---: |
| raw (previous default) | 593.7 | 622.0 | 10.6 s | 489 ms |
| zlib-1 | 56.0 | 78.0 | 10.9 s | 470 ms |
| delta-dict-zlib-1 | 42.3 | 66.0 | 12.5 s | 1,129 ms |

`zlib-1` is about 87% smaller on disk than raw with no measurable read/resume cost in this sample. The 622 B/group for
raw agrees with the roughly 663 B/group the repository recorded for its annual XAUUSD estimate. File sizes include
SQLite page granularity, so the small-sample on-disk figures overstate the per-group cost of the compressed codecs.

## What this does and does not solve
- Scaling the repository's own 663.5 B/group projection by the measured ratio gives roughly 4 to 5 GB per annual
  XAUUSD timeline instead of about 37 GB (arithmetic on a projection; the annual group count is still unproven).
- That is still far above a 500 MB per-Session target. Reaching it needs the persistence-contract review already
  recorded in `XAU_2024_SESSION_STORAGE_CHECKPOINT_4_2026_10_30.md` (a compact block proof or checkpoint scheme),
  which is a contract change and is NOT made here.
- Separate finding: `IndexedTickTimeline.resume` took about 10 s for 2,048 groups in every codec, so resume cost, not
  log size, may dominate cold-start latency for long Sessions. Not investigated here.

## Tests
```text
cd backend
PYTHONPATH=. python -B -m unittest tests.test_session_log_codec -v
```
Synthetic only: default rule, identical checkpoint and revealed history versus raw with a several-fold smaller log,
existing raw archive keeps its layout and resumes, mixed layout still refused. The PostgreSQL-dependent worker and
historical-workspace suites were not run for this candidate.

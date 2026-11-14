# Compact tick fast path (derived, non-authoritative)

Status: candidate implementation for comparison. It changes **no** frozen contract, hash, or the authoritative
reader/writer (`market_data/monthly_parquet.py`, `ticks/contracts.py`). It does not grant source rights, settle
trades, or add execution. This document is not an architecture authority; the blueprint and
`MARKET_DATA_STANDARD.md` remain the owners.

## What it is
`backend/market_data/compact_tick.py` writes and reads a **derived** per-UTC-month Parquet projection of an
already validated tick dataset:

| Column | Type | Meaning |
| --- | --- | --- |
| `ts_ns` | int64 | UTC nanoseconds |
| `bid`, `ask` | int64 | exact scaled integers (`priceScale` in `compact.json`); never binary floats |
| `ordinal` | int64 | source ordinal (not a trusted venue sequence) |
| `is_crossed` | bool | `ask < bid`, flagged and never repaired |
| `group_id` | int64 | equal-timestamp group, so consumers advance a group atomically |

`compact.json` pins the parent dataset (`datasetId`, `datasetVersion`, optional `manifestHash`), the SHA-256 of
every file, row-group time ranges, ordering/ties (`UNTRUSTED` by default), rights (`UNKNOWN` by default),
evidence class and quality counts (crossed quotes, equal-timestamp ticks, max group size).

## Cost model
Validation runs **once**, vectorised per block, at write time (non-decreasing time, strictly increasing ordinal,
positive exactly representable prices). Reading is plain Arrow column access: no per-tick Python object, canonical
JSON or hash. Files are verified by SHA-256 against the manifest on demand (`verify_all`, `deep=True` re-checks
order, ordinals, groups and crossed counts).

## Boundaries
- Not authoritative: replay that must carry provenance, source-rights evidence or the frozen canonical identity
  still uses the authoritative path. Parent identity is recorded so a result can be traced back to it.
- No-look-ahead is the caller's responsibility: the reader only returns rows inside the requested
  `[start_ns, end_ns)`; `iter_groups`/`iter_blocks(atomic=True)` never split a timestamp group.
- Source order inside equal timestamps is preserved, not trusted. Ambiguity (for example TP and SL touched in one
  group) must still be reported as unresolved by the consumer.
- Raw market data must never be committed. Tests use synthetic data only.

## Tests
```text
cd backend
PYTHONPATH=. python -B -m unittest tests.test_compact_tick -v
```
Covers exact round trip, atomic groups across row groups, end-exclusive ranges, crossed flags, month files,
tamper and manifest-pin detection, refusal of reversal/duplicate ordinals/precision loss/overwrite, and parity with
the authoritative `SyntheticTickProvider` events.

## Local measurement (not a benchmark claim)
One real month, one pair (909,227 ticks), private local data, a busy workstation, n=1; no data is stored here.

| | Authoritative monthly Parquet | Compact |
| --- | --- | --- |
| Write | about 800 ticks/s | about 95,000 ticks/s |
| Size | about 43 B/tick | about 10.6 B/tick |
| Read whole month | about 395 s | about 0.08 s |
| `verify_all` | about 439 s | 0.03 s hash, 0.11 s deep |

These numbers do not prove parity on real data beyond the synthetic and 150k-tick checks that were run, and they
do not cover the product worker, PostgreSQL, or browser. Treat them as a reason to measure properly, with
medians and ranges, before any decision.

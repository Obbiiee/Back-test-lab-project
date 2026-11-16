# XAUUSD 2024 serving efficiency — bounded Checkpoint 1

Result: PASS for the explicit 16,384-tick QA slice only. Full-year export,
annual replay and Session persistence redesign were NOT RUN. This is an
experiment report, not a new architecture or admission authority.

Baseline: existing owner `codex/beta-integration-20261028`, commit
`3bce589aad8f41b03d73b327dac405b93c09cffb`, clean and equal to actual GitHub
before this experiment. Existing `ticks.read_snapshot_v2.export_read_snapshot`
was reused without runtime changes.

Private evidence:
`/home/riksora/riksora-qa-evidence/serving-efficiency-20261030T161839Z/`.
`PLAN.json` precedes execution; `run.py`, `report.json`, `verification.json`,
`parent-qualification.json`, test output and `SHA256_MANIFEST.json` are retained.
The two source/snapshot databases and experiment-only replay logs remain private.

## Scope and preflight

The exporter requires a COMPLETE, fingerprint-pinned parent with one matching
publication and a closed DELETE-mode SQLite archive without WAL/SHM companions.
It copies all canonical objects and publications, validates every body, checks
parent fingerprints before/after copying and protects the new snapshot.

No suitable existing qualified HF-2024 slice was identified. A NEW bounded QA
parent was created from the first 16,384 ticks of qualified H1, at a checked
atomic timestamp-group boundary. All selected ticks were independently compared
with the first original Parquet part, whose manifest SHA/LFS pin was verified.
Checks include exact Bid/Ask decimals, binary64 bit round trips, UTC timestamps,
original ordinals/provenance and independently calculated event IDs. H1's full
hash was reused from its pinned qualification, not recomputed over 23GB; its
size/inode/mtime/mode and companion absence were checked before/after reads.
H2/H3 were not accessed and production/configuration were not changed.

The slice has an explicit `:qa-serving-first:16384` dataset ID and version
`0c9283523359fd8d808c605c4bd758361721b23d82ad8b53f1b1d7b5817abb2e`.
This derivative does not claim the annual dataset identity. All event fields
except the explicit derivative dataset ID/version match H1; export preserves
the derivative identity and canonical objects exactly.

Budget: 256MiB total new QA allocation, 1GiB memory, CPUQuota100%, swap0,
900-second runtime, 30GiB filesystem safety reserve. Expected parent was about
7MB; snapshot, journals, TEMP and paired replay logs fit the bounded allowance.
A sampled guard stops on disk budget/reserve/time violation; cgroup CPU/RAM
limits were enforced. Experiment exited successfully without violations.

## Exact physical storage

| SQLite object | Parent allocated bytes | Snapshot allocated bytes |
|---|---:|---:|
| objects | 1,376,256 | 1,363,968 |
| identities | 2,949,120 | absent |
| uniqueness index | 2,211,840 | absent |
| journal | 8,192 | absent |
| publications | 8,192 | 8,192 |
| storage_layout | absent | 4,096 |
| sqlite_schema | 4,096 | 4,096 |
| freelist | 20,480 | 0 |
| **Archive total** | **6,578,176** | **1,380,352** |

File lengths equal allocated bytes here. Reduction is **79.016189%**, saving
5,197,824 bytes. Identical logical object payload occupies slightly different
B-tree allocation after copying; object payload bytes are exactly 1,205,104
on each side. Identities and their uniqueness index alone occupy 5,160,960B.

Parent SHA256: `c09b07581f40f15d83f3e7ccd078c2197a251ab9bf9dae863e78b694b9b27fb4`.
Snapshot SHA256 is recorded in its receipt and the private SHA manifest.
Canonical public stream SHA256 on both sides:
`2c0e635d973159debba1246899b411944a68e5486c5acb3108f31e6f2525ae93`.

## Parity and resources

- All 71 canonical objects, including compressed bytes/hashes/kinds, exactly equal.
- Entire publication/root/completion/index binding bytes exactly equal.
- All 16,384 public ticks exactly equal; seven boundary/index seeks equal.
- Full bounded paired replay: 256 advances, 16,384 rows, identical reveals and
  checkpoints; revealed-view clipping checked after every advance.
- Cold reconstruction against both representations gives the exact checkpoint
  and revealed tail. Existing original parent fingerprint/hash remains unchanged.
- Existing exporter regression suite: 8 tests PASS, 0.481s, including corruption,
  incomplete/WAL/wrong-pin refusal, cancellation, isolation and atomic resume.

| Measurement | Result |
|---|---:|
| Existing exporter wall / CPU | 0.107236s / 0.092206s |
| Whole experiment wall / CPU | 158.720718s / 157.615819s |
| Peak process RSS | 233,548KiB = 239,153,152B |
| Sampled peak QA allocation | 36,143,104B, below 268,435,456B budget |
| Minimum sampled filesystem available | 60,326,612,992B, above 32,212,254,720B reserve |
| Sequential full-slice read, parent / snapshot | 6.895514s / 6.608188s |
| Paired advance median / p95 / max | 0.057107s / 0.283304s / 0.453378s |
| Cold reconstruction, parent / snapshot | 14.886711s / 14.964479s |
| Process-attributed block read / write deltas | 74,231,808B / 88,702,976B |

Latency is from sequential readers with warm OS caches; paired advance latency
includes BOTH readers, equality/clipping checks and their durable QA logs.
Cold reconstruction means new provider/timeline instances, not a cold OS cache
or a killed application worker. CPU/RSS cover this process; /proc/self/io
counter deltas are not a device-wide I/O benchmark. There was no financial
Session/account/order test, new eligibility or broker-execution grant.

## Decision and remaining blockers

This proves material serving savings with the EXISTING exporter on genuine
HF-2024 ticks. It does not prove the full H1 table breakdown or annual size.
Simple arithmetic at this slice's 84.25B/tick yields 4,735,567,051.75B for the
annual count; that is NOT a qualified annual projection, budget or upper bound.
Only the initial January slice was measured. No full-year export follows
automatically, and the full protected archives remain local and intact.

Serving projection does not solve required per-Session log/SQL growth, TEMP
lookup amplification, annual cold cost or the failed 500MB product projection.
Annual acceptance remains BLOCKED/NOT RUN. Stop after Checkpoint 1; any larger
export, source switch or Session storage work requires its own authorized scope.

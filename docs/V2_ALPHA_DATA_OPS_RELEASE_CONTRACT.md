# Backtest Lab v2 Alpha — Data, Operations & Release Contract v1

Status: **FROZEN PLAN CONTRACT**. Planning authority only until operationally authorized.

## 1. Tick→candle aggregation v1

Alpha chart candles use **mid price = exact (bid + ask) / 2** from valid revealed bid/ask events. Mid is presentation/research input only; execution remains bid/ask.

- internal time UTC;
- buckets are left-closed/right-open: `[bucket_start, bucket_end)`;
- bucket boundaries are Unix-epoch aligned UTC multiples of timeframe duration;
- candle timestamp = bucket_start UTC;
- OHLC from ordered revealed mid observations within the bucket;
- no synthetic candle for an empty bucket;
- no forward-fill;
- current incomplete bucket may be displayed as explicitly incomplete and changes only with newly revealed events;
- no future event may affect current output;
- tick count may be exposed as `event_count`; it is not exchange volume;
- source volume is absent unless the provider supplies a defined compatible field; never fabricate volume;
- DST does not change UTC bucket boundaries;
- provider session/calendar metadata is retained separately and does not shift bucket math.

Provider-native candles, if present, are separate validation evidence and are never silently mixed with derived candles.

## 2. Calendar/gap semantics

Calendar status vocabulary:
`KNOWN_OPEN`, `KNOWN_CLOSED`, `UNKNOWN`.

Only pinned provider/session metadata can assert KNOWN_OPEN/CLOSED. Silence alone cannot. A gap during UNKNOWN remains `UNEXPLAINED_SILENCE`; a gap during known closure is `EXPECTED_CLOSURE`; absence during known-open is a quality warning and may disqualify precision coverage depending on the dataset gate.

## 3. Dataset eligibility classes

- **CHART_ELIGIBLE:** valid OHLC/tick-derived candles and identity/timeframe metadata; no precision execution claim.
- **REPLAY_ELIGIBLE:** chart eligible + immutable dataset/version/hash + coverage bounds + bounded seek/reveal semantics.
- **PRECISION_ELIGIBLE:** replay eligible + ordered canonical bid/ask events + required instrument profile + validated chronology policy + quality report + no unresolved corrupt segments in the experiment window + evidence sufficient to apply Execution Contract v1.
- **EXTERNAL_ALPHA_ELIGIBLE:** required technical class + documented rights for the exact audience, storage, display/derived use, retention and region/product mode.

Unknown completeness may be disclosed for chart/replay. Precision experiments cannot cross a segment whose evidence uncertainty can alter execution without producing UNRESOLVED. Corrupt segments are never eligible.

## 4. Early rights gate

Before provider-specific production integration, record:
- provider/product;
- intended audience;
- raw storage;
- derived storage;
- display;
- redistribution/API/export;
- retention/backup;
- commercial use;
- attribution;
- region/user limits;
- termination/deletion;
- evidence reference and review date.

Decision:
- external permitted → provider may become external Alpha candidate;
- internal/personal only → engineering/internal benchmark only;
- unclear → no external integration;
- prohibited → reject provider for that mode.

A final rights re-check remains mandatory immediately before first external cohort.

## 5. Migration matrix

| v1 asset | v2 Alpha policy |
|---|---|
| M1 decade candles | read-only chart/compat source; no precision-result migration |
| v1 paper account/balance/P&L | retain legacy MODELLED; no automatic import into v2 canonical account |
| v1 closed trades | legacy view/export only unless explicit lossless import format marks LEGACY_MODELLED |
| v1 journal notes | may import only with stable referenced legacy identity; otherwise export/read-only |
| 8 drawing persistence | migrate only after S-1/S-2 round-trip proof; original storage preserved until cutover retention ends |
| v1 indicator runtime configs | runtime-only state has no durable migration promise; S-7 tick-alpha preferences use a separate Session-isolated local namespace with unknown/foreign-byte preservation, no v1 migration |
| replay date | convenience preference only; not financial/session evidence |
| news dataset/preferences | preserved independent domain; non-blocking for v2 Alpha |
| Method/Session prototype | no state migration; concepts only |
| malformed/future local storage | preserve original bytes; refuse destructive rewrite |

## 6. Cutover lifecycle

`V2_HIDDEN → INTERNAL_OPT_IN → INTERNAL_DEFAULT → COHORT_DEFAULT → V1_ROLLBACK_ONLY → V1_RETIRE_REVIEW`.

No v1 deletion during Alpha. V1 retirement requires a separate post-Alpha evidence review; therefore the frozen Alpha journey ends with v1 still recoverable.

## 7. STITCH selection rubric

Drawing candidates **current BTL, pinned OpenAlgo, pinned OpenCharts** are all evaluated before selection.

A candidate is disqualified if any MUST fails:
- license/provenance acceptable;
- all eight Alpha drawing types supported directly or through bounded adapter;
- canonical TIME+PRICE anchor round-trip;
- create/select/hit-test/drag/edit/delete;
- lock/hide;
- undo/redo semantics;
- persistence/reload;
- timeframe/replay/zoom/pan/resize;
- no look-ahead;
- no execution/account/research authority;
- production build/browser regression;
- rollback possible;
- no critical/high unmitigated security finding.

Among qualifying candidates rank lexicographically:
1. lowest number of BTL production modules requiring semantic rewrite;
2. lowest new runtime dependency count;
3. lowest maintained BTL adapter/custom LOC measured after spike;
4. smallest minified+gzip JS delta;
5. current BTL wins exact tie.

Feature count beyond Alpha MUSTs is not a tie-breaker.

Indicator candidates use the same principle: semantic parity/no-look-ahead are MUST. Rank calculator and host separately by semantic rewrite count → dependency count → maintained adapter/custom LOC → bundle delta → current BTL tie.

Upstream is pinned to the exact commit/tag inspected at spike start. No moving HEAD during migration. License/NOTICE are recorded. Major upgrades are never automatic.

## 8. Reference Alpha deployment envelope

Performance is evaluated on a **reference class**, not a vendor:
- Linux x86_64;
- 4 dedicated/shared-vCPU equivalent with sustained benchmark availability;
- 8 GiB RAM;
- SSD/NVMe-backed storage;
- at least 80 GiB usable disk for app/test data;
- PostgreSQL may share the node for Alpha;
- one application node + bounded worker processes;
- monthly infrastructure target **<= USD 50 equivalent before market-data licensing/domain/email costs**.

If actual chosen host is stronger, it must also be possible to reproduce the acceptance workload on this class or a throttled equivalent.

## 9. SLO and resource gates

For Alpha acceptance on reference class under the frozen H-4 workload:
- ordinary authenticated non-heavy API p95 <= 500 ms, p99 <= 1000 ms;
- session command acknowledgement excluding intentionally queued heavy research p95 <= 750 ms, p99 <= 1500 ms;
- indexed random historical seek to first bounded page p95 <= 750 ms, p99 <= 1500 ms;
- replay must sustain **>= 20× virtual speed for 10 concurrent active sessions** without changing deterministic hashes;
- process/node peak RAM <= 85% of 8 GiB;
- disk utilization <= 80% of provisioned usable disk during acceptance;
- queue must remain bounded and recover to zero after workload;
- 0 lost/duplicate committed financial events;
- 0 cross-tenant access;
- 0 deterministic hash mismatches;
- error rate for valid non-adversarial requests < 1%.

These are Alpha engineering gates, not promises to public users. If a measurement is invalid because the workload was not reproducible, the benchmark fails and must be rerun.

## 10. Resource default ceilings

Before measured tuning, hard defaults:
- request body <= 2 MiB except dedicated authorized dataset ingestion path;
- normal API page <= 5,000 records;
- browser raw tick API: disabled by default;
- active replay workers <= max(2, CPU_count);
- queued heavy jobs <= 100 per node;
- one user <= 4 active heavy jobs;
- worker/job wall timeout <= 30 minutes unless checkpoint explicitly classifies a bounded ingestion benchmark;
- cache, if adopted, <= 20% node RAM;
- session checkpoint serialized payload <= 2 MiB;
- open dataset file handles are pooled/bounded, never one-per-user unbounded.

Tune only through measured config revisions; raising a ceiling is not a correctness fix.

## 11. Release severity

- **S0 Critical:** security breach/cross-tenant exposure, unrecoverable data loss, silent financial-truth corruption, rights violation. Immediate stop.
- **S1 High:** wrong deterministic fill/P&L/account, look-ahead, duplicate/lost event, restore changes outcome, corrupt data accepted as valid, auth bypass. Blocks release/cohort.
- **S2 Major:** core Alpha flow unavailable, repeated crash, material journal/research mismatch without financial corruption, severe performance gate failure. Blocks cohort advance.
- **S3 Moderate:** workaround exists; non-core UX/visual defect; does not alter truth.
- **S4 Minor:** cosmetic/documentation.

External cohort requires zero open S0/S1/S2. S3/S4 may remain with documented workaround/owner.

## 12. Cohort evidence gates

Each cohort must satisfy all technical gates plus:
- minimum elapsed observation: 7 calendar days;
- minimum completed distinct-user sessions: max(20, 3 × cohort_size);
- minimum aggregate replay time: 20 hours for cohort 5, then +20 hours per subsequent cohort;
- at least one successful recovery drill in the current deployed build lineage;
- no open S0/S1/S2;
- deterministic audit sample: at least 20 completed financial sessions or all if fewer, replayed/reconciled with identical hashes;
- support incidents classified and no unresolved pattern indicating systemic correctness/security/data issue.

If adoption cannot produce the minimum sample, HOLD; do not fake progression.

## 13. RPO/RTO and backups

Alpha target:
- PostgreSQL durable state RPO <= 15 minutes;
- session/event financial truth RPO = 0 for acknowledged committed transactions;
- application recovery RTO <= 60 minutes;
- dataset/index artifacts are immutable/rebuildable from licensed retained source where permitted; otherwise backup policy must match rights;
- daily backup + transaction/WAL strategy sufficient for RPO;
- 7 daily + 4 weekly backup generations unless rights require shorter retention;
- restore drill before external Alpha and at least monthly during cohorts.

## 14. Telemetry/privacy

Never log:
- passwords/tokens/secrets;
- full session cookies;
- raw private provider files;
- arbitrary journal free text by default;
- complete strategy/Method bodies in metrics;
- raw order payloads when IDs/aggregates suffice.

Metrics use IDs, versions, durations, sizes, counts, status/reason codes. Application diagnostic logs retained 30 days by default; security/audit metadata 90 days where lawful; product analytics must be disclosed/consented as required. Sensitive debugging requires explicit temporary opt-in and expiry.

## 15. Alpha threat model

Mandatory tests/review:
- authentication/session fixation/revocation/expiry;
- CSRF where cookie auth applies;
- password recovery/verification enumeration;
- brute-force/rate abuse;
- object/workspace IDOR;
- cross-tenant dataset/session/Method/Passport access;
- parser/decompression bombs;
- path traversal/symlink escape for local/dataset files;
- oversized/range abuse;
- malformed canonical encodings;
- SQL injection/ORM misuse;
- XSS from Method/journal/text drawing fields;
- SSRF if any user-controlled remote fetch exists (otherwise remote fetch remains disabled);
- secrets in repo/log/build;
- dependency known-vulnerability review;
- privilege/admin/support access documented;
- backup access and deletion/rights handling.

## 16. Browser/accessibility Alpha baseline

Supported:
- current stable Chromium desktop;
- current stable Firefox desktop;
- latest stable Android Chromium for narrow fallback/basic inspection.

Primary authoring/research target is desktop >= 1280×720. Narrow web must not horizontally corrupt the document and critical read/cancel/logout flows remain reachable; full mobile authoring parity is not required.

Critical desktop flow must support keyboard reachability, visible focus, modal focus trap/return, labels for form controls, Escape/cancel semantics, and no color-only critical state indication.

## 17. Dependency policy

- lockfile committed;
- no opportunistic major framework/dependency upgrade during frozen journey;
- donor exact commit/tag pinned at acceptance;
- security-critical patch may create a bounded maintenance checkpoint; if breaking semantics, use Change Request;
- remove unused dependencies at consolidation;
- license/NOTICE updated with adoption;
- dependency vulnerability scan/review before each external cohort.

## 18. Test family contract

Every implementation checkpoint registers applicable commands in `AI_CONTEXT/07_TEST_COMMANDS.md` using families:
- `contract`;
- `unit`;
- `property`;
- `integration`;
- `migration`;
- `browser`;
- `security`;
- `recovery`;
- `performance`;
- `repository`.

A checkpoint cannot waive an applicable family silently. Exemption requires written reason in its evidence report. Financial truth changes require contract+unit+property+integration. UI authority changes require browser. Durable schema changes require migration+recovery.

## 19. Commit/checkpoint rule

A checkpoint may use multiple atomic commits. Every commit must leave protected baselines recoverable. Exactly one completion report/marker closes a checkpoint after all acceptance gates pass. Push and remote/local equality are required at closure.

Repeated implementation failure is not counted by attempts. It becomes hard invalidation only when root-cause evidence demonstrates a mandatory acceptance criterion cannot be met under the frozen contract after the applicable predefined fallback/optimization tree is exhausted.


## Code-informed capacity hardening

The [Reality → Plan Gap Matrix](V2_ALPHA_REALITY_PLAN_GAP_MATRIX.md) and [Capacity & Failure Hardening Contract](V2_ALPHA_CAPACITY_FAILURE_HARDENING_CONTRACT.md) are normative acceptance hardening for this contract.

Additional invariants:
- production ingestion/validation/replay memory is bounded by configured working sets, not total dataset size;
- late-history seek/resume cannot require a complete prefix scan;
- queues, workers, DB connections, browser history/cache and telemetry cardinality are bounded;
- overload is rejected before heavy allocation;
- mass recovery obeys admission control;
- active sessions pin immutable dataset/version/profile identity;
- actual safe concurrency is benchmark-derived; a cheaper host needs its own certification and cannot inherit the reference-node result.

These rules do not change the reference Alpha SLOs above. They prevent an implementation from nominally meeting a feature checkpoint while retaining an unbounded failure path.

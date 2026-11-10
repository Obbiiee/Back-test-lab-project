# 07 — Test and Certification Matrix + Closed Known-Unknown Register

**Principle:** deep full-system certificate once per architecture/environment baseline; automated small tests with every code change; isolated data admission each additional dataset. Never promise no testing after changes to financial rules, reader, profile, rights or hardware.

## Evidence levels and mandatory language

`DRAFT_DESIGN` = specification only; `IMPLEMENTED` = code integrated; `FIXTURE_VERIFIED` = authored deterministic tests; `PUBLISHED_SOURCE_VERIFIED` = identified original real dataset/hash and timed tests; `CAPACITY_CERTIFIED` = repeatable host/workload metrics; `HOSTED_RELEASE_ELIGIBLE` = TLS, provider commercial rights, backup/restore, payments, security and E2E tests. All five separately required; no "DONE" based solely on source files or console report.

## Acceptance matrix

| ID | Test family / workload | Pass criteria | Evidence and cadence |
| --- | --- | --- | --- |
| T01 | Source identity and admission | original source/manifest/hash/rows, exact Bid/Ask/UTC order/ties/quality; rights separately verified | every source/version; independent raw probes |
| T02 | SQLite vs daily/monthly Parquet | equal canonical event/group/evidence/quality hashes; complete size/index/WAL/scratch measured; row-group time pruning | once at reader/layout switch; real published source finalists 3 trials |
| T03 | bounded memory + selective reader | locate first full group, no full-year materialization, 1h/day/72h/month/year boundaries and EOF correct | reader regression each change; real dataset certificate |
| T04 | normal replay and 72h Jump | exact identical ledger/cursor/revision/projections, first eligible event; no-event keeps pending; no OCO/no lookahead | fixture golden every replay change; full source relevant cases |
| T05 | financial order semantics | long/short market, buy/sell stop/limit price improvements/gaps, SL/TP, activation same tick, partial/manual vs Protocol | canonical financial goldens every financial change; no silent relaxation |
| T06 | untrusted equal timestamp/quality | outcome-equivalent ties common; uncertain causal outcomes unresolved, not filled | real-source diagnostic + crafted ambiguous fixture |
| T07 | Session storage amplification | 0 / 100 / 500 committed action trials, 1 / 2 / 5 / 10 Sessions same dataset pin; **zero per-user market copy**, explain bytes per tick and per command, full command JSON/WAL + snapshot measured | storage benchmark and long-run certificate |
| T08 | cold restore and idempotency | latest snapshot+suffix exact events/hashes, order state, money, cursor; kill worker before/after commit and retry exact command | DB recovery suite every schema change; real long-prefix trial |
| T09 | Instrument/conversion | XAUUSD golden unchanged; FX pairs with quote USD and non-USD JPY/CHF/CAD/GBP/NZD; historical bid/ask, exact money rounding, freshness/no future rates | per profile contract change and dataset admission |
| T10 | Session/Method aggregation | one Method many Sessions, overlapping samples counted, normalized R only where valid, no synthetic combined portfolio curve | research stats unit+integration every change |
| T11 | account security | Google/password account linkage only with verified explicit ownership; cross-workspace 0 exposure; logout/refresh/token/CSRF/entitlement | auth regression each change + HTTPS browser |
| T12 | Free/Pro and quota | identical canonical finance, Free 1 calendar-month/day, max 5 saved Sessions, 30d Trash; open position does not force close | billing/auth integration before public release |
| T13 | UI desktop/mobile/app | 320/375/390/768/1024/1440, pointer/touch/fullscreen landscape/keyboard/focus, draft-review-confirm, PWA install/logout/offline read-only | Claude each UI milestone; full browser/device release |
| T14 | rare instrument and cache | cold partition access and eviction, bounded RAM/files/request traffic, no per-user hot data copies, truthful missing-source status | cache/layout/VPS certificate |
| T15 | one VPS capacity and host recovery | p95/99 API/seek/ack, 20x/10 sessions on frozen Alpha reference if applicable, one-user real year, <=85% RAM and <=80% disk, worker queue drains, off-node backup restore | on chosen host and major workload/hardware change |
| T16 | licensing and commercialization | written storage/display/derived/cache/backup/redistribution rights for precise dataset, no false advertised coverage; paid payment webhook idempotency/restore | before hosted/paid cohort and per license change |
| T17 | failure/adversarial | bad hash, partial file, full disk, S3 outage, network timeout, tenant switch, stale/replayed command, queue 429, mixed dataset pins | negative tests each changed boundary |
| T18 | reproducibility / retention | accepted Git commit, dependency versions, source/manifest hash, test report, backup+rollback; no private raw prices in Git | every checkpoint |

Minimum official Alpha reference SLOs are specified in [Data/Ops contract](../V2_ALPHA_DATA_OPS_RELEASE_CONTRACT.md); do not quietly substitute invented softer targets. Reports must include full actual workload and host environment; p99 cannot be claimed from three runs.

## Finite known-unknown table — design action is determined now

| ID | Unknown fact | Decided method | Choice / fail gate |
| --- | --- | --- | --- |
| U01 | exact active 2024 VPS published data, duplicates, private logs and rights | read-only host manifest, path/bytes/hash + receipts; compare all snapshots byte-by-byte before any cleanup | **STOP SOURCE_NOT_VERIFIED**; no guessed 21GB/97GB deletion |
| U02 | Parquet day vs month and ZSTD/row groups | published-source ABBA 3 trials; compare exact canonical hashes, cold seek, RAM, disk, S3 request model | choose Pareto-safe candidate; no finance change |
| U03 | PyArrow vs DuckDB read path | independent bounded reader adapters to V2, include cross-file ties and no full-year scan | select lower safe latency/read amp; DuckDB not financial engine |
| U04 | per-Session timeline and command-result duplication | byte accounting for timeline.sqlite, tick_commands, tick_checkpoints and WAL at 0/100/500 decisions | remove redundant per-tick/session copies with versioned compat; stop on dedup/restore mismatch |
| U05 | long-history cold restart speed | 30m/day/month/year suffix replay from safe checkpoint and identical canonical hashes | tune indexed checkpoints/cadence, not lossy state |
| U06 | full 16×5 coverage and lawful commercial use | independent per feed/time/source passport + rights check | mark unavailable honestly; no misleading launch |
| U07 | reliable non-USD FX conversion model | versioned instrument and conversion profiles + historical point-in-time quote-side golden vectors | unsupported feed/ambiguous conversion = refused/unresolved, not guessed |
| U08 | object storage necessity / 2TB plan | precise canonical+raw+DB+scratch+backup/working-set accounting after compression and retention | keep one VPS, add storage only on objective full-disk/DR gate |
| U09 | extra compute necessity | stable host repeatable profiling CPU/RAM/IO/queue, measure optimizations first | add VPS only with bottleneck evidence |
| U10 | true mobile drawing usability and app capabilities | real device test at 320/375/390, portrait/landscape, touch targets and PWA lifecycle | adjust Claude-owned interaction without modifying financial contract |
| U11 | account linking vs existing OAuth/email model | explicit proof of possession, conflict refusal and same-user integration tests | no automatic email-linking or user duplication |
| U12 | public payments/permissions/reliability | test mode webhook idempotency, actual TLS and backup restore; provider legal/data rights | no paid roll out without PASS |
| U13 | benchmark sample duration and real quote quality | existing 2015 Exness Aug–Dec structural report vs actual verified 2024 year | label PARTIAL_YEAR vs YEAR_PASS; no invented fills on UNKNOWN quote quality |
| U14 | portfolio/AI scenario features | future scoped version with point-in-time opportunity and causal replay | **OUT OF V1**; do not delay core release for speculative feature |

**Important distinction:** The above is a finite list of *known* factual and technical gates. It is not an open architectural brainstorm. Each has a pre-decided acceptance action and fail-safe. Unknown unknowns discovered later require an explicit Change Request; they do not give agents permission to rewrite the product.

## Three testing classes to avoid repeating full work needlessly

1. **Base architecture certificate:** after implementation, real-source canonical parity, storage+capacity+recovery+security+cross-device end-to-end, pinned commit+dataset+host; retain immutable report.
2. **Automatic regression:** run targeted unit/golden/contract/visual/DB tests for each change; broader integration test at boundary changes. CSS-only change does NOT trigger a full year market re-ingestion.
3. **Dataset Admission:** every new pair/month/year gets hash, profile, time order/quality, rights, example queries, conversion freshness and manifest/index tests; no whole-program benchmark unless dataset size/access profile materially changes.

## STOP and rollback gate

STOP immediately for changed ledger/canonical event hashes, missing original data, ownership leak, financially different Jump, lookahead, snapshot restore mismatch, outside-authority Git/file change, disk/CPU resource exhaustion, invalid quote currency conversion, rights uncertainty for public deployment, or an untested destructive cleanup. Preserve old data/source/log; write objective failing fixture + remediation options. No claiming PASS from a different fixture/hardware/source.

# Checkpoint 7 — integrated Session acceptance

**Integrated isolated QA: PASS. Annual acceptance, annual 500 MB economics and production cutover: NOT PROVEN / NO-GO.** This checkpoint composes the existing C1 serving projection, C5 verified ranges and C6 PostgreSQL object representation. It does not amend architecture authority or frozen 42.17/42.19.

Owner worktree `/tmp/riksora-beta-integration-current-20261028`, branch `codex/beta-integration-20261028`, starting local/actual remote HEAD `7875628490e3c44f50c5f940bf60dc63f18a5b7d`, initially clean. References read: `PRODUCT_SYSTEM_ARCHITECTURE_BLUEPRINT.md`, existing AI context/current phase and handoff, C1/C5/C6 reports and their QA implementations, annual resource/recovery findings. This report is experiment evidence, not competing architecture authority.

Private retained evidence: `/home/riksora/riksora-qa-evidence/session-storage-20261030/checkpoint7/`. `PLAN.json` predates execution; `assets.json` records exact source identity, seed, command schedule and source pins; `report.json` contains main results, byte parity, crash/adversarial/multi-worker results; `verified-continuation.json` closes independent reconstructed-log continuation; `closure.json`, `evidence-index.json` and `repository-gates.log` close resources and checks. No raw data or private database connection is committed to Git.

## Compatibility and workload

Existing engine, financial reducer, provider, exporter, store and contracts remain unchanged. Explicit-run QA modules under `backend/tests/qa_integrated_*7.py` are unmounted and never imported by the app. Format `RIKSORA-QA-INTEGRATED-SESSION-1` extends the C5 experiment to all original commands: non-ADVANCE records commit empty ranges; zero-reveal ADVANCEs remain distinct acknowledgements. Original durable intents are included in **both** arms, separate from their mandatory receipts. C6 object nodes are counted once, including their indexes/TOAST/forks, rather than assigned repeatedly to each reference.

Two identical-input baseline/candidate lanes were run:

1. **Actual C1 XAUUSD 2024 derivative:** accepted existing 16,384-tick bounded source, replay prefix **2,222 ticks / 2,222 timestamp groups**, 35 advances of at most 64 groups plus one zero-reveal advance. Parent SHA-256 `c09b07581f40f15d83f3e7ccd078c2197a251ab9bf9dae863e78b694b9b27fb4`; projection SHA-256 `7d88591601c29246c07239763efbb9c802e0925a265c84fb1d4daf6202ed1a90`. C1 explicitly derived dataset ID/version is preserved; this is not relabelled as the full canonical year. A fresh Session binds that identity. Public provider descriptions/publication metadata agree. No financial orders; real-source execution eligibility remains **NOT_GRANTED**.
2. **Native financial execution on authored observed QA ticks:** 320 ticks/groups, 512 commands, 64 zero-reveal advances, 64 LONG LIMIT and 64 LONG STOP orders. Pending orders execute on later actual QA quotes; 64 TP and 64 SL exits produce final balance **9987.2** from 10000 (zero commission, quantity 0.01 lot). This is the unchanged financial engine, not candle execution, broker outcome certification or real-XAU execution admission. Both arms retain 128 orders; order 129 is refused with `REFUSED_STATE_LIMIT` and unchanged state/journal.

Baseline: parent provider + existing zlib timeline + original PostgreSQL canonical payloads (normal PostgreSQL compression enabled). Candidate: C1 projection + verified ranges + C6 lossless PostgreSQL DAG. Baseline and candidate each use private databases in one copied, isolated QA cluster. Only a private Unix socket is enabled. The stopped source QA cluster is copied and never started in place. All original evidence, H1/H2/H3, production and active configuration remain untouched. H1/H2/H3 were not accessed.

## Physical storage

Actual file allocation uses `st_blocks × 512`. PostgreSQL includes Session relations, object/format/range tables, TOAST, indexes and all auxiliary forks/segments, reconciled against PostgreSQL relation sizes after private QA CHECKPOINT. Shared database catalogs, cluster WAL, temporary/rebuildable logs and shared market source are accounted separately, not charged to every user.

| Lane / physical persistent role | Baseline bytes | Candidate bytes | Session saving |
|---|---:|---:|---:|
| XAU Session SQLite + PostgreSQL | 724,992 | 577,536 | **20.34%** |
| Financial 128-order Session SQLite + PostgreSQL | 19,079,168 | 5,439,488 | **71.49%** |
| XAU PostgreSQL portion | 483,328 | 499,712 | — |
| XAU Session SQLite portion | 241,664 | 77,824 | — |
| Financial PostgreSQL portion | 18,423,808 | 4,755,456 | — |
| Financial Session SQLite portion | 655,360 | 684,032 | — |

The financial SQLite candidate is larger: this schedule has many commands but few groups. Range proofs are not automatically smaller for every workload. PostgreSQL deduplication supplies the principal integrated saving here. Exact source-only C1 directory allocations are 6,578,176 B parent and 1,384,448 B projection; these directories are shared once, not copied per Session.

**Retaining protected source changes the host conclusion:** XAU serving-role + Session is 7,303,168 → 1,961,984 B, but actual retained parent + projection + Session is **7,303,168 → 8,540,160 B**. For this one tiny Session, the host uses **1,236,992 B more**, because no parent is released. Financial fixture parent + projection + Session is 19,197,952 → 5,615,616 B. These host-role numbers exclude QA cluster/catalog/WAL and scratch, which are separately retained in the full artifact inventory. No local disk was reclaimed.

Candidate writer legacy timeline is rebuildable experimental scratch: 208,896 B XAU / 475,136 B financial. Independent verifier scratch is 208,896 / 471,040 B respectively. These are excluded only from the **proposed compact persistent role**, included in the actual QA disk footprint, and never deleted. Current approved production recovery still requires its existing legacy evidence. A total over all private QA artifacts is therefore a different quantity from per-Session physical relation allocation.

Identical-prefix measurements distinguish fixed pages and marginal allocation:

| Financial commands | Baseline Session B | Candidate Session B |
|---:|---:|---:|
| 0 | 151,552 | 217,088 |
| 16 | 491,520 | 397,312 |
| 64 | 1,343,488 | 860,160 |
| 256 | 7,249,920 | 2,600,960 |
| 512 | 19,079,168 | 5,439,488 |

Marginal 256→512 growth is **46,208 → 11,088 B/command**. XAU 16→36 growth is **12,697.6 → 9,216 B/command**, with 64-group batching except the last partial/zero-reveal advance. Commands/events/checkpoints co-vary; these are measured combined slopes, not independently identified costs for each record kind. PostgreSQL MVCC, autovacuum, page slack and order-state growth affect them. The 128-order limit prevents extrapolating this financial fixture indefinitely. No annual group count is inferred from annual tick count.

## Correctness, independent verification and recovery

All gates below PASS in bounded QA:

- Direct independent decode compares **original canonical bytes**, IDs and hashes for XAU 36 receipts / 36 events / 37 checkpoints and financial 512 receipts / 512 events / 513 checkpoints. State, cursor, group stream, receipt stream, acknowledgement tips and publication identity match baseline/candidate exactly. Financial byte comparisons cover 18,233,018 receipt bytes, 584,168 event bytes and 17,903,984 checkpoint bytes.
- Independent verifier imports no writer range/index/cache or writer codec decoder. It traverses immutable source positions, rebuilds group commitments, replays the existing engine, checks every cursor/log tip, complete SQL event chain, cash reconciliation and final immutable checkpoint/tip. Authored numeric oracle independently checks pending/entry/TP/SL prices, counts and balances.
- Missing prepare, intent or SQL reference; reordered/duplicated SQL reference; corrupt compressed prepare; substituted dataset binding; and missing shared object all reject. Existing C5/C6 adversarial coverage remains referenced, not claimed to have all been rerun here. Consumer revealed reads exactly match source; access beyond the revealed prefix rejects; no provider/index/EOF handle is exposed.
- Source-free exact retries return original receipts. Changed intent under an existing ID rejects. No acknowledgement/receipt or shared object is counted twice in the persistent model.
- **Six actual dedicated-worker SIGKILL cases:** baseline before/after SQL commit; candidate after SQLite prepare, before SQL commit, after SQL commit and after SQLite publish. Before commit, authoritative revision remains 3 and newly inserted SQL objects roll back; after commit revision is 4. Independent cold recovery before retry reconciles balance 10000/10002 appropriately. Retry completes once with one TP posting, four receipts and balance 10002; repeat retry is byte-identical.
- Cross-store protocol: SQLite FULL-synchronous prepare → SQL transaction atomically commits financial records, object references and range reference → SQLite published head. SQL is the visibility authority. Orphan prepares are not committed history; an interrupted published head is rebuilt from verified SQL references. This is a QA protocol, not a formal change to 42.17/42.19. `fsync`, `synchronous_commit`, `full_page_writes` were all on. Worker SIGKILL does not certify host power-loss durability.
- **Independent reconstruction actually resumes execution:** a separate candidate Session is verified at revision 3 into a fresh log directory, then resumed from that reconstructed directory through revision 8, including TP/SL and zero-reveal acknowledgement. Original writer scratch stays unchanged and is not used for continuation. Second independent verification and oracle confirm two closed orders, one TP/one SL and balance 9999.8. All main histories are also rechecked with explicit format-schema/revision validation.
- **Two OS workers:** distinct Sessions both commit; same command on one Session yields one commit plus one original receipt; different intents at the same revision yield one commit and one stale refusal. All final Sessions independently verify. A single-host `flock` serializes the whole per-Session prepare/engine/commit/publish sequence. C6 process-global adapters are isolated per process; threads, distributed locking and cross-host operation are not qualified.

## Performance and unit-economics inputs

Wall latencies below are descriptive, warm host-cache measurements, not an SLA. Read sample counts are 35 XAU pages and only five financial pages. Candidate reads reconstruct source positions rather than trusting a persistent writer index.

| Measure | XAU baseline → candidate | Financial baseline → candidate |
|---|---:|---:|
| Write median / p95 | 109.16 / 228.57 → 153.76 / 285.45 ms | 266.90 / 476.45 → 358.95 / 613.44 ms |
| Revealed-read median / p95 | 252.28 / 289.51 → 161.95 / 306.94 ms | 40.40 / 40.88 → 22.16 / 59.18 ms |
| Native legacy cold resume | 2.414 s → not used | 1.456 s → not used |
| Independent full-history cold reconstruction | 3.621 → 3.764 s | **44.731 → 47.245 s** |
| Write-stage aggregate CPU seconds | 5.956 → 7.699 | 167.617 → 219.260 |
| Write-stage wall seconds | 5.973 → 7.684 | 167.656 → 219.322 |
| Worker peak RSS | 54,192 → 52,808 KiB | 220,884 → 155,564 KiB |

Cold numbers are explicitly different operations: a fast baseline native resume is not equivalent to independent full-history verification. Financial full reconstruction already exceeds a 30-second job window; integration into existing job deadlines/asynchronous recovery is **not proven**. The reconstructed-log continuation at revisions 3→8 takes 0.870 s, excluding its preceding independent history rebuild.

Write-stage CPU includes PostgreSQL and worker/orchestrator usage under a shared one-CPU quota. Normalized CPU seconds per million **revealed** ticks are XAU **2680.42 → 3464.82**, financial **523803.13 → 685187.62**. These are small-sample ratios, **not million-tick runs or annual runtime forecasts**. The financial fixture intentionally executes 512 durable commands on just 320 ticks, explaining its high ratio. Provider page deliveries are separately recorded and are not mislabeled as processed ticks. Candidate write CPU per command is 0.214 s XAU / 0.428 s financial at these schedules.

Two distinct Sessions' single concurrent TP operation consumes 0.566 aggregate CPU s / 0.560 wall s, or 0.283 CPU s per successful Session operation. Duplicate-command and competing-intent cases consume 0.362 / 0.279 aggregate CPU s. These are contention/recovery probes, not 1/10/50/100-user capacity benchmarks. Peak process RSS is not incremental per-active-user RAM; the whole experiment's capped peak includes PostgreSQL, verifier and workers. Exact currency/user cost still needs billing, utilization, duty cycle, tick/command mix, retention, shared-source amortization, recovery frequency and real concurrency measurements.

## Resource limits and closure

Main run: **590.08 s**, aggregate CPU **588.90 s**, capped peak memory **409,874,432 B**, 148,353,024 B allocated artifacts at report time. Independent-continuation closure uses another 3.13 CPU s with peak 157,884,416 B and finishes at **648.13 s since the original plan**. Scopes enforce `CPUQuota=100%`, `MemoryMax=1 GiB`, swap zero; main timeout 900 s with internal 845 s stop guard; supplement shares the original cumulative artifact/time budget. These scopes run sequentially. New QA cluster/source/logs, WAL, rebuildable scratch, fault and corruption evidence all remain below **512 MiB**. Final exact totals, WAL/TEMP/catalog separation and disk free space are pinned in `closure.json` after repository checks. More than **30 GiB** reserve remains throughout. The private cluster is cleanly stopped, not deleted.

Closure inventory before final Git receipts: **166,289,408 B** retained QA files, including the **158,494,720 B** private cluster (of which **33,554,432 B WAL**, zero retained PostgreSQL TEMP). Remaining files include source fixtures, Session journals/logs, independent reconstructions and reports. Free filesystem space is **59,396,685,824 B**, leaving **27,184,431,104 B above the 30 GiB reserve**. These categories are nested explicitly: do not add cluster WAL again to cluster total, or add per-Session relation totals again to the whole-cluster inventory. Final index/receipt additions may change the exact final allocation slightly; `closure.json` records it.

Reproduction entry points are `python -B -m tests.qa_integrated_checkpoint7` then `python -B -m tests.qa_integrated_recovery7`, from this worktree with `PYTHONPATH=backend`, the existing `/tmp/riksora-vps-candidate-venv/bin/python`, no bytecode writes, and TMPDIR under the private C7 artifact root. Both must run inside the stated one-CPU/1 GiB/zero-swap scopes with 900 s / 150 s outer timeouts; the latter retains the original cumulative deadline. Evidence directories intentionally refuse recreation over retained fixtures. A rerun needs a separately owner-approved fresh QA output root and full preflight; do not rerun over these artifacts or alter source pins/admission to force acceptance.

Repository gates: Python AST parse for all four new modules, `git diff --check`, `test:repository`, `test:ai-bundle`, `ai:bundle`, `ai:bundle:verify` PASS. No application/frontend changes warrant rebuilding the app. No production deployment, migration, service restart, cleanup, new infrastructure or annual replay occurred.

## Decision and single next milestone

**Technical GO applies only to this integrated isolated experiment. Economic direction improves materially for the command-heavy sample; annual ≤500 MB/Session and ≤500 MB/user across Sessions remain NO-GO/unproven.** No extrapolation from 2,222 groups or 512 commands establishes the target. Shared source/QA logs are not hidden in the user quota. Actual retained-host storage is disclosed separately.

Remaining gates: owner-reviewed contract disposition of verified range recovery versus current mandatory per-group logs; production-safe codec/transaction/locking design; full canonical-year serving identity/export and independent parity (the C1 limited derivative is not annual authority); explicit real-source financial admission, which remains NOT_GRANTED; workload policy for the 128-retained-order limit; bounded recovery under actual worker deadlines; long-duration determinism/browser auth/persistence, year-end reconciliation and actual annual/concurrency economics. This checkpoint does not silently grant any of them.

**Recommended single next milestone: owner review and acceptance of a versioned integrated persistence/recovery contract proposal, including the 30-second job-boundary and retained-order policy.** Use these measured bytes/CPU/cold costs to define its bounded validation plan. Do not automatically amend 42.17/42.19, optimize another codec, export the full year, run annual acceptance or deploy. STOP after C7.

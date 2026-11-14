# Claude handoff: continue on the Linux VPS

Branch: `claude/dual-engine-v1-20261114` (common baseline PR #55 head `f941eba`). Read `docs/DUAL_ENGINE_CLAUDE_REPORT.md` first. Owner brief: RIKSORA Dual Engine Challenge V1
(nine precomputed OHLC timeframes in private R2, tick execution on VPS SSD, strict no-lookahead, same acceptance for both engines, no moving of standards).

## Why this move
The product data/worker layer uses POSIX-only calls (`O_NOFOLLOW`, file mode `0o400/0o500`, `geteuid`) and cannot run on the owner's Windows PC. On Linux it runs unchanged.
Target host: 6 vCPU / 16 GiB / 200 GB NVMe + object storage. Keep a safety margin for PostgreSQL, the API and the OS.

## Already done and pushed (do not redo)
- Baseline merge, parity of the Claude jump engine with the reference reducer (fuzz 24/24 plain, 12/12 archive).
- `backend/tools/claude_exp/ohlc/`: independent oracle, streaming nine-timeframe engine (MID per tick, exact int64), object-store port (local SIMULATION + S3/R2 adapter),
  cursor-bound HTTP chart API, 13 golden + 13 service/attack tests, staged benchmark. Result file `docs/benchmarks/CLAUDE_OHLC_EURUSD_2026-05.json`.
- `backend/tools/claude_exp/local_trader/`: prototype trading UI (Free Style/Protocol), 49-check HTTP e2e test. Prototype only, not the product frontend.
- `backend/tools/claude_exp/stack/local_stack.py`: boots the REAL product stack (Postgres, identity API, queue worker, built frontend). Worked on Windows up to login/landing; data and worker could not run there.

## NOT done (this is the work to continue)
1. Bring up the Codex product stack as the baseline on Linux (PostgreSQL 17, Python 3.13, `backend/requirements.lock`, `npm ci && npm run build`). `local_stack.py setup|api|gateway` is a start;
   deploy/vps has the production procedure. Then prove: register/verify (outbox), login, two users cannot see each other, a replay session on a synthetic or locally qualified source.
2. Wire the Claude engine into the product at the narrowest reversible seam (observed session dispatch / chart history), on this branch only, without changing frozen contracts.
   Chart: `AlphaWorkspace` must fetch the selected timeframe from the cursor-bound chart service (512 first page, 500-1000 older pages, 5,000 cap per timeframe incl. D1).
3. Measure on the SAME host and data for both engines: G0..G6 gates, then 1, 2, 5, 10 active traders (20 and 50 only if resource gates pass). Warm and cold. Report median and range.
   Metrics: wall, CPU-s, peak RSS, disk, PG WAL, queue wait, API p50/p95/p99, R2 PUT/GET/LIST. Do not claim capacity without it.
4. Google login and Midtrans: code exists in the repo; they stay disabled until the owner puts real keys in the private config on the VPS. Never ask for or print keys.
5. Real R2: use a test bucket only with credentials the owner injects on the VPS; until then label every result SIMULATION.

## Data (not in Git)
Owner PC: `C:\Users\kuchi\OneDrive\Dokumen\mix data\` (HistData zips, `Hisdata parequet` = compact parquet, `Dukascopy`). Copy what is needed to `/home/developer/data/` with scp/rsync.
Rights for real data are UNKNOWN; the product refuses real sources without pinned rights evidence. Use synthetic fixtures or the owner's local-private path for QA, and say so.

## Rules (from the owner brief)
No force-push, no reset, no merge into main, no copying the other engine's experimental code before both are frozen, no weakening acceptance, no PnL tolerance to hide a financial mismatch.
Report claims as: proven / hypothesis / prototype-only / needs production-like acceptance. Mention what was not measured.

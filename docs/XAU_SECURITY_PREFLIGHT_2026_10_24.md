# VPS security and XAU target preflight — 2026-10-24

This is an operational audit, not architecture authority. PR8 source changes remain separate; no VPS/app service or engine contract was modified.

## VPS reconciliation and rollout boundary

The active static symlink resolves to `/srv/riksora/releases/2fba7560385a-claude-ui`. API runs as `riksora-beta` through `/opt/riksora-beta/venv/bin/python -B /opt/riksora-beta/beta-server.py`, loads source from `/opt/riksora-beta/releases/c370845467608e3d67e74e39b714d501dba7c275`, and binds localhost:8001. Its backend lock SHA256 is `d1158e8ceac7399f87053fdbb413c51d0a59d5924868fe6253bd5db7ade2a220`; it imports certifi2026.7.22. PR8 has a different lock and is not the live release. No release manifest/Git link was found in inspected locations.

Caddy, riksora-beta and PostgreSQL16 were active with zero restarts. The systemd unit has no drop-in. The static updater handles static assets; native demo updater refuses dependency-lock drift. The shell is uid1000 `riksora`; venv and /opt are root-owned, sudo requires authentication, no cached wheel or verified operator restore drill was available. Nothing was written.

Safe plan: establish active source identity and protected root-owned backup/restore; create a side-by-side venv from active lock changing only certifi to2026.10.19; compare package graph, pip check, TLS roots and credential-free public OIDC discovery; verify interpreter-only unit drop-in and rollback with systemd-analyze; capture health/hashes; restart only riksora-beta in an operator-approved window; verify health/login/workspace 401/billing disabled; roll back immediately on failure. Current shell cannot perform privileged steps. Live security remediation remains open; no service readiness claim.

## XAUUSD 2024–2025 source evidence

Read-only comparison used existing numeric/order reports and original HistData monthly GZIP identities. All22 passing originals still matched compressed SHA, bytes, inode and nanosecond mtime. Total22 months:112,657,023 rows and783,291,505 compressed bytes; all are NUMERIC_ORDER_PASS_NOT_ACCEPTANCE with zero invalid rows, reversals, ambiguous timestamp groups or oversized groups. October2024 and October2025 remain gaps/refused.

October2024:5,595,679 rows, reversal at row4,494,120 from 2024-10-28T00:59:58.047Z to 2024-10-28T00:00:00.061Z. October2025:9,259,985 rows, reversal at row7,316,421 from 2025-10-27T00:59:59.951Z to 2025-10-27T00:00:00.087Z. Preserve and refuse; do not sort, drop, stitch or infer fills. rawOrdinalIsTrustedSequence=false. Coverage, freshness, rights and semantic acceptance remain UNKNOWN; no canonical publication/admission. This does not establish two continuous accepted years or executable capacity.

## Isolated parser/private-store probe

Original XAUUSD_2024-01.csv.gz SHA256: `9e6bcfd231494a0730237ecc9826b0e8b158bd3d513ee7255e66fc0c64e974b1`. Existing HistDataIngestion stored an isolated 10,000-row prefix under /tmp. Readback in 256-event pages matched source timestamp/Bid/Ask numeric values for every row; source hash stayed unchanged. An initial 512-row page was rejected by the artifact cap; retry at256 passed. HistDataReplaySource rejected the prefix as a full replay source (REFUSED_PREFIX_AS_FULL_SOURCE). No execution replay or fills were generated.

Source price lexemes have six fractional characters; canonical serialization strips trailing zeroes for all10,000 rows, while Decimal numeric values remain equal. Manifest declares PRESERVE_RAW_TEXT and records source/member/ordinal identity, but canonical tick records cannot reproduce original lexemes. Exact source-scale preservation remains unresolved under frozen authority.

Sample timestamps have three fractional digits, are monotonic, with no equal-time neighbors. All10,000 prices fall off-grid only versus the synthetic XAU fixture tickSize0.01. That synthetic fixture does not establish the real provider grid. Do not round, infer a real grid, or loosen engine checks; financial execution remains refused pending source-backed profile and precision evidence.

## Decisions

GO: bounded read-only source comparison and isolated compatibility probes. Next resolve source-scale/profile evidence and run controller/replay equivalence on complete immutable tick evidence without changing tick rules. Before full import/admission, separately measure storage, peak temporary conversion, RAM, recovery and execution equivalence. Other instruments wait for object storage.

NO-GO: live VPS changes without root/operator restore path, full two-year import/admission, or public release while rights/coverage are unknown. No payment activation. No source sorting/deletion, mass import or service restart.

## Parser provenance and code location follow-up

The actual 10k probe used `HistDataIngestion` from the unmerged candidate branch `codex/columnar-storage-probe-20261024` at ba63f070 (adapter blob cbc2c608). Main's `backend/ticks/provider.py` is explicitly synthetic/test only; the probe does not establish main or VPS runtime behavior.

The candidate parser calls `decimal_text(decimal(value))`, dropping trailing zeros. Its metadata declares `PRESERVE_RAW_TEXT` and retains archive/member hashes, ordinal and original timestamp, so raw price lexemes are recoverable by reopening the matching source archive, not from the canonical event alone. V2 event/provenance fields are frozen. No parser/schema or engine change is safe as an opportunistic fix; resolve through a bounded controller-side sidecar checkpoint and archive/ordinal round-trip evidence. No source change, import or test was performed.


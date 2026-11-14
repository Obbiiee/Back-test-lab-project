# RIKSORA — retention design, monitoring and backup, Git state, security audit (2026-11-15)

Status: **IMPLEMENTATION REGISTER / DESIGN RECOMMENDATIONS, not an architecture authority.** Facts come from commands run on riksora_vps1 without root. Items needing root or an owner decision are marked. No irreversible deletion of financial evidence is performed or proposed here.

## 1. Retention, trash, deletion, export (P1-3)
Implemented and tested (reversible only):
- **Trash/Restore:** `POST .../sessions/{id}/trash|restore`, `GET .../sessions?trashed=true`, table `btl.session_lifecycle` (migration 034). Owner only, tenant isolated, idempotent, 30-day restore window, financial tables untouched. UI: Session overview "Move to Trash", Sessions page "Trash" panel with Restore.
- **Audit trail:** `btl.audit_events` append-only (migration 035): export, trash/restore, refused window claims. No payloads.
- **Data export:** CSV (committed ledger) and PDF (report); JSON journal export already exists in the Journal view.
- **Finished job results:** age-based retention (900 s, cap 4,096).

Design recommendations for owner approval (NOT implemented, nothing deleted):
| Topic | Recommendation | Trade-off |
|---|---|---|
| Permanent purge of a trashed Session | Purge only the user-facing pointers and notes after 30 days; keep the immutable event/receipt rows until the account is erased; evidence tables are protected by `deny_evidence_mutation` triggers on purpose | Keeping receipts costs disk (small) and conflicts with a strict "erase everything" promise unless the privacy text says financial simulation records are retained for integrity for N days |
| Account deletion | Two stages: (1) deactivate and revoke tokens at once, (2) after a 30-day grace, anonymise identity rows (email, name, Google subject) and delete notes/exports; keep anonymised ledger rows only if a legal retention period applies, otherwise delete the workspace in a controlled maintenance job that disables the evidence triggers inside one reviewed migration | Needs a lawyer's view of Indonesian data-protection duties and the owner's promise; the trigger bypass is an irreversible operation and needs separate approval |
| Data export for the user | Self-service ZIP of CSV + JSON + PDF per Session and a profile JSON, generated on demand, never stored longer than 24 h | Cheap; reuses existing exports |
| Temporary export files | None are written to disk today (streamed from memory, bounded to 50,000 orders); keep it so | A ZIP of many sessions would need a temp dir with a 24 h sweep |
| Backup retention | 7 daily + 4 weekly + 6 monthly encrypted copies; WAL 7 days. A deleted user's data leaves backups after the oldest copy expires (state this in the privacy text) | Longer retention = larger cost and longer erasure latency |
| Terms/Privacy | Pages need a legal author; placeholders must not be shipped as final | OWNER DECISION REQUIRED |

## 2. Monitoring (P1-4)
Audit of what exists: queue depth/latency metrics are stored per job (migrations 019/020), QA-only per-role CPU accounting exists in the test harness, PostgreSQL logs are local. There is no persistent metrics view and no alerting.
Recommendation (lightest that covers the list): **no monitoring platform.** One script run every minute by cron or a systemd user timer, plus a push or mail on non-zero exit.
- Implemented: `backend/tools/ops_metrics.py` (tests `backend/tests/test_ops_metrics.py`) prints one JSON line with host memory/swap/load/disk, PostgreSQL reachability, queue depth, oldest queued wait, failed jobs in the last hour, connections, database size, backup marker age; exit 0 OK / 1 WARN / 2 CRIT. Thresholds are in the file; it never prints a DSN or tenant data.
- Covered by it: CPU (load per CPU), RAM, disk, PostgreSQL, queue depth, job failure, backup status. Not covered: API latency percentiles (needs access-log parsing by the reverse proxy once one exists), per-worker crash events (visible as RECONCILE_REQUIRED/FAILED job counts), export job failures (exports are synchronous; failures are audit rows with outcome REFUSED and 5xx in the proxy log).
- Alert path: cron `MAILTO` or a small curl to a push service; the owner chooses the channel (needs a credential, never in Git).

## 3. Backup (P1-4)
Proven (disposable PostgreSQL 17, `docs/benchmarks/ops-drills/`): base backup + WAL archive with point-in-time restore (706 MB test database restored in 11.9 s, exact target recovery), `pg_dump -Fc` 5.4 s / `pg_restore -j 4` 5.2 s. WAL archive timeout 60 s gives an RPO of about one minute locally.
Gap: backups are on the same VPS. Recommended architecture: **encrypted push to a provider that is not the VPS**, any S3-compatible bucket or an SFTP storage box; R2 is allowed but not required. Use `age` or restic encryption with a key kept off the VPS; the VPS holds only a write-only credential; a weekly automated restore test on a disposable instance; the backup marker file written only after a verified restore of the newest copy feeds `ops_metrics.py`.
Not run: any upload to a remote provider (no credentials exist or were requested). The local restore drill is the evidence.

## 4. Git state (P1-5)
- Branch `claude/dual-engine-v1-20261114`; `git status` clean at the time of writing; local branch is 0 behind and 44 ahead of `origin/claude/dual-engine-v1-20261114` (no one else wrote to it). `git fetch` works (public read); `git push --dry-run` fails with "could not read Username": there is no credential on the VPS, by design.
- Nothing was reset, rebased, force-pushed or deleted. Commits are grouped by concern (retention, chart route, export, entitlements, window guard, PDF, ops, grants, docs).
- Unblock: the owner creates a fine-grained token limited to this repository (contents: write) and places it in a 0600 file on the VPS, or pushes from the laptop with `git fetch <vps-path> claude/dual-engine-v1-20261114`. Then run CI on the pushed SHA. **Remote CI has NOT run; no remote CI PASS is claimed.**

## 5. Security configuration audit (P1-6, read-only, no root)
| Item | Finding | Recommendation |
|---|---|---|
| SSH root login | `sshd_config` says `PermitRootLogin yes`, but `sshd_config.d/01-riksora-hardening.conf` says `no` and is read first (OpenSSH uses the first value). Effective value cannot be proven without `sshd -T` (root) | OWNER: run `sudo sshd -T | grep -E 'permitrootlogin|passwordauthentication'`; delete the `yes` line afterwards |
| Password / keyboard auth | `PasswordAuthentication no`, `KbdInteractiveAuthentication no`, `PubkeyAuthentication yes` (hardening file and main file agree); one authorized key, file mode 0600, `~/.ssh` 0700 | keep; test a second admin key before any further change |
| `50-cloud-init.conf` | unreadable without root | OWNER: confirm it does not re-enable password login |
| X11 forwarding | `yes` in the main config | set `X11Forwarding no` |
| Firewall | `ufw` service active, `/etc/default/ufw` default input policy DROP, IPv6 on; rules not readable without root | OWNER: `sudo ufw status verbose`; expect only 22 (and 80/443 when the site is served) |
| Intrusion tools | `fail2ban` inactive | OWNER: enable fail2ban for sshd (key-only already limits the risk) |
| Listening ports | public: 22 only. Loopback only: PostgreSQL 54329 and 54411 (QA), QA API 8001, local tooling | keep; the QA API and clusters must not be exposed |
| PostgreSQL | QA clusters bind 127.0.0.1 and use `trust` in `pg_hba.conf` (acceptable only for these disposable QA clusters); the product runs through restricted roles with explicit GRANTs (a missing grant was caught by the browser gate and fixed) | production cluster: scram-sha-256, roles `btl_app` (no owner membership), separate billing role, no `trust` |
| Service users | app, workers and databases run as the unprivileged user `developer` (uid 1000), none as root; `developer` is in the `sudo` group (password required) | production: dedicated service users, systemd sandboxing, no sudo membership |
| Dataset ownership | `~/data` mode 700; subdirectories group-writable (775) | tighten to 750/700 for the service user only |
| Secrets | no credential files found in the project tree or home (only an agent session key outside the repo); no Git credential helper; several token-like environment variables belong to the user's tooling | keep secrets in 0600 files outside Git; never in chat |
| Reverse proxy / TLS | none present yet (QA only) | required before any public use: TLS, HSTS, request size limits, rate limits aligned with the 30/10/600 policy, trusted-proxy configuration for Uvicorn |
Nothing was changed on the host. No SSH or firewall change is proposed without a separate approval and a tested alternative admin path.

# RIKSORA VPS — operations and security checklist (W8), 2026-11-14

Status: **CHECKLIST + MEASURED STATE, not an architecture authority.** Executed by Claude on riksora_vps1 without root (no sudo), read-only unless stated. Items that need root are marked UNVERIFIED and are listed for the owner.

## 1. Host
| Item | State | Evidence / note |
|---|---|---|
| Spec | 6 vCPU AMD EPYC, 15.6 GiB RAM, no swap, 197 GB disk (about 9% used), Ubuntu 24.04.5, kernel 6.8.0-146 | `lscpu`, `free`, `df` |
| Toolchain | user-space Python 3.13.18, PostgreSQL 17.12 (micromamba), Node 22.23.5, NumPy 2.5.4, PyArrow 26.0.0 | no sudo needed |
| Reboot flag | none | `/var/run/reboot-required` absent |
| Uptime | 6+ days | boot 2026-11-07 |

## 2. Network and access
| Item | State | Action |
|---|---|---|
| Externally listening ports | only SSH 22 (IPv4 and IPv6); PostgreSQL 54329 and QA APIs bind to 127.0.0.1 | none |
| SSH authentication | password and keyboard-interactive disabled, public key only; one authorized key; all logins in the last days from one address | none |
| Root login | **CONFLICTING settings found** (`PermitRootLogin no` in one file and `yes` in another); the effective value needs `sshd -T` (root) | OWNER: run `sudo sshd -T | grep -i permitroot` and keep only `no` |
| X11 forwarding | enabled | OWNER: disable (`X11Forwarding no`), not needed |
| Firewall (ufw/iptables/nft) | **UNVERIFIED**: needs root | OWNER: confirm default-deny inbound except 22 (and 80/443 when the site is served) |
| Failed SSH attempts | journal not readable without root | OWNER: check `journalctl -u ssh` / fail2ban |

## 3. Data and secrets
| Item | State | Action |
|---|---|---|
| Market data location | `~/data` (real EURUSD, rights UNKNOWN: private QA only), now mode 700 (was 775) | done |
| Secrets in Git | none found in added lines or tracked files; raw market data not tracked; QA evidence folders are git-ignored | none |
| Credentials on the VPS | no Git credential helper (push is impossible by design); no R2 or payment keys present | OWNER injects GitHub and R2 credentials in a 0600 file, never through chat |
| Environment tokens | several `*TOKEN` variables exist in the environments of the user's tool processes (names only inspected, values never printed) | keep out of logs and artifacts |
| Backups of market data | sources live on the owner's laptop; derived data is reproducible | keep the laptop source as the original |

## 4. Database backup and restore (W6 drill, PostgreSQL 17, QA cluster)
Executed with `docs/benchmarks/ops-drills/pg_backup_restore_drill.sh`, result in `docs/benchmarks/ops-drills/pg_backup_restore_drill_result_2026-11-14.log`.
- WAL archiving on (`archive_mode=on`, `archive_timeout=60s`): shipping delay bound of 60 s, so RPO of about 1 minute for a locally archived WAL (a copy to R2 was NOT tested).
- Physical base backup (tar+gzip, streamed WAL) of a 706 MB test database: 16.0 s.
- **Point-in-time restore proven:** restoring the base backup plus archived WAL to a target time recovered the 700,000 baseline rows and the 1,000 rows written before the target, and none of the 1,000 rows written after it. Restore plus recovery took 11.9 s for this size.
- Logical `pg_dump -Fc`: 5.4 s; `pg_restore -j 4`: 5.2 s, 702,000 rows.
- Limits: the test data compresses unusually well; the restore time per GB for real data is not established; off-box copy to R2 and a restore from R2 are NOT tested; `pg_verifybackup` does not verify tar-format backups in PostgreSQL 17 (a plain-format backup is needed for it). The drill left no data behind (databases dropped, archive disabled again, backup directories removed).

## 5. Operational rules
1. One measurement at a time on the VPS. Before a measurement: `ps`, `who`, `uptime`; if another session is running, wait. A concurrent session touched files and started runs during this work; nothing of it was changed or stopped.
2. Test harness hygiene: QA processes must die with their parent (fixed for the extra API instance); leftover QA processes and databases created by Claude were removed (5 orphan API processes, 3 queue-QA databases, drill databases).
3. Observability today exists only in the QA harness (per-role CPU, queue depth, latency percentiles). **Missing for beta:** a persistent metrics view (queue depth, p95/p99, PostgreSQL WAL and bloat, CPU per role) and alerting.
4. Cleanup candidates needing the owner's OK: `~/tools/pgdata` QA cluster and the old `local_stack.py` API on 8001 from the first bring-up; `frontend/tests/artifacts` (about 77 MB, 281 evidence folders, git-ignored).

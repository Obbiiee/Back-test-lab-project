# RIKSORA — go-live plan: from current source to a live website with Google login and a payment gateway (2026-11-15)

Status: **PLAN / implementation register, not an architecture authority.** Written from the actual source (`deploy/vps/*`, `cloud/*`, `identity/google.py`, `cloud/midtrans.py`, `cloud/doku.py`, `frontend/`) and the measured state on riksora_vps1. Nothing here is executed yet. Commercial V1 verdict stays **BLOCKED** until every gate in section 6 is met.
Labels: **ME** = I can do it on this VPS without new authority; **OWNER** = only the owner can do it (account, money, DNS, root, legal); **BOTH** = needs an owner input, then I execute.

## 0. Facts that shape the plan
- The shipped deployment package (`deploy/vps/compose.yaml`, `Caddyfile`) needs **Docker + Compose, root, ports 80/443 and a domain**. This VPS has **no Docker, no sudo**, only port 22 open. So either (a) the owner installs Docker/Caddy and opens 80/443 (root step), or (b) I build a **user-space deployment** (systemd --user units, Caddy binary with `setcap` or a root-owned port forward). (b) still needs one root action for ports 80/443.
- Domain and DNS: none configured (**OWNER**). Staging config explicitly forbids `riksora.com` until the owner decides.
- Google login is already coded (`BTL_GOOGLE_CLIENT_ID/SECRET/REDIRECT_URI`, disabled when blank). Midtrans is coded (`cloud/midtrans.py`, `cloud/billing.py`, sandbox); DOKU is design plus tested pure code only.
- Capacity so far (synthetic, same-host, V2 opt-in): 20 staggered and 8 simultaneous 262,144-tick Sessions pass; Journal/export 10-16 s under load is the open UX defect. No external-generator or HTTPS-path measurement yet.
- Backups exist only on the same disk; no offsite, no `fail2ban`, 64 pending OS updates, firewall status unverified (needs root).

## 1. Phase A — decisions the owner must make (blocks everything below)
| # | Decision | Why it blocks |
|---|---|---|
| A1 | **Data rights**: which licensed tick/OHLC source may be sold (current data is rights UNKNOWN = private QA only) | Without it nothing can be sold |
| A2 | **Instrument list and profiles** (16 pairs need contract size, lot rules, pip, USD conversion; none invented) | Product scope and accuracy |
| A3 | **Domain name** and who controls DNS | TLS, Google redirect URI, payment webhook URL |
| A4 | **Payment provider**: Midtrans (coded) or DOKU (design only), merchant account and sandbox keys | Payment integration |
| A5 | **Plans and prices** (Free/Pro, currency, trial/refund/cancel rules) | Billing logic and legal text |
| A6 | **Promote V2 checkpoint** to the production path (delta proposal in `RIKSORA-COMPACT-CHECKPOINT-V2-20261115.md` section 5) and **UX SLO** for Journal/export | Long Sessions and latency |
| A7 | **Root actions**: open 80/443, Docker or Caddy install, `fail2ban`, OS updates, firewall | Public access and hardening |
| A8 | **Offsite backup target** (R2 for user data only, per 2026-11-14 decision) with credentials in a 0600 file | Disaster recovery |
| A9 | **Legal**: terms of service, privacy policy, risk disclaimer ("simulation, not advice"), data-source attribution | Required before taking payment |

## 2. Phase B — platform and security hardening (VPS)
1. **BOTH** Root steps: OS updates, `fail2ban`, firewall allow 22/80/443 only, confirm no public 5432/8001. (A7)
2. **ME** Replace the scratch PostgreSQL in `/tmp` with a persistent PostgreSQL 17 cluster (own data dir, `pg_hba` local only, separate owner and runtime roles `btl_owner` / `btl_app` with no privileges, as `deploy/vps/README.md` requires); run the explicit operator migration/grant step, never at API start.
3. **ME** Secrets in `/etc`-style private dir or `~/secrets` mode 0600 outside Git (db password, `runtime.json`, `owner.json`, Google secret, Midtrans server key, SMTP). Verify none in Git history.
4. **BOTH** TLS reverse proxy: Caddy serving the built `frontend/dist` and proxying only `/api/v1/*` to the API on 127.0.0.1:8001 (real client-IP rate limiting; unknown-host refusal; HTTP redirect). If Docker is not wanted: user-space Caddy + systemd user units; one root step for 80/443.
5. **ME** systemd units with resource slices: API, native workers (3 recommended product setting, max 4), PostgreSQL, proxy; budget 5 vCPU / 14 GiB, `MemoryMax`, `CPUQuota`, restart policies; unit for the retention/cleanup job.
6. **ME** SMTP (real TLS sender) for verification/recovery mail. **OWNER** supplies the SMTP account (A3).

## 3. Phase C — Google login (BOTH)
1. **OWNER** Google Cloud Console: create OAuth consent screen (app name, domain, privacy URL, support email) and an OAuth 2.0 Web client. Authorized redirect URI exactly `https://<domain>/api/v1/auth/google/callback` (route confirmed in `identity/google.py`). Publish the consent screen to production (basic scopes `openid email profile` need no verification review).
2. **OWNER** Put client id and secret into the private runtime file (not in chat or Git): `BTL_GOOGLE_CLIENT_ID`, `BTL_GOOGLE_CLIENT_SECRET`, `BTL_GOOGLE_REDIRECT_URI`.
3. **ME** Wire config, run the existing staging helper (`deploy/vps/google_staging.py`) and tests; real-browser E2E: sign in, account linking (`CP6A-10-account-linking-contract-decision`), logout, token expiry (1,800 s), cross-account isolation, same email via password and Google.
4. Exit gate: Google sign-in works on the real domain from a clean browser, with 2 accounts, desktop and mobile.

## 4. Phase D — payment gateway (BOTH)
1. **OWNER** Merchant account and **sandbox** keys; decision A4; stored in a 0600 file (never in chat/Git).
2. **ME** Midtrans path (already coded): create Snap transaction server-side, verify notification **signature** (SHA512 of order_id+status+gross_amount+server key), idempotent handler using `payment_provider.next_state` (duplicate ignored; late PAID after EXPIRED goes to HOLD for manual reconciliation), activation of Pro entitlement only from a verified server-side event, never from the browser redirect.
3. **ME** If DOKU is chosen: finish `cloud/doku.py` against the DOKU sandbox and settle the open points listed in `RIKSORA-PAYMENT-PROVIDER-20261115.md` (digest bytes, checkout path, timestamp tolerance).
4. **BOTH** Public HTTPS notification URL (needs domain + proxy from Phase B); webhook allow-listing if the provider publishes IPs.
5. **ME** Sandbox end-to-end: pay, fail, expire, duplicate notification, out-of-order notification, refund/cancel path, downgrade at period end, Free-window and monthly-quota rules unchanged, audit trail (`cloud/audit.py`), no card data stored.
6. **OWNER** Provider go-live review (KYC/business verification, settlement account) and the switch from sandbox to production keys. **No real payment is made by me.**
7. Exit gate: a sandbox payment upgrades exactly one account to Pro exactly once, and the receipt/entitlement survive a worker restart.

## 5. Phase E — product readiness gates (ME unless stated)
| Gate | Work | Evidence |
|---|---|---|
| Latency | Fix Journal/export cold read (A6 permission), set SLO | p95 per SLO on HTTPS path |
| Capacity | Isolated benchmark MINI/MEDIUM/FULL, 10 personas, loopback TLS, same-host affinity-isolated (owner chose no VPS2) | `RIKSORA-RESOURCE-ISOLATED-CAPACITY-REPORT.md`, labels MEASURED / ESTIMATED / UNPROVEN |
| Sellable limit | Conservative capacity = core-seconds budget x safety factor / per-persona cost; product caps (active Sessions per account, max Session length, export quota, admission 16/2 unchanged) | capacity table + caps in code |
| Browser | Real-browser E2E desktop+mobile, Free/Pro with enforcement ON, 2 accounts | Playwright run |
| Instruments | Add only profiles with real metadata; keep SKU range 2023-01..2025-10 | matrix updated |
| Security | Read-only security audit, dependency licence/CVE check (PDF export libs), rate limits 30/10/600, cookie/header review, backup restore drill | audit report |
| Ops | Monitoring + alerts (disk, MemAvailable, queue age, failed jobs, cert expiry), encrypted offsite backup with restore drill, runbook and rollback | restore drill log |
| CI | Push credential from owner, remote CI green on the release commit | CI run link |

## 6. Phase F — release sequence
1. Staging on the real domain with `Caddyfile.staging` (basic auth) using sandbox Google and sandbox payment; run all Phase E gates there.
2. Freeze: tag the release commit, create verified Git bundle + SHA-256, offsite copy, record image/dependency pins.
3. **OWNER** go/no-go review against this checklist: A1-A9 done; C and D exit gates passed; Phase E gates passed; legal pages live; data-source attribution live.
4. Production cutover: switch keys (Google already production; payment live keys), remove staging basic auth, DNS to the VPS, smoke tests (signup, verify email, Google login, sandbox-then-live payment with the owner's own small real transaction, Session create and Jump, Journal, export, logout), enable alerts.
5. Soft launch with a small invited cohort and a hard per-account cap; watch queue age, SERVICE_BUSY rate, p95 latency, error budget for 7 days; widen only if inside SLO.
6. Rollback: previous release tag, DB backup taken immediately before migration, maintenance page, payment provider webhooks idempotent so replays are safe.

## 7. What I can start immediately (no owner input needed)
1. Persistent PostgreSQL + operator migration on this VPS and the systemd slices (Phase B2, B5).
2. HTTPS harness and isolated capacity benchmark on this VPS (Phase E, same-host, labelled as such).
3. Journal/export optimisation once A6 is approved; per-tick CPU optimisation (reducer untouched).
4. Midtrans sandbox flow tests with mocked provider responses until sandbox keys exist; DOKU adapter finish after A4.
5. Security read-only audit, restore drill, monitoring units, runbook, legal-page placeholders for the owner's lawyer to fill.

## 8. Risks to keep honest
- Selling market data without licensed rights is the largest legal and commercial risk (A1).
- Single node, no HA: a VPS failure means downtime; offsite backup limits data loss only.
- Same-host benchmarks are not network-realistic; capacity beyond measured cohorts is UNPROVEN.
- Real-money payments need the provider's approval and the owner's accounts; I cannot and will not execute them.

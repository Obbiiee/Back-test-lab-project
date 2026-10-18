# VPS staging candidate — not sales acceptance

This is the operator procedure for the existing system blueprint's VPS preparation contract. It does not introduce architecture authority. No VPS, domain, actual Google/SMTP/merchant credentials, approved historical month or container runtime acceptance is supplied. Existing financial/causal contracts and pending Claude UI remain preserved.

## What is packaged

Caddy serves the built static app and proxies only `/api/v1/*` to an API listening on127.0.0.1:8001 inside the shared gateway network namespace. Only80/443 are published. PostgreSQL17 has a separate internal network and persistent volume; no database port is published. API is non-root/read-only, has no owner credentials and accepts forwarded headers only from127.0.0.1. Caddy overwrites forwarded scheme/IP and disables its admin API. Uvicorn access logs are disabled to avoid recording Google authorization codes. Do not place another proxy/CDN in front without reviewing the trust chain; real client-IP and HTTPS enforcement must be tested on the host.

The build/archive excludes local public market/history files, raw source CSVs/archives/stores, credentials, dependencies and QA seeds. Frontend here is the existing engineering baseline, not an accepted integration of pending Claude UI. The image must not be sold or opened as complete Beta yet; legacy v1 is not commercially quota-certified and v2/Google browser cutover is outstanding. Sandbox Pro is simulated; no checkout or actual funds flow exists.

## Prerequisites and private configuration

1. A Linux host with Docker Engine/ComposeV2 and owned domain resolving to it; allow SSH only for intended operators and80/443 for HTTPS. These host changes are not performed by this package. Resource caps in compose are initial test budgets, not measured capacity, minimum hosting guarantees or purchase advice.
2. Pin official Python3.13, Node22.12+, Caddy2 and PostgreSQL17 images by immutable `@sha256:` digest. Set the four image references in a private copy of `.env.example`. Do not substitute a fake/example digest. No automatic PostgreSQL major upgrade. An image pull, build, vulnerability check and restart/restore drill on the chosen host are mandatory unpassed gates.
3. Create a private directory such as `/etc/backtest-lab`, accessible only to root/operators. Keep it outside the checkout/build context. Populate `db_password`, `runtime.json` and `owner.json` from the examples using private editors/secret tooling, never chat, Git or command-line passwords. Owner DB password must match `db_password`; runtime DB password must differ. API auth secret must be high entropy (at least48 random bytes), not a sample string.
4. File-backed Compose secrets use bind mounts; uid/gid/mode remapping must not be assumed. The host parent directory must protect the files. The explicitly mounted files must be readable by UID10001 for API/operator, and the postgres image's initialization user for `db_password`. One workable single-host arrangement is operator-only0700 parent and0444 files mounted individually; verify actual access on Linux. Docker/root operators remain trusted. Never mount the directory wholesale.
5. Configure real TLS SMTP and sender identity; verification/recovery sends expiring tokens, not fake success. Set the opt-in sandbox reset explicitly toUTC. Google stays blank/disabled until the owned client ID/secret and exact `https://DOMAIN/api/v1/auth/google/callback` are registered. API may not receive sandbox-event signing or owner/migration credentials.

From checkout root with the project Python dependencies installed:

```sh
python deploy/vps/preflight.py --env-file /private/vps.env
```

Only configuration shape is checked. No database, DNS ownership, TLS certificate, email delivery, payment, data rights or release acceptance is certified.

## Explicit first deployment on the chosen host

Use the private environment file for every command. Do not print rendered Compose configuration containing private values to shared logs.

```sh
docker compose --env-file /private/vps.env -f deploy/vps/compose.yaml config --quiet
docker compose --env-file /private/vps.env -f deploy/vps/compose.yaml build
docker compose --env-file /private/vps.env -f deploy/vps/compose.yaml up -d db
docker compose --env-file /private/vps.env -f deploy/vps/compose.yaml exec db psql -U btl_owner -d btl
```

Inside the private psql terminal, create only the runtime login (no privileges/role membership), then set its password interactively and place the matching DSN privately in runtime.json:

```sql
CREATE ROLE btl_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
\password btl_app
\q
```

Do not rerun CREATE ROLE blindly on an existing database. Inspect its actual role/ownership first. Existing users/data must be preserved.

```sh
docker compose --env-file /private/vps.env -f deploy/vps/compose.yaml --profile ops run --rm operator
docker compose --env-file /private/vps.env -f deploy/vps/compose.yaml up -d gateway api
docker compose --env-file /private/vps.env -f deploy/vps/compose.yaml ps
```

Migration/grant is explicit, never API startup. API refuses privileged/runtime-owner membership, table/schema ownership, missing schema USAGE and mismatched migration checksums. Operator grants preserve existing v1 routes and additive v2/Google state; API cannot INSERT sandbox test events. Application data is stored in PostgreSQL. The volume/certificate state must survive recreation; do not run `down -v` against application state.

Validate externally: correct HTTPS hostname and redirect, unknown host refusal, no public5432/8001/admin port, real client-IP rate limiting, HTTP account refusal, signup/verify/login/logout, cross-user isolation, actual Google consent and callback, v2 reviewed orders and journal, expiry/quota/trash, and unavailable configuration states. ASGI/unit tests are not these browser/network checks. No `/api` proxy retries should be enabled for uncertain financial writes.

## Backup, upgrade and rollback

Before a change, enter maintenance and stop new admission; retain exact previous image digests, release manifest, configuration versions and an encrypted/off-host backup. From the private operator terminal, use the database image's matching native tools (no passwords on CLI):

```sh
docker compose --env-file /private/vps.env -f deploy/vps/compose.yaml exec -T db pg_dump -U btl_owner -d btl --no-owner --no-acl --format=custom > /private/btl-before-change.dump
sha256sum /private/btl-before-change.dump
```

Check the exit status and nonempty artifact. The matching client/server major is required. A backup is not proven until restored into a separate empty QA target and receipt/user/access/ledger evidence is verified. Do not overwrite a live DB to test recovery. Reapply explicit grants after a restore because backups omit ACLs. Retention/encryption/off-host destination and actual RPO/RTO measurement still need an operator policy; do not invent acceptance numbers.

For an upgrade, build/pin the new release, perform the explicit migration step, then recreate gateway and API together because the API shares gateway's network namespace. Never silently restart old images against incompatible schema. If readiness/receipt integrity fails, stop admission and diagnose; rollback requires the previous compatible image/schema/config/backup, not automatic destructive restore. No automated rollback is shipped.

## Reproducible upload archive

From a clean backend checkout after committing/pushing:

```sh
python deploy/vps/package.py --output /private/backtest-lab-vps-candidate.zip
```

The archive reads selected committed Git blobs (not a mutable working-file snapshot) and includes source, Docker/config examples and licenses only, with `RELEASE_MANIFEST.json` mapping each file to SHA256 and the source commit. Files have0644 archive permissions. Existing output is never overwritten. Verify the archive SHA256 and per-file hashes after transfer. Install dependencies/build images on the host; no container binaries, private data or real credentials are included. The package's marker explicitly says untested-container staging candidate, not sales acceptance.

## Required acceptance before selling

Keep existing rights/source completeness and canonical tick eligibility, UI/v2-only commercial quota, real Google/email/payment/refund/reconciliation, backup/restore, resource/reference capacity, telemetry/support and existing cohort/GO-HOLD gates. A static package test, working HTTPS page or sample payment is not final paid-Beta certification. No automatic public enrollment or live charges are enabled here.

## Primary references inspected2026-10-18

- https://docs.docker.com/compose/how-tos/use-secrets/
- https://docs.docker.com/compose/how-tos/startup-order/
- https://caddyserver.com/docs/caddyfile/directives/reverse_proxy

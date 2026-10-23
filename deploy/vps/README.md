# VPS staging candidate — not sales acceptance

This is the operator procedure for the existing system blueprint's VPS preparation contract. It does not introduce architecture authority. No VPS, domain, actual Google/SMTP/merchant credentials, approved historical month or container runtime acceptance is supplied. Existing financial/causal contracts remain preserved. The handed-over Claude UI is now included in the integration candidate; the UI entrypoint and provider/data/host gates still require acceptance.

## What is packaged

Caddy serves the built static app and proxies only `/api/v1/*` to an API listening on127.0.0.1:8001 inside the shared gateway network namespace. Only80/443 are published. PostgreSQL17 has a separate internal network and persistent volume; no database port is published. API is non-root/read-only, has no owner credentials and accepts forwarded headers only from127.0.0.1. Caddy overwrites forwarded scheme/IP and disables its admin API. Uvicorn access logs are disabled to avoid recording Google authorization codes. Do not place another proxy/CDN in front without reviewing the trust chain; real client-IP and HTTPS enforcement must be tested on the host.

The build/archive excludes local public market/history files, raw source CSVs/archives/stores, credentials, dependencies and QA seeds. Frontend includes the handed-over RIKSORA Playful UI. The tested main-branch HTTPS QA journey uses the existing v1 synthetic account flow; it does not certify the integrated v2/multipair/Google/payment UI. The image must not be sold or opened as complete Beta yet; legacy v1 is not commercially quota-certified and v2/Google browser cutover is outstanding. Sandbox Pro is simulated; no checkout or actual funds flow exists.

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


## Candidate entrypoints and remaining product gates

Before launch, verify that the actual HTTPS domain opens the public landing and its main CTA reaches verified account access. The current private HTTP loopback root is not a production entrypoint. The human explicitly approved the four-file routing correction after automatic review initially rejected it. HTTPS/default public entry now uses the landing and its CTA enters account access. Private HTTP loopback retains its separate local source. Real-domain browser/host acceptance still remains required; no TLS weakening.

Main62471fa's generated-account HTTPS browser QA reached10000→9997USD with one completed0.1lot Buy, exact Ask2006.05→Bid2005.75,−3USD, then retained the same results after logout/login and reload. It used a fresh isolated PostgreSQL and authored fixture, not a merchant/provider/historical-month claim. This is an engineering reference for host acceptance, not a substitute for running it against the final integrated image.

Unpopulated real datasets must fail clearly; do not copy private QA clusters, credentials, local QA CA/key, synthetic account state or raw market folders into the VPS. Provisioning data later also requires its provenance, license, coverage and causal chart/execution checks. Payment order/webhook/durable Pro composition, operator-owned provider secrets, commercial quotas, container and Linux recovery/capacity, and launch acceptance are still independent prerequisites. This package cannot honestly be described as requiring data alone.

Beta UI entry: `https://YOUR_DOMAIN/?page=beta` uses the configured v2 sandbox (UTC reset). Previous v1 Sessions remain at `/?page=account`. The Beta link is also available on the landing page. It does not enable real checkout, Google consent or licensed data. Backend runtime is unchanged; actual container/host acceptance remains required.


## Optional sandbox billing configuration (2026-10-20)

Billing remains off when its configuration is absent. After creating a restricted LOGIN role `btl_billing` (no superuser, schema ownership, owner/app role membership or inherited broad grants), add `"BTL_ENABLE_SANDBOX_BILLING":"true"` to the private owner config and run the existing explicit migration operator. It grants only provider-ledger writes to the worker and ledger SELECT to `btl_app`; the API role cannot insert billing events. Never put owner credentials or the sandbox HMAC event-signing secret into runtime config.

Add all six keys to the private runtime JSON together: `BTL_BILLING_DATABASE_URL` (same db/btl database, user btl_billing), `BTL_MIDTRANS_SERVER_KEY` (SB-Mid-server sandbox key), `BTL_MIDTRANS_MERCHANT_ID`, `BTL_BILLING_PLAN_VERSION`, `BTL_BILLING_AMOUNT_IDR` (whole rupiah integer string), `BTL_BILLING_DURATION_SECONDS` (integer string,1..366 days). The price and duration are operator decisions; no QA offer is a retail default. Keep UTC reset. Partial configuration, production keys, app/owner DSNs and malformed offer values refuse. Existing file-mounted runtime secret remains the only input; no secrets in build args, browser bundle or shell arguments.

The Beta account page shows server access, saved payments, checkout, explicit reconciliation and safe resume only for CREATED orders. A lost checkout response is recovered by server order/request lookup; CHECKOUT_STARTED/PENDING/HOLD blocks new UI checkout until reconciled. The returned sandbox hosted URL is validated before rendering a separate-tab link. Signing a notification never authenticates its unsigned success status; the server independently fetches provider status. Expiry/refund may change eligibility; browser time or return URL never grants Pro. Saved order listing is bounded to50 and discloses truncation. Existing orders pin merchant and offer across restarts.

Configure the provider notification destination to `https://YOUR_DOMAIN/api/v1/billing/sandbox/notification`. Real provider/account/card/HTTPS acceptance is still required after operator credentials exist. QA uses authored MockTransport only; no real card is charged. Docker/Linux/SMTP/Google/domain/capacity/data and final launch gates remain separate. Existing backup/restore commands must be exercised and scheduled on the actual host with protected backup storage; this Windows QA does not install a VPS scheduler.


## Read-only audit of the separately installed native staging

The Ubuntu PostgreSQL16 /opt/riksora-beta installation is distinct from the Compose/PostgreSQL17 candidate above. Do not rerun the old native installer or assume package/restore acceptance. After reviewing this source, an operator may run it with the installed Python environment:

```sh
sudo /opt/riksora-beta/venv/bin/python -B /path/to/reviewed/repository/deploy/vps/audit_native.py
```

This performs only file metadata, local database SELECTs in read-only transactions, and pg_restore --list of the latest private dump. Output excludes credentials, subjects and identifiers. No migrations, grants, service operations, restoration or writes occur. A valid dump hash/catalog is not an actual restore drill; a verified Google binding is not an application OWNER grant. Keep actual provider/browser, permissions and restore acceptance separate.


## Opt-in Google/workspace metadata candidate

`google_staging.create_google_staging_app(dsn, auth_secret, workspace_metadata=True, google_client_id=..., google_client_secret=..., google_redirect_uri=...)` uses canonical identity and only workspace create/list/get. Omit opt-in to keep workspace routes absent. It starts no background research worker. Newer FastAPI lazy included routers are filtered at their child paths so canonical logout remains available; the older standalone Google-only wrapper can omit logout under that runtime. Do not equate local token clearing with verified server revocation. No migration or grant runs on factory startup.

The separate operator function `grant_workspace_metadata(operator_dsn)` adds SELECT/INSERT on workspaces/memberships plus immutable key UPDATE locks only. It refuses a privileged/owner runtime role or a runtime operator connection; it grants no resource/research/member-delete/financial/admin privilege. Existing identity grants are prerequisite. Stage and inspect backup, existing ACL snapshot and role ownership before calling it on a live database. Do not run tests against live or rerun the old installer.

`frontend/staging/workspace.html` is a separate build entry using the existing memory-only verified client. It lists/creates/selects saved workspace metadata, blocks uncertain create retries until list refresh, and labels trading/data/statistics unavailable. No Claude-owned presentation file is modified. Run ordinary frontend build then `npx vite build --config staging/vite.config.js`. The output under dist/workspace is an isolated candidate; it must be packaged with existing landing/assets preserved, login HTML at /login/index.html and only exact workspace routes added to the private Caddy allowlist. Do not expose broad /api/* or dev server.

Live cutover requires an authenticated operator: first perform reviewed read-only audit, actual backup/restore rehearsal and record current release/API/config/ACL snapshots; validate candidate Caddy before replacing active config; use new immutable release and API paths; reload only Caddy/restart only RIKSORA API; verify identity/logout/workspace and rollback on failure. Rollback restores previous static pointer, API entry and validated Caddy config; preserve new workspaces and backups, never drop the database. Extra metadata ACLs need a separately reviewed restoration of the exact pre-change ACL snapshot, not blanket revocation. This source checkpoint is not an executable deployment script or live acceptance.


## Reproducible private functional gate

Run `python -B deploy/vps/tests/run_private_pg.py --group functional` as an ordinary user with the existing repository Python environment. No external DSN, system services, sudo, provider credentials or actual customer records are used. It creates a unique private UTF8 PostgreSQL16 cluster with TCP disabled, executes the sixteen-instrument authored Google journey and verified-email/recovery gate, then stops/removes its own cluster. Other supported exclusive groups are workspace and regression. `--keep` retains only the stopped private QA files for local diagnostics. Do not confuse this test with an actual provider/browser acceptance or historical acquisition.

Source packaging now includes the exact four frontend/staging source files plus google_staging.py and audit_native.py. Nested staging files, runtime/operator config, raw CSV, built output and QA source are excluded. This fixes candidate portability without changing the Compose default factory or installing the native candidate.


## Explicit short synthetic practice mode and native upgrade

`create_google_demo_app` is a separate explicit factory enabling the existing v2 synthetic simulator and metadata routes, not a change to metadata-only defaults. It keeps UTC Free quotas, source overrides/real-source refusal and canonical ownership rules. No password, member administration, support, billing, app OWNER or signed plan-event mutation is exposed. The API advertises demoConfigured=true; the separate login entry then mounts existing BetaWorkspace, with prominent short-synthetic/no-real-history labels and preserved saved journal/statistics. This is not16-instrument five-year historical acceptance.

Interactive API default is bounded600/IP/min (operator bound60..1200); an additional canonical DB-backed auth admission remains30/IP/min and ignores raw forwarded-IP headers. Google state/PKCE/OIDC and normal API admission/causal guards remain unchanged. The explicit demo ACL helper grants all required metadata/v2 permissions in one transaction and cannot insert plan events or delete memberships.

`native_demo_upgrade.py` only targets the existing audited native installation. It requires a pinned source archive, built static-only overlay, exact current API/Caddy/release hashes and protected existing runtime/operator configuration. No apt/pip/roles/schema/migration/unit/firewall/SSH/Tailscale/GNOME changes. It freezes operator inputs root-side, validates source/dependency/migration/Caddy state, uses exported-snapshot fingerprints and pg_dump to prove an actual restore into a newly created CONNECT-restricted temporary database, and drops only that invocation's restore copy. It preserves the source database and existing root landing/assets, adds minimum transactional demo ACLs, replaces only the API launcher, restarts riksora-beta, reloads Caddy and switches the static symlink. Files/ACL/config drift cause refusal.

The operator launcher must use installed Python with -I and a hash-checked operator_bootstrap.py. Bootstrap validates/freezes the pinned plan and full source archive before importing any upgrade module, avoiding editable-home/PYTHONPATH code as root. root-owned private snapshots contain original API/Caddy/link/table+column ACL state and the database dump/restore proof. Automatic rollback handles apply failures; explicit --rollback-snapshot requires exact current deployment/ACL state and preserves all saved database rows. Service rollback is rehearsed with simulated services in QA; real host success still requires executing the reviewed plan and actual public/browser acceptance. Do not execute an incomplete/unreviewed plan or rerun the old installer.


### Private intake of existing converted HistData files

Use `PYTHONPATH=backend python -B -m ticks.histdata_v2 --source /absolute/SYMBOL_YYYY-MM.csv.gz --symbol SYMBOL --store /private/new-store --report /private/new-report.json --first-rows 100000` from the repository. This reads the source without modifying it, verifies gzip integrity plus compressed/decompressed hashes and publishes only a private structural dataset. Do not put source/derived tick artifacts in Git, public assets or the web root. Do not use .part files. Prefixes complete their final equal-time group; they are not a full month or five-year dataset. `--resume` must match original source hashes/selection/packing; gzip seek decompresses its prefix. `--full-file` is explicit full-file structural intake, not coverage/rights/execution approval. Refusal JSON reports never signify a published dataset.

The hosted API remains synthetic-only. No installation, sudo, restart, production migration, real-source profile relaxation or API mount is performed by this command. Keep freshness/coverage/rights unknown unless independently evidenced.


### Private pre-replay tick context (not hosted admission)

`market_data.tick_context.load_tick_context` accepts an already pinned `DiskTickProvider`, a `FrameWarmup` from `plan_warmup`, and a trusted replay-start nanosecond integer. The ordinary-user controller can obtain completed BID reference OHLC without loading full history: defaults100k events/512 bounded pages, explicit finite lookback, cancellation and whole-request budget refusal. Return only `TickContext.selection` and its fixed quality/basis disclosures to a prospective adapter, never the provider or private index position. This checkpoint mounts no route and performs no deployment.

BID_OBSERVATIONS is a distinct explicit basis; the existing hosted chart uses exact mid display. Do not silently prepend these BID bars to mid-based indicators. UNKNOWN coverage/freshness stays unknown, ambiguous equal-time BID buckets are omitted, missing bars are not synthesized, and SUFFICIENT_COUNT is not a completeness/rights/convergence guarantee. No OHLC financial fills, source permission grant or real-provider profile bypass. Hosted composition still requires identity/source scoping, reviewed real-source eligibility and final acceptance.

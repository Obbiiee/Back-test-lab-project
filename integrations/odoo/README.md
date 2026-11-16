# Odoo Community business integration

Odoo19 Community source is pinned to dbec872e39b030828e7cd22aae1d39d2da87c29e (LGPL-3). Native CRM/Contacts and Invoicing plus the authored btl_business addon run in a separate database/filestore. No Enterprise or OCA dependency is silently required. Company/chart/tax and statutory reporting are operator-owned and not certified here.

## Functions

- CRM customers/contact mapping and native opportunity pipeline.
- Scheduled one-way customer and sandbox payment synchronization through native Odoo19 JSON2. Stable company/source/order/revision identity makes repeated delivery idempotent. Customer email changes deliberately stop for identity review.
- Billing-only Free/Pro projection and paid expiry for staff, with source observation time; observations older than ten minutes show STALE / UNKNOWN on read/reload. Open staff screens require reload to refresh; they are not push-refreshed. These labels do not include separate HMAC QA access events and never grant app access.
- Verified app users submit durable account-owned support requests; the next sync creates staff tickets. Requests survive Odoo downtime. Staff status/notes are preserved on repeat import. App receipt means saved intake, not proof of delivery or staff response. There is no reply/email synchronization in this checkpoint.
- Independent provider payout/bank reconciliation: gross minus evidenced fee/refund must equal the independently entered bank deposit. Confirmation produces exactly one immutable net bank cash entry. Do not post the same fee/refund again as bank cash; this is clearing reconciliation, not automatic revenue/tax accounting.
- Monthly/annual operating-cost plans for VPS, domain/software/data and other costs. Due plans create drafts only. Replace estimated amount and PLANNED ONLY evidence with the actual receipt before confirmation. Unknown costs stay unknown.

Sandbox orders never create revenue, invoices, bank deposits, refund amounts, provider fees or Pro grants. Reconciliation/cost examples are authored QA amounts, not actual funds. Native invoice/vendor-bill operations remain in Invoicing after actual company/chart/tax setup. Cashbook is cash movement, not an automatic profit-and-loss statement or tax return.

## Install and isolate

Install btl_business from addons/ on a separate private Odoo19 database with crm,contacts,account,mail,rpc. Assign CRM, Importer and Finance only to corresponding internal staff; portal users receive none. Keep Odoo private/loopback for local QA, disable public signup and provision individual production staff credentials. Product identity, billing and replay never call Odoo in their request path; outages cannot block them.

Use a separate PostgreSQL LOGIN export role with NOSUPERUSER NOCREATEDB NOCREATEROLE and only the exact column grants supplied by export.grant_export_reader, including support intake. The worker role must not inherit owner/app/billing roles or broader grants. An owner must apply migration014 before granting support SELECT and grant_support_runtime to the product app role. Never use a product owner DSN in the worker or in Odoo. Odoo itself never connects to the product database. Product operator grants now include the support intake table; no credentials/ticks/provider secrets are exported.

Create a dedicated Odoo internal service user in only the intended company, with Backtest Business Importer (no Finance/System group). As an Odoo administrator bind that user's btl_source field to the installation's stable UUID. The field is system-only and is configured through private Odoo shell/admin provisioning, not public API. Issue an expiring native Odoo API key for that service identity through the normal operator workflow and rotate it. Never use a staff administrator key or put keys in source/browser/command-line arguments.

## Scheduled synchronization

Run the existing backend Python with repository/backend on PYTHONPATH:

    python -B integrations/odoo/sync.py

Supply all six values privately in the worker environment:

    BTL_BUSINESS_EXPORT_DSN
    BTL_BUSINESS_SOURCE
    BTL_ODOO_URL
    BTL_ODOO_DATABASE
    BTL_ODOO_API_KEY
    BTL_ODOO_COMPANY

The URL is the configured Odoo root, HTTPS required except literal localhost/127.0.0.1/::1 QA. Company is the positive numeric Odoo company ID. Source UUID must exactly match the service user's binding. The worker reads one repeatable-read/read-only snapshot, posts once to /json/2/btl.import.batch/sync_bundle, refuses redirects, ignores proxy environment and bounds requests/responses/timeouts. It prints only accepted counts or a fixed failure code. No automatic retries inside an HTTP request; the next schedule safely re-exports current state. Monitor nonzero exit codes; persistent failure must alert the operator rather than being treated as successful delivery.

btl-odoo-sync.service/timer are opt-in Linux host templates (one cycle per minute, non-overlapping oneshot). They require an existing least-privilege OS user, reviewed filesystem paths and protected /etc/backtest-lab/odoo-sync.env. They are not installed or enabled automatically. Local QA uses its own process timer and authored data. The stock product Compose database has no published port: a host-native worker cannot simply resolve its internal db hostname. Do not expose the database to solve that; actual container/private network placement and HTTPS routing must be reviewed/tested on the chosen host. No Docker/Linux runtime certification is claimed.

A full snapshot refuses above1000 customers,1000 orders or1000 tickets (8MiB sync /2MiB payment export), never silently truncates. Extend with reviewed bounded pagination before exceeding those limits. The importer serializes by source/company, refuses stale/future observations, same-observation conflicts, mutable order pins and terminal reversal regressions. One transaction covers contacts/payments/tickets/observation state. Manual reviewed snapshot import/export remains available for recovery; manual imports do not assert a fresh automatic observation.

## Payout and cost workflow

Backtest Business -> Payout reconciliation accepts independently supplied provider payout reference, bank reference, evidence/date and whole-IDR gross/fee/refund/bank amounts. A difference blocks confirmation; references are unique per company. Repeated confirmation returns the same cash entry; confirmed records cannot be edited/deleted. Current scope is positive net IDR payouts up to one billion per record, not net-negative batches, automatic bank feeds, tax journals or external settlement verification. Unknown report formats/actual provider amounts are not invented.

Operating cost plans -> Prepare due cost draft advances the next due date and creates an unconfirmed draft. Planning never creates cash or a vendor bill. Confirm only after replacing the placeholder evidence and estimate with the actual receipt/amount. Native Invoicing handles vendor bills separately after accounting setup; avoid entering the same actual movement twice.

## Optional isolated Odoo container candidate

compose.yaml uses its own internal business network, database and filestore, not the product network. Host binding is127.0.0.1:8070 only. Set BTL_ODOO_IMAGE to an official odoo:19.0@sha256:... and BTL_ODOO_POSTGRES_IMAGE to postgres:17@sha256:... after reviewing actual digests. No invented digest/default latest tag. Create private secrets/db_owner_password and secrets/odoo.conf from the example with separate owner/app credentials. PostgreSQL initializes as btl_odoo_owner; explicitly create restricted LOGIN odoo NOSUPERUSER NOCREATEDB NOCREATEROLE and assign only the separate odoo database to it before app startup. Never run Odoo as the initialization superuser. This candidate has not been started on Docker/Linux; the current Windows host has no Docker/WSL runtime.

Back up Odoo database and filestore together, separately from product backups, and verify recovery before actual business use. Keep upstream source/dependencies, QA credentials, customer exports and raw market data out of Git/source archives. Real merchant/provider/bank reports, company/tax/retention policy, production keys, TLS/private networking, scheduled alerting and Linux capacity remain operator acceptance prerequisites.


## Operations and recovery

See OPERATIONS.md for daily support/payment/cost handling and the explicit cold database+filestore backup/recovery procedure in recovery.py. The tool restores only a trusted-hash archive into a different new empty database and new filestore path, after operator quiescence. Actual local rehearsal evidence is recorded in the existing phase/history owners; host encryption/off-site retention and production recovery acceptance are separate.


## Operator views (Community, presentation-only)

operations.xml extends the existing views without new models, fields, security grants or financial methods. Customers/payment details remain read-only projections; plan freshness is recomputed on read and needs a refresh, not a persistent searchable Fresh/STALE flag. Support has a non-draggable state kanban plus list/form and assignment/state searches. Internal work is labelled intake-only: app/email reply delivery is not implemented. Cashbook has evidenced/draft/direction/category/month filters and a confirmation warning; its existing signed-IDR sum still counts confirmed cash only. Payout mismatch shows the gross-fee-refund=bank rule and withholds the confirmation button until amounts agree; server-side independent evidence and immutability guards remain authoritative. Cost preparation explicitly creates a draft and advances its due date, not cash.

No dashboard tiles, searchable computed freshness, sync-worker last-exit monitor, identity-review flag, correcting-entry relation, domain category or smart counts were fabricated. These need their existing model/contract owner before adding. Full canvas37-screen parity is not accepted without the requested reference export. Native Odoo styling is retained; no upstream/Enterprise patch.

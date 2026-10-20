# Business operations and local recovery rehearsal

Procedure only. Architecture and current readiness remain owned by the existing PRODUCT_SYSTEM_ARCHITECTURE_BLUEPRINT and AI_CONTEXT/04_CURRENT_PHASE. All local examples are authored QA; never treat their balances, prices, contacts or payment status as actual business evidence.

## Daily checks

1. Check product identity/replay health separately from the Odoo worker. Odoo failure does not authorize pausing or altering trading records.
2. Check the last successful sync and the worker exit status. Refresh Odoo customer/ticket views; open views are not pushed automatically. After ten minutes without a fresh observation the next read shows STALE / UNKNOWN. Do not infer live Pro access from an old staff screen.
3. Review new/unassigned support tickets. Match the stable account identity, assign a staff owner and move Open -> In progress -> Closed as work proceeds. Record resolution notes. Current sync is intake-only: staff replies/status are not delivered back into the app or by an automatic email workflow. Use an owner-approved communication channel; never request passwords/card details/private keys.
4. Review pending payments against the product's saved order ledger and independently authenticated provider status. A signed notification is a lookup signal; a screenshot/return URL/client claim is not paid authority. Odoo records never grant Pro.
5. Reconcile actual provider payout references against independent bank evidence. Review due operating-cost drafts and replace estimates with actual receipts/amounts before confirmation. A draft changes no cash.

## Interrupted or duplicate requests

- Support: the application saves the request before Odoo delivery. Reload saved support requests before retrying an interrupted submission. Retry the same request identity, not a new copy of the same issue. A known saved response followed by a failed list refresh remains saved. Staff work survives later imports.
- Trading: reload committed evidence after an uncertain request. Do not invent a new financial command identity or force revisions. A committed request replay returns its original receipt; review/confirm and next tick execution remain required. Source display failure must not become an OHLC fill or fabricated result.
- Checkout: do not repost a checkout after uncertainty. Recover the saved order/request; resume only if the server still says CREATED. CHECKOUT_STARTED/PENDING/HOLD need explicit authenticated reconciliation. Never renew expiry from duplicate notifications or edit payment rows in Odoo.
- Sync: keep the same installation UUID/company binding and restricted reader/service identity. A failed cycle exits nonzero; the next scheduled export is safe. Do not reset source observation/revision pins to hide an error. Email identity conflicts, stale observations and limits require review. Above1000 customers/orders/tickets needs reviewed bounded pagination.

## Refund and payout handling

Actual refunds are merchant operations outside this addon. Only the merchant owner should execute an approved refund in the provider's supported workflow. This guide does not issue a refund, choose commercial eligibility or promise a refund policy.

After the provider confirms reversal, let the product reconcile authenticated status; the order's reversal is terminal and the next sync mirrors it. Other independent paid orders can still grant access; do not assume every refund makes an account Free. A partial reversal follows the existing adapter's conservative order-access policy; actual refund amount is not inferred from the order face value.

For payout reconciliation, enter actual gross, fee, refund and independently observed bank deposit with provider/bank references and receipt evidence. Zero means an evidenced zero, not an unknown amount. If any component is unknown, leave the case unconfirmed pending evidence. gross-fee-refund must equal the positive bank amount. Unique references prevent assigning the same payout/deposit twice. Confirmation produces only the net bank cash entry; do not enter the same fees/refunds again as bank movements. Current scope excludes negative/zero net payout batches, bank feeds, automatic fee/report fetching and tax journals. Use native Invoicing/vendor bills only after actual company/chart/tax setup, with an approved rule to avoid recording the same movement twice.

## Cost plans

Monthly/annual plans create due drafts, not paid expenses. A plan may cover VPS, domain, data or software; actual prices are operator evidence. Replace PLANNED ONLY with the actual receipt reference and actual amount before confirming. Confirmed cash entries cannot be edited/deleted; record an explicit correcting movement with its own evidence. Never erase an original receipt to make totals look right.

## Cold Odoo backup

The Odoo database and its filestore form one recovery unit. Product database backups are a separate process; a business backup contains no market dataset or proof of trading-engine recovery.

1. Choose a maintenance window. Stop Odoo HTTP/cron workers, outgoing jobs and business sync. Confirm there are no other clients on this Odoo database. Product login/replay can remain available because they do not call Odoo.
2. Record the deployed Odoo upstream commit, addon/product Git commit, relevant release manifest and private configuration/secret recovery references. The backup manifest records the Odoo upstream commit; keep the matching addon release separately. Do not dump secret values into a report.
3. As the intended Odoo OS/database operator, provide BTL_ODOO_RECOVERY_DSN and BTL_PG_BIN through protected environment. Use Python3.12+ and an operator-private destination directory outside the source filestore; the ZIP contains sensitive business data and credential hashes. New files request POSIX0600 and restore roots0700; Windows relies on the private parent directory ACL. Encrypt and restrict production backup storage using the chosen host's approved mechanism; encryption/off-host retention is not supplied by this ZIP tool.
4. With repository/backend on PYTHONPATH, run:

       python -B integrations/odoo/recovery.py backup --filestore PRIVATE/filestore/SOURCE_DB --archive PRIVATE/odoo-cold.zip --odoo-commit REVIEWED_40_HEX_PIN --quiesced

5. Keep the returned SHA256 receipt in a separately protected record. The tool checks DB/directory name agreement, refuses other connected clients, verifies attachment references/sizes/content identities and stores checksums for the dump and blobs. Odoo GC checklist markers are excluded; actual attachment bytes are retained. File count100000, total2GiB and180-second pg-tool bounds deliberately refuse oversized operations; capacity expansion needs a reviewed change. It never overwrites a destination. A failed partial archive is not a usable backup.

An archive hash proves integrity against the trusted receipt, not authenticity if an attacker can replace both. Restore only operator-owned trusted PostgreSQL dumps; they contain executable SQL. --quiesced is an explicit operator assertion, not an automatic shutdown/maintenance system.

## Restore rehearsal and recovery

1. Keep the source untouched. The PostgreSQL owner provisions a NEW empty database with a DIFFERENT name, owned by the restricted Odoo database role. Provide a new nonexistent filestore directory with the same basename as that new database. Do not reuse the source directory, a populated target or an old failed partial target.
2. Keep target Odoo and integration jobs stopped. Use the recorded trusted archive hash and matching source/addon release. Run:

       python -B integrations/odoo/recovery.py restore --filestore PRIVATE/filestore/NEW_DB --archive PRIVATE/odoo-cold.zip --hash TRUSTED_64_HEX_SHA256 --quiesced

3. The tool verifies every archive member/hash/path before writes, refuses nonempty/connected targets and restores PostgreSQL in one transaction. On failure, keep the rejected target for review and use another new empty destination; no automatic deletion or overwrite is performed. Run as the appropriate Odoo filesystem owner or arrange reviewed ownership before startup.
4. Configure the clone's exact db_name/dbfilter and new data_dir, list_db=False, max_cron_threads=0 and loopback-only HTTP for QA. Keep outgoing email, callbacks, scheduled integrations and production keys inactive. Never let a restored QA clone contact real customers or a live provider. Do not route the existing sync worker to the clone.
5. Verify business row identities/revisions, protected cash/payout totals, customer/support state, native CRM/invoice records and attachment content hashes. Login and open a recovered ticket/attachment. Test access permissions with proper staff roles. Confirm the original source's before/after fingerprints are unchanged.
6. Record measured recovery time and result. A local rehearsal does not define a production recovery-time/recovery-point promise. Before production cutover, approve network/TLS, rotated credentials, recovery schedule/retention/off-host storage and restart order on the chosen host. Do not re-enable cron/email/integrations until the intended production target has been accepted.

## Escalation record

Record time, affected component, private correlation/request/order identity, last confirmed state, observed error and operator action. Never include bearer tokens, database passwords, API keys, card details or raw market files. Keep an unresolved status explicit if provider/bank evidence is missing. Repair proposals must preserve immutable financial/source identities and receive their normal validation/Git checkpoint; there is no emergency Odoo edit that can settle a trade or grant production access.

# Security dependency checkpoint — 2026-10-24

Owner instruction: `kerjakan`, following the comprehensive audit and its first recommended checkpoint. Scope is a dependency-only candidate on parent `ba63f0709e33a6354998746fcccad91c6ddbbc15`; no integration of the separate main, functional, Claude or handoff branches. Existing blueprint/frozen contracts remain authority.

## Changes

| Package | Before | Candidate | Scope |
| --- | --- | --- | --- |
| certifi | 2026.7.22 | 2026.10.19 | Exact backend lock; add minimum2026.10.19 to requirements.txt so a normal requirements install cannot select the affected version. |
| Vite | 8.3.1 | 8.3.3 | Exact devDependency and regenerated npm lock; no major/minor upgrade. |
| Zod | 4.6.5 | 4.6.7 | Compatible transitive dev dependency in lock, satisfying the fixed>=4.6.6 range; no new direct dependency/override. |

Primary references: [certifi publisher advisory](https://github.com/certifi/python-certifi/security/advisories/GHSA-6q48-6c7w-9gw2), [reviewed advisory and recommended2026.10.19](https://github.com/advisories/GHSA-6q48-6c7w-9gw2), [Vite8.3.3 release](https://github.com/vitejs/vite/releases/tag/v8.3.3), [Zod advisory](https://github.com/advisories/GHSA-mrhx-c7xc-m3w5). The publisher originally removed emSign roots in2026.10.18; the reviewed advisory recommends2026.10.19 or later. This checkpoint selects2026.10.19.

No application source, engine, financial vectors, data/parser/profile/admission contract, migration, frontend component, payment configuration or live infrastructure changes. Root CA trust changes are the intended runtime behavior change when the candidate is eventually deployed.

## Validation performed on the candidate

- Fresh private venv `/tmp/riksora-security-app-venv`, installed all38 exact lock pins; `pip check` PASS. No system/active service environment changed.
- Full backend **573 tests PASS, zero skips,461.306s**, using the existing repository helper with a newly owned socket-only SCRAM PostgreSQL16 cluster. QA cluster stopped; private fixture files retained. No production DSN, credentials or user data used.
- Real verified outbound HTTPS to public Google OIDC discovery: HTTP200, explicit candidate certifi SSLContext, hostname verification required, proxy environment disabled; no credentials, OAuth consent or account mutation. This is TLS compatibility evidence, not a live login certificate.
- Parsed candidate bundle:120 roots; affected `emSign ECC Root CA - G3` absent; SSLContext requires certificates and hostname verification. Bundle SHA256 `50f79f98dac192b20dbf73f35c56f0b0c557ab267ff5199d1117cc1180b70785`. Cryptography warns about an existing nonpositive serial number in a bundled certificate; do not weaken validation or silently modify the upstream bundle.
- `pip-audit --no-deps --disable-pip -r backend/requirements.lock`:38 pins, **zero known vulnerabilities**. Fully pinned lock scanned; it is not a complete code security proof or hash-locked supply-chain certificate.
- `npm ci --ignore-scripts` PASS with system Node20.20.2/npm10.8.2 after lock generation. Installed148 packages, audited149. Full and production-only npm audits both **zero known vulnerabilities**. npm graph resolves Vite8.3.3 and Zod4.6.7, including react-hooks/zod-validation-error consumers.
- Complete registered frontend regression PASS, with `BTL_RESEARCH_PYTHON=/tmp/riksora-security-app-venv/bin/python`; includes market data, exact financial vectors, client/workspace and staging SSR gates. Lint PASS; main build150 modules PASS; separate staging workspace/home build103 modules PASS; release audit PASS. Existing mixed static/dynamic AlphaHome import warning remains; no unrelated optimization.
- Deployment/package/native-audit/static-upgrade/filesystem tests **23 PASS,1.294s**, using temporary/mocked filesystem only. Printed upgrade/rollback messages describe fixtures, not a live service change.
- Repository boundary/context gates PASS (133 reachable production files); bundle determinism/generation/verification PASS (393 files); independent Node reference16 authored profile canonical bytes/hashes PASS. Graph comparison proves no npm package addition/removal and only Vite/Zod version changes. Complete diff reviewed before commit.

Local log/audit artifacts: `/tmp/riksora-security-backend.log`, `/tmp/riksora-security-frontend.log`, `/tmp/riksora-security-deploy.log`, `/tmp/riksora-security-python-audit.json`, `/tmp/riksora-security-npm-audit.json`, `/tmp/riksora-security-npm-production.json`. They are temporary private evidence, not a durable backup guarantee. No raw data or credentials committed.

## Resolver failure and browser scope

System npm10.8.2 and locally invoked npm10.9.4 both crashed in Arborist `edgesOut` during lock resolution. No peer/engine checks were bypassed, no `--force`/`--legacy-peer-deps`, and no global tooling upgrade. Locally invoked npm11.6.4 successfully generated the narrowly changed lock. System npm10.8.2 then installed that lock cleanly; only Vite/Zod package versions changed in the npm graph. Vite's rolldown dependency range updates to~1.2.11; its already-locked package version remains unchanged.

Browser product acceptance is not claimed: there is no presentation, route, API wire or consumer change; backend native/HTTPS, registered SSR/client tests and both production build entrypoints were exercised. Interactive browser unavailable during the audit; retain real browser login/workspace/replay acceptance as an integration/rollout gate. No new authored test mirrors package metadata; existing functional and golden gates verify behavior under the new dependencies.

## Decision and deployment boundary

**GO for review/integration of this validated source candidate. NO-GO to call the active VPS patched.** Its venv was deliberately left untouched, so the installed certifi2026.7.22 exposure remains until an operator-approved security rollout succeeds. The main app and static/DB services are not restarted or reloaded; no migration, bulk import, source admission, payment enablement, dataset deletion or financial-engine change.

Next checkpoint proposal: read-only release-manifest reconciliation covering actual active frontend/backend commits, source branch provenance, exact dependency pins and existing upgrade/rollback procedures; produce a concrete minimal rollout plan. Do not integrate unrelated functional/Claude changes, update the active environment, restart services or invoke payment endpoints before the required approval. Historical rights, XAU October/precision/coverage and two-year storage acceptance remain separate unresolved gates.

Ready-to-copy next prompt: "Izinkan checkpoint preflight release keamanan RIKSORA. Baca AGENTS, authority dan handoff terbaru; verifikasi kandidat dependency security dan provenance release frontend/backend aktif, susun manifest serta rencana upgrade/rollback minimal tanpa mengintegrasikan draft lain. Tetap read-only terhadap layanan/data/akun, billing OFF; jangan deploy, restart, impor, mengubah engine atau frozen contracts. Validasi, catat blocker/hasil di owner docs dan handoff, commit/push dokumentasi, verifikasi remote HEAD dan clean0/0, lalu STOP."

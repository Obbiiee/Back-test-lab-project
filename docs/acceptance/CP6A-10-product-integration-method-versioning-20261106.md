# CP6A-10 Product Integration — Method Versioning Checkpoint

Status: `IMPLEMENTED_CANDIDATE_PENDING_POSTGRES_QA`

Candidate base: `f68ba9d7e56fffd7a4be90f8da265ae6098c9a23` on `codex/product-integration-v1-20261106`.

## Implemented candidate behavior

- Existing immutable `btl.tick_methods` rows are not rewritten. Migration `022_product_method_versions.sql` gives each existing Method a self-family stable ID and version 1 mapping.
- New Methods create family version 1. Successor versions insert a new immutable Method record and append-only version mapping; the family pointer/revision advances with a database guard and deferred latest-version foreign key.
- Existing Sessions keep their original `method_id`, canonical Method bytes/hash and financial Session metadata. Archive/unarchive only changes family lifecycle metadata with expected-revision compare-and-set.
- Archived families are omitted from the default list, remain available with `includeArchived=true`, and refuse new Sessions. Existing Sessions remain readable. Create/version/archive operations serialize on the existing workspace catalog lock.
- Authenticated hosted UI displays current family versions, version history, successor creation, and archive/unarchive. Form retries reuse the same Method ID so exact request retries remain idempotent.
- Existing Method list/detail routes and Method/Session financial wires are retained. No financial reducer, receipt, canonical market data, or Annual PASS evidence changes are included.

## API candidate

- `GET /api/v1/workspaces/{workspaceId}/research/method-families?limit=&after=&includeArchived=`
- `GET /api/v1/workspaces/{workspaceId}/research/method-families/{familyId}`
- `POST /api/v1/workspaces/{workspaceId}/research/method-families/{familyId}/versions` with `{expectedRevision, method}`
- `POST /api/v1/workspaces/{workspaceId}/research/method-families/{familyId}/lifecycle` with `{expectedRevision, archived}`

All reads use the authenticated workspace scope. Writes require workspace owner authorization. Stale revisions and lifecycle conflicts return 409. Method version content remains hash-validated by the existing immutable Method contract.

## Checks performed

- Python syntax compilation: PASS for changed backend modules and tests.
- `git diff --check`: PASS.
- Frontend ESLint: PASS.
- Frontend production build: PASS (Vite 8.3.3).
- Frontend product page pagination/version transport tests: PASS.
- Frontend confirm outcome, TickAlpha transport, and Phase 18.8 financial contract regressions: PASS.
- PostgreSQL migration/trigger, authenticated Method family/session pinning, stale revision, archive, existing-session compatibility, authorization and concurrent-operation tests: **NOT RUN**.
- Browser account journey and viewport screenshots at 320, 375, 390, 768, 1024 and 1440 px: **NOT RUN**.

## Hold reason and next gate

Current host observation: 35 GiB free disk, about 4.5 GiB MemAvailable, swap 0. The product QA preflight requires at least 36 GiB free disk and 10 GiB MemAvailable. The system PostgreSQL service is active and was not used for test writes. No private QA PostgreSQL cluster was created. Until an isolated PostgreSQL gate runs safely, this candidate is not accepted, not committed/pushed, and not complete.

Account linking is separately blocked before migration or authentication cutover. The current `google_identities` relation is immutable and one-subject-per-user; the evidence and minimum proposed owner decision are in `CP6A-10-account-linking-contract-decision-20261106.md`.

No production service, deployment, data cleanup, benchmark, or historical replay was run.

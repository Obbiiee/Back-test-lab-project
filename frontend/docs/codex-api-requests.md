# Frontend → Codex API contract requests

Requests from the frontend for routes or fields that the UI needs but the backend does not publish. The frontend does not implement or simulate any of them against production. Until a request is shipped in a versioned DTO, the UI shows the honest state described here. Owner of every item: Codex (backend). Frontend owner: Claude.

## REQ-01: exact start-month availability per instrument (P0, founder remediation 2026-11-06)

**Why.** The New Session wizard must only offer start months that the server will accept. Today `GET /catalog` returns only `startPeriod` (the month of the source's first observed quote). A min/max range is not proof of eligibility: months can have gaps, rights limits, expiry or QA holds. `HistoricalSource.start_for_period` additionally refuses months outside the start year and months without observations (`REFUSED_HISTORICAL_PERIOD`), and the client cannot see these rules in advance.

**Requested shape.** An additive field on `GET /catalog` (catalog `schemaVersion` stays 1, the new block carries its own version):

```json
"availability": {
  "schemaVersion": 1,
  "instruments": [
    {
      "instrumentId": "XAUUSD",
      "status": "AVAILABLE | PARTIAL | QA_BLOCKED | RIGHTS_BLOCKED | PLANNED",
      "periods": [
        {"period": "2024-11", "status": "AVAILABLE"},
        {"period": "2024-12", "status": "GAP", "reason": "optional human text"},
        {"period": "2025-02", "status": "RIGHTS_BLOCKED"},
        {"period": "2025-03", "status": "EXPIRED"}
      ]
    }
  ]
}
```

- `period` is `YYYY-MM` in UTC; `periods` lists every month the server knows about for that instrument. Unlisted months are never offered.
- A month is selectable when the instrument is `AVAILABLE` or `PARTIAL` and that exact month is `AVAILABLE`. `PARTIAL` summarizes the instrument's overall coverage; it does not erase individually verified start months. `RIGHTS_BLOCKED`, `QA_BLOCKED`, `UNKNOWN`, and unrecognized instrument statuses deny all months. Month `PARTIAL`, `GAP`, `RIGHTS_BLOCKED`, `EXPIRED`, `QA_BLOCKED`, `UNKNOWN`, and unrecognized statuses are not selectable.
- `availability.scope` is `SESSION_START_MONTH_ONLY`: `AVAILABLE` means the server accepts a Session start in that month, not that complete month coverage exists. The DTO includes source rights and eligibility classification. Synthetic fixture availability is explicitly `SYNTHETIC_QA_ONLY`; historical source with rights `UNKNOWN` is `UNKNOWN` / `NOT_GRANTED`, never selectable.
- `POST /sessions` stays the authority: it rechecks the exact start-month status and refuses a month it would not serve. The local route also refuses historical sources while source rights remain unknown.
- No future knowledge leaks: the list describes which months a new Session may start in, not EOF or the future tick range of an open Session.

**Instrument in POST /sessions.** The wizard has an Instrument step, but `POST /sessions` takes no `instrumentId`; the server pins the instrument from the workspace profile. The frontend keeps the payload unchanged (`id, name, methodId, initialBalance, startPeriod`) and states "pinned from this workspace's server profile" on Review. When the catalog lists more than one instrument, the backend needs a versioned `instrumentId` field on `POST /sessions` (with refusal code for an instrument that is not `AVAILABLE`) before the picker offers a second option.

**Frontend behaviour** (`src/tickAlpha/periodAvailability.js`, `AlphaSessionWizard.jsx`):

| Catalog | Period step | Sent `startPeriod` |
|---|---|---|
| Synthetic fixture, version 1 DTO | Searchable month list with the one server-approved synthetic start month; bounded scope shown | a listed AVAILABLE month only |
| Historical source, version 1 DTO and rights UNKNOWN | blocked; no month offered | none |
| Legacy catalog with no `availability` field | "Earliest observed · {month}" or "Another month"; server checks it on Create | the chosen month; historical local Create remains rights-blocked |
| Present but unknown/malformed `availability` schema | fail-closed, no month offered | none |

A server refusal (`REFUSED_HISTORICAL_PERIOD`, `REFUSED_FIXTURE_PERIOD`) returns the user to the Period step with the server's reason and "nothing was created"; other refusals (409 and validation) stay on Review, keep every choice, and retry with the same creation id.

**Acceptance.** Versioned DTO and client tests cover partial instrument with individually AVAILABLE months, GAP, RIGHTS_BLOCKED, QA_BLOCKED, UNKNOWN and unknown schema. Server Create rechecks eligibility. Historical rights UNKNOWN never yields a selectable month.

**Proof today.** See the CP6A-10 P0 local integration report and backend/frontend tests in this branch. Historical data rights remain UNKNOWN; no historical Session is created by the local API.

## REQ-02: order confirmation receipt lookup (P0, founder remediation round 2, 2026-11-06)

**Status: IMPLEMENTED for the local synthetic QA API; hosted API remains blocked.**

**Why.** After `POST /sessions/{id}/confirm`, a lost response, timeout or 5xx leaves the outcome unknown. The frontend must never say "not placed" without a definitive answer, and must never re-send the confirmation or create a new review on the user's behalf.

**What the frontend does today** (`src/tickAlpha/confirmOutcome.js`, read from the current backend code, not from a published contract):

| Situation | Frontend outcome |
|---|---|
| 200 with `artifact: BTL-TICK-EXECUTION-RESULT-1`, matching `commandId`, `durable: true` | COMMITTED. A failed Session refresh afterwards shows "Order saved" with Reload Session. |
| 400 / 401 / 403 / 404 / 409 / 413 / 415 / 422; local 429 `LOCAL_BUSY` or `RATE_LIMITED` | REFUSED (STALE when a 409 names a stale revision/review). Only these say "not placed". |
| Anything else: network error, abort/timeout, 408, 5xx, unreadable body, other 200 body, hosted 429 | UNKNOWN: "Could not verify whether the order was saved; checking its durable command receipt." The review identity is kept, new orders are locked, and only a read-only check is offered. |

The read-only check is `GET /sessions/{id}/commands/{commandId}`. The server reads the immutable `tick_commands` receipt and the associated review in a repeatable-read snapshot. `COMMITTED` requires a hash-validated durable receipt matching Session and command. `NOT_COMMITTED` requires a persisted matching review, no command receipt, no order in Session state, and current Session revision greater than the review's `expectedRevision`; a command at that revision can no longer apply. If the review/receipt is absent or the Session is still at the reviewed revision, the result is `UNKNOWN`. Absence alone never means NOT_COMMITTED. The client verifies Session, command, review hash, receipt identity and revision before settling the UI; Session refresh is separate.

**Published DTO:** `{schemaVersion:1, artifact:"BTL-TICK-COMMAND-STATUS-1", sessionId, commandId, status:"COMMITTED"|"NOT_COMMITTED"|"UNKNOWN", currentRevision, reviewHash?, expectedRevision?, reason?, receipt?}`. `COMMITTED.receipt` is the original `BTL-TICK-EXECUTION-RESULT-1`. The local confirm route commits command, events, checkpoint and receipt in one transaction. Exact duplicate `{reviewId, reviewHash}` returns the same durable receipt; a different command hash under the same command id is refused. A lookup does not write or trigger a retry.

Only local API validation refusals (400/409/413/415) are definitive after the server handler decides; transport timeout, 408, 5xx, unreadable response, or unknown status remain UNKNOWN. The UI does not retry confirm automatically. Hosted auth/HTTP status guarantees are not implemented by this local contract.

**Acceptance.** Backend PostgreSQL race/idempotency tests plus `tests/confirm-outcome.test.mjs` and `tests/qa/confirm-outcome-qa.cjs` exercise receipt read, lost response, stale revision and exact retry.

**Proof today.** See the CP6A-10 P0 local integration report and branch test evidence. The hosted account API remains a separate checkpoint; this local loopback API is not a production authentication contract.

## REQ-03: select a pinned observed source when the hosted catalog is active (P0 integration)

**Status: the backend contract already exists; the frontend must consume it.** When the hosted service has an operator-pinned observed catalog, `GET /api/v1/workspaces/{workspaceId}/research/catalog` returns `artifact: BTL-OBSERVED-RESEARCH-CATALOG-1` and a `datasets` array. Each public dataset includes `key`, `period`, `label`, and its source profile. `POST /sessions` for a new Session must include the selected `sourceKey`, its exact `period`, and `day` (`null` for a whole-period start or a selected UTC date where that mode is exposed), in addition to `id`, `name`, `methodId`, and `initialBalance`.

- Use the catalog's public `key` as `sourceKey`; do not synthesize a key or infer it from a label.
- Keep the selected key and period paired. The backend revalidates their membership and profile pin during creation.
- Do not send filesystem paths, qualification receipt locations/hashes, provider handles, or profile overrides. These are operator-only capabilities and are not part of the request DTO.
- If a configured catalog is active and `sourceKey` is absent, the queued creation resolves as `INVALID_INPUT`; it will not silently create a V1 synthetic Session. The API's durable queue may acknowledge admission before the worker returns this refusal.
- Catalog visibility does not grant data rights or financial eligibility. Source rights remain fail-closed and limitations must remain visible.

**Acceptance.** Frontend account-transport tests should cover the observed catalog artifact, selecting a dataset, the exact `sourceKey`/`period`/`day` payload, and preserving the selection across a definitive refusal. The authenticated UI → queue → worker → replay → receipt → Journal → Analytics → resume journey still needs integration evidence.

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
- A month is selectable only when both the instrument and the month are `AVAILABLE`.
- **Pinned semantics (founder round 2).** Instrument `PARTIAL`, `QA_BLOCKED`, `RIGHTS_BLOCKED`, `PLANNED`, or any status the frontend does not know: no month is offered, even rows marked `AVAILABLE`, and the Period step shows the instrument reason. Month `GAP`, `RIGHTS_BLOCKED`, `EXPIRED`, `QA_BLOCKED` or unknown: listed but disabled with its reason. **Open question for Codex:** does `PARTIAL` with an `AVAILABLE` month mean that month is complete and accepted by `POST /sessions`? Until Codex answers in this document, the frontend stays fail-closed; it does not relax the gate on a guess. Fixtures: `tests/period-availability.test.mjs` (labeled `QA FIXTURE / INSTRUMENT STATUS / NOT MARKET DATA`).
- `POST /sessions` stays the authority: it must still refuse a month it would not serve, even if the catalog listed it (race with re-ingest).
- No future knowledge leaks: the list describes which months a new Session may start in, not EOF or the future tick range of an open Session.

**Instrument in POST /sessions.** The wizard has an Instrument step, but `POST /sessions` takes no `instrumentId`; the server pins the instrument from the workspace profile. The frontend keeps the payload unchanged (`id, name, methodId, initialBalance, startPeriod`) and states "pinned from this workspace's server profile" on Review. When the catalog lists more than one instrument, the backend needs a versioned `instrumentId` field on `POST /sessions` (with refusal code for an instrument that is not `AVAILABLE`) before the picker offers a second option.

**Frontend behaviour today** (`src/tickAlpha/periodAvailability.js`, `AlphaSessionWizard.jsx`):

| Catalog | Period step | Sent `startPeriod` |
|---|---|---|
| Synthetic fixture | Fixed, nothing to choose | `catalog.startPeriod` |
| Historical, no `availability` | "Earliest observed · {month}" (default) or "Another month" (any month ≥ earliest, no guessed maximum), with the note that the server checks it on Create | the chosen month |
| Historical, `availability.schemaVersion === 1` | Searchable month list; non-available months disabled with their reason; no available month → blocked state | a listed AVAILABLE month only |
| Unknown `availability.schemaVersion` | treated as not published | as row 2 |

A server refusal (`REFUSED_HISTORICAL_PERIOD`, `REFUSED_FIXTURE_PERIOD`) returns the user to the Period step with the server's reason and "nothing was created"; other refusals (409 and validation) stay on Review, keep every choice, and retry with the same creation id.

**Acceptance.** Catalog fixture from the backend test suite with a gap, a rights-blocked month, an expired month and a cross-year range; `tests/period-availability.test.mjs` and `tests/qa/wizard-period-qa.cjs` then run against that real response instead of the browser fixture.

**Proof today.** Unit: `npm run test:period-availability`. Browser: `node tests/qa/wizard-period-qa.cjs <out>` (all `/tick-alpha` routes answered by a labeled browser fixture `QA FIXTURE / PERIOD AVAILABILITY / NOT MARKET DATA`; it proves UI behaviour only, not backend support).

## REQ-02: order confirmation receipt lookup (P0, founder remediation round 2, 2026-11-06)

**Status: HOLD: CODEX RECEIPT INSPECTION.** No endpoint returns the outcome of a confirmation by its id.

**Why.** After `POST /sessions/{id}/confirm`, a lost response, timeout or 5xx leaves the outcome unknown. The frontend must never say "not placed" without a definitive answer, and must never re-send the confirmation or create a new review on the user's behalf.

**What the frontend does today** (`src/tickAlpha/confirmOutcome.js`, read from the current backend code, not from a published contract):

| Situation | Frontend outcome |
|---|---|
| 200 with `artifact: BTL-TICK-EXECUTION-RESULT-1`, matching `commandId`, `durable: true` | COMMITTED. A failed Session refresh afterwards shows "Order saved" with Reload Session. |
| 400 / 401 / 403 / 404 / 409 / 413 / 415 / 422; local 429 `LOCAL_BUSY` or `RATE_LIMITED` | REFUSED (STALE when a 409 names a stale revision/review). Only these say "not placed". |
| Anything else: network error, abort/timeout, 408, 5xx, unreadable body, other 200 body, hosted 429 | UNKNOWN: "Could not verify whether the order was saved; checking Session status." The review identity is kept, new orders are locked, and only a read-only check is offered. |

The read-only check is `GET /sessions/{id}`: the order is COMMITTED if `state.orders` has the key `commandId` (current `engine.py`: order id = commandId). It is REFUSED if the key is absent and `state.revision` is past the review's `expectedRevision` (current `postgres.py`: a command applies only at its `expectedRevision`). Otherwise it stays UNKNOWN. Any later Session view the page loads runs the same check.

**Requested contract.** A versioned read, for example `GET /sessions/{id}/commands/{commandId}` returning `{schemaVersion, commandId, status: COMMITTED | NOT_FOUND, revision, result?}`, with written guarantees that:
1. order id equals commandId, or the receipt names the order id;
2. a command never applies after the Session revision moved past its `expectedRevision`;
3. which HTTP statuses on `/confirm` are definitive (no commit happened);
4. whether re-posting the same `{reviewId, reviewHash}` is a safe idempotent retry. The current code returns the stored result, but the frontend does not offer it until Codex confirms.

**Acceptance.** Codex confirms or corrects items 1–4. `tests/confirm-outcome.test.mjs` and `tests/qa/confirm-outcome-qa.cjs` then switch from the Session read to the receipt read.

**Proof today.** Unit: `npm run test:confirm-outcome`. Browser, against the real local backend with faults injected in the browser: `node tests/qa/confirm-outcome-qa.cjs <out>` covers (a) POST 200 + refresh failure, (b) commit with a lost response, (c) a real 409 from the server, (d) 503, (e) double tap, (f) Back and reload while pending, (g) reconciliation finding the order saved, or finding that the Session moved on without it.

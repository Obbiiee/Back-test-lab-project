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

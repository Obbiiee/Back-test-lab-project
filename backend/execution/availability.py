"""Versioned start-month eligibility. This DTO never grants historical rights."""

SCHEMA_VERSION = 1
INSTRUMENT_STATUSES = frozenset({"AVAILABLE", "PARTIAL", "RIGHTS_BLOCKED", "QA_BLOCKED", "UNKNOWN"})
PERIOD_STATUSES = frozenset({"AVAILABLE", "PARTIAL", "GAP", "RIGHTS_BLOCKED", "QA_BLOCKED", "UNKNOWN", "EXPIRED"})
ELIGIBLE_INSTRUMENT_STATUSES = frozenset({"AVAILABLE", "PARTIAL"})


def catalog_availability(*, instrument_id, dataset_id, dataset_version, start_period, synthetic):
    common = dict(schemaVersion=SCHEMA_VERSION, scope="SESSION_START_MONTH_ONLY",
                  datasetId=dataset_id, datasetVersion=dataset_version)
    if synthetic:
        return {**common, "sourceKind": "SYNTHETIC_QA", "sourceRights": "NOT_APPLICABLE_SYNTHETIC",
                "executionEligibility": "SYNTHETIC_QA_ONLY", "instruments": [{
                    "instrumentId": instrument_id, "status": "PARTIAL", "periods": [{
                        "period": start_period, "status": "AVAILABLE",
                        "reason": "This bounded synthetic fixture accepts this Session start month; it is not complete month coverage.",
                    }],
                }]}
    return {**common, "sourceKind": "HISTORICAL_LOCAL", "sourceRights": "UNKNOWN",
            "executionEligibility": "NOT_GRANTED", "instruments": [{
                "instrumentId": instrument_id, "status": "UNKNOWN", "periods": [{
                    "period": start_period, "status": "UNKNOWN",
                    "reason": "Historical source rights and month eligibility have not been granted.",
                }],
            }]}


def eligible_start_month(availability, instrument_id, period):
    """An exact AVAILABLE period under a PARTIAL/AVAILABLE synthetic parent only."""
    if (type(availability) is not dict or availability.get("schemaVersion") != SCHEMA_VERSION
            or availability.get("scope") != "SESSION_START_MONTH_ONLY"
            or availability.get("sourceKind") != "SYNTHETIC_QA"
            or availability.get("sourceRights") != "NOT_APPLICABLE_SYNTHETIC"
            or availability.get("executionEligibility") != "SYNTHETIC_QA_ONLY"):
        return False
    for instrument in availability.get("instruments", ()):
        if type(instrument) is not dict or instrument.get("instrumentId") != instrument_id:
            continue
        if instrument.get("status") not in ELIGIBLE_INSTRUMENT_STATUSES:
            return False
        return any(type(row) is dict and row.get("period") == period and
                   row.get("status") == "AVAILABLE" for row in instrument.get("periods", ()))
    return False

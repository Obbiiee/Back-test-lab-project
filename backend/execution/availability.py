"""Versioned, fail-closed start-month availability for local tick-alpha.

Availability here authorizes a Session *start month*; it does not certify full
month coverage or grant data rights. Synthetic fixtures are QA-only. Historical
source rights remain UNKNOWN until separately granted.
"""

SCHEMA_VERSION = 1
INSTRUMENT_STATUSES = frozenset({"AVAILABLE", "PARTIAL", "RIGHTS_BLOCKED", "QA_BLOCKED", "UNKNOWN"})
PERIOD_STATUSES = frozenset({"AVAILABLE", "PARTIAL", "GAP", "RIGHTS_BLOCKED", "QA_BLOCKED", "UNKNOWN", "EXPIRED"})
ELIGIBLE_INSTRUMENT_STATUSES = frozenset({"AVAILABLE", "PARTIAL"})


def catalog_availability(*, instrument_id, dataset_id, dataset_version, start_period, synthetic):
    if synthetic:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "scope": "SESSION_START_MONTH_ONLY",
            "datasetId": dataset_id,
            "datasetVersion": dataset_version,
            "sourceKind": "SYNTHETIC_QA",
            "sourceRights": "NOT_APPLICABLE_SYNTHETIC",
            "executionEligibility": "SYNTHETIC_QA_ONLY",
            "instruments": [{
                "instrumentId": instrument_id,
                "status": "PARTIAL",
                "periods": [{
                    "period": start_period,
                    "status": "AVAILABLE",
                    "reason": "This bounded synthetic fixture accepts this Session start month; it is not complete month coverage.",
                }],
            }],
        }
    return {
        "schemaVersion": SCHEMA_VERSION,
        "scope": "SESSION_START_MONTH_ONLY",
        "datasetId": dataset_id,
        "datasetVersion": dataset_version,
        "sourceKind": "HISTORICAL_LOCAL",
        "sourceRights": "UNKNOWN",
        "executionEligibility": "NOT_GRANTED",
        "instruments": [{
            "instrumentId": instrument_id,
            "status": "UNKNOWN",
            "periods": [{
                "period": start_period,
                "status": "UNKNOWN",
                "reason": "Historical source rights and month eligibility have not been granted.",
            }],
        }],
    }


def eligible_start_month(availability, instrument_id, period):
    """Only an exact AVAILABLE row under an eligible parent can be selected."""
    if (type(availability) is not dict or availability.get("schemaVersion") != SCHEMA_VERSION
            or availability.get("scope") != "SESSION_START_MONTH_ONLY"
            or availability.get("executionEligibility") != "SYNTHETIC_QA_ONLY"):
        return False
    for instrument in availability.get("instruments", ()):
        if instrument.get("instrumentId") != instrument_id:
            continue
        if instrument.get("status") not in ELIGIBLE_INSTRUMENT_STATUSES:
            return False
        return any(row.get("period") == period and row.get("status") == "AVAILABLE"
                   for row in instrument.get("periods", ()))
    return False

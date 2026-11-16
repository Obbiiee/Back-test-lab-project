"""Fail-closed gate for additional one-day reader measurements."""
def baseline_gate(active, result, reports, manifest):
    if active:
        return 'WAIT'
    if not result or result.get('status') != 'PASS':
        raise ValueError('BASE_ONE_DAY_NOT_PASS')
    if (result.get('dayGroups') != 137108 or
            result.get('canonicalHash') != manifest.get('canonicalDayHash') or
            manifest.get('dayGroups') != 137108):
        raise ValueError('BASE_ONE_DAY_COUNT_OR_HASH_MISMATCH')
    if set(reports) != {'sqlite','single','daily'}:
        raise ValueError('BASE_ONE_DAY_REPORTS_MISSING')
    parity = reports['sqlite'].get('parity')
    if not parity or parity != result.get('transactionParity'):
        raise ValueError('BASE_TRANSACTION_HASH_MISSING')
    for report in reports.values():
        if (report.get('status') != 'PASS' or report.get('timestampGroupCount') != 137108 or
                report.get('coldResume',{}).get('status') != 'PASS' or
                report.get('idempotencyRetry') != 'PASS' or
                report.get('independentVerification',{}).get('status') != 'PASS' or
                report.get('parity') != parity):
            raise ValueError('BASE_INDEPENDENT_GATE_OR_TRANSACTION_HASH_FAILED')
    return 'PASS'

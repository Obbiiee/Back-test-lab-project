"""Versioned observed-tick simulation profiles.

Version 1 retains its original conditional semantics. Version 2 is an explicit
QA-only technical historical simulation policy; it does not attest broker
execution, data completeness, or third-party usage rights.
"""
from dataclasses import dataclass
import json

from contracts.canonical import canonical_bytes, content_hash
from contracts.primitives import digest, identifier, require
from ticks.contracts import keys

ENGINE_VERSION = 'BTL-TICK-EXECUTION-OBSERVED-1'
MODEL = 'CONDITIONAL_OBSERVED_TICK_SIMULATION'
MODEL_V2 = 'HISTORICAL_TECHNICAL_TICK_SIMULATION_V2'
_PROFILE_V2 = dict(schemaVersion=1, artifact='BTL-HISTORICAL-TECHNICAL-SIMULATION-PROFILE-2')
_CHECKS_V2 = ('TIMESTAMP_ORDER', 'BID_ASK_VALIDITY', 'ATOMIC_TIMESTAMP_GROUPS',
              'IMMUTABLE_SOURCE_IDENTITY', 'DETERMINISTIC_QUOTE_INTERPRETATION',
              'INSTRUMENT_SPECIFICATION', 'ANTI_LOOKAHEAD')
_FIXED = dict(schemaVersion=1, artifact='BTL-OBSERVED-EXECUTION-PROFILE-1',
              engineVersion=ENGINE_VERSION, model=MODEL, symbol='XAUUSD',
              baseCurrency='XAU', quoteCurrency='USD', accountCurrency='USD',
              conversion=None, tickSize='0.001', priceScale='1000', contractSize='100',
              lotStep='0.01', minLot='0.01', maxLot='100', moneyScale=2,
              commissionModel='NONE', commissionPerLotSide='0', commissionCurrency='USD',
              slippageModel='NONE', latencyModel='ZERO', maxObservedSilenceNs='60000000000')


def validate_profile(raw):
    model = raw.get('model')
    if model == MODEL_V2:
        keys(raw, 'engineVersion model symbol baseCurrency quoteCurrency accountCurrency conversion tickSize priceScale contractSize lotStep minLot maxLot moneyScale commissionModel commissionPerLotSide commissionCurrency slippageModel latencyModel maxObservedSilenceNs primary schemaVersion artifact technicalEligibility gapPolicy sourceQuality executionLabel')
        fixed = dict(_FIXED, **_PROFILE_V2, model=MODEL_V2)
        require(type(raw['schemaVersion']) is int and raw['schemaVersion'] == 1 and
                raw['artifact'] == 'BTL-HISTORICAL-TECHNICAL-SIMULATION-PROFILE-2',
                'profileVersion', 'REFUSED_MODEL')
        eligibility = raw['technicalEligibility']
        keys(eligibility, 'schemaVersion artifact policyVersion qualificationReceiptHash checks')
        require(eligibility['schemaVersion'] == 1 and eligibility['artifact'] == 'BTL-HISTORICAL-TECHNICAL-ELIGIBILITY-1' and
                eligibility['policyVersion'] == '1' and eligibility['checks'] == list(_CHECKS_V2),
                'technicalEligibility', 'REFUSED_TECHNICAL_ELIGIBILITY')
        digest(eligibility['qualificationReceiptHash'], 'qualificationReceiptHash')
        gap = raw['gapPolicy']
        keys(gap, 'schemaVersion artifact version mode silenceThresholdNs closureEvidence')
        require(gap == dict(schemaVersion=1, artifact='BTL-OBSERVED-GAP-POLICY-2', version='2',
                            mode='OBSERVED_QUOTES_ONLY', silenceThresholdNs='60000000000',
                            closureEvidence='SOURCE_QUALITY_ONLY'),
                'gapPolicy', 'REFUSED_GAP_POLICY')
        quality = raw['sourceQuality']
        keys(quality, 'schemaVersion artifact provenance completeness freshness rights')
        require(quality == dict(schemaVersion=1, artifact='BTL-HISTORICAL-SOURCE-DISCLOSURE-1',
                                provenance='PROVIDER_OBSERVATION', completeness='UNKNOWN',
                                freshness='UNKNOWN', rights='UNKNOWN'),
                'sourceQuality', 'REFUSED_SOURCE_DISCLOSURE')
        require(raw['executionLabel'] == 'EXPERIMENTAL — UNVERIFIED SOURCE — SIMULATED EXECUTION',
                'executionLabel', 'REFUSED_EXECUTION_LABEL')
    else:
        keys(raw, ' '.join(_FIXED)+' primary')
        fixed = _FIXED
        require(model == MODEL, 'model', 'REFUSED_MODEL')
    for field, value in fixed.items():
        require(type(raw[field]) is type(value) and raw[field] == value,
                field, 'REFUSED_OBSERVED_MODEL_ASSUMPTION')
    source = raw['primary']
    keys(source, 'datasetId datasetVersion providerId feedId feedInstrumentId providerSymbol evidenceClass')
    for field in ('datasetId', 'providerId', 'feedId', 'feedInstrumentId', 'providerSymbol'):
        identifier(source[field], field)
    digest(source['datasetVersion'], 'datasetVersion')
    require(source['providerSymbol'] == 'XAUUSD' and source['evidenceClass'] == 'PROVIDER_OBSERVATION'
            and source['providerId'] != 'SYNTHETIC' and not source['datasetId'].startswith('synthetic:'),
            'primary', 'REFUSED_OBSERVED_SOURCE_IDENTITY')
    result = canonical_bytes(raw)
    require(len(result) <= 16384, 'profileBytes')
    return result


def historical_technical_profile(raw, qualification_hash):
    """Build the explicit QA-only profile bound to a technical proof receipt."""
    digest(qualification_hash, 'qualificationReceiptHash')
    result = dict(raw)
    result.update(schemaVersion=1, artifact='BTL-HISTORICAL-TECHNICAL-SIMULATION-PROFILE-2', model=MODEL_V2)
    result['technicalEligibility'] = dict(schemaVersion=1,
        artifact='BTL-HISTORICAL-TECHNICAL-ELIGIBILITY-1', policyVersion='1',
        qualificationReceiptHash=qualification_hash, checks=list(_CHECKS_V2))
    result['gapPolicy'] = dict(schemaVersion=1, artifact='BTL-OBSERVED-GAP-POLICY-2', version='2',
        mode='OBSERVED_QUOTES_ONLY', silenceThresholdNs='60000000000',
        closureEvidence='SOURCE_QUALITY_ONLY')
    result['sourceQuality'] = dict(schemaVersion=1, artifact='BTL-HISTORICAL-SOURCE-DISCLOSURE-1',
        provenance='PROVIDER_OBSERVATION', completeness='UNKNOWN', freshness='UNKNOWN', rights='UNKNOWN')
    result['executionLabel'] = 'EXPERIMENTAL — UNVERIFIED SOURCE — SIMULATED EXECUTION'
    return result


@dataclass(frozen=True)
class ObservedExecutionProfile:
    _bytes: bytes

    def __post_init__(self):
        require(type(self._bytes) is bytes and len(self._bytes) <= 16384, 'profileBytes')
        require(validate_profile(json.loads(self._bytes)) == self._bytes, 'canonicalProfile')

    @classmethod
    def from_wire(cls, raw):
        return cls(validate_profile(raw))

    @property
    def wire(self):
        return json.loads(self._bytes)

    @property
    def profile_hash(self):
        return content_hash(self.wire)

"""Frozen conditional observation profile; codec validity grants no source admission."""
from dataclasses import dataclass
import json

from contracts.canonical import canonical_bytes, content_hash
from contracts.primitives import digest, identifier, require
from ticks.contracts import keys

ENGINE_VERSION = 'BTL-TICK-EXECUTION-OBSERVED-1'
MODEL = 'CONDITIONAL_OBSERVED_TICK_SIMULATION'
_FIXED = dict(schemaVersion=1, artifact='BTL-OBSERVED-EXECUTION-PROFILE-1',
              engineVersion=ENGINE_VERSION, model=MODEL, symbol='XAUUSD',
              baseCurrency='XAU', quoteCurrency='USD', accountCurrency='USD',
              conversion=None, tickSize='0.001', priceScale='1000', contractSize='100',
              lotStep='0.01', minLot='0.01', maxLot='100', moneyScale=2,
              commissionModel='NONE', commissionPerLotSide='0', commissionCurrency='USD',
              slippageModel='NONE', latencyModel='ZERO', maxObservedSilenceNs='60000000000')


def validate_profile(raw):
    keys(raw, ' '.join(_FIXED)+' primary')
    for field, value in _FIXED.items():
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

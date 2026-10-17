"""Short authored demos only; no historical month or provider-specification claim."""
from dataclasses import dataclass
from fractions import Fraction
from functools import lru_cache
from contracts.primitives import require
from market_data.instruments import INSTRUMENTS, instrument
from ticks.provider import SyntheticTickProvider
from .contracts import text
from .conversion import conversion_route
from .profile_v2 import ExecutionProfileV2, ENGINE_VERSION

START_NS=1577836800000000000
STEP_NS=15000000000
PERIOD="2020-01"
_BASE={"AUDUSD":65000,"EURGBP":85000,"NZDUSD":60000,"USDCHF":90000,"AUDJPY":98000,"CADJPY":110000,
       "EURUSD":110000,"GBPUSD":125000,"NZDJPY":90000,"USDCAD":135000,"CHFJPY":165000,"EURJPY":160000,
       "EURNZD":180000,"GBPJPY":190000,"USDJPY":150000,"XAUUSD":200000}

def scale(symbol):return 100 if symbol=="XAUUSD" else 1000 if symbol.endswith("JPY") else 100000

def authored_provider(symbol,*,conversion=False):
    units=scale(symbol);rows=[]
    for i in range(96):
        phase=i%32;offset=0 if conversion else 5*(phase if phase<=16 else 32-phase)
        bid=_BASE[symbol]+offset
        rows.append(dict(ordinal=str(i),timeNs=str(START_NS+i*STEP_NS),bid=text(Fraction(bid,units)),ask=text(Fraction(bid+2,units)),sequence=None))
    return SyntheticTickProvider(rows,dataset_id="synthetic:v2-demo:"+("conversion:" if conversion else "primary:")+symbol,execution_fixture=True)

@dataclass(frozen=True)
class FixtureBundle:
    profile: ExecutionProfileV2
    primary: object
    conversion: object

@lru_cache(maxsize=16)
def bundle(symbol):
    spec=instrument(symbol);primary=authored_provider(symbol);fx=None;pin=None
    if spec.quote!="USD":
        route,_=conversion_route(spec.quote);fx=authored_provider(route,conversion=True)
        pin=dict(currency=spec.quote,symbol=route,datasetId=fx.dataset_id,datasetVersion=fx.dataset_version,
                 providerId="SYNTHETIC",feedId="TEST_ONLY",feedInstrumentId="SYNTHETIC_INSTRUMENT",maxAgeNs="60000000000")
    profile=ExecutionProfileV2.from_wire(dict(schemaVersion=1,artifact="BTL-EXECUTION-PROFILE-2",engineVersion=ENGINE_VERSION,
        model="AUTHORED_SYNTHETIC_ONLY",symbol=symbol,baseCurrency=spec.base,quoteCurrency=spec.quote,accountCurrency="USD",
        primary=dict(datasetId=primary.dataset_id,datasetVersion=primary.dataset_version,providerId="SYNTHETIC",feedId="TEST_ONLY",feedInstrumentId="SYNTHETIC_INSTRUMENT",evidenceClass="SYNTHETIC_CONTRACT_ONLY"),
        conversion=pin,tickSize=text(Fraction(1,scale(symbol))),priceScale=str(scale(symbol)),contractSize="100" if symbol=="XAUUSD" else "100000",
        lotStep="0.01",minLot="0.01",maxLot="100",moneyScale=2,commissionModel="NONE",commissionPerLotSide="0",commissionCurrency="USD",slippageModel="NONE",latencyModel="ZERO"))
    return FixtureBundle(profile,primary,fx)

def binding(profile):
    parsed=ExecutionProfileV2.from_wire(profile);result=bundle(parsed.wire["symbol"])
    require(result.profile.profile_hash==parsed.profile_hash,"source","SOURCE_VERSION_UNAVAILABLE")
    return result

def catalogue():
    return [dict(symbol=s,baseCurrency=v.base,quoteCurrency=v.quote,model="AUTHORED_SYNTHETIC_ONLY",label="SHORT SYNTHETIC DEMO; NOT HISTORICAL MONTH",startPeriod=PERIOD)
            for s,v in INSTRUMENTS.items()]

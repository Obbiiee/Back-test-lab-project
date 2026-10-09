"""Explicit synthetic CLI inspection through the real durable execution path.

Run migrations separately on an isolated local DB. Never reads a provider CSV,
starts a server, rewrites a session, or imports legacy account data.
"""
import argparse
import json
import os

from application.models import TrustedScope
from contracts.models import MethodPolicy
from ticks.provider import SyntheticTickProvider
from .controller import ExecutionController
from .postgres import PostgresExecutionStore


def fixture_provider():
    return SyntheticTickProvider([
        dict(ordinal="0",timeNs="1",bid="100",ask="101",sequence=None),
        dict(ordinal="1",timeNs="2",bid="104",ask="105",sequence=None)
    ],dataset_id="synthetic:execution-demo",execution_fixture=True)


def fixture_profile():
    return dict(instrumentId="XAUUSD",providerId="SYNTHETIC",feedId="TEST_ONLY",feedInstrumentId="SYNTHETIC_INSTRUMENT",
                quoteCurrency="USD",accountCurrency="USD",tickSize="0.01",priceScale="100",contractSize="100",
                lotStep="0.01",minLot="0.01",maxLot="100",moneyScale=2,commissionModel="NONE",
                commissionPerLotSide="0",slippageModel="NONE",latencyModel="ZERO")


def main():
    parser=argparse.ArgumentParser(description="SYNTHETIC / TEST ONLY; not a broker fill or historical-data benchmark")
    parser.add_argument("--workspace",required=True)
    parser.add_argument("--session",required=True)
    parser.add_argument("--inspect",action="store_true",help="Read existing evidence without creating, executing or rewinding")
    args=parser.parse_args()
    scope=TrustedScope(args.workspace,"fixture:local-operator")
    controller=ExecutionController(PostgresExecutionStore(os.environ["BTL_DATABASE_URL"]),fixture_provider())
    if not args.inspect:
        controller.create(scope,args.session,fixture_profile(),MethodPolicy("fixture:free","0"*64,"FREE_STYLE",False,()))
        controller.apply(scope,dict(schemaVersion=1,artifact="BTL-TICK-EXECUTION-COMMAND-1",sessionId=args.session,
            commandId="demo:order",expectedRevision=0,kind="OPEN",payload=dict(side="LONG",orderType="MARKET",
            workflow="QUICK",entry="101",quantity="0.1",sl="99",tp="104",riskPercent="1",observations=[])))
        controller.apply(scope,dict(schemaVersion=1,artifact="BTL-TICK-EXECUTION-COMMAND-1",sessionId=args.session,
            commandId="demo:advance",expectedRevision=1,kind="ADVANCE",payload={"targetNs":"2"}))
    report=controller.inspect(scope,args.session,maximum=256)
    print(json.dumps(dict(label="SYNTHETIC / TEST ONLY",model="SIMULATED_QUOTE_BASELINE_NOT_BROKER_EXECUTION",
                          limitations=["No real provider, margin, conversion or broker liquidity model", "No browser/Method/Session product integration"],
                          **report),indent=2,ensure_ascii=False))


if __name__=="__main__":
    main()

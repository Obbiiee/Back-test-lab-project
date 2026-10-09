"""S-6 explicit pure-calculator oracle; no execution, datasets or package install.

Optional exact-pin donor mode executes original function ASTs and required pure
helpers, not package initialization/download/reporting. No arithmetic is patched.
"""
import ast
from copy import deepcopy
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from warnings import warn

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from execution.analysis import metrics

def rows(values):
    return [dict(net=str(v)) for v in values]

def rational(n, d=1):
    value=Fraction(n,d)
    return dict(numerator=str(value.numerator),denominator=str(value.denominator))

def oracle():
    sample=rows(['200','0','-100','0']);before=deepcopy(sample);got=metrics(sample)
    assert got['tradeCount']==4 and (got['wins'],got['losses'],got['breakeven'])==(1,1,2)
    for key,expected in dict(winRate=rational(1,4),averageWin=rational(200),averageLoss=rational(-100),expectancy=rational(25),profitFactor=rational(2)).items():assert got[key]==expected,(key,got[key])
    assert sample==before
    assert metrics([])['winRate'] is None and metrics([])['profitFactor'] is None
    assert metrics(rows([1,2]))['profitFactor'] is None
    assert metrics(rows([0,0]))['winRate']==rational(0)
    assert metrics(rows([1,1,0,1,-1,-1,0,-1]))['maxWinStreak']==2
    assert metrics(rows([1,1,0,1,-1,-1,0,-1]))['maxLossStreak']==2
    assert metrics(rows(['0.01','0.01','0']))['expectancy']==rational(1,150)
    assert metrics(rows(['9007199254740993','-9007199254740992']))['expectancy']==rational(1,2)
    # Caller grouping supplies one final net per completed position. Unresolved,
    # open and partial events never become a calculator denominator here.
    assert got['rEligible']==0 and got['rExcluded']==4 and got['monteCarlo']['status']=='INSUFFICIENT_SAMPLE'
    print('PASS S-6 exact completed-position goldens, BE denominators/streaks, missing-R disclosure, empty/no-loss, decimal and >2**53 precision.')

def functions(file,names,namespace):
    tree=ast.parse(file.read_text(encoding='utf8'))
    selected=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name in names]
    assert {n.name for n in selected}==set(names),'Missing pinned primitive'
    # Preserve original bodies/annotations/helpers. No imports or top-level
    # package side effects, plots, network functions or arithmetic substitutions.
    exec(compile(ast.Module(body=selected,type_ignores=[]),str(file),'exec'),namespace)
    return {name:namespace[name] for name in names}

def compare(root):
    import numpy as np
    import pandas as pd
    pin='9ef4c6d0a4ffe7831f6ebba6a5824fd33a90c05a'
    def git(*args):return subprocess.check_output(['git','-C',str(root),*args],text=True).strip()
    assert git('rev-parse','HEAD')==pin and git('status','--porcelain')==''
    namespace={'_np':np,'_pd':pd,'Returns':pd.Series|pd.DataFrame,'warn':warn}
    helpers=functions(root/'quantstats/utils.py',['aggregate_returns','_count_consecutive','_looks_like_returns','_prepare_prices','validate_input','QuantStatsError','DataValidationError'],namespace)
    namespace['_utils']=SimpleNamespace(**helpers)
    names=['avg_return','avg_win','avg_loss','win_rate','profit_factor','consecutive_wins','consecutive_losses','to_drawdown_series','_get_baseline_value']
    qs=functions(root/'quantstats/stats.py',names,namespace)
    data=pd.Series([200.,0.,-100.,0.]);before=data.copy()
    def run(name,source=data):return qs[name](source,prepare_returns=False)
    assert run('win_rate')==.5 and run('avg_return')==50
    assert run('avg_win')==200 and run('avg_loss')==-100 and run('profit_factor')==2
    assert pd.isna(run('avg_win',pd.Series([-1.,0.])))
    assert np.isinf(run('profit_factor',pd.Series([1.,2.])))
    assert run('profit_factor',pd.Series([0.,0.]))==0
    for name in ['consecutive_wins','consecutive_losses']:assert run(name,pd.Series([1.,1.,0.,1.,-1.,-1.,0.,-1.]))==2
    large=pd.Series([9007199254740993.,-9007199254740992.])
    assert run('avg_return',large)==0, 'Binary floats must not be presented as exact cash'
    equity=pd.Series([100.,110.,105.,120.,90.],index=pd.date_range('2020-01-01',periods=5))
    drawdown=qs['to_drawdown_series'](equity)
    assert abs(drawdown.iloc[-1]+.25)<1e-12
    for n in range(1,len(equity)+1):assert np.allclose(qs['to_drawdown_series'](equity.iloc[:n]),drawdown.iloc[:n])
    assert helpers['_looks_like_returns'](pd.Series([.5,.4])) is True,'Cash <1 would be reinterpreted as returns without a guard'
    pd.testing.assert_series_equal(data,before)
    report=dict(pin=pin,scope='Original selected function ASTs; package integration NOT certified',numpy=np.__version__,pandas=pd.__version__,licenseSha256=hashlib.sha256((root/'LICENSE.txt').read_bytes()).hexdigest(),statsSha256=hashlib.sha256((root/'quantstats/stats.py').read_bytes()).hexdigest(),donorWinRate=.5,btlWinRate=rational(1,4),donorAverageReturn=50,btlExpectancy=rational(25),noLossProfitFactor='Infinity vs BTL null',averageWinEmpty='NaN vs BTL null',largeCashMean='0 vs exact BTL 1/2',streakParity=True,positiveCashDrawdownPercentParity=True,smallCashMisclassified=True,decision='KEEP exact BTL; no QuantStats production dependency')
    print(json.dumps(report,sort_keys=True))
    print('PASS S-6 pinned primitive scope evaluation; gaps are recorded, not repaired or relabelled parity.')

if __name__=='__main__':
    oracle()
    if os.getenv('BTL_QUANTSTATS_ROOT'):compare(Path(os.environ['BTL_QUANTSTATS_ROOT']))

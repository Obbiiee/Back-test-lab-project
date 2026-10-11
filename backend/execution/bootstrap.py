"""Pure descriptive bootstrap of canonical completed net R, never a forecast.

Primitive, order and quantiles frozen before implementation in the existing
Research Metrics Contract. No provider, account, storage, clock or hidden seed.
"""
from fractions import Fraction
from math import lcm

from contracts.canonical import content_hash
from contracts.primitives import require
from .analysis import ratio
from .contracts import MAX_ORDERS

PRNG_VERSION = 'BTL-XORSHIFT32-13-17-5-1'
PATHS = 10000
MINIMUM = 30
DOMAIN = 0xffffffff


def validate_seed(seed):
    require(type(seed) is int and 1<=seed<=DOMAIN,'seed')


class ResearchRandom:
    def __init__(self, seed):
        validate_seed(seed)
        self.state = seed

    def word(self):
        x = self.state
        x = (x^(x<<13)) & DOMAIN
        x = (x^(x>>17)) & DOMAIN
        x = (x^(x<<5)) & DOMAIN
        self.state = x
        return x

    def index(self, size):
        require(type(size) is int and 1<=size<=MAX_ORDERS,'sampleSize')
        ceiling = (DOMAIN//size)*size
        while True:
            value = self.word()-1
            if value<ceiling:
                return value%size


def bootstrap(completed, seed):
    random = ResearchRandom(seed)
    require(type(completed) is list and len(completed)<=MAX_ORDERS,'bootstrapInput','REFUSED_RESEARCH_LIMIT')
    inputs = [dict(id=row['id'],net=row['net'],rMultiple=row.get('rMultiple')) for row in completed]
    require(len({row['id'] for row in inputs})==len(inputs),'completedIdentity','CORRUPT_RECORD')
    values = [Fraction(int(row['rMultiple']['numerator']),int(row['rMultiple']['denominator']))
              for row in inputs if row['rMultiple'] is not None]
    count = len(values)
    result = dict(schemaVersion=1,artifact='BTL-DESCRIPTIVE-BOOTSTRAP-1',
        status='INSUFFICIENT_SAMPLE' if count<MINIMUM else 'COMPLETE',
        eligible=count,exclusions=len(inputs)-count,minimum=MINIMUM,
        seed=seed,prngVersion=PRNG_VERSION,paths=PATHS,pathsComputed=0,
        inputHash=content_hash(dict(schemaVersion=1,artifact='BTL-BOOTSTRAP-INPUT-1',completed=inputs)),
        quantileMethod='NEAREST_RANK',model='DESCRIPTIVE_OBSERVED_NET_R_NOT_FORECAST',
        terminalR=None,maxDrawdownR=None,longestNegativeStreak=None)
    if count<MINIMUM:
        return result
    denominator = lcm(*(v.denominator for v in values))
    units = [v.numerator*(denominator//v.denominator) for v in values]
    terminal, drawdowns, streaks = [], [], []
    for _path in range(PATHS):
        total=peak=drawdown=run=streak=0
        for _step in range(count):
            value=units[random.index(count)]
            total+=value;peak=max(peak,total);drawdown=max(drawdown,peak-total)
            run=run+1 if value<0 else 0;streak=max(streak,run)
        terminal.append(total);drawdowns.append(drawdown);streaks.append(streak)
    def quantiles(samples, percentages, money):
        samples.sort()
        return {f'p{p}':ratio(Fraction(samples[(p*PATHS+99)//100-1],denominator)) if money
                else samples[(p*PATHS+99)//100-1] for p in percentages}
    result.update(pathsComputed=PATHS,terminalR=quantiles(terminal,(5,50,95),True),
                  maxDrawdownR=quantiles(drawdowns,(50,95,99),True),
                  longestNegativeStreak=quantiles(streaks,(50,95,99),False))
    return result

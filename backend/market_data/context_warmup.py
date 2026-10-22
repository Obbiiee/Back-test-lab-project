"""Unwired controller-side OHLC context helpers; never execution evidence.

Counts address finite lookbacks and normalized recursive seed decay only, NOT
absolute indicator convergence, source rights, market completeness or tick
eligibility. An authorized bounded provider/pagination adapter is still needed.
Fixed UTC intraday/daily buckets only; calendar week/month adapters are separate.
"""
from collections import deque
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
import math

TIMEFRAMES = (60, 180, 300, 900, 1800, 3600, 7200, 14400, 86400)
MAX_BARS = 100000


def _integer(value, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError('Invalid bounded integer')
    return value


@dataclass(frozen=True)
class IndicatorSpec:
    kind: str
    timeframe_seconds: int
    period: int = 14
    fast_period: int = 12
    slow_period: int = 26
    signal_period: int = 9
    k_period: int = 14
    d_period: int = 3


@dataclass(frozen=True)
class FrameWarmup:
    timeframe_seconds: int
    required_bars: int
    seed_decay_tolerance: float
    basis: str = field(default='SEED_DECAY_ONLY_NOT_CONVERGENCE_CERTIFICATE', init=False)


def _recursive(seed_bars, alpha, tolerance):
    if alpha == 1:
        return seed_bars
    return seed_bars + math.ceil(math.log(tolerance) / math.log1p(-alpha))


def plan_warmup(indicators, *, seed_decay_tolerance=1e-6, buffer_bars=0):
    """Union by timeframe, never sum overlapping indicator lookbacks.

EMA is SMA-seeded; RSI requires N deltas/N+1 closes; ATR also reserves a prior close.
MACD budgets one third of normalized seed tolerance to each recursive channel.
This does not guarantee a bound on nonlinear RSI or arbitrary price amplitudes.
"""
    if type(seed_decay_tolerance) not in (int, float) or not 1e-12 <= seed_decay_tolerance < 1:
        raise ValueError('Invalid seed-decay tolerance')
    _integer(buffer_bars, 0, 10000)
    tolerance = float(seed_decay_tolerance)
    counts = {}
    for index, spec in enumerate(indicators):
        if index >= 128:
            raise ValueError('Too many indicator configurations')
        if type(spec) is not IndicatorSpec or spec.timeframe_seconds not in TIMEFRAMES or type(spec.timeframe_seconds) is not int:
            raise ValueError('Unsupported indicator/timeframe')
        p = _integer(spec.period, 1, 1000)
        if spec.kind in ('SMA', 'BOLLINGER'):
            count = p
        elif spec.kind == 'EMA':
            count = _recursive(p, 2 / (p + 1), tolerance)
        elif spec.kind in ('RSI', 'ATR'):
            if spec.kind == 'RSI' and p < 2:
                raise ValueError('RSI requires at least two periods')
            count = _recursive(p + 1, 1 / p, tolerance)
        elif spec.kind == 'MACD':
            fast = _integer(spec.fast_period, 1, 1000)
            slow = _integer(spec.slow_period, 1, 1000)
            signal = _integer(spec.signal_period, 1, 1000)
            if fast >= slow:
                raise ValueError('MACD fast period must precede slow')
            primary = max(_recursive(fast, 2 / (fast + 1), tolerance / 3),
                          _recursive(slow, 2 / (slow + 1), tolerance / 3))
            count = primary + _recursive(signal, 2 / (signal + 1), tolerance / 3)
        elif spec.kind == 'STOCHASTIC':
            count = _integer(spec.k_period, 1, 1000) + _integer(spec.d_period, 1, 1000) - 1
        else:
            raise ValueError('Unsupported indicator')
        counts[spec.timeframe_seconds] = max(counts.get(spec.timeframe_seconds, 0), count)
    return tuple(FrameWarmup(tf, _integer(count + buffer_bars, 1, MAX_BARS), tolerance)
                 for tf, count in sorted(counts.items()))


@dataclass(frozen=True)
class ContextBar:
    open_ns: int
    close_ns: int
    open: str
    high: str
    low: str
    close: str


@dataclass(frozen=True)
class ContextSelection:
    candles: tuple
    required_bars: int
    available_bars: int
    state: str
    execution_authority: bool = field(default=False, init=False)


def completed_context(bars, plan, *, trusted_start_ns):
    """Retain only latest completed reference bars, entirely before start.

Caller owns authorization/provenance and bounded IO. Never expose its provider,
future row count, gaps, EOF, or cursor to the consumer. Missing candles are not
invented; enough bars is NOT a coverage/rights/convergence assertion. No trade,
financial state, price conversion, indicator mutation or execution API exists.
"""
    _integer(trusted_start_ns, 0, 2**63 - 1)
    if type(plan) is not FrameWarmup or type(plan.timeframe_seconds) is not int or plan.timeframe_seconds not in TIMEFRAMES:
        raise ValueError('Invalid timeframe plan')
    _integer(plan.required_bars, 1, MAX_BARS)
    result = deque(maxlen=plan.required_bars)
    previous_close = None
    step = plan.timeframe_seconds * 1000000000
    for bar in bars:
        if type(bar) is not ContextBar:
            raise ValueError('Invalid reference bar')
        _integer(bar.close_ns, 0, 2**63 - 1)
        # Ignore future candle content before examining its OHLC or opening time.
        if bar.close_ns > trusted_start_ns:
            continue
        _integer(bar.open_ns, 0, 2**63 - 1)
        if bar.open_ns % step or bar.close_ns - bar.open_ns != step:
            raise ValueError('Reference bar is not a complete aligned UTC bucket')
        if previous_close is not None and bar.open_ns < previous_close:
            raise ValueError('Overlapping, duplicated or disordered reference bars')
        try:
            values = tuple(Decimal(v) for v in (bar.open, bar.high, bar.low, bar.close)
                           if type(v) is str and 0 < len(v) <= 128)
        except InvalidOperation as error:
            raise ValueError('Invalid exact reference price') from error
        if len(values) != 4 or not all(v.is_finite() and v > 0 for v in values):
            raise ValueError('Invalid exact reference price')
        o, h, l, c = values
        if not l <= min(o, c) <= max(o, c) <= h:
            raise ValueError('Invalid OHLC envelope')
        previous_close = bar.close_ns
        result.append(bar)
    rows = tuple(result)
    return ContextSelection(rows, plan.required_bars, len(rows),
                            'SUFFICIENT_COUNT' if len(rows) == plan.required_bars else 'WARMUP_INCOMPLETE')

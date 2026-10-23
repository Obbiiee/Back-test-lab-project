"""Controller-private, bounded BID reference OHLC from accepted disk ticks.

Not execution/source-rights admission. No hosted route or consumer provider
capability. UNKNOWN coverage stays unknown; no empty buckets are invented.
"""
from collections import deque
from dataclasses import dataclass, field
from decimal import Decimal

from contracts.primitives import require
from ticks.provider import Cancellation
from ticks.storage_v2 import DiskTickProvider
from .context_warmup import ContextBar, ContextSelection, FrameWarmup, TIMEFRAMES, MAX_BARS, completed_context


@dataclass(frozen=True)
class TickContext:
    selection: ContextSelection
    ambiguous_buckets: int
    price_basis: str = field(default='BID_OBSERVATIONS', init=False)
    coverage: str = field(default='UNKNOWN', init=False)
    freshness: str = field(default='UNKNOWN', init=False)
    execution_authority: bool = field(default=False, init=False)


def load_tick_context(provider, plan, *, trusted_start_ns, lookback_buckets=None,
                      max_events=100000, max_pages=512, cancellation=None):
    """Return completed reference buckets before start, never settle from them.

Provider and dataset metadata remain controller-side. A bucket whose equal-time
quotes have differing BID values is omitted: raw ordinal cannot decide open or
close. This conservative rule also omits interior ambiguous groups. Missing or
ambiguous buckets are never interpolated. SUFFICIENT_COUNT is count-only, not
market completeness, freshness, convergence or permission certification.

Any IO/group/cancellation budget failure returns no partial selection. The
caller must not substitute a previously sufficient selection on failure.
"""
    require(type(provider) is DiskTickProvider, 'provider', 'CONTEXT_PROVIDER_REFUSED')
    require(type(plan) is FrameWarmup and type(plan.timeframe_seconds) is int
            and plan.timeframe_seconds in TIMEFRAMES and type(plan.required_bars) is int
            and 1 <= plan.required_bars <= MAX_BARS, 'plan', 'CONTEXT_PLAN_REFUSED')
    require(type(trusted_start_ns) is int and 0 <= trusted_start_ns <= 2**63-1,
            'start', 'CONTEXT_START_REFUSED')
    lookback = plan.required_bars*2 if lookback_buckets is None else lookback_buckets
    require(type(lookback) is int and plan.required_bars <= lookback <= 2*MAX_BARS,
            'lookback', 'CONTEXT_BUDGET_REFUSED')
    require(type(max_events) is int and 1 <= max_events <= 1000000
            and type(max_pages) is int and 1 <= max_pages <= 4096,
            'budget', 'CONTEXT_BUDGET_REFUSED')
    cancel = cancellation or Cancellation(); cancel.check()
    step = plan.timeframe_seconds*1000000000
    end = trusted_start_ns//step*step
    begin = max(0, end-lookback*step)
    if begin == end:
        return TickContext(completed_context([], plan, trusted_start_ns=trusted_start_ns), 0)
    dataset, version = provider.dataset_id, provider.dataset_version
    position = provider.locate_v2(dataset, version, str(begin))['position']
    pages = events = 0; group_time = None; group_bid = None; group_count = 0
    ambiguous_group = False; bucket = None; prices = None; bucket_bad = False
    bars = deque(maxlen=plan.required_bars); ambiguous = 0

    def finish_bucket():
        nonlocal ambiguous
        if bucket is not None:
            if bucket_bad:
                ambiguous += 1
            else:
                bars.append(ContextBar(bucket, bucket+step, *prices))

    def finish_group():
        nonlocal bucket, prices, bucket_bad
        if group_time is None:
            return
        opening = group_time//step*step
        if opening != bucket:
            finish_bucket(); bucket = opening; prices = [group_bid]*4; bucket_bad = False
        else:
            prices[1] = max(prices[1], group_bid, key=Decimal)
            prices[2] = min(prices[2], group_bid, key=Decimal)
            prices[3] = group_bid
        bucket_bad = bucket_bad or ambiguous_group

    stop = False
    while position is not None and not stop:
        cancel.check()
        require(pages < max_pages and events < max_events, 'read', 'CONTEXT_BUDGET_EXCEEDED')
        page = provider.read_page_v2(dataset, version, position, min(256, max_events-events))
        pages += 1; events += len(page['events'])
        for event in page['events']:
            cancel.check()
            stamp = int(event['timeNs'])
            if stamp >= end:
                stop = True; break
            require(stamp >= begin and (group_time is None or stamp >= group_time),
                    'order', 'ORDER_REVERSAL')
            if stamp != group_time:
                finish_group(); group_time = stamp; group_bid = event['bid']
                group_count = 0; ambiguous_group = False
            group_count += 1
            require(group_count <= 1024, 'group', 'GROUP_LIMIT')
            ambiguous_group = ambiguous_group or Decimal(event['bid']) != Decimal(group_bid)
        position = page['nextPosition']
    cancel.check(); finish_group(); finish_bucket()
    selection = completed_context(bars, plan, trusted_start_ns=trusted_start_ns)
    return TickContext(selection, ambiguous)

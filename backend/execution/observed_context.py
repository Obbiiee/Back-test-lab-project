"""Controller-only preparation of an observed start and separate prior OHLC.

This is not a Session/API response, financial profile, or revealed-view extension.
Reference candles retain their own reference-only role; they never become tick
execution evidence or claim the observed feed's quote/mid-price provenance.
"""
from dataclasses import dataclass

from contracts.primitives import require
from market_data.context_archive import PinnedContextArchive
from market_data.context_warmup import plan_warmup
from .observed_source import ObservedReplaySource


@dataclass(frozen=True)
class ObservedStartContext:
    dataset_id: str
    dataset_version: str
    start_ns: int
    # Each entry is (existing FrameWarmup, existing ContextSelection). Neither
    # type contains a provider, file pin/path, future extent, EOF or index handle.
    reference_frames: tuple


def prepare_observed_context(source, period, reference_archive, indicators, *,
                             seed_decay_tolerance=1e-6, buffer_bars=0):
    """Resolve the ACTUAL observed start before clipping reference warmup.

    The controller supplies separately pinned reference files and indicator
    configuration. Unavailable months refuse before reference I/O. Missing
    reference history stays WARMUP_INCOMPLETE; no tick aggregation or cross-feed
    price substitution is attempted. This result must not be serialized as the
    existing EXACT_REVEALED_MID_DISPLAY_ONLY chart-history wire artifact.
    """
    require(type(source) is ObservedReplaySource, 'observedSource')
    require(type(reference_archive) is PinnedContextArchive, 'referenceArchive')
    plans = plan_warmup(indicators, seed_decay_tolerance=seed_decay_tolerance,
                        buffer_bars=buffer_bars)
    start = source.start_for_period(period)
    frames = tuple((plan, reference_archive.select(plan, trusted_start_ns=start))
                   for plan in plans)
    return ObservedStartContext(source.dataset_id, source.version, start, frames)

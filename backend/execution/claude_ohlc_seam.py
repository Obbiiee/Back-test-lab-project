"""Reversible seam: serve the product's past-chart context (BTL-PAST-CHART-CONTEXT-1) from precomputed OHLC objects.

Enabled only when BTL_CLAUDE_OHLC_ROOT is set (a LocalObjectStore directory = SIMULATION of the private R2 bucket). Unset -> the
product path is untouched. Same frozen artifact, same previous-calendar-month window, same 512-bar offset paging, same display basis,
so the frontend contract does not change. Only bars that ended before the Session start month leave this method (no look-ahead).
"""
import json
import os
import re
from datetime import datetime, timezone

import numpy as np

from contracts.primitives import require
from tools.claude_exp.ohlc import engine
from tools.claude_exp.ohlc.store import LocalObjectStore

TF = {'1m': 'M1', '3m': 'M3', '5m': 'M5', '15m': 'M15', '30m': 'M30', '1h': 'H1', '2h': 'H2', '4h': 'H4', 'D': 'D1'}
SECONDS = {'1m': 60, '3m': 180, '5m': 300, '15m': 900, '30m': 1800, '1h': 3600, '2h': 7200, '4h': 14400, 'D': 86400}
PAGE = 512
_stores = {}


def enabled():
    return bool(os.environ.get('BTL_CLAUDE_OHLC_ROOT'))


def _decimal(value, den):
    digits = len(str(den))                          # den = 2 * 10**s has s+1 digits; value/den = value*5 / 10**(s+1)
    q, r = divmod(int(value) * 5, 10 ** digits)
    return f'{q}.{r:0{digits}d}'


def past_context(state, timeframe, offset):
    require(timeframe in TF and type(offset) is int and 0 <= offset <= 50000, 'historyRequest', 'INVALID_INPUT')
    root = os.environ['BTL_CLAUDE_OHLC_ROOT']
    instrument = os.environ.get('BTL_CLAUDE_OHLC_INSTRUMENT', 'EURUSD')
    store = _stores.setdefault(root, LocalObjectStore(root))
    stamp = datetime.fromtimestamp(int(state['startNs']) // 10 ** 9, timezone.utc)
    py, pm = (stamp.year - 1, 12) if stamp.month == 1 else (stamp.year, stamp.month - 1)
    month = f'{py:04d}-{pm:02d}'
    start = int(datetime(py, pm, 1, tzinfo=timezone.utc).timestamp())
    end = int(datetime(stamp.year, stamp.month, 1, tzinfo=timezone.utc).timestamp())
    base = dict(schemaVersion=1, artifact='BTL-PAST-CHART-CONTEXT-1', datasetId=state['datasetId'], datasetVersion=state['datasetVersion'],
                startTime=start, endTime=end, timeframe=timeframe, priceBasis='EXACT_REVEALED_MID_DISPLAY_ONLY', volumeAvailable=False,
                coverage='UNKNOWN', executionAuthority=False, status='READY', candles=[], nextOffset=None)
    found = [k for k in store.list(f'ohlc/{engine.TRANSFORM_VERSION}/{instrument}/')
             if k.endswith(f'/MID/{month}/manifest.json') or k.endswith(f'/MID/{month}-manifest.json')]
    if not found:
        found = [k for k in store.list(f'ohlc/{engine.TRANSFORM_VERSION}/{instrument}/') if k.endswith('/manifest.json')]
        found = [k for k in found if json.loads(store.get(k)).get('month') == month and json.loads(store.get(k)).get('priceBasis') == 'MID']
    require(len(found) <= 1, 'ohlcSource', 'REFUSED_AMBIGUOUS_OHLC_SOURCE')
    if not found:
        return base
    manifest = json.loads(store.get(found[0]))
    require(manifest.get('transformVersion') == engine.TRANSFORM_VERSION, 'ohlcSource', 'REFUSED_OHLC_SOURCE')
    cols = engine.from_parquet_bytes(store.get(manifest['objects'][TF[timeframe]]['key']))
    width = SECONDS[timeframe]
    t = cols['t'] // 10 ** 9
    keep = np.flatnonzero((t >= start) & (t + width <= end))     # whole bars strictly before the Session month
    den = manifest['priceScaleDenominator']
    page = keep[offset:offset + PAGE]
    base['candles'] = [dict(time=int(t[i]), **{name: _decimal(cols[k][i], den) for name, k in (('open', 'o'), ('high', 'h'), ('low', 'l'), ('close', 'c'))})
                       for i in page]
    if offset + PAGE < len(keep):
        base['nextOffset'] = offset + PAGE
    return base

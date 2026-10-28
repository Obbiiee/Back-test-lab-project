"""Bounded controller-private reader for pinned reference OHLC archives.

No public route, execution evidence, source admission or price-feed splicing.
File pins and filesystem access belong only to the trusted controller.
"""
from dataclasses import dataclass
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from threading import RLock

from .context_warmup import ContextBar, completed_context

MAX_FILES = 24
MAX_FILE_BYTES = 4 * 1024 * 1024
MAX_FILE_ROWS = 50000
_FRAMES = {'1m': 60, '3m': 180, '5m': 300, '15m': 900, '30m': 1800,
           '1h': 3600, '2h': 7200, '4h': 14400, 'D': 86400}
_NAME = re.compile(r'[0-9]{4}-(?:0[1-9]|1[0-2])-(1m|3m|5m|15m|30m|1h|2h|4h|D)\.json')
_HASH = re.compile(r'[0-9a-f]{64}')


@dataclass(frozen=True)
class ContextFilePin:
    name: str
    sha256: str
    first_ns: int
    last_ns: int


def _refuse_constant(_):
    raise ValueError('Non-finite JSON number')


def _rows(raw, pin, timeframe):
    rows = json.loads(raw, parse_float=Decimal, parse_constant=_refuse_constant)
    if type(rows) is not list or not 1 <= len(rows) <= MAX_FILE_ROWS:
        raise ValueError('Reference file row bound')
    first = last = None
    for row in rows:
        if type(row) is not list or len(row) != 5 or type(row[0]) is not int:
            raise ValueError('Invalid reference row')
        moment = row[0] * 1000000000
        if not 0 <= moment <= 2**63 - 1 - timeframe * 1000000000:
            raise ValueError('Invalid reference timestamp')
        if first is None:
            first = moment
        if last is not None and moment <= last:
            raise ValueError('Disordered reference file')
        last = moment
        # Exact decimal tokens, never Python binary floats. completed_context
        # validates eligible OHLC and ignores future price content causally.
        prices = tuple(str(v) if type(v) in (int, Decimal, str) else '' for v in row[1:])
        yield ContextBar(moment, moment + timeframe * 1000000000, *prices)
    if (first, last) != (pin.first_ns, pin.last_ns):
        raise ValueError('Reference extent pin mismatch')


class PinnedContextArchive:
    """Private bounded I/O capability; never pass this object to a consumer."""
    def __init__(self, folder, pins):
        folder = Path(folder)
        if folder.is_symlink() or not folder.is_dir():
            raise ValueError('Invalid reference folder')
        if type(pins) not in (list, tuple) or len(pins) > 4096:
            raise ValueError('Reference pin bound')
        checked = {}
        for pin in pins:
            if type(pin) is not ContextFilePin or type(pin.name) is not str:
                raise ValueError('Invalid reference pin')
            match = _NAME.fullmatch(pin.name)
            if (match is None or type(pin.sha256) is not str or _HASH.fullmatch(pin.sha256) is None
                    or type(pin.first_ns) is not int or type(pin.last_ns) is not int
                    or not 0 <= pin.first_ns <= pin.last_ns <= 2**63 - 1 or pin.name in checked):
                raise ValueError('Invalid reference pin')
            checked[pin.name] = (pin, _FRAMES[match[1]])
        self.__folder, self.__pins = folder.resolve(), tuple(checked.values())
        self.__cache_lock = RLock()
        self.__selection_cache = {}

    def pin(self, name):
        if type(name) is not str:
            raise ValueError('Invalid reference pin')
        for pin, _ in self.__pins:
            if pin.name == name:
                return dict(name=pin.name,sha256=pin.sha256,firstNs=str(pin.first_ns),lastNs=str(pin.last_ns))
        return None

    def select(self, plan, *, trusted_start_ns, month=None):
        # Validate the trusted request before filesystem reads.
        completed_context((), plan, trusted_start_ns=trusted_start_ns)
        if month is not None and (type(month) is not str or re.fullmatch(r'[0-9]{4}-(0[1-9]|1[0-2])', month) is None):
            raise ValueError('Invalid reference month')
        candidates = sorted((p for p, frame in self.__pins if frame == plan.timeframe_seconds
                             and p.first_ns < trusted_start_ns
                             and (month is None or p.name.startswith(month+'-'))), key=lambda p: p.first_ns)
        if any(a.last_ns >= b.first_ns for a, b in zip(candidates, candidates[1:])):
            raise ValueError('Overlapping reference pins')
        # Use a bounded suffix. Too little history remains WARMUP_INCOMPLETE.
        selected = candidates[-MAX_FILES:]

        def read_pin(pin):
            path = self.__folder / pin.name
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(descriptor, 'rb') as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_FILE_BYTES:
                    raise ValueError('Reference file type or byte bound')
                raw = stream.read(MAX_FILE_BYTES + 1)
            if len(raw) > MAX_FILE_BYTES or hashlib.sha256(raw).hexdigest() != pin.sha256:
                raise ValueError('Reference file hash mismatch')
            return raw

        if len(selected) > 1:
            def bars():
                for pin in selected:
                    yield from _rows(read_pin(pin), pin, plan.timeframe_seconds)
            return completed_context(bars(), plan, trusted_start_ns=trusted_start_ns)

        # The same Session requests bounded 512-bar pages repeatedly. Reuse its
        # immutable clipped selection after rechecking the file hash each time;
        # never parse the full monthly JSON once per page. One selection is
        # retained per archive instance and remains controller-private.
        cache_key = (selected[0].name, selected[0].sha256, plan, trusted_start_ns, month) if selected else None
        with self.__cache_lock:
            if cache_key is not None:
                raw = read_pin(selected[0])
                if cache_key in self.__selection_cache:
                    return self.__selection_cache[cache_key]
                bars = _rows(raw, selected[0], plan.timeframe_seconds)
            else:
                bars = ()
            result = completed_context(bars, plan, trusted_start_ns=trusted_start_ns)
            if cache_key is not None:
                self.__selection_cache.clear()
                self.__selection_cache[cache_key] = result
            return result

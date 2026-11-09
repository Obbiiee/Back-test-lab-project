"""Small process-local cache for immutable committed-analysis projections.

The committed events remain the only financial authority. Cache entries are
keyed by the complete Session head and are a disposable optimization for paging
through one unchanged revision; oversized projections bypass the cache.
"""
import json
from collections import OrderedDict
from threading import RLock

from contracts.canonical import canonical_bytes, content_hash


class AnalysisProjectionCache:
    def __init__(self, *, max_bytes=16 * 1024 * 1024, max_entry_bytes=512 * 1024):
        if (
            type(max_bytes) is not int
            or max_bytes < 1
            or type(max_entry_bytes) is not int
            or not 1 <= max_entry_bytes <= max_bytes
        ):
            raise ValueError('invalid analysis cache bounds')
        self.max_bytes = max_bytes
        self.max_entry_bytes = max_entry_bytes
        self._entries = OrderedDict()
        self._bytes = 0
        self._lock = RLock()

    @staticmethod
    def key(*, dsn, workspace_id, session_id, revision, event_head, quote):
        return content_hash(
            dict(
                schemaVersion=1,
                artifact='BTL-ANALYSIS-CACHE-KEY-1',
                dsnHash=content_hash({'schemaVersion': 1, 'dsn': dsn}),
                workspaceId=workspace_id,
                sessionId=session_id,
                revision=revision,
                eventHead=event_head,
                quoteHash=None if quote is None else content_hash(
                    {'schemaVersion': 1, 'quote': quote}
                ),
            )
        )

    def get(self, key):
        with self._lock:
            raw = self._entries.get(key)
            if raw is None:
                return None
            self._entries.move_to_end(key)
        return json.loads(raw)

    def put(self, key, value):
        try:
            raw = canonical_bytes(value)
        except (TypeError, ValueError):
            return False
        size = len(raw)
        if size > self.max_entry_bytes:
            return False
        with self._lock:
            prior = self._entries.pop(key, None)
            if prior is not None:
                self._bytes -= len(prior)
            while self._entries and self._bytes + size > self.max_bytes:
                _old_key, old = self._entries.popitem(last=False)
                self._bytes -= len(old)
            self._entries[key] = raw
            self._bytes += size
        return True

    @property
    def byte_size(self):
        with self._lock:
            return self._bytes


COMMITTED_ANALYSIS_CACHE = AnalysisProjectionCache()

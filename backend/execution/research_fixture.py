"""Bounded authored fixture for the local alpha; no provider/market claim."""
from functools import lru_cache
import json
from contracts.canonical import canonical_bytes
from contracts.primitives import require
from .fixture_demo import fixture_profile
from ticks.provider import SyntheticTickProvider

START_NS = 1577836800000000000  # Authored 2020-01 UTC fixture, not historical data.
STEP_NS = 15000000000
WARMUP_NS = START_NS + 120 * STEP_NS


class _ImmutableFixturePages:
    """Private bounded page cache; timeline still validates every returned page.

    Only this authored immutable fixture is cached, never a mutable/live provider.
    JSON decoding returns fresh objects so consumers cannot modify stored bytes.
    """
    def __init__(self, source):
        self.__source = source
        self.dataset_id, self.dataset_version = source.dataset_id, source.dataset_version
        self.__manifest = canonical_bytes(source.describe(self.dataset_id, self.dataset_version))
        self.__pages = {}

    def describe(self, dataset_id, dataset_version):
        require((dataset_id,dataset_version) == (self.dataset_id,self.dataset_version),
                "dataset", "VERSION_MISMATCH")
        return json.loads(self.__manifest)

    def read_page(self, dataset_id, dataset_version, after_token=None, max_events=1024):
        self.describe(dataset_id,dataset_version)
        if max_events != 64:
            return self.__source.read_page(dataset_id,dataset_version,after_token,max_events)
        key = None if after_token is None else canonical_bytes(after_token)
        if key not in self.__pages:
            page = self.__source.read_page(dataset_id,dataset_version,after_token,max_events)
            # Source validation runs before caching. Invalid tokens cannot consume entries.
            require(len(self.__pages) < 32,"fixturePages","REFUSED_FIXTURE_LIMIT")
            self.__pages[key] = canonical_bytes(page)
        return json.loads(self.__pages[key])


@lru_cache(maxsize=1)
def research_provider():
    rows = []
    for i in range(2048):
        phase = i % 240
        cents = 200000 + (phase if phase <= 120 else 240-phase) * 5
        def quoted(value):
            return f"{value//100}.{value%100:02}".rstrip('0').rstrip('.')
        rows.append(dict(ordinal=str(i), timeNs=str(START_NS+i*STEP_NS), bid=quoted(cents),
                         ask=quoted(cents+10), sequence=str(i)))
    return _ImmutableFixturePages(SyntheticTickProvider(rows, dataset_id="synthetic:local-alpha-v1", trusted=True, execution_fixture=True))


def research_profile():
    return fixture_profile()

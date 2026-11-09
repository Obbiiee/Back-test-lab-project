"""Combine fixed-size, revision-pinned Session aggregates for Method analytics."""
from fractions import Fraction

from contracts.primitives import require
from .contracts import text

MAX_SESSION_DETAILS = 128
METHOD_ROLLUP_ARTIFACT = 'BTL-METHOD-ANALYTICS-ROLLUP-1'


class MethodAnalyticsAccumulator:
    """Pool Session summaries with bounded response detail memory."""

    def __init__(self, method_id, method_hash):
        self.common = dict(schemaVersion=1, artifact='BTL-METHOD-ANALYTICS-1',
            methodId=method_id, methodHash=method_hash,
            aggregation='POOLED_COMMITTED_COMPLETED_POSITIONS',
            balancesCombined=False, financialAuthority='COMMITTED_EVENTS_ONLY')
        self.totals = dict(tradeCount=0, wins=0, losses=0, breakeven=0,
            positive=Fraction(), negative=Fraction(), net=Fraction(), durationNs=0)
        self.unit = None
        self.incompatible = False
        self.included_sessions = []
        self.included_count = 0
        self.excluded_sessions = []
        self.excluded_count = 0

    @staticmethod
    def _bounded_append(rows, value):
        if len(rows) < MAX_SESSION_DETAILS:
            rows.append(value)

    def exclude(self, value):
        self.excluded_count += 1
        self._bounded_append(self.excluded_sessions, value)

    def observe_unit(self, unit):
        if self.unit is None:
            self.unit = unit
        elif unit != self.unit:
            self.incompatible = True

    def snapshot(self):
        """Return a bounded, versioned value suitable for durable storage.

        Session details are deliberately only a compatibility window. Exact
        totals and the total included/excluded counts remain independent of
        that window, so restoring a rollup never requires retaining every
        Session id in process memory.
        """
        return dict(schemaVersion=1, artifact=METHOD_ROLLUP_ARTIFACT,
            methodId=self.common['methodId'], methodHash=self.common['methodHash'],
            totals=dict(tradeCount=self.totals['tradeCount'], wins=self.totals['wins'],
                losses=self.totals['losses'], breakeven=self.totals['breakeven'],
                positive=[self.totals['positive'].numerator,
                          self.totals['positive'].denominator],
                negative=[self.totals['negative'].numerator,
                          self.totals['negative'].denominator],
                net=[self.totals['net'].numerator, self.totals['net'].denominator],
                durationNs=self.totals['durationNs']),
            unit=list(self.unit) if self.unit is not None else None,
            incompatible=self.incompatible,
            includedCount=self.included_count, excludedCount=self.excluded_count,
            includedSessions=[dict(row) for row in self.included_sessions],
            excludedSessions=[dict(row) for row in self.excluded_sessions])

    @classmethod
    def restore(cls, value, *, method_id, method_hash):
        """Restore a strict bounded snapshot without trusting its stored shape."""
        require(type(value) is dict and value.get('schemaVersion') == 1 and
            value.get('artifact') == METHOD_ROLLUP_ARTIFACT and
            value.get('methodId') == method_id and value.get('methodHash') == method_hash,
            'methodAnalyticsRollup', 'CORRUPT_RECORD')
        require(set(value) == {'schemaVersion','artifact','methodId','methodHash',
            'totals','unit','incompatible','includedCount','excludedCount',
            'includedSessions','excludedSessions'},
            'methodAnalyticsRollup', 'CORRUPT_RECORD')
        totals = value['totals']
        total_keys = {'tradeCount','wins','losses','breakeven','positive','negative',
                      'net','durationNs'}
        require(type(totals) is dict and set(totals) == total_keys,
            'methodAnalyticsRollup', 'CORRUPT_RECORD')
        for key in ('tradeCount','wins','losses','breakeven','durationNs'):
            require(type(totals[key]) is int and totals[key] >= 0,
                'methodAnalyticsRollup', 'CORRUPT_RECORD')
        require(totals['wins'] + totals['losses'] + totals['breakeven'] ==
                totals['tradeCount'], 'methodAnalyticsRollup', 'CORRUPT_RECORD')
        parsed = {}
        for key in ('positive','negative','net'):
            pair = totals[key]
            require(type(pair) is list and len(pair) == 2 and
                all(type(part) is int for part in pair) and pair[1] > 0,
                'methodAnalyticsRollup', 'CORRUPT_RECORD')
            parsed[key] = Fraction(pair[0], pair[1])
        require(parsed['positive'] >= 0 and parsed['negative'] >= 0 and
                parsed['net'] == parsed['positive'] - parsed['negative'],
                'methodAnalyticsRollup', 'CORRUPT_RECORD')
        unit = value['unit']
        require(unit is None or (type(unit) is list and len(unit) == 3 and
            all(type(part) is str and part for part in unit)),
            'methodAnalyticsRollup', 'CORRUPT_RECORD')
        require(type(value['incompatible']) is bool and
            type(value['includedCount']) is int and value['includedCount'] >= 0 and
            type(value['excludedCount']) is int and value['excludedCount'] >= 0 and
            value['includedCount'] + value['excludedCount'] >= 0,
            'methodAnalyticsRollup', 'CORRUPT_RECORD')
        included = value['includedSessions']
        excluded = value['excludedSessions']
        included_keys = {'sessionId','revision','datasetId','datasetVersion',
                         'profileHash','engineVersion','eventHead','tradeCount'}
        require(type(included) is list and len(included) <= MAX_SESSION_DETAILS and
            type(excluded) is list and len(excluded) <= MAX_SESSION_DETAILS and
            all(type(row) is dict and set(row) == included_keys and
                all(type(row[key]) is str and 0 < len(row[key]) <= 256
                    for key in included_keys - {'revision','tradeCount'}) and
                type(row['revision']) is int and row['revision'] >= 0 and
                type(row['tradeCount']) is int and row['tradeCount'] >= 0
                for row in included) and
            all(type(row) is dict and set(row) == {'sessionId','reason'} and
                all(type(row[key]) is str and 0 < len(row[key]) <= 256
                    for key in ('sessionId','reason')) for row in excluded),
            'methodAnalyticsRollup', 'CORRUPT_RECORD')
        require(value['includedCount'] >= len(included) and
            value['excludedCount'] >= len(excluded),
            'methodAnalyticsRollup', 'CORRUPT_RECORD')
        result = cls(method_id, method_hash)
        result.totals.update(tradeCount=totals['tradeCount'], wins=totals['wins'],
            losses=totals['losses'], breakeven=totals['breakeven'],
            positive=parsed['positive'], negative=parsed['negative'], net=parsed['net'],
            durationNs=totals['durationNs'])
        result.unit = tuple(unit) if unit is not None else None
        result.incompatible = value['incompatible']
        result.included_count = value['includedCount']
        result.excluded_count = value['excludedCount']
        result.included_sessions = [dict(row) for row in included]
        result.excluded_sessions = [dict(row) for row in excluded]
        return result

    def include(self, item):
        projection = item['projection']
        unit = item['unit']
        self.observe_unit(unit)
        for key in ('tradeCount', 'wins', 'losses', 'breakeven'):
            require(type(projection.get(key)) is int and projection[key] >= 0,
                'analyticsProjection', 'CORRUPT_RECORD')
            self.totals[key] += projection[key]
        require(projection['wins'] + projection['losses'] + projection['breakeven'] ==
                projection['tradeCount'] and
                item['session'].get('tradeCount') == projection['tradeCount'],
                'analyticsProjection', 'CORRUPT_RECORD')
        for key in ('positive', 'negative', 'net'):
            self.totals[key] += Fraction(projection[key])
        positive = Fraction(projection['positive'])
        negative = Fraction(projection['negative'])
        duration = int(projection['durationNs'])
        require(positive >= 0 and negative >= 0 and
                Fraction(projection['net']) == positive - negative and duration >= 0,
                'analyticsProjection', 'CORRUPT_RECORD')
        self.totals['durationNs'] += duration
        self.included_count += 1
        self._bounded_append(self.included_sessions, item['session'])

    def result(self):
        common = self.common
        if self.incompatible:
            incompatible = [dict(sessionId=item['sessionId'],
                reason='MULTIPLE_FINANCIAL_UNITS') for item in self.included_sessions]
            excluded = (self.excluded_sessions + incompatible)[:MAX_SESSION_DETAILS]
            excluded_count = self.excluded_count + self.included_count
            return dict(**common, status='UNAVAILABLE', reason='INCOMPATIBLE_FINANCIAL_UNITS',
                includedSessions=[], includedSessionCount=0, includedSessionsTruncated=False,
                excludedSessions=excluded, excludedSessionCount=excluded_count,
                excludedSessionsTruncated=excluded_count > len(excluded), metrics=None)

        totals = self.totals
        count = totals['tradeCount']
        wins = totals['wins']
        losses = totals['losses']

        def ratio(value):
            if value is None:
                return None
            value = Fraction(value)
            return dict(numerator=str(value.numerator), denominator=str(value.denominator))

        metrics = dict(tradeCount=count, wins=wins, losses=losses,
            breakeven=totals['breakeven'],
            winRate=ratio(Fraction(wins, count) if count else None),
            averageWin=ratio(totals['positive'] / wins if wins else None),
            averageLoss=ratio(-totals['negative'] / losses if losses else None),
            expectancy=ratio(totals['net'] / count if count else None),
            profitFactor=ratio(totals['positive'] / totals['negative']
                               if totals['negative'] else None),
            rEligible=0, rExcluded=count, rReason='PREENTRY_R0_NOT_PINNED', averageR=None,
            averageDurationNs=ratio(Fraction(totals['durationNs'], count) if count else None),
            monteCarlo=dict(status='INSUFFICIENT_SAMPLE', eligible=0,
                            exclusions=count, minimum=30))
        return dict(**common, status='COMPLETE',
            accountCurrency=self.unit[2] if self.unit else None,
            completedTradeNet=text(totals['net']), includedSessions=self.included_sessions,
            includedSessionCount=self.included_count,
            includedSessionsTruncated=self.included_count > len(self.included_sessions),
            excludedSessions=self.excluded_sessions, excludedSessionCount=self.excluded_count,
            excludedSessionsTruncated=self.excluded_count > len(self.excluded_sessions),
            metrics=metrics)


def summarize(method_id, method_hash, units, included, excluded):
    """Compatibility wrapper for callers with already bounded collections."""
    accumulator = MethodAnalyticsAccumulator(method_id, method_hash)
    for item in included:
        accumulator.include(item)
    for item in excluded:
        accumulator.exclude(item)
    if len(units) > 1:
        accumulator.incompatible = True
    return accumulator.result()


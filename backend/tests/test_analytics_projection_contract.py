"""Synthetic durable analytics projection contracts without a database."""
import unittest
from fractions import Fraction

from execution.analytics_projection import initial_projection,advance_projection,analytics_view


class AnalyticsProjectionContractTests(unittest.TestCase):
    def test_exact_financial_aggregate_matches_bounded_windows(self):
        initial=dict(sessionId='session:analytics',revision=0,eventHash='a'*64,
            initialBalance='100',balance='100')
        projection=initial_projection(initial)
        order=dict(side='LONG',status='CLOSED',quantity='1',remaining='0',entry='10',
            entryPrice='10',entryFillRef='entry-ref',entryCost='0',exitRequest=None,
            grossPosted='2',riskBalance='100',riskBasisHash='0'*64,sl='9',tp='12')
        history=dict(entryTimeNs='100',entryFillRef='b'*64,exitTimeNs='130',exitPrice='12',
            exitFillRef='d'*64,exitReason='TP',exactGross='2',exitFills=2)
        entry=[dict(sequence=0,eventId='b'*64,kind='ENTRY_FILL',orderId='trade:one',
            detail=dict(balanceDelta='0',evidence=dict(timeNs='100',chronologyLimited=False),price='10'))]
        first_state=dict(initial,revision=1,eventHash='c'*64)
        active=dict(order,status='ACTIVE',grossPosted='0')
        first_history=dict(history,exitTimeNs=None,exitPrice=None,exitFillRef=None,
            exitReason=None,exactGross='0',exitFills=0)
        projection=advance_projection(projection,entry,first_state,
            [dict(orderId='trade:one',order=active,history=first_history)])
        partial=[dict(sequence=1,eventId='c'*64,kind='EXIT_FILL',orderId='trade:one',
            detail=dict(balanceDelta='1',remaining='0.5',evidence=dict(timeNs='125',chronologyLimited=False),
                        price='12',reason='TP'))]
        second_state=dict(initial,revision=2,eventHash='d'*64,balance='101',realizedGross='1')
        partial_order=dict(active,grossPosted='1')
        partial_history=dict(history,exitTimeNs='125',exitPrice='12',exitFillRef='c'*64,
            exactGross='1',exitFills=1)
        projection=advance_projection(projection,partial,second_state,
            [dict(orderId='trade:one',order=partial_order,history=partial_history)])
        self.assertEqual(projection['tradeCount'],0)
        final_event=[dict(sequence=2,eventId='e'*64,kind='EXIT_FILL',orderId='trade:one',
            detail=dict(balanceDelta='1',remaining='0',evidence=dict(timeNs='130',chronologyLimited=False),
                        price='12',reason='TP'))]
        final=dict(initial,revision=3,eventHash='f'*64,balance='102',realizedGross='2',
            engineVersion='engine:test',datasetId='dataset:test',datasetVersion='v1',
            profileHash='f'*64,policy=dict(definitionHash='1'*64))
        projection=advance_projection(projection,final_event,final,
            [dict(orderId='trade:one',order=order,history=history)])
        view=analytics_view(projection,final)
        self.assertEqual((view['metrics']['tradeCount'],view['metrics']['wins'],
                          view['metrics']['realizedNetCompleted']),(1,1,'2'))
        self.assertEqual(view['metrics']['averageDurationNs'],dict(numerator='30',denominator='1'))
        self.assertEqual(view['equity'][-1]['balance'],'102')
        self.assertEqual(len(view['equity']),3)
        self.assertEqual(len(view['annotations']),3)
        self.assertEqual(projection['eventHead'],final['eventHash'])

    def test_projection_windows_are_bounded_to_contract_limits(self):
        state=dict(sessionId='session:analytics',revision=0,eventHash='a'*64,
            initialBalance='100',balance='100',realizedGross='0',engineVersion='engine:test',datasetId='dataset:test',
            datasetVersion='v1',profileHash='f'*64,policy=dict(definitionHash='1'*64))
        projection=initial_projection(state)
        order=dict(side='LONG')
        events=[dict(sequence=i,eventId=f'{i:064x}',kind='ENTRY_FILL',orderId='trade:one',
            detail=dict(balanceDelta='0',evidence=dict(timeNs=str(i),chronologyLimited=False),price='10'))
            for i in range(600)]
        next_state=dict(state,revision=1,eventHash='b'*64)
        projection=advance_projection(projection,events,next_state,
            [dict(orderId='trade:one',order=order,history={})])
        view=analytics_view(projection,next_state)
        self.assertEqual((projection['financialCount'],len(view['equity']),len(view['annotations'])),
                         (600,256,512))


if __name__=='__main__':
    unittest.main()

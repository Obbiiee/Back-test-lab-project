"""Synthetic durable analytics projection contracts without a database."""
import unittest
from fractions import Fraction
from pathlib import Path
from contracts.primitives import ContractError

from execution.analytics_projection import (initial_projection,advance_projection,analytics_view,
    completed_trade_row,encode_trade_cursor,decode_trade_cursor)


class AnalyticsProjectionContractTests(unittest.TestCase):
    def test_analytics_cursor_is_session_revision_and_order_bound(self):
        token=encode_trade_cursor('session:analytics',42,128,'trade:128')
        self.assertEqual(decode_trade_cursor(token,'session:analytics'),(42,128,'trade:128'))
        for invalid in (('session:other',token),('session:analytics','not-a-cursor')):
            with self.subTest(invalid=invalid), self.assertRaises(ContractError):
                decode_trade_cursor(invalid[1],invalid[0])
        with self.assertRaises(ContractError):
            encode_trade_cursor('session:analytics',42,-1,'trade:128')

    def test_migration_adds_a_partial_keyset_index_without_rewriting_history(self):
        migration=Path(__file__).parents[1]/'infrastructure'/'migrations'/\
            '031_tick_analytics_closed_order_keyset.sql'
        sql=migration.read_text(encoding='utf-8')
        self.assertIn('CREATE INDEX tick_journal_order_projection_analytics_c',sql)
        self.assertIn('(workspace_id, session_id, last_sequence, (order_id COLLATE "C"))',sql)
        self.assertIn("WHERE order_status = 'CLOSED'",sql)
        self.assertNotIn('DROP ',sql.upper())

    def test_closed_trade_projection_matches_existing_analytics_response_shape(self):
        order=dict(side='SHORT',quantity='2',entryPrice='20',sl='21',tp='18',grossPosted='4')
        history=dict(entryTimeNs='200',entryFillRef='a'*64,exitTimeNs='240',exitPrice='18',
            exitFillRef='b'*64,exitReason='TP',exactGross='4')
        row=completed_trade_row('trade:two',order,history)
        self.assertEqual(set(row),{'id','side','status','quantity','remaining','entry','entryPrice',
            'entryTimeNs','exitTimeNs','entryFillRef','sl','tp','exitPrice','exitFillRef','exitReason',
            'gross','commission','net','durationNs','mae','mfe','excursionReason','rMultiple','rReason'})
        self.assertEqual((row['side'],row['status'],row['gross'],row['net'],row['durationNs']),
                         ('SHORT','CLOSED','4','4','40'))

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

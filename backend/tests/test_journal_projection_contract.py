"""Synthetic contracts for the bounded Journal projection fold."""
import unittest

from execution.journal_projection import journal_projection_changes,journal_order_summary


class JournalProjectionContractTests(unittest.TestCase):
    def test_closed_and_active_order_rows_keep_the_existing_journal_shape(self):
        order=dict(side='LONG',status='CLOSED',quantity='1',remaining='0',entry='10',entryPrice='10',
            entryCost='0',exitRequest=None,grossPosted='2',sl='9',tp='12')
        history=dict(entryTimeNs='100',entryFillRef='a'*64,exitTimeNs='130',exitPrice='12',
            exitFillRef='b'*64,exitReason='TP',exactGross='2',exitFills=1)
        closed=journal_order_summary('trade:one','CLOSED',order,history)
        self.assertEqual(set(closed),{'id','side','status','quantity','remaining','entry','entryPrice',
            'entryTimeNs','entryFillRef','sl','tp','exitRequested','exitPrice','exitFillRef','exitReason',
            'gross','commission','net','netCashChange','unrealizedIndicative','mae','mfe','excursionReason'})
        self.assertEqual(closed['entryTimeNs'],'100')
        active=journal_order_summary('trade:one','ACTIVE',dict(order,status='ACTIVE',remaining='1'),history)
        self.assertIsNone(active['entryTimeNs']);self.assertIsNone(active['exitFillRef'])

    def test_latest_status_and_trade_history_are_folded_from_incremental_events(self):
        order=dict(side='LONG',status='CLOSED',quantity='1',remaining='0',entry='10',
            entryPrice='10',entryFillRef='entry-ref',entryCost='0',exitRequest=None,
            grossPosted='2',riskBalance='100',riskBasisHash='0'*64,sl='9',tp='12')
        first_events=[
            dict(sequence=0,eventId='a'*64,kind='ORDER_ACCEPTED',orderId='trade:one',detail={}),
            dict(sequence=1,eventId='b'*64,kind='ENTRY_FILL',orderId='trade:one',
                 detail=dict(evidence=dict(timeNs='100'))),
        ]
        first=journal_projection_changes(first_events,
            dict(orders={'trade:one':dict(order,status='ACTIVE')}))
        second_events=[
            dict(sequence=2,eventId='c'*64,kind='EXIT_FILL',orderId='trade:one',
                 detail=dict(evidence=dict(timeNs='125'),price='12',reason='TP',grossExact='1')),
            dict(sequence=3,eventId='d'*64,kind='EXIT_FILL',orderId='trade:one',
                 detail=dict(evidence=dict(timeNs='130'),price='12',reason='TP',grossExact='1')),
        ]
        rows=journal_projection_changes(second_events,dict(orders={}),
            [dict(orderId='trade:one',order=order)],
            {'trade:one':first[0]['history']})
        self.assertEqual(len(rows),1)
        row=rows[0]
        self.assertEqual((row['sequence'],row['status'],row['eventId']),(3,'CLOSED','d'*64))
        self.assertEqual(row['history'],dict(entryTimeNs='100',entryFillRef='b'*64,
            exitTimeNs='130',exitPrice='12',exitFillRef='d'*64,exitReason='TP',
            exactGross='2',exitFills=2))

    def test_unresolved_only_updates_affected_orders(self):
        events=[dict(sequence=9,eventId='e'*64,kind='UNRESOLVED',orderId=None,
                     detail=dict(affectedOrderIds=['trade:two','trade:one']))]
        archive=[dict(orderId='trade:one',order=dict(status='UNRESOLVED')),
                 dict(orderId='trade:two',order=dict(status='UNRESOLVED'))]
        rows=journal_projection_changes(events,dict(orders={'unrelated':dict(status='ACTIVE')}),archive)
        self.assertEqual([row['orderId'] for row in rows],['trade:one','trade:two'])
        self.assertTrue(all(row['status']=='UNRESOLVED' for row in rows))


if __name__=='__main__':
    unittest.main()

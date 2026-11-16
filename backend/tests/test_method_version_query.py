"""SQL contracts for bounded, ordered Method-version pagination."""
import unittest

from contracts.primitives import ContractError
from execution.method_version_query import version_rows, latest_version_window
from execution.method_version_cursor import decode, encode


class FakeCursor:
    def __init__(self, rows):
        self.rows=rows

    def fetchall(self):
        return self.rows


class FakeDb:
    def __init__(self, rows):
        self.rows=rows
        self.calls=[]

    def execute(self, sql, params):
        self.calls.append((sql,params))
        return FakeCursor(self.rows)


def row(version):
    return {'version':version,'method_id':f'method:v{version}',
            'payload':b'payload','content_hash':'a'*64}


class MethodVersionQueryTests(unittest.TestCase):
    def test_page_uses_ordered_keyset_and_fixed_limit(self):
        db=FakeDb([row(4),row(5),row(6)])
        page,more=version_rows(db,'workspace:one','family:one',after_version=3,limit=2)
        self.assertEqual([item['version'] for item in page],[4,5])
        self.assertTrue(more)
        sql,params=db.calls[0]
        self.assertIn('v.version>%s',sql)
        self.assertIn('ORDER BY v.version LIMIT %s',sql)
        self.assertNotIn('OFFSET',sql.upper())
        self.assertEqual(params,('workspace:one','family:one',3,3))

    def test_version_gap_and_invalid_bounds_are_rejected(self):
        with self.assertRaises(ContractError):
            version_rows(FakeDb([row(5)]),'workspace:one','family:one',
                         after_version=3,limit=2)
        with self.assertRaises(ContractError):
            version_rows(FakeDb([]),'workspace:one','family:one',
                         after_version=-1,limit=2)
        with self.assertRaises(ContractError):
            version_rows(FakeDb([]),'workspace:one','family:one',
                         after_version=0,limit=51)

    def test_compatibility_window_is_bounded_and_ends_at_latest(self):
        descending=[row(version) for version in range(130,1,-1)]
        db=FakeDb(descending)
        window,truncated=latest_version_window(
            db,'workspace:one','family:one',latest_version=130,limit=128)
        self.assertTrue(truncated)
        self.assertEqual([item['version'] for item in window],list(range(3,131)))
        sql,params=db.calls[0]
        self.assertIn('ORDER BY v.version DESC LIMIT %s',sql)
        self.assertNotIn('OFFSET',sql.upper())
        self.assertEqual(params,('workspace:one','family:one',130,129))

    def test_compatibility_window_rejects_a_gap(self):
        with self.assertRaises(ContractError):
            latest_version_window(FakeDb([row(4),row(2),row(1)]),
                                  'workspace:one','family:one',latest_version=4,limit=3)

    def test_compatibility_window_preserves_complete_short_history(self):
        window,truncated=latest_version_window(
            FakeDb([row(3),row(2),row(1)]),
            'workspace:one','family:one',latest_version=3,limit=128)
        self.assertFalse(truncated)
        self.assertEqual([item['version'] for item in window],[1,2,3])

    def test_cursor_is_canonical_and_bound_to_family_and_revision(self):
        token=encode('family:one',9,50)
        self.assertEqual(decode(token,'family:one'),(9,50))
        for family,invalid in (('family:two',token),('family:one','not-a-cursor')):
            with self.subTest(family=family),self.assertRaises(ContractError):
                decode(invalid,family)
        with self.assertRaises(ContractError):
            encode('family:one',9,0)


if __name__=='__main__':
    unittest.main()

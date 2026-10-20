import importlib.util,json,sys,time,unittest,uuid
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'integrations/odoo'))
import sync as worker
class WorkerTests(unittest.TestCase):
    def test_exact_destination_bounded_authenticated_request(self):
        def send(req):
            self.assertEqual(req.url.path,'/json/2/btl.import.batch/sync_bundle');self.assertEqual(req.headers['x-odoo-database'],'authored');self.assertEqual(json.loads(req.content),dict(bundle='{}',company_id=1))
            return httpx.Response(200,json=dict(accepted=True,customers=1,payments=0,tickets=0))
        self.assertTrue(worker.push(b'{}','http://127.0.0.1:8071','authored','a'*40,1,transport=httpx.MockTransport(send))['accepted'])
        for url in ('http://example.com','https://user:secret@example.com','https://example.com/path','https://example.com?query=1'):
            with self.assertRaises(ValueError):worker.push(b'{}',url,'authored','a'*40,1,transport=httpx.MockTransport(send))
    def test_no_redirect_or_oversized_unvalidated_response(self):
        for result in (httpx.Response(302,headers={'location':'https://elsewhere.example'}),httpx.Response(200,content=b'x'*16385),httpx.Response(200,json={'accepted':True}),httpx.Response(401)):
            calls=[]
            def send(req):calls.append(req);return result
            with self.assertRaises(ValueError):worker.push(b'{}','https://odoo.example','authored','a'*40,1,transport=httpx.MockTransport(send))
            self.assertEqual(len(calls),1)
    def test_sync_envelope_rejects_unknown_fields_and_duplicate_intake(self):
        contract=worker.bundle.__globals__['contract'];actor=str(uuid.uuid4());source=str(uuid.uuid4())
        snapshot=dict(schemaVersion=1,artifact='BTL-BUSINESS-EXPORT-1',source=source,mode='SANDBOX',customers=[dict(id=actor,email='authored@example.com')],orders=[])
        value=dict(schemaVersion=1,artifact='BTL-BUSINESS-SYNC-1',source=source,observedAtUs=str(time.time_ns()//1000),snapshot=snapshot,tickets=[])
        self.assertEqual(contract.sync_decode(json.dumps(value).encode()),value)
        for bad in ({**value,'password':'forbidden'},{**value,'observedAtUs':True},{**value,'source':str(uuid.uuid4())}):
            with self.assertRaises(ValueError):contract.sync_decode(json.dumps(bad).encode())

        ticket=dict(id=str(uuid.uuid4()),account=actor,title='QA',message='QA',createdAt='2026-10-20T00:00:00+00:00')
        with self.assertRaises(ValueError):contract.sync_decode(json.dumps({**value,'tickets':[ticket,ticket]}).encode())
        with self.assertRaises(ValueError):contract.sync_decode(json.dumps({**value,'tickets':[{**ticket,'createdAt':'2026-10-20T00:00:00+07:00'}]}).encode())

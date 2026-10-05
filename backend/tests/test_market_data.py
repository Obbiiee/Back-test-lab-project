"""Local service acceptance using authored fixtures, never provider quotes."""
import asyncio
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import httpx
from contracts.primitives import ContractError
from market_data.local import open_local, valid_rows
from market_data.service import DataService, PersonalLocalPolicy
from market_data.serve import create_local_app


class MarketDataTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.rows = [[60, '1.20', '1.40', '1.10', '1.30'], [120, '1.30', '1.50', '1.20', '1.40'], [240, '1.40', '1.60', '1.30', '1.50']]
        self.path = self.root/'2025-01-1m.json'
        self.path.write_text(json.dumps(self.rows),encoding='utf-8')
        self.manifest = {'symbol':'XAUUSD','source':'HistData.com','priceType':'bid','timezone':'UTC',
                         'sourceTimezone':'EST fixed UTC-5', 'frames':{'1m':[{'path':self.path.name,'count':3,'first':60,'last':240}]}}
        self.save_manifest()
        self.service = open_local(self.root)

    def save_manifest(self):
        (self.root/'manifest.json').write_text(json.dumps(self.manifest),encoding='utf-8')

    def test_identity_restart_exact_prices_and_unknowns(self):
        again = open_local(self.root)
        self.assertEqual(self.service.descriptor(),again.descriptor())
        result = self.service.read(self.service.dataset.version,0,300)
        self.assertEqual(result['rows'],[[60,'1.2','1.4','1.1','1.3'],[120,'1.3','1.5','1.2','1.4'],[240,'1.4','1.6','1.3','1.5']])
        self.assertFalse(result['coverageComplete'])
        self.assertEqual(result['intrabarOutcome'],'AMBIGUOUS')
        self.assertIsNone(result['fillPrice'])
        self.assertIsNone(result['pnl'])
        self.assertFalse(self.service.descriptor()['publicDisplayApproved'])
        # Mutating returned data cannot alter catalog identity or subsequent rows.
        result['rows'][0][1]='999'
        self.assertEqual(self.service.read(self.service.dataset.version,0,300)['rows'][0][1],'1.2')

    def test_pagination_gaps_and_completed_prefix(self):
        version=self.service.dataset.version
        first=self.service.read(version,0,300,1)
        second=self.service.read(version,0,300,1,first['nextAfter'])
        third=self.service.read(version,0,300,1,second['nextAfter'])
        self.assertEqual([first['rows'][0][0],second['rows'][0][0],third['rows'][0][0]],[60,120,240])
        self.assertFalse(third['more'])
        self.assertEqual(self.service.read(version,0,300,revealed_before=179)['rows'],first['rows'])
        self.assertEqual(len(self.service.read(version,0,300,revealed_before=180)['rows']),2)
        self.assertEqual(self.service.read(version,0,300,revealed_before=59)['rows'],[])

    def test_version_changes_and_corruption_fail_without_repair(self):
        old=self.service.dataset.version
        self.path.write_text(json.dumps([[60,'2','3','1','2'],*self.rows[1:]]),encoding='utf-8')
        with self.assertRaises(ContractError): self.service.read(old,0,300)
        changed=open_local(self.root)
        self.assertNotEqual(old,changed.dataset.version)
        with self.assertRaises(ContractError): changed.read(old,0,300)

    def test_inventory_and_traversal_refusal(self):
        for key in ['../2025-01-1m.json','https://example.com/data','C:/private.json','2025-01-1m.json/../x']:
            self.manifest['frames']['1m'][0]['path']=key
            self.save_manifest()
            with self.assertRaises((ContractError,OSError)): open_local(self.root)
        self.manifest['frames']['1m'][0]['path']=self.path.name
        self.manifest['frames']['1m'][0]['count']=4
        self.save_manifest()
        with self.assertRaises(ContractError): open_local(self.root)

    def test_bad_rows_rejected(self):
        for value in [[],[[True,1,2,1,1]],[[61,1,2,1,1]],[[60,1,2,3,1]],[[60,1,2,1,1],[60,1,2,1,1]],[[60,0,2,0,1]],[[120,1,2,1,1],[60,1,2,1,1]]]:
            with self.assertRaises(ContractError): valid_rows(json.dumps(value).encode())
        with self.assertRaises(ContractError): valid_rows(b'[[60,NaN,2,1,1]]')

    def test_limits_and_permission_rechecked(self):
        version=self.service.dataset.version
        for args in [(version,0,33*86400),(version,False,300),(version,0,300,10001),(version,0,300,0),(version,0,300,1,301),(version,300,0)]:
            with self.assertRaises(ContractError): self.service.read(*args)
        denied=DataService(replace(self.service.dataset,audience='PUBLIC'),self.service.store,PersonalLocalPolicy())
        with self.assertRaises(ContractError): denied.descriptor()
        with self.assertRaises(ContractError): denied.read(version,0,300)
        self.path.write_bytes(b' '*2097153)
        with self.assertRaises(ContractError): self.service.read(version,0,300)

    def test_http_boundary_statuses_and_no_store(self):
        async def run():
            app=create_local_app(self.service,rate_limit=100)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app,client=('127.0.0.1',1000)),base_url='http://127.0.0.1:5199') as client:
                r=await client.get('/api/v1/local-market/dataset')
                self.assertEqual(r.status_code,200)
                self.assertEqual(r.headers['cache-control'],'no-store')
                path='/api/v1/local-market/candles'
                q={'version':self.service.dataset.version,'start':0,'end':300,'limit':1}
                self.assertEqual((await client.get(path,params=q)).status_code,200)
                self.assertEqual((await client.get(path,params={**q,'version':'wrong'})).status_code,409)
                self.assertEqual((await client.get(path,params={**q,'limit':10001})).status_code,422)
                self.assertEqual((await client.get(path,params={**q,'audience':'PUBLIC'})).status_code,422)
                self.assertEqual((await client.get(path,params=[*q.items(),('start',60)])).status_code,422)
                for headers in [{'host':'evil.example:5199'},{'origin':'http://evil.example'},{'sec-fetch-site':'cross-site'}]:
                    self.assertEqual((await client.get(path,params=q,headers=headers)).status_code,403)
                self.assertEqual((await client.post(path,json={})).status_code,405)
                self.path.write_text('[]')
                self.assertEqual((await client.get(path,params=q)).status_code,503)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app,client=('10.0.0.1',1000)),base_url='http://127.0.0.1:5199') as client:
                self.assertEqual((await client.get('/api/v1/local-market/dataset')).status_code,403)
        asyncio.run(run())

    def test_large_page_continuation_and_future_filter(self):
        rows=[[t,'1','2','1','2'] for t in range(60,3001*60,60)]
        self.path.write_text(json.dumps(rows),encoding='utf-8')
        entry=self.manifest['frames']['1m'][0]
        entry.update(count=3000,first=60,last=180000)
        self.save_manifest()
        service=open_local(self.root)
        page=service.read(service.dataset.version,0,180060,10000)
        self.assertEqual(len(page['rows']),2000)
        self.assertTrue(page['more'])
        rest=service.read(service.dataset.version,0,180060,10000,page['nextAfter'])
        self.assertEqual(len(rest['rows']),1000)
        self.assertFalse(rest['more'])
        prefix=service.read(service.dataset.version,0,180060,revealed_before=180)['rows']
        rows[-1]=[180000,'5','6','4','5']
        self.path.write_text(json.dumps(rows),encoding='utf-8')
        changed=open_local(self.root)
        self.assertEqual(prefix,changed.read(changed.dataset.version,0,180060,revealed_before=180)['rows'])

    def test_http_rate_limit(self):
        async def run():
            app=create_local_app(self.service,rate_limit=1)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app,client=('127.0.0.1',1)),base_url='http://127.0.0.1:5199') as client:
                self.assertEqual((await client.get('/api/v1/local-market/dataset')).status_code,200)
                self.assertEqual((await client.get('/api/v1/local-market/dataset')).status_code,429)
        asyncio.run(run())

"""CP6A-10 P0 local integration: synthetic QA only, real isolated PostgreSQL."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import os
from pathlib import Path
import tempfile
import unittest
import uuid
from unittest.mock import patch

import psycopg
from fastapi.testclient import TestClient

from contracts.primitives import ContractError
from execution.availability import catalog_availability, eligible_start_month
from execution.local_api import create_local_app
from execution.research import ResearchApplication
from execution.research_fixture import STEP_NS
from infrastructure.database import connect, migrate
from market_data.monthly_parquet import MonthlyParquetProvider, write_monthly_parquet
from ticks.provider import SyntheticTickProvider

DSN = os.getenv("BTL_TEST_DATABASE_URL")
ORIGIN = "http://127.0.0.1:5173"
ROOT = "/api/v1/tick-alpha"


def new_method():
    return dict(schemaVersion=1, artifact="BTL-LOCAL-METHOD-1", id="method:" + uuid.uuid4().hex,
                name="P0 planned QA", kind="PROTOCOL", checklistOn=False,
                conditions=[dict(id="condition:qa", label="QA setup")], riskPercent="1", rr="2")


@unittest.skipUnless(DSN, "Dedicated isolated PostgreSQL QA required; skip is not PASS")
class P0LocalIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        migrate(DSN)

    def setUp(self):
        self.client = TestClient(create_local_app(DSN), base_url="http://127.0.0.1:5188",
                                  client=("127.0.0.1", 61001),
                                  headers={"Origin": ORIGIN, "X-BTL-Local": "1", "X-BTL-Source": "synthetic"})
        self.client.__enter__()
        catalog = self.client.get(ROOT + "/catalog").json()
        self.assertEqual(catalog["availability"]["executionEligibility"], "SYNTHETIC_QA_ONLY")
        self.assertEqual(catalog["availability"]["sourceRights"], "NOT_APPLICABLE_SYNTHETIC")
        entry = catalog["availability"]["instruments"][0]
        self.assertEqual(entry["status"], "PARTIAL")
        self.assertEqual(entry["periods"][0]["status"], "AVAILABLE")
        self.assertIn("not complete month coverage", entry["periods"][0]["reason"])
        self.method = new_method()
        self.assertEqual(self.client.post(ROOT + "/methods", json=self.method).status_code, 200)
        self.session_id = "session:" + uuid.uuid4().hex
        created = self.client.post(ROOT + "/sessions", json=dict(
            id=self.session_id, name="P0 local QA", methodId=self.method["id"],
            initialBalance="10000", startPeriod=catalog["startPeriod"]))
        self.assertEqual(created.status_code, 200, created.text)
        self.view = created.json()

    def tearDown(self):
        self.client.__exit__(None, None, None)

    def review(self):
        quote = self.view["quote"]
        from decimal import Decimal
        entry = Decimal(quote["ask"]) - Decimal("1")
        body = dict(sessionId=self.session_id, requestId="order:" + uuid.uuid4().hex,
                    expectedRevision=self.view["state"]["revision"], planId="plan:" + uuid.uuid4().hex,
                    planRevision=0, draft=dict(side="LONG", orderType="LIMIT", workflow="PLANNED",
                        entry=str(entry), quantity=None, sl=str(entry-Decimal("1")), tp=None,
                        riskPercent=None, observations=[]))
        response = self.client.post(ROOT + "/reviews", json=body)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def count_commands(self, command_id):
        with connect(DSN) as db:
            return db.execute("SELECT count(*) FROM btl.tick_commands WHERE workspace_id=%s AND session_id=%s AND command_id=%s",
                              ("fixture:local-alpha", self.session_id, command_id)).fetchone()[0]

    def test_create_planned_review_confirm_receipt_journal_and_exact_retry(self):
        reviewed = self.review()
        command_id = reviewed["review"]["command"]["commandId"]
        status_path = f"{ROOT}/sessions/{self.session_id}/commands/{command_id}"
        before = self.client.get(status_path).json()
        self.assertEqual(before["status"], "UNKNOWN", "absence at the review revision is not refusal")
        confirm_path = f"{ROOT}/sessions/{self.session_id}/confirm"
        response = self.client.post(confirm_path, json={"reviewId": command_id, "reviewHash": reviewed["reviewHash"]})
        self.assertEqual(response.status_code, 200, response.text)
        receipt = response.json()
        self.assertEqual(receipt["artifact"], "BTL-TICK-EXECUTION-RESULT-1")
        self.assertEqual(receipt["commandId"], command_id)
        self.assertTrue(receipt["durable"])
        checked = self.client.get(status_path).json()
        self.assertEqual((checked["status"], checked["reviewHash"]), ("COMMITTED", reviewed["reviewHash"]))
        self.assertEqual(checked["receipt"], receipt)
        self.assertEqual(checked["receipt"]["commandHash"], receipt["commandHash"])
        self.assertEqual(checked["receipt"]["state"]["revision"], self.view["state"]["revision"] + 1)
        self.assertTrue(all(event["sessionId"] == self.session_id for event in receipt["events"]))
        journal = self.client.get(f"{ROOT}/sessions/{self.session_id}/journal").json()
        self.assertEqual(journal["financialAuthority"], "COMMITTED_EVENTS_ONLY")
        self.assertTrue(any(order["id"] == command_id for order in journal["orders"]))
        duplicate = self.client.post(confirm_path, json={"reviewId": command_id, "reviewHash": reviewed["reviewHash"]})
        self.assertEqual(duplicate.status_code, 200, duplicate.text)
        self.assertEqual(duplicate.json(), receipt)
        self.assertEqual(self.count_commands(command_id), 1, "exact retry created a second financial command")

        # Same command ID with a changed command body must fail closed at the
        # durable store's idempotency check, before any reducer transition.
        service = ResearchApplication(DSN)
        try:
            changed = deepcopy(reviewed["review"]["command"])
            changed["payload"]["entry"] = str(float(changed["payload"]["entry"]) - 1)
            with self.assertRaisesRegex(ValueError, "REFUSED_IDEMPOTENCY_CONFLICT"):
                service.controller.apply(service.scope, changed)
        finally:
            service.close()
        self.assertEqual(self.count_commands(command_id), 1)

    def test_commit_with_lost_response_is_resolved_from_receipt_not_retried(self):
        reviewed = self.review()
        command_id = reviewed["review"]["command"]["commandId"]
        confirm_path = f"{ROOT}/sessions/{self.session_id}/confirm"
        original = ResearchApplication.confirm

        def commit_then_drop(service, session_id, body):
            original(service, session_id, body)
            raise RuntimeError("simulated response loss after durable commit")

        with patch.object(ResearchApplication, "confirm", commit_then_drop):
            lost = self.client.post(confirm_path, json={"reviewId": command_id, "reviewHash": reviewed["reviewHash"]})
        self.assertEqual(lost.status_code, 503)
        status_path = f"{ROOT}/sessions/{self.session_id}/commands/{command_id}"
        checked = self.client.get(status_path).json()
        self.assertEqual(checked["status"], "COMMITTED")
        self.assertEqual(checked["receipt"]["commandId"], command_id)
        self.assertEqual(self.count_commands(command_id), 1)

    def test_jump_to_next_event_stops_at_entry_then_exit_and_retry_is_receipt_safe(self):
        reviewed = self.review()
        order_id = reviewed['review']['command']['commandId']
        confirmed = self.client.post(f"{ROOT}/sessions/{self.session_id}/confirm",
            json={'reviewId':order_id,'reviewHash':reviewed['reviewHash']})
        self.assertEqual(confirmed.status_code,200,confirmed.text)
        start = confirmed.json()['state']

        def jump(expected):
            raw=dict(schemaVersion=1,artifact='BTL-JUMP-NEXT-EVENT-1',requestId=uuid.uuid4().hex,
                     sessionId=self.session_id,expectedRevision=expected,timeframe='1m')
            response=self.client.post(f"{ROOT}/sessions/{self.session_id}/jump-next-event",json=raw)
            self.assertEqual(response.status_code,200,response.text)
            return raw,response.json()

        request,entry=jump(start['revision'])
        self.assertEqual(entry['status'],'EVENT_FOUND')
        self.assertEqual([event['kind'] for event in entry['events'] if event['kind']=='ENTRY_FILL'],['ENTRY_FILL'])
        self.assertEqual(entry['view']['state']['orders'][order_id]['status'],'ACTIVE')
        self.assertEqual(entry['view']['state']['throughNs'],entry['throughNs'])
        # The same request reuses its exact ADVANCE receipt after a response loss.
        retry=self.client.post(f"{ROOT}/sessions/{self.session_id}/jump-next-event",json=request)
        self.assertEqual(retry.status_code,200,retry.text)
        self.assertEqual(retry.json()['events'],entry['events'])
        self.assertEqual(retry.json()['view']['state']['revision'],entry['view']['state']['revision'])

        _request,exit_event=jump(entry['view']['state']['revision'])
        self.assertEqual(exit_event['status'],'EVENT_FOUND')
        fills=[event for event in exit_event['events'] if event['kind']=='EXIT_FILL']
        self.assertEqual(len(fills),1)
        self.assertEqual(fills[0]['detail']['reason'],'SL')
        self.assertTrue(any(order['id']==order_id and order['status']=='CLOSED'
                            for order in exit_event['view']['analysis']['orders']))
        journal=self.client.get(f"{ROOT}/sessions/{self.session_id}/journal").json()
        self.assertTrue(any(order['id']==order_id and order['status']=='CLOSED' for order in journal['orders']))
        summary=self.client.get(f"{ROOT}/sessions/{self.session_id}/summary").json()
        self.assertEqual(summary['completedTrades'],1)
        self.assertEqual(summary['balance'],exit_event['view']['state']['balance'])

    def test_jump_processes_the_last_tick_when_its_timestamp_is_already_the_frontier(self):
        reviewed=self.review()
        order_id=reviewed['review']['command']['commandId']
        confirmed=self.client.post(f"{ROOT}/sessions/{self.session_id}/confirm",
            json={'reviewId':order_id,'reviewHash':reviewed['reviewHash']})
        self.assertEqual(confirmed.status_code,200,confirmed.text)
        state=confirmed.json()['state']
        raw=dict(schemaVersion=1,artifact='BTL-JUMP-NEXT-EVENT-1',requestId=uuid.uuid4().hex,
            sessionId=self.session_id,expectedRevision=state['revision'],timeframe='1m')
        response=self.client.post(f"{ROOT}/sessions/{self.session_id}/jump-next-event",json=raw)
        self.assertEqual(response.status_code,200,response.text)
        result=response.json()
        self.assertEqual(result['status'],'EVENT_FOUND')
        self.assertEqual(result['advances'],1)
        self.assertTrue(any(event['kind']=='ENTRY_FILL' for event in result['events']))
        self.assertEqual(result['view']['state']['revision'],state['revision']+1)

    def test_jump_preserves_pending_order_when_no_event_through_three_day_session_end(self):
        from application.models import TrustedScope
        from execution.research_fixture import START_NS
        from ticks.provider import SyntheticTickProvider

        day = 86_400_000_000_000
        source = SyntheticTickProvider([
            dict(ordinal=str(i), timeNs=str(START_NS + i * day),
                 bid='2000', ask='2000.1', sequence=str(i))
            for i in range(4)
        ], dataset_id='synthetic:jump-three-day-no-event-v1', trusted=True,
           execution_fixture=True, chunk_size=1)
        scope = TrustedScope('fixture:jump-three-day:'+uuid.uuid4().hex,
                             'fixture:jump-three-day-owner:'+uuid.uuid4().hex)
        app = ResearchApplication(DSN, scope, synthetic_provider=source)
        try:
            record = new_method()
            app.create_method(record)
            session = 'session:jump-three-day:'+uuid.uuid4().hex
            view = app.create_session(dict(id=session, name='Three day no event',
                methodId=record['id'], initialBalance='10000', startPeriod='2020-01'))
            request = dict(sessionId=session, requestId='order:'+uuid.uuid4().hex,
                expectedRevision=view['state']['revision'], planId='plan:'+uuid.uuid4().hex,
                planRevision=0, draft=dict(side='LONG', orderType='LIMIT', workflow='PLANNED',
                    entry='1990', quantity=None, sl='1980', tp=None, riskPercent='1', observations=[]))
            reviewed = app.review(request)
            app.confirm(session, dict(reviewId=request['requestId'], reviewHash=reviewed['reviewHash']))
            start = app.inspect(session)['state']
            jump = dict(schemaVersion=1, artifact='BTL-JUMP-NEXT-EVENT-1',
                requestId=uuid.uuid4().hex, sessionId=session,
                expectedRevision=start['revision'], timeframe='1m')
            result = app.jump_next_event(session, jump)
            self.assertEqual(result['status'], 'NO_EVENT_UNTIL_SESSION_END')
            self.assertEqual(result['view']['state']['orders'][request['requestId']]['status'], 'PENDING')
            self.assertEqual(int(result['throughNs']), int(source.describe(
                source.dataset_id, source.dataset_version)['range']['endNs']) - 1)
            retried = app.jump_next_event(session, jump)
            self.assertEqual((retried['status'], retried['throughNs'], retried['events']),
                             (result['status'], result['throughNs'], result['events']))
            self.assertEqual(retried['view']['state'], result['view']['state'])
            journal = app.journal(session)
            self.assertEqual([row['status'] for row in journal['orders']], ['PENDING'])
            with connect(DSN) as db:
                count = db.execute('SELECT count(*) FROM btl.tick_commands '
                    'WHERE workspace_id=%s AND session_id=%s AND command_id LIKE %s',
                    (scope.workspace_id, session, 'jump:'+jump['requestId']+':r%')).fetchone()[0]
            self.assertEqual(count, 1)
        finally:
            app.close()

    def test_jump_reads_monthly_parquet_across_partition_boundary(self):
        """A fill on the February partition is found through canonical Jump/ADVANCE."""
        from datetime import datetime, timezone
        from application.models import TrustedScope

        jan_start = int(datetime(2020, 1, 1, 0, 30, 0, tzinfo=timezone.utc).timestamp() * 1_000_000_000)
        jan = int(datetime(2020, 1, 31, 23, 59, 59, tzinfo=timezone.utc).timestamp() * 1_000_000_000)
        feb = int(datetime(2020, 2, 1, 0, 0, 0, tzinfo=timezone.utc).timestamp() * 1_000_000_000)
        source = SyntheticTickProvider([
            dict(ordinal='0', timeNs=str(jan_start), bid='2000', ask='2000.1', sequence='0'),
            dict(ordinal='1', timeNs=str(jan), bid='2000', ask='2000.1', sequence='1'),
            dict(ordinal='2', timeNs=str(feb), bid='1998', ask='1998.1', sequence='2'),
        ], dataset_id='synthetic:jump-month-boundary-v1', trusted=True,
           execution_fixture=True, chunk_size=1)
        source_manifest = source.describe(source.dataset_id, source.dataset_version)
        def source_events():
            token = None
            while True:
                page = source.read_page(source.dataset_id, source.dataset_version, token, 64)
                yield from page['events']
                if page['endOfDataset']:
                    return
                token = page['nextToken']
        with tempfile.TemporaryDirectory(prefix='riksora-jump-month-') as temporary:
            parquet_root = Path(temporary) / 'dataset'
            manifest = write_monthly_parquet(parquet_root, source_events(), source_manifest,
                expected_version=source.dataset_version, row_group_size=1)
            provider = MonthlyParquetProvider(parquet_root,
                expected_dataset_id=source.dataset_id,
                expected_dataset_version=source.dataset_version,
                expected_manifest_hash=manifest['manifestHash'])
            self.assertEqual([item['month'] for item in manifest['files']], ['2020-01', '2020-02'])
            scope = TrustedScope('fixture:jump-month:'+uuid.uuid4().hex,
                                 'fixture:jump-month-owner:'+uuid.uuid4().hex)
            app = ResearchApplication(DSN, scope, synthetic_provider=provider)
            try:
                record = new_method()
                app.create_method(record)
                session = 'session:jump-month:' + uuid.uuid4().hex
                created = app.create_session(dict(id=session, name='Monthly boundary Jump',
                    methodId=record['id'], initialBalance='10000', startPeriod='2020-01'))
                quote = created['quote']
                from decimal import Decimal
                entry = Decimal(quote['ask']) - Decimal('1')
                request = dict(sessionId=session, requestId='order:'+uuid.uuid4().hex,
                    expectedRevision=created['state']['revision'], planId='plan:'+uuid.uuid4().hex,
                    planRevision=0, draft=dict(side='LONG', orderType='LIMIT', workflow='PLANNED',
                        entry=str(entry), quantity=None, sl=str(entry-Decimal('100')), tp=None,
                        riskPercent='1', observations=[]))
                reviewed = app.review(request)
                app.confirm(session, dict(reviewId=request['requestId'],
                                          reviewHash=reviewed['reviewHash']))
                before = app.inspect(session)['state']
                jump = dict(schemaVersion=1, artifact='BTL-JUMP-NEXT-EVENT-1',
                    requestId=uuid.uuid4().hex, sessionId=session,
                    expectedRevision=before['revision'], timeframe='1m')
                result = app.jump_next_event(session, jump)
                self.assertEqual(result['status'], 'EVENT_FOUND')
                self.assertTrue(any(event['kind'] == 'ENTRY_FILL' for event in result['events']))
                self.assertEqual(result['view']['state']['datasetId'], source.dataset_id)
                self.assertEqual(result['view']['state']['datasetVersion'], source.dataset_version)
                self.assertEqual(result['view']['state']['revision'], before['revision'] + 1)
                self.assertEqual(result['view']['state']['throughNs'], str(feb))
            finally:
                app.close()

    def test_concurrent_jump_requests_apply_one_session_revision_once(self):
        """Distinct requests at one revision cannot duplicate a financial ADVANCE."""
        from application.models import TrustedScope
        scope = TrustedScope('fixture:jump-concurrent:'+uuid.uuid4().hex,
                             'fixture:jump-concurrent-owner:'+uuid.uuid4().hex)
        app = ResearchApplication(DSN, scope)
        try:
            record = new_method()
            app.create_method(record)
            session = 'session:jump-concurrent:' + uuid.uuid4().hex
            created = app.create_session(dict(id=session, name='Concurrent Jump',
                methodId=record['id'], initialBalance='10000', startPeriod='2020-01'))
            review_id = 'order:'+uuid.uuid4().hex
            reviewed = app.review(dict(sessionId=session, requestId=review_id,
                expectedRevision=created['state']['revision'], planId='plan:concurrent', planRevision=0,
                draft=dict(side='LONG', orderType='LIMIT', workflow='PLANNED', entry='2000',
                    quantity=None, sl='1990', tp=None, riskPercent='1', observations=[])))
            app.confirm(session, dict(reviewId=review_id,
                                      reviewHash=reviewed['reviewHash']))
            revision_now = app.inspect(session)['state']['revision']
            requests = [dict(schemaVersion=1, artifact='BTL-JUMP-NEXT-EVENT-1',
                requestId=uuid.uuid4().hex, sessionId=session,
                expectedRevision=revision_now, timeframe='1m') for _ in range(2)]

            def jump(raw):
                try:
                    return app.jump_next_event(session, raw)
                except ContractError as error:
                    return error

            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(jump, requests))
            committed = [value for value in results if isinstance(value, dict)]
            refused = [value for value in results if isinstance(value, ContractError)]
            self.assertEqual(len(committed), 1)
            self.assertEqual(len(refused), 1)
            self.assertEqual(refused[0].code, 'REFUSED_STALE_REVISION')
            state = app.inspect(session)['state']
            self.assertEqual(state['revision'], revision_now + 1)
            with connect(DSN) as db:
                count = db.execute('SELECT count(*) FROM btl.tick_commands '
                    'WHERE workspace_id=%s AND session_id=%s AND command_id LIKE %s',
                    (scope.workspace_id, session, 'jump:%:r'+str(revision_now))).fetchone()[0]
            self.assertEqual(count, 1)
        finally:
            app.close()

    def test_revision_advance_proves_not_committed_and_stale_confirm_refuses(self):
        reviewed = self.review()
        command_id = reviewed["review"]["command"]["commandId"]
        advance = dict(schemaVersion=1, artifact="BTL-TICK-EXECUTION-COMMAND-1",
                       sessionId=self.session_id, commandId="advance:" + uuid.uuid4().hex,
                       expectedRevision=self.view["state"]["revision"], kind="ADVANCE",
                       payload={"targetNs": str(int(self.view["state"]["throughNs"]) + STEP_NS)})
        moved = self.client.post(f"{ROOT}/sessions/{self.session_id}/commands", json=advance)
        self.assertEqual(moved.status_code, 200, moved.text)
        status_path = f"{ROOT}/sessions/{self.session_id}/commands/{command_id}"
        status = self.client.get(status_path).json()
        self.assertEqual(status["status"], "NOT_COMMITTED")
        self.assertGreater(status["currentRevision"], status["expectedRevision"])
        stale = self.client.post(f"{ROOT}/sessions/{self.session_id}/confirm",
                                 json={"reviewId": command_id, "reviewHash": reviewed["reviewHash"]})
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(self.count_commands(command_id), 0)

    def test_in_flight_session_lock_stays_unknown_then_receipt_becomes_committed(self):
        reviewed = self.review()
        command_id = reviewed["review"]["command"]["commandId"]
        lock = psycopg.connect(DSN, autocommit=False)
        lock.execute("SELECT 1 FROM btl.tick_sessions WHERE workspace_id=%s AND session_id=%s FOR UPDATE",
                     ("fixture:local-alpha", self.session_id))
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                pending = pool.submit(self.client.post, f"{ROOT}/sessions/{self.session_id}/confirm",
                                      json={"reviewId": command_id, "reviewHash": reviewed["reviewHash"]})
                # The writer is waiting on the Session row; a read-only lookup
                # sees the prior snapshot and must not call it NOT_COMMITTED.
                import time
                time.sleep(0.2)
                unknown = self.client.get(f"{ROOT}/sessions/{self.session_id}/commands/{command_id}").json()
                self.assertEqual(unknown["status"], "UNKNOWN")
                lock.commit()
                response = pending.result(timeout=8)
            self.assertEqual(response.status_code, 200, response.text)
            committed = self.client.get(f"{ROOT}/sessions/{self.session_id}/commands/{command_id}").json()
            self.assertEqual(committed["status"], "COMMITTED")
            self.assertEqual(self.count_commands(command_id), 1)
        finally:
            if not lock.closed:
                lock.rollback()
                lock.close()


class AvailabilityContractTests(unittest.TestCase):
    def test_partial_allows_only_exact_available_synthetic_start_month(self):
        dto = catalog_availability(instrument_id="XAUUSD", dataset_id="synthetic:qa",
                                   dataset_version="a"*64, start_period="2020-01", synthetic=True)
        self.assertTrue(eligible_start_month(dto, "XAUUSD", "2020-01"))
        self.assertFalse(eligible_start_month(dto, "XAUUSD", "2020-02"))
        dto["instruments"][0]["periods"].append({"period":"2020-02", "status":"GAP"})
        self.assertFalse(eligible_start_month(dto, "XAUUSD", "2020-02"))

    def test_historical_rights_unknown_is_never_eligible(self):
        dto = catalog_availability(instrument_id="XAUUSD", dataset_id="historical:qa",
                                   dataset_version="b"*64, start_period="2015-08", synthetic=False)
        self.assertEqual(dto["sourceRights"], "UNKNOWN")
        self.assertEqual(dto["executionEligibility"], "NOT_GRANTED")
        self.assertFalse(eligible_start_month(dto, "XAUUSD", "2015-08"))
        self.assertFalse(eligible_start_month({**dto, "schemaVersion":2}, "XAUUSD", "2015-08"))


if __name__ == "__main__":
    unittest.main()

import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from contracts.canonical import canonical_bytes, content_hash
from contracts.primitives import ContractError
from execution.postgres import pack
from execution.observed_postgres import QA3_RESULT, QA3_CHECKPOINT
from tests.qa_historical_day_v2 import _hash_canonical_records
from tests.qa_annual_streaming_verifier import (
    EXPECTED_GROUPS, EXPECTED_SESSION, EXPECTED_WORKSPACE, RecordHasher, VerificationError,
    _check_replay_config, _coverage_boundary_gaps, _enable_qa_shared_source_mode,
    _io_delta, _load_source_progress, _verify_timeline_session_binding,
    _source_verification_input_hash,
    _canonical_record_wire,
    _seal_progress, _verify_manifest_tree,
    _verify_receipts,
)


class NoFetchallCursor:
    def __init__(self, rows):
        self.rows=iter(rows)
        self.closed=False

    def execute(self, query, params):
        self.query=query
        self.params=params

    def fetchmany(self, size):
        batch=[]
        for _ in range(size):
            try: batch.append(next(self.rows))
            except StopIteration: break
        return batch

    def fetchall(self):
        raise AssertionError('fetchall must not be used')

    def close(self):
        self.closed=True


class FakeConnection:
    def __init__(self, counts, base, rows):
        self.counts=counts
        self.base=base
        self.cursor_rows=rows
        self.stream_cursor=None

    def execute(self, query, params):
        if 'SELECT (SELECT count(*) FROM btl.tick_commands' in query:
            return FakeResult(self.counts)
        if 'revision=0' in query:
            return FakeResult(self.base)
        raise AssertionError('unexpected execute: '+query)

    def cursor(self, name=None):
        self.stream_cursor=NoFetchallCursor(self.cursor_rows)
        return self.stream_cursor


class FakeResult:
    def __init__(self, row): self.row=row
    def fetchone(self): return self.row


class StreamingVerifierTests(unittest.TestCase):
    def test_requested_interval_prefix_and_suffix_are_explicit_unknown_gaps(self):
        first=1704150000312000000
        last=1735682335257000000
        through=1735689599999999999
        gaps=_coverage_boundary_gaps(str(first),str(last),str(through))
        self.assertEqual([gap['boundary'] for gap in gaps],
            ['REQUESTED_INTERVAL_PREFIX','REQUESTED_INTERVAL_SUFFIX'])
        self.assertTrue(all(gap['kind']=='UNKNOWN_COVERAGE_GAP' and
                            gap['sourceQuality']=='UNKNOWN' and gap['quoteAvailable'] is False
                            for gap in gaps))
        self.assertEqual(gaps[0]['elapsedNs'],'82800312000000')
        self.assertEqual(gaps[1]['elapsedNs'],'7264742999999')

    def test_shared_source_mode_is_enabled_only_in_verifier_process(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {}, clear=False):
            os.environ.pop('BTL_HISTORICAL_QA_ROOT',None)
            os.environ.pop('BTL_QA_SHARED_CANONICAL_SOURCE_V1',None)
            _enable_qa_shared_source_mode(tmp)
            self.assertEqual(os.environ['BTL_HISTORICAL_QA_ROOT'],str(Path(tmp).resolve()))
            self.assertEqual(os.environ['BTL_QA_SHARED_CANONICAL_SOURCE_V1'],'1')

    def test_timeline_visible_prefix_hash_binds_session_source_prefix(self):
        state=dict(nextGroupIndex='56208511',throughNs='1735689599999999999',
            sourceCursorRevision='219566',sourcePrefixHash='b'*64)
        cursor=dict(nextGroupIndex='56208511',throughNs='1735689599999999999',
            sessionStartNs='1704150000312000000',revision='219566',visiblePrefixHash='b'*64)
        result=_verify_timeline_session_binding(state,cursor,'1735689599999999999')
        self.assertEqual(result['status'],'PASS')
        self.assertEqual(result['sessionSourcePrefixHash'],result['timelineVisiblePrefixHash'])
        cursor['visiblePrefixHash']='c'*64
        with self.assertRaisesRegex(VerificationError,'TIMELINE_SESSION_CHECKPOINT_MISMATCH:sourcePrefixHash'):
            _verify_timeline_session_binding(state,cursor,'1735689599999999999')

    def test_source_verification_input_hash_uses_canonical_versioned_envelope(self):
        first=_source_verification_input_hash('a'*64,'b'*64,'source-v1')
        self.assertEqual(len(first),64)
        self.assertEqual(first,_source_verification_input_hash('a'*64,'b'*64,'source-v1'))
        self.assertNotEqual(first,_source_verification_input_hash('a'*64,'c'*64,'source-v1'))

    def test_process_io_fallback_reports_cgroup_process_delta(self):
        before=dict(ioStat=None,processIo=dict(read_bytes=100,write_bytes=30,rchar=1000,wchar=200,
            samples=2,samplingErrors=0))
        after=dict(ioStat=None,processIo=dict(read_bytes=5100,write_bytes=930,rchar=9000,wchar=1200,
            samples=9,samplingErrors=1))
        delta=_io_delta(before,after)
        self.assertEqual(delta['read_bytes'],5000)
        self.assertEqual(delta['write_bytes'],900)
        self.assertEqual(delta['rchar'],8000)
        self.assertEqual(delta['wchar'],1000)
        self.assertEqual(delta['samplingErrors'],1)

    def test_record_hasher_matches_reference_ordered_hash(self):
        records=[{'a':1}, {'schemaVersion':1,'b':'x'}, ['c',3]]
        hasher=RecordHasher('fixture')
        for record in records: hasher.add(record)
        self.assertEqual(hasher.hexdigest(),_hash_canonical_records('fixture',records))
        reordered=RecordHasher('fixture')
        for record in reversed(records): reordered.add(record)
        self.assertNotEqual(hasher.hexdigest(),reordered.hexdigest())

    def test_source_group_chain_projection_uses_btl_cjson_v1_envelope_golden(self):
        projection=dict(timeNs='1704150000312000000',groupId='a'*64,
            eventIds=['evt:one','evt:two'],bid='2030.125',ask='2030.250')
        before=dict(projection)
        wire=_canonical_record_wire(projection)
        expected=(b'{"record":{"ask":"2030.250","bid":"2030.125",'
            b'"eventIds":["evt:one","evt:two"],"groupId":"'+b'a'*64+
            b'","timeNs":"1704150000312000000"},"schemaVersion":1}')
        self.assertEqual(wire,expected)
        self.assertEqual(hashlib.sha256(wire).hexdigest(),
            '89c4ba862296956d7be7fc36bdbfb0a066dc0ab00c10e8962dac17df1d2907d0')
        self.assertEqual(projection,before,'verifier envelope must not mutate source projection')

    def test_canonical_root_schema_negative_vectors_still_refuse(self):
        record=dict(timeNs='1',groupId='a'*64,eventIds=[],bid='1',ask='2')
        for root in (record,dict(schemaVersion=True,record=record),
                     dict(schemaVersion=2,record=record),
                     dict(schemaVersion='1',record=record)):
            with self.assertRaises(ContractError):canonical_bytes(root)

    def test_receipts_stream_in_small_batches_without_fetchall(self):
        rows=[]
        for rev,cid,replay in ((1,'advance:1',{'throughNs':'1'}),(2,'read:2',None)):
            command_hash=hashlib.sha256(f'command-{rev}'.encode()).hexdigest()
            chain_hash=hashlib.sha256(f'chain-{rev}'.encode()).hexdigest()
            checkpoint,checkpoint_hash=pack(dict(schemaVersion=1,artifact=QA3_CHECKPOINT,
                revision=rev,stateHash=f'{rev:064x}',chainHash=chain_hash))
            receipt,receipt_hash=pack(dict(schemaVersion=1,artifact=QA3_RESULT,
                commandId=cid,commandHash=command_hash,stateRevision=rev,
                stateHash=f'{rev:064x}',chainHash=chain_hash,durable=True,replay=replay))
            rows.append((rev,cid,command_hash,receipt,receipt_hash,rev,checkpoint,checkpoint_hash))
        base,base_hash=pack(dict(schemaVersion=1,revision=0))
        conn=FakeConnection((2,3),(base,base_hash),rows)
        with patch('tests.qa_annual_streaming_verifier._guard',return_value={}):
            result=_verify_receipts(conn,EXPECTED_WORKSPACE,EXPECTED_SESSION,2,Path('/cgroup'),0)
        self.assertEqual(result['status'],'PASS')
        self.assertEqual(result['commands'],2)
        self.assertEqual(result['advanceCommands'],1)
        self.assertTrue(conn.stream_cursor.closed)

    def test_source_progress_hash_rejects_tampering(self):
        state={'schemaVersion':1,'sessionId':EXPECTED_SESSION,'revision':1}
        input_hash='a'*64
        value=_seal_progress(dict(schemaVersion=1,
            artifact='RIKSORA-ANNUAL-SOURCE-VERIFY-PROGRESS-2',inputHash=input_hash,
            sessionId=EXPECTED_SESSION,stateHash=content_hash(state),nextPosition='cursor-1',
            groups=0,ticks=0,firstQuoteNs=None,lastQuoteNs=None,previousGroupNs=None,
            matchedFillEventIds=[],sourceGapCounts={},sourceGapChain='0'*64,
            groupChainHash='0'*64,status='RUNNING',pages=0))
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'progress.json';path.write_text(json.dumps(value))
            self.assertEqual(_load_source_progress(path,input_hash,state)['groups'],0)
            value['nextPosition']='tampered';path.write_text(json.dumps(value))
            with self.assertRaisesRegex(VerificationError,'SOURCE_PROGRESS_HASH_MISMATCH'):
                _load_source_progress(path,input_hash,state)

    def test_manifest_verifier_streams_and_detects_changed_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'nested').mkdir(mode=0o700)
            content=b'bounded manifest fixture\n';file=root/'nested'/'record.bin';file.write_bytes(content)
            os.chmod(file,0o600)
            entries=[]
            for path in (root,root/'nested',file):
                rel='.' if path==root else path.relative_to(root).as_posix()
                info=os.lstat(path)
                entry=dict(path=rel,mode=info.st_mode&0o777,
                    type='directory' if path.is_dir() else 'file',
                    size=0 if path.is_dir() else info.st_size)
                if path.is_file(): entry['sha256']=hashlib.sha256(content).hexdigest()
                if path!=root: entries.append(entry)
            result=_verify_manifest_tree(dict(entries=entries),root)
            self.assertEqual(result['logicalBytes'],len(content))
            file.write_bytes(b'x'*len(content))
            with self.assertRaisesRegex(VerificationError,'SNAPSHOT_FILE_HASH_MISMATCH'):
                _verify_manifest_tree(dict(entries=entries),root)

    def test_schedule_pins_every_day_and_first_day_extra_six(self):
        additional=[[day*24+hour for hour in (0,6,12,18)] for day in range(1,366)]
        config=dict(artifact='BTL-QA-REPLAY-CONFIG-1',continuousDays=366,
            timelineStorageMode='shared-source-v1',sourceProcessing='ALL_OBSERVED_GROUPS',
            maximumScheduledOrderAcceptances=1469,maxCumulativeOrders=4096,
            productionEnabled=False,annualSchedule=dict(version='cp6a10-annual-v1',
                maximumAcceptances=1469,annualLimit=4096,firstDayMaximumAcceptances=9,
                subsequentDayMaximumAcceptances=4,utcSlots=[0,6,12,18]),
            firstDayOrderStages=[0,6,12,18],additionalDayOrderStages=additional,
            ordersPerHourlyDecision=1,additionalDayOrdersPerDecision=1)
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp,'replay-config.json').write_text(json.dumps(config))
            source=type('Source',(),{'dataset_id':'dataset','version':'version'})()
            _,limits=_check_replay_config(Path(tmp),{'datasetId':'dataset','datasetVersion':'version'},source)
        self.assertEqual(limits[0],6)
        self.assertEqual(limits[6],1)
        self.assertEqual(sum(limits.values()),1469)
        self.assertEqual(len(limits),1464)
        self.assertEqual(EXPECTED_GROUPS,56_208_511)


if __name__=='__main__':
    unittest.main()

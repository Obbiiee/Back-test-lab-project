"""Actual native timeout kills the authored child, not merely its launcher."""
import ctypes
import asyncio
from concurrent.futures import Future
import os
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from cloud import worker
from contracts.primitives import ContractError

POOL_ENTRY = '''import json,os,sys
for line in sys.stdin:
 p=json.loads(line)
 result={"schemaVersion":1,"ready":True} if p.get("control")=="WARM_OPERATOR_SOURCES" else {"schemaVersion":1,"result":{"pid":os.getpid()}}
 sys.stdout.write(json.dumps(result)+"\\n");sys.stdout.flush()
'''


class WorkerDeadlineTests(unittest.TestCase):
    def tearDown(self):
        worker.close()

    def test_child_environment_receives_parent_job_limit(self):
        with patch.object(worker, 'MAX_JOBS', 120000):
            self.assertEqual(worker._environment('private-dsn')['BTL_WORKER_MAX_JOBS'], '120000')
        with patch.object(worker, 'MAX_JOBS', 0), self.assertRaises(ContractError):
            worker._environment('private-dsn')

    def test_native_pool_reuses_child_and_recycles_at_its_bound(self):
        with patch.object(worker,'SERVE_ENTRY',POOL_ENTRY):
            first=worker.pooled_invoke('authored-not-a-database',{'schemaVersion':1})
            second=worker.pooled_invoke('authored-not-a-database',{'schemaVersion':1})
            self.assertEqual(first,second)
            for slot in worker._slots:
                if slot.process is not None:slot.jobs=worker.MAX_JOBS
            recycled=worker.pooled_invoke('authored-not-a-database',{'schemaVersion':1})
            self.assertNotEqual(first,recycled)
            rebound=worker.pooled_invoke('different-authored-database',{'schemaVersion':1})
            self.assertNotEqual(recycled,rebound)

    def test_pooled_timeout_reaps_child_and_next_job_uses_fresh_process(self):
        entry='import json,os,sys,time\nfor line in sys.stdin:\n p=json.loads(line)\n if p.get("control")=="WARM_OPERATOR_SOURCES": result={"schemaVersion":1,"ready":True}\n else:\n  if p.get("sleep"): time.sleep(300)\n  result={"schemaVersion":1,"result":{"pid":os.getpid()}}\n sys.stdout.write(json.dumps(result)+"\\n");sys.stdout.flush()'
        with patch.object(worker,'SERVE_ENTRY',entry):
            first=worker.pooled_invoke('authored-not-a-database',{'schemaVersion':1})
            process=next(slot.process for slot in worker._slots if slot.process is not None)
            with self.assertRaises(ContractError) as failed:
                worker.pooled_invoke('authored-not-a-database',{'schemaVersion':1,'sleep':True},deadline=.5)
            self.assertEqual(failed.exception.code,'EXPIRED')
            self.assertIsNotNone(process.poll())
            next_job=worker.pooled_invoke('authored-not-a-database',{'schemaVersion':1})
            self.assertNotEqual(first,next_job)

    def test_pooled_oversized_response_is_reaped_without_import(self):
        entry='import sys; sys.stdin.readline();sys.stdout.write("{\\"schemaVersion\\":1,\\"ready\\":true}\\n");sys.stdout.flush();sys.stdin.readline();sys.stdout.write("x"*200+"\\n");sys.stdout.flush()'
        with patch.object(worker,'SERVE_ENTRY',entry),patch.object(worker,'MAX_RESULT',64):
            with self.assertRaises(ContractError) as failed:
                worker.pooled_invoke('authored-not-a-database',{'schemaVersion':1})
            self.assertEqual(failed.exception.code,'WORKER_UNAVAILABLE')
            self.assertTrue(all(slot.process is None for slot in worker._slots))

    def test_interrupted_pool_call_reaps_its_native_child(self):
        with patch.object(worker,'SERVE_ENTRY',POOL_ENTRY):
            worker.pooled_invoke('authored-not-a-database',{'schemaVersion':1})
            process=next(slot.process for slot in worker._slots if slot.process is not None)
            with patch.object(Future,'result',side_effect=KeyboardInterrupt),self.assertRaises(KeyboardInterrupt):
                worker.pooled_invoke('authored-not-a-database',{'schemaVersion':1})
            self.assertIsNotNone(process.poll())
            self.assertTrue(all(slot.process is None for slot in worker._slots))

    def test_failed_api_lifespan_reaps_retained_native_children(self):
        from cloud import queue
        with patch.object(worker,'SERVE_ENTRY',POOL_ENTRY):
            worker.pooled_invoke('authored-not-a-database',{'schemaVersion':1})
            process=next(slot.process for slot in worker._slots if slot.process is not None)
            async def fail():
                async with queue.lifespan(SimpleNamespace(state=SimpleNamespace(dsn='authored-not-a-database'))):
                    raise RuntimeError('Authored API shutdown failure')
            with patch.object(queue,'work_one',return_value=False),self.assertRaises(Exception):
                asyncio.run(fail())
            self.assertIsNotNone(process.poll())
            self.assertTrue(all(slot.process is None for slot in worker._slots))

    def test_configured_sources_warm_once_outside_replay_job(self):
        with patch.object(worker,'SERVE_ENTRY',POOL_ENTRY), patch.object(worker,'_start_slot',wraps=worker._start_slot) as start_slot, patch.dict(os.environ,{
                'BTL_OBSERVED_OPERATOR_CATALOG':'/private/operator-catalog.json',
                'BTL_OBSERVED_OPERATOR_CATALOG_SHA256':'a'*64}):
            self.assertTrue(worker.warm_sources('authored-not-a-database'))
            process=worker._slots[0].process
            result=worker.pooled_invoke('authored-not-a-database',{'schemaVersion':1})
            self.assertEqual(result['pid'],process.pid)
            worker._slots[0].jobs=worker.MAX_JOBS
            recycled=worker.pooled_invoke('authored-not-a-database',{'schemaVersion':1})
            self.assertNotEqual(recycled['pid'],process.pid)
            self.assertEqual(start_slot.call_count,2)
            self.assertTrue(all(call.args[2]==worker.STARTUP_WARMUP_DEADLINE for call in start_slot.call_args_list))

    def test_native_process_is_reaped_after_deadline(self):
        entry='import json,os,sys,time; p=json.loads(sys.stdin.buffer.read()); open(p["pidPath"],"w").write(str(os.getpid())); time.sleep(300)'
        with tempfile.TemporaryDirectory(prefix='btl-native-timeout-') as directory:
            path=Path(directory)/'authored-child.pid'
            with patch.object(worker,'ENTRY',entry),self.assertRaises(ContractError) as failed:
                worker.invoke('authored-not-a-database',{'schemaVersion':1,'pidPath':str(path)},deadline=1.5)
            self.assertEqual(failed.exception.code,'EXPIRED')
            pid=int(path.read_text())
            if os.name=='nt':
                native=ctypes.WinDLL('kernel32',use_last_error=True)
                native.OpenProcess.restype=ctypes.c_void_p
                native.GetExitCodeProcess.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_ulong)]
                native.CloseHandle.argtypes=[ctypes.c_void_p]
                handle=native.OpenProcess(0x1000,False,pid)
                if handle:
                    try:
                        code=ctypes.c_ulong()
                        self.assertTrue(native.GetExitCodeProcess(handle,ctypes.byref(code)))
                        self.assertNotEqual(code.value,259,'Native child must no longer be active')
                    finally:
                        native.CloseHandle(handle)
            else:
                with self.assertRaises(ProcessLookupError):os.kill(pid,0)

    def test_deadline_and_input_budget_refuse_before_process_creation(self):
        with patch.object(worker.subprocess,'run') as process:
            for deadline in (0,31,True):
                with self.assertRaises(ContractError):worker.invoke('unused',{'schemaVersion':1},deadline=deadline)
                with self.assertRaises(ContractError):worker.pooled_invoke('unused',{'schemaVersion':1},deadline=deadline)
            with self.assertRaises(ContractError):worker.invoke('unused',{'schemaVersion':1,'oversize':'a'*32769})
            process.assert_not_called()

    def test_chart_history_is_an_allowed_read_only_worker_operation(self):
        import json
        from cloud import research
        actor='11111111-1111-4111-8111-111111111111';workspace='22222222-2222-4222-8222-222222222222'
        payload={'schemaVersion':1,'actor':actor,'workspace':workspace,'operation':'chart_history',
                 'args':['session:qa',{'timeframe':'1m','offset':0}],'write':False}
        expected={'schemaVersion':1,'artifact':'BTL-OBSERVED-REFERENCE-OHLC-1','candles':[]}
        with patch.dict(os.environ,{'BTL_WORKER_DATABASE':'authored-qa'}),patch.object(research,'run',return_value=expected):
            result=json.loads(worker._execute(json.dumps(payload).encode()))
        self.assertEqual(result,{'schemaVersion':1,'result':expected})

"""Bounded process-local operational counters. Never a financial dependency.

No Session/user/source IDs, paths, query text, exceptions or market payloads.
Unavailable resource attribution remains explicit rather than invented.
"""
from collections import deque
from threading import Lock
from pathlib import Path
import time
import os

OPERATIONS=frozenset({'catalog','methods','sessions','reviews','view','confirm','commands','bootstrap','journal','summary','operational','unknown'})

class OperationalMetrics:
    def __init__(self, enabled=True):
        self.enabled=enabled;self.lock=Lock();self.started=time.monotonic()
        self.cpu_started=time.process_time()
        self.active=0;self.admitted=0;self.rejected=0;self.dropped=0
        self.counts={name:0 for name in OPERATIONS}
        self.status={'success':0,'refused':0,'error':0}
        self.latencies=deque(maxlen=256);self.response_bytes=0

    def observe(self,kind,operation='unknown',duration=0,status=200,response_bytes=0):
        if not self.enabled:return False
        if not self.lock.acquire(blocking=False):
            self.dropped+=1;return False
        try:
            if kind=='admitted':self.active+=1;self.admitted+=1
            elif kind=='rejected':self.rejected+=1
            elif kind=='completed':
                self.active=max(0,self.active-1)
                self.counts[operation if operation in OPERATIONS else 'unknown']+=1
                self.status['success' if status<400 else 'refused' if status<500 else 'error']+=1
                self.latencies.append(max(0,min(float(duration),3600)))
                self.response_bytes+=max(0,min(int(response_bytes),1048576))
            return True
        except Exception:
            self.dropped+=1;return False
        finally:self.lock.release()

    def snapshot(self):
        if not self.lock.acquire(blocking=False):return dict(artifact='BTL-OPERATIONAL-OBSERVATIONS-1',status='INCOMPLETE')
        try:
            samples=sorted(self.latencies)
            def percentile(p):return None if not samples else str(samples[max(0,(len(samples)*p+99)//100-1)])
            elapsed=max(0.0,time.monotonic()-self.started)
            cpu_seconds=max(0.0,time.process_time())
            io=self._io()
            return dict(artifact='BTL-OPERATIONAL-OBSERVATIONS-1',schemaVersion=1,
                status='PROCESS_LOCAL_ONLY' if self.enabled and self.dropped==0 else 'DISABLED_OR_INCOMPLETE',
                uptimeSeconds=str(elapsed),processCpuSeconds=str(cpu_seconds),
                processCpuUtilizationCores=str(max(0.0,cpu_seconds-self.cpu_started)/elapsed) if elapsed else None,
                processRssBytes=self._rss(),processIoBytes=io,
                cgroup=self._cgroup(),
                active=self.active,admitted=self.admitted,rejected=self.rejected,dropped=self.dropped,
                routeCounts=dict(self.counts),statusCounts=dict(self.status),responseBytes=self.response_bytes,
                latencyWindow=len(samples),latencyWindowLimit=256,
                latencySeconds=dict(p50=percentile(50),p95=percentile(95),p99=percentile(99)),
                admissionLimit=2,queuePolicy='IMMEDIATE_REJECTION_NO_QUEUE',
                unavailable=['nodeCPU','DBPoolPressure','perSessionCPU','perSessionStorage','hostedTariffs'],
                interpretation='Process/cgroup observations only; not per-Session attribution, hosted capacity certification, per-user cost or financial evidence. Reset on process restart.')
        finally:self.lock.release()

    @staticmethod
    def _read_int(path):
        try:
            raw=Path(path).read_text().strip()
            return None if raw in ('max','') else int(raw)
        except (OSError,ValueError):return None

    @classmethod
    def _rss(cls):
        try:
            resident=int(Path('/proc/self/statm').read_text().split()[1])
            return resident*os.sysconf('SC_PAGE_SIZE')
        except (OSError,ValueError,IndexError):return None

    @staticmethod
    def _io():
        try:
            values={}
            for line in Path('/proc/self/io').read_text().splitlines():
                key,value=line.split(':',1);values[key]=int(value.strip())
            return {key:values.get(key) for key in ('read_bytes','write_bytes','rchar','wchar')}
        except (OSError,ValueError):return None

    @classmethod
    def _cgroup(cls):
        memory_current=cls._read_int('/sys/fs/cgroup/memory.current')
        memory_peak=cls._read_int('/sys/fs/cgroup/memory.peak')
        cpu_usec=None
        try:
            for line in Path('/sys/fs/cgroup/cpu.stat').read_text().splitlines():
                key,value=line.split();
                if key=='usage_usec':cpu_usec=int(value)
        except (OSError,ValueError):pass
        io=None
        try:
            io=Path('/sys/fs/cgroup/io.stat').read_text().splitlines()
        except OSError:pass
        return {'memoryCurrentBytes':memory_current,'memoryPeakBytes':memory_peak,
                'cpuUsageUsec':cpu_usec,'ioStat':io}

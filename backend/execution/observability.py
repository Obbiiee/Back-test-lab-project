"""Bounded process-local operational counters. Never a financial dependency.

No Session/user/source IDs, paths, query text, exceptions or market payloads.
Unavailable resource attribution remains explicit rather than invented.
"""
from collections import deque
from threading import Lock
import time

OPERATIONS=frozenset({'catalog','methods','sessions','reviews','view','confirm','commands','bootstrap','journal','operational','unknown'})

class OperationalMetrics:
    def __init__(self, enabled=True):
        self.enabled=enabled;self.lock=Lock();self.started=time.monotonic()
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
            return dict(artifact='BTL-OPERATIONAL-OBSERVATIONS-1',schemaVersion=1,
                status='PROCESS_LOCAL_ONLY' if self.enabled and self.dropped==0 else 'DISABLED_OR_INCOMPLETE',
                uptimeSeconds=str(time.monotonic()-self.started),processCpuSeconds=str(time.process_time()),
                active=self.active,admitted=self.admitted,rejected=self.rejected,dropped=self.dropped,
                routeCounts=dict(self.counts),statusCounts=dict(self.status),responseBytes=self.response_bytes,
                latencyWindow=len(samples),latencyWindowLimit=256,
                latencySeconds=dict(p50=percentile(50),p95=percentile(95),p99=percentile(99)),
                admissionLimit=2,queuePolicy='IMMEDIATE_REJECTION_NO_QUEUE',
                unavailable=['RSS','nodeCPU','diskIO','DBPoolPressure','perSessionCPU','hostedTariffs'],
                interpretation='Not a hosted capacity certificate, per-user cost or financial evidence. Reset on process restart.')
        finally:self.lock.release()

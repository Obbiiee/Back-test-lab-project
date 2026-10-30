"""Operator-only conditional source admission; never a consumer capability.

A trusted operator pins an independently reviewed qualification receipt hash.
Receipt paths/hashes must NEVER be accepted from a public request. This first
capability supports only empty sidecar catalogs; it does not invent a causal
interpretation for unrestricted future gap metadata. Raw UNKNOWN is unchanged.
"""
from datetime import datetime,timezone
import hashlib,json,stat,os
from pathlib import Path

from contracts.primitives import digest,require
from ticks.contracts_v2 import shape,validate_container
from ticks.storage_v2 import ArtifactStore
from .observed_profile import ObservedExecutionProfile, MODEL_V2
from .observed_source import ObservedDatasetPin,ObservedReplaySource
from .historical import IndexedTimelineCache


def _sha(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        while block:=stream.read(1048576):h.update(block)
    return h.hexdigest()


class AdmittedObservedSource:
    """Private model capability, not strict financial/source-quality eligibility."""
    def __init__(self,folder,profile,*,receipt_path,receipt_sha256,log_root):
        require(type(profile) is ObservedExecutionProfile,'profile');digest(receipt_sha256,'receiptHash')
        self.profile=profile;self._folder=Path(folder);self._archive=self._folder/'archive.sqlite';proof=Path(receipt_path)
        require(not proof.is_symlink() and proof.stat().st_size<=1048576,'receipt','REFUSED_QUALIFICATION_PROOF')
        descriptor=os.open(proof,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        with os.fdopen(descriptor,'rb') as stream:
            require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode),'receipt','REFUSED_QUALIFICATION_PROOF');raw=stream.read(1048577)
        require(len(raw)<=1048576 and hashlib.sha256(raw).hexdigest()==receipt_sha256,'receipt','SOURCE_PIN_CHANGED');r=json.loads(raw)
        if profile.wire['model']==MODEL_V2:
            require(profile.wire['technicalEligibility']['qualificationReceiptHash']==receipt_sha256,
                    'qualificationReceiptHash','REFUSED_TECHNICAL_ELIGIBILITY')
            require(profile.wire['sourceQuality']['rights']=='UNKNOWN' and
                    profile.wire['sourceQuality']['provenance']=='PROVIDER_OBSERVATION',
                    'sourceQuality','REFUSED_SOURCE_DISCLOSURE')
        rows=r.get('rows');require(type(rows) is int and 0<rows<=17179869184,'rows','REFUSED_QUALIFICATION_PROOF')
        if r.get('status')=='READONLY_PROJECTION_REAL_DAY_PASS':
            require(r.get('fullPublicReaderParityRows')==rows and r.get('allCanonicalObjectsAndPublicationsExactlyEqual') is True and r.get('parentHashAndMtimeUnchanged') is True,'receipt','REFUSED_QUALIFICATION_PROOF');archive_hash=r['archiveSha256']
        elif r.get('status')=='QUALIFIED_MONTH_PASS_NOT_FINANCIAL_ADMISSION':
            require(type(r.get('sourceParityReceipts')) is int and r['sourceParityReceipts']>0 and r.get('sqliteIntegrity')=='ok' and r.get('indexedSeekChecks')==3,'receipt','REFUSED_QUALIFICATION_PROOF');archive_hash=r['readArchiveSha256']
        elif r.get('status')=='PASS' and r.get('classification')=='FULL_BINARY_SOURCE_PUBLIC_PAGE_PARITY_NOT_FINANCIAL_ADMISSION':
            require(r.get('sourcesUnchanged') is True and r.get('snapshotUnchanged') is True and r.get('sqliteIntegrity')=='ok','receipt','REFUSED_QUALIFICATION_PROOF');archive_hash=r['snapshotSha256']
        else:require(False,'receipt','REFUSED_QUALIFICATION_PROOF')
        digest(archive_hash,'archiveHash');p=profile.wire['primary']
        require(r['datasetId']==p['datasetId'] and r['datasetVersion']==p['datasetVersion'],'receipt','REFUSED_OBSERVED_SOURCE_IDENTITY')
        self._fingerprint=self._protected_fingerprint();require(_sha(self._archive)==archive_hash,'archive','SOURCE_PIN_CHANGED')
        pin=ObservedDatasetPin(p['datasetId'],p['datasetVersion'],p['providerId'],p['feedId'],p['feedInstrumentId'],p['providerSymbol'])
        self.observed=ObservedReplaySource(folder,pin,log_root=log_root)
        provider=self.observed.provider()
        try:root=provider.describe_v2(p['datasetId'],p['datasetVersion'])['root']
        finally:provider.close()
        require(int(root['eventCount'])==rows,'rows','REFUSED_QUALIFICATION_PROOF')
        store=ArtifactStore(folder,read_only=True)
        try:
            catalog=store.get(root['evidenceCatalogHash'],p['datasetVersion']);shape(catalog,'BTL-TICK-EVIDENCE-CATALOG-2');validate_container(catalog,root,expected_hash=root['evidenceCatalogHash'])
            require(catalog['children']==[],'sourceCapability','REFUSED_UNSUPPORTED_OBSERVED_SIDECARS')
        finally:store.close()
        # Admission is static operator configuration. No future catalog fields
        # or refusal diagnostics are projected into an active revealed view.
        self.dataset_id=p['datasetId'];self.version=p['datasetVersion'];self.log_root=Path(log_root);self.qualification_hash=receipt_sha256
        # Technical simulation eligibility is deliberately separate from strict
        # broker/source financial admission and from external data-use rights.
        self.technical_simulation_eligibility='PASS'
        self.execution_eligibility='NOT_GRANTED'
        self.execution_label=profile.wire.get('executionLabel','CONDITIONAL OBSERVED-TICK SIMULATION')
        self.cache=IndexedTimelineCache(self)

    def _protected_fingerprint(self):
        require(not self._folder.is_symlink() and not self._archive.is_symlink(),'source','REFUSED_UNPROTECTED_SOURCE')
        d=self._folder.stat();f=self._archive.stat()
        require(stat.S_ISDIR(d.st_mode) and stat.S_ISREG(f.st_mode) and stat.S_IMODE(d.st_mode)==0o500 and stat.S_IMODE(f.st_mode)==0o400,'source','REFUSED_UNPROTECTED_SOURCE')
        return f.st_dev,f.st_ino,f.st_size,f.st_mtime_ns

    def assert_current(self):
        require(self._protected_fingerprint()==self._fingerprint,'source','SOURCE_PIN_CHANGED')

    def provider(self):
        self.assert_current()
        return self.observed.provider()

    def start_for_period(self,period,*,day=None):
        if day is None:return self.observed.start_for_period(period)
        require(type(day) is str and len(day)==10 and day[:7]==period,'day')
        try:
            when=datetime.strptime(day,'%Y-%m-%d').replace(tzinfo=timezone.utc)
        except ValueError:require(False,'day')
        require(when.strftime('%Y-%m-%d')==day,'day')
        epoch=datetime(1970,1,1,tzinfo=timezone.utc);low=(when-epoch).days*86400*10**9;high=low+86400*10**9
        require(low>=0,'day');provider=self.provider()
        try:
            located=provider.locate_v2(self.dataset_id,self.version,str(low));require(located['position'] is not None and low<=int(located['groupTimeNs'])<high,'day','OBSERVED_PERIOD_UNAVAILABLE')
            return int(located['groupTimeNs'])
        finally:provider.close()

    def close(self):self.cache.close()

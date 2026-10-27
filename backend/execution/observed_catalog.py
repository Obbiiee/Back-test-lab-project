"""Trusted operator-pinned catalog for the separate observed family.

No public request may supply any file path, qualification hash, or profile.
Only public configured source keys are eligible selection inputs.
"""
from collections import OrderedDict
from copy import deepcopy
import hashlib,json,os,stat
from pathlib import Path
from threading import RLock
from contracts.primitives import require,identifier,digest
from ticks.contracts import keys
from execution.observed_profile import ObservedExecutionProfile,MODEL
from execution.observed_admission import AdmittedObservedSource


class ObservedCatalog:
    def __init__(self,path,sha256):
        digest(sha256,'catalogHash');path=Path(path)
        fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        with os.fdopen(fd,'rb') as stream:
            f=os.fstat(stream.fileno());require(stat.S_ISREG(f.st_mode) and stat.S_IMODE(f.st_mode)==0o400 and f.st_size<=1048576,'catalog','REFUSED_OPERATOR_CATALOG');raw=stream.read(1048577)
        require(len(raw)<=1048576 and hashlib.sha256(raw).hexdigest()==sha256,'catalog','SOURCE_PIN_CHANGED');value=json.loads(raw)
        keys(value,'schemaVersion artifact sources');require(type(value['schemaVersion']) is int and value['schemaVersion']==1 and value['artifact']=='BTL-OBSERVED-OPERATOR-CATALOG-1' and type(value['sources']) is list and 1<=len(value['sources'])<=24,'catalog','REFUSED_OPERATOR_CATALOG')
        self._entries={};self._profiles={};self._cache=OrderedDict();self._lock=RLock();self.config_hash=sha256
        for r in value['sources']:
            keys(r,'key period label profile folder receiptPath receiptSha256 logRoot');identifier(r['key'],'sourceKey');profile=ObservedExecutionProfile.from_wire(r['profile']);digest(r['receiptSha256'],'receiptHash')
            require(type(r['period']) is str and len(r['period'])==7 and r['period'][:4] in ('2024','2025') and r['period'][4]=='-' and r['period'][5:] in tuple(f'{n:02d}' for n in range(1,13)),'period','REFUSED_OPERATOR_CATALOG')
            require(type(r['label']) is str and 1<=len(r['label'])<=128 and not any(ord(c)<32 for c in r['label']),'label')
            for f in ('folder','receiptPath','logRoot'):require(type(r[f]) is str and Path(r[f]).is_absolute(),'operatorPath')
            require(r['key'] not in self._entries,'sourceKey','REFUSED_OPERATOR_CATALOG')
            # One annual root may legitimately bind 12 requested month labels.
            # Its private paths/profile/proof must agree across those entries.
            private={k:r[k] for k in ('profile','folder','receiptPath','receiptSha256','logRoot')}
            prior=self._profiles.get(profile.profile_hash);require(prior is None or prior==private,'profileConfig','REFUSED_OPERATOR_CATALOG')
            self._entries[r['key']]=deepcopy(r);self._profiles[profile.profile_hash]=private

    def selection(self,key,period):
        identifier(key,'sourceKey');r=self._entries.get(key);require(r is not None and period==r['period'],'source','OBSERVED_PERIOD_UNAVAILABLE');return ObservedExecutionProfile.from_wire(r['profile'])

    def public(self):
        result=[]
        for key,r in sorted(self._entries.items(),key=lambda pair:(pair[1]['period'],pair[0])):
            p=ObservedExecutionProfile.from_wire(r['profile']);result.append(dict(key=key,period=r['period'],label=r['label'],model=MODEL,profileHash=p.profile_hash,profile=p.wire))
        return result

    def resolve(self,profile_hash):
        digest(profile_hash,'profileHash')
        with self._lock:
            r=self._profiles.get(profile_hash);require(r is not None,'source','REFUSED_OBSERVED_SOURCE_IDENTITY')
            if profile_hash not in self._cache:
                p=ObservedExecutionProfile.from_wire(r['profile']);source=AdmittedObservedSource(r['folder'],p,receipt_path=r['receiptPath'],receipt_sha256=r['receiptSha256'],log_root=r['logRoot']);self._cache[profile_hash]=source
                # At most24 configured profiles. Keep admitted sources until
                # service shutdown; never evict a handle leased by another call.
            self._cache.move_to_end(profile_hash);source=self._cache[profile_hash];source.assert_current();return source

    def close(self):
        with self._lock:
            for source in self._cache.values():source.close()
            self._cache.clear()

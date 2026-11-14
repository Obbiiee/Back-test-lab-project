"""Object-store port for the OHLC publication, with a local test-compatible implementation and an S3/R2 adapter.

LocalObjectStore is a SIMULATION of an S3-compatible bucket (same operations, same immutability rule, request and byte counters). A pass
against it is NOT a Cloudflare R2 production PASS. S3ObjectStore targets R2 (endpoint https://<account>.r2.cloudflarestorage.com) through
boto3; boto3 is imported lazily and the adapter is exercised in tests only against a stub client.
Credentials are never read from this module: the caller injects an already configured client.
"""
import hashlib
import os
import threading
from pathlib import Path


class Conflict(Exception):
    pass


class Counters:
    def __init__(self):
        self.lock = threading.Lock()
        self.put = self.get = self.head = self.list = 0
        self.bytes_put = self.bytes_get = 0

    def add(self, **kw):
        with self.lock:
            for k, v in kw.items():
                setattr(self, k, getattr(self, k) + v)

    def snapshot(self):
        return dict(put=self.put, get=self.get, head=self.head, list=self.list, bytesPut=self.bytes_put, bytesGet=self.bytes_get)


class LocalObjectStore:
    simulation = True

    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.counters = Counters()

    def _path(self, key):
        p = (self.root / key).resolve()
        if self.root.resolve() not in p.parents:
            raise ValueError("KEY_ESCAPES_ROOT")
        return p

    def put_immutable(self, key, data):
        p = self._path(key)
        self.counters.add(head=1)
        if p.exists():
            if hashlib.sha256(p.read_bytes()).digest() != hashlib.sha256(data).digest():
                raise Conflict(key)
            return False
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + f".tmp{os.getpid()}")
        tmp.write_bytes(data)
        os.replace(tmp, p)
        self.counters.add(put=1, bytes_put=len(data))
        return True

    def get(self, key):
        data = self._path(key).read_bytes()
        self.counters.add(get=1, bytes_get=len(data))
        return data

    def get_range(self, key, start, length):
        with open(self._path(key), "rb") as f:
            f.seek(start)
            data = f.read(length)
        self.counters.add(get=1, bytes_get=len(data))
        return data

    def exists(self, key):
        self.counters.add(head=1)
        return self._path(key).exists()

    def list(self, prefix):
        self.counters.add(list=1)
        base = self.root.resolve()
        return sorted(str(p.relative_to(base)).replace("\\", "/") for p in (base / prefix).rglob("*") if p.is_file()) if (base / prefix).exists() else []


class S3ObjectStore:
    """Cloudflare R2 / S3 adapter. `client` is a configured boto3 S3 client supplied by trusted code."""
    simulation = False

    def __init__(self, client, bucket):
        self.client, self.bucket = client, bucket
        self.counters = Counters()

    def put_immutable(self, key, data):
        self.counters.add(head=1)
        try:
            head = self.client.head_object(Bucket=self.bucket, Key=key)
            if head.get("ContentLength") == len(data) and head.get("Metadata", {}).get("sha256") == hashlib.sha256(data).hexdigest():
                return False
            raise Conflict(key)
        except Conflict:
            raise
        except Exception as error:                                  # botocore ClientError 404 -> create
            if getattr(error, "response", {}).get("Error", {}).get("Code") not in ("404", "NoSuchKey", "NotFound"):
                raise
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, IfNoneMatch="*", Metadata={"sha256": hashlib.sha256(data).hexdigest()})
        self.counters.add(put=1, bytes_put=len(data))
        return True

    def get(self, key):
        data = self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        self.counters.add(get=1, bytes_get=len(data))
        return data

    def get_range(self, key, start, length):
        data = self.client.get_object(Bucket=self.bucket, Key=key, Range=f"bytes={start}-{start + length - 1}")["Body"].read()
        self.counters.add(get=1, bytes_get=len(data))
        return data

    def exists(self, key):
        self.counters.add(head=1)
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception:
            return False

    def list(self, prefix):
        self.counters.add(list=1)
        keys, token = [], None
        while True:
            kw = dict(Bucket=self.bucket, Prefix=prefix, **({"ContinuationToken": token} if token else {}))
            page = self.client.list_objects_v2(**kw)
            keys += [o["Key"] for o in page.get("Contents", [])]
            token = page.get("NextContinuationToken")
            if not token:
                return sorted(keys)

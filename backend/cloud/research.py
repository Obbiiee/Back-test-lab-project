"""Verified workspace composition; private loopback datasets are never mounted."""
from functools import partial
from collections import OrderedDict
from threading import RLock
import hashlib
import os
import uuid

import anyio
from fastapi import Depends, Request, Query
from fastapi.responses import Response
from psycopg.rows import dict_row

from application.models import TrustedScope
from contracts.canonical import canonical_bytes
from contracts.primitives import require, ContractError
from execution.local_api import body
from execution.research import ResearchApplication
from identity.store import User
from infrastructure.database import connect
from workspace.policy import owner
from workspace.store import WorkspaceUnit
from . import queue

_OPERATOR_LOCK=RLock()
_OPERATOR_CATALOGS=OrderedDict()
_MONTHLY_LOCK=RLock()
_MONTHLY_PROVIDER=None
_MONTHLY_PIN=None


def _operator_catalog(dsn):
    path=os.environ.get('BTL_OBSERVED_OPERATOR_CATALOG');sha=os.environ.get('BTL_OBSERVED_OPERATOR_CATALOG_SHA256')
    require((path is None)==(sha is None),'operatorCatalog','REFUSED_OPERATOR_CATALOG')
    if path is None:return None
    require(len(path)<=4096 and os.path.isabs(path),'operatorCatalog','REFUSED_OPERATOR_CATALOG')
    from execution.observed_catalog import ObservedCatalog
    key=(hashlib.sha256(dsn.encode()).hexdigest(),path,sha)
    with _OPERATOR_LOCK:
        catalog=_OPERATOR_CATALOGS.get(key)
        if catalog is None:
            catalog=ObservedCatalog(path,sha);_OPERATOR_CATALOGS[key]=catalog
        _OPERATOR_CATALOGS.move_to_end(key)
        # A single configured catalog per DB process; changing its pin requires
        # a clean worker restart, which also closes the exact old capability.
        require(len(_OPERATOR_CATALOGS)<=1,'operatorCatalog','SOURCE_PIN_CHANGED')
        return catalog


def _synthetic_monthly_provider():
    """Resolve only a server-pinned synthetic QA fixture; requests carry no path."""
    values = tuple(os.environ.get(name) for name in (
        'BTL_QA_SYNTHETIC_MONTHLY_ROOT', 'BTL_QA_SYNTHETIC_MONTHLY_DATASET_ID',
        'BTL_QA_SYNTHETIC_MONTHLY_DATASET_VERSION', 'BTL_QA_SYNTHETIC_MONTHLY_MANIFEST_SHA256'))
    if not any(values):
        return None
    require(os.environ.get('BTL_QA_SYNTHETIC_MONTHLY_ENABLE') == '1' and all(values),
            'syntheticMonthly', 'REFUSED_SOURCE')
    root, dataset_id, dataset_version, manifest_hash = values
    require(len(root) <= 4096 and os.path.isabs(root), 'syntheticMonthlyRoot', 'REFUSED_SOURCE')
    from contracts.primitives import digest
    digest(dataset_version, 'syntheticMonthlyVersion')
    digest(manifest_hash, 'syntheticMonthlyManifestHash')
    pin = (os.path.realpath(root), dataset_id, dataset_version, manifest_hash)
    global _MONTHLY_PROVIDER, _MONTHLY_PIN
    with _MONTHLY_LOCK:
        require(_MONTHLY_PIN in (None, pin), 'syntheticMonthly', 'SOURCE_PIN_CHANGED')
        if _MONTHLY_PROVIDER is None:
            from market_data.monthly_parquet import MonthlyParquetProvider
            provider = MonthlyParquetProvider(pin[0], expected_dataset_id=dataset_id,
                expected_dataset_version=dataset_version, expected_manifest_hash=manifest_hash)
            manifest = provider.describe(dataset_id, dataset_version)
            require(manifest['evidenceClass'] == 'SYNTHETIC_CONTRACT_ONLY' and
                    manifest['rights']['class'] == 'SYNTHETIC' and not manifest['diagnostics'],
                    'syntheticMonthly', 'REFUSED_SOURCE')
            _MONTHLY_PROVIDER, _MONTHLY_PIN = provider, pin
        return _MONTHLY_PROVIDER


def warm_worker_sources(dsn):
    """Admit all server-pinned sources before the native worker accepts jobs."""
    catalog = _operator_catalog(dsn)
    if catalog is not None:
        for profile_hash in sorted(catalog._profiles):
            catalog.resolve(profile_hash)
    monthly = _synthetic_monthly_provider()
    return catalog is not None or monthly is not None


def close_operator_catalogs():
    global _MONTHLY_PROVIDER, _MONTHLY_PIN
    with _OPERATOR_LOCK:
        for catalog in _OPERATOR_CATALOGS.values():catalog.close()
        _OPERATOR_CATALOGS.clear()
    with _MONTHLY_LOCK:
        _MONTHLY_PROVIDER = None
        _MONTHLY_PIN = None


def warm_operator_sources(dsn):
    """Admit configured source pins before a Session request needs them."""
    catalog = _operator_catalog(dsn)
    if catalog is None:
        return False
    for profile_hash in sorted(catalog._profiles):
        catalog.resolve(profile_hash)
    return True


def _observed_session_uses_product_archive(db,workspace_id,session_id):
    """Select a validator from the persisted Session version, never from HTTP."""
    row=db.execute('SELECT payload,content_hash FROM btl.tick_sessions '
                   'WHERE workspace_id=%s AND session_id=%s',(str(workspace_id),session_id)).fetchone()
    if row is None:return None
    from execution.postgres import unpack
    stored=unpack(row[
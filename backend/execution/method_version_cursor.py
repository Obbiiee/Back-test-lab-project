"""Canonical family- and revision-bound cursor for immutable Method versions."""
import base64
import binascii
import json
import re

from contracts.canonical import canonical_bytes
from contracts.primitives import identifier, require, revision

ARTIFACT='BTL-PRODUCT-METHOD-VERSION-CURSOR-1'


def encode(family_id, family_revision, after_version):
    identifier(family_id,'familyId');revision(family_revision)
    require(type(after_version) is int and after_version>=1,
            'cursor','INVALID_CURSOR')
    value=dict(schemaVersion=1,artifact=ARTIFACT,familyId=family_id,
               revision=family_revision,afterVersion=after_version)
    return base64.urlsafe_b64encode(canonical_bytes(value)).decode('ascii').rstrip('=')


def decode(token, family_id):
    identifier(family_id,'familyId')
    require(type(token) is str and 1<=len(token)<=2048 and
            re.fullmatch(r'[A-Za-z0-9_-]+',token) is not None,
            'cursor','INVALID_CURSOR')
    try:
        raw=base64.urlsafe_b64decode(token+'='*(-len(token)%4))
        value=json.loads(raw)
    except (ValueError,UnicodeError,binascii.Error):
        require(False,'cursor','INVALID_CURSOR')
    try:
        canonical=type(value) is dict and canonical_bytes(value)==raw
    except (TypeError,ValueError):
        canonical=False
    require(canonical and set(value)==
            {'schemaVersion','artifact','familyId','revision','afterVersion'} and
            value.get('schemaVersion')==1 and value.get('artifact')==ARTIFACT and
            value.get('familyId')==family_id,'cursor','INVALID_CURSOR')
    revision(value.get('revision'),'revision')
    require(type(value.get('afterVersion')) is int and value['afterVersion']>=1,
            'cursor','INVALID_CURSOR')
    return value['revision'],value['afterVersion']

"""Bounded mutable notes over verified canonical order identities, no settlement."""
import base64
import json
import re

from contracts.canonical import canonical_bytes
from contracts.primitives import require, identifier, revision
from ticks.contracts import keys, tag

MAX_JOURNAL_ORDERS = 32  # Complete JSON snapshot stays below the transport's 1MiB budget.
MAX_JOURNAL_PAGE_SIZE = 32
MAX_JOURNAL_READ_ORDERS = 4096


def encode_cursor(session_id, session_revision, after_order_id):
    identifier(session_id, 'sessionId'); revision(session_revision)
    identifier(after_order_id, 'afterOrderId')
    value = dict(schemaVersion=1, artifact='BTL-TICK-JOURNAL-CURSOR-1',
                 sessionId=session_id, revision=session_revision, afterOrderId=after_order_id)
    return base64.urlsafe_b64encode(canonical_bytes(value)).decode('ascii').rstrip('=')


def decode_cursor(token, session_id):
    require(type(token) is str and 1 <= len(token) <= 2048 and
            re.fullmatch(r'[A-Za-z0-9_-]+', token) is not None,
            'cursor', 'INVALID_CURSOR')
    try:
        raw = base64.urlsafe_b64decode(token + '=' * (-len(token) % 4))
        value = json.loads(raw)
    except (ValueError, UnicodeError):
        require(False, 'cursor', 'INVALID_CURSOR')
    try:
        valid = type(value) is dict and canonical_bytes(value) == raw
    except (TypeError, ValueError):
        valid = False
    require(valid, 'cursor', 'INVALID_CURSOR')
    tag(value, 'BTL-TICK-JOURNAL-CURSOR-1', 'sessionId revision afterOrderId')
    require(value['sessionId'] == session_id, 'cursor', 'INVALID_CURSOR')
    revision(value['revision']); identifier(value['afterOrderId'], 'afterOrderId')
    return value['revision'], value['afterOrderId']


def note_text(value):
    require(type(value) is str and len(value) <= 4096 and not any(0xD800 <= ord(c) <= 0xDFFF for c in value)
            and len(value.encode('utf-8')) <= 16384
            and not any(ord(c) < 32 and c not in '\n\t' for c in value), 'note')
    return value


def note_tags(value):
    require(type(value) is list and len(value) <= 8, 'tags')
    for item in value:
        require(type(item) is str and 1 <= len(item.strip()) <= 32 and item == item.strip()
                and not any(ord(c) < 32 for c in item), 'tag')
    require(len(set(value)) == len(value), 'duplicateTags')
    return value


def validate_note(value, state, orders):
    tag(value, 'BTL-TICK-JOURNAL-NOTE-1', 'sessionId datasetId datasetVersion orderId noteRevision text tags')
    identifier(value['orderId'], 'orderId'); revision(value['noteRevision'])
    require(value['noteRevision'] > 0 and value['orderId'] in orders and
            (value['sessionId'], value['datasetId'], value['datasetVersion']) ==
            (state['sessionId'], state['datasetId'], state['datasetVersion']), 'journalIdentity', 'CORRUPT_RECORD')
    note_text(value['text']); note_tags(value['tags'])
    return value


def request(value):
    keys(value, 'orderId expectedNoteRevision text tags')
    identifier(value['orderId'], 'orderId'); revision(value['expectedNoteRevision'])
    note_text(value['text']); note_tags(value['tags'])
    return value

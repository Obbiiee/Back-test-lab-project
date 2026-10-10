"""Bounded mutable notes over verified canonical order identities, no settlement."""
from contracts.primitives import require, identifier, revision
from ticks.contracts import keys, tag

MAX_JOURNAL_ORDERS = 32  # Complete JSON snapshot stays below the transport's 1MiB budget.


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

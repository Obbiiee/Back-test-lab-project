"""Durable scoped nonexecuting intake and immutable research provenance."""
from application.models import TrustedScope, IntakeResult
from contracts.models import (SessionContext, ReviewedRequest, Passport, LineageEntry,
                              validate_confirmation, validate_event_context)
from contracts.canonical import content_hash
from contracts.primitives import require
from .database import connect
from .codec import pack, unpack, fingerprint


class PostgresUnit:
    def __init__(self, db, scope, session_id):
        self.db, self.scope, self.session_id = db, scope, session_id
        row = db.execute("SELECT payload,content_hash,next_sequence,session_revision,quote_revision FROM btl.session_contexts WHERE workspace_id=%s AND session_id=%s FOR UPDATE",
                         (scope.workspace_id, session_id)).fetchone()
        require(row is not None, "session", "RESOURCE_UNAVAILABLE")
        self.context, self.sequence = unpack(row[0], row[1], SessionContext), row[2]
        require(self.context.workspace_id == scope.workspace_id and self.context.session_id == session_id,
                "session", "CORRUPT_RECORD")
        require((self.context.session_revision, self.context.quote_revision) == (row[3], row[4]), "storedRevisions", "CORRUPT_RECORD")

    def find_review(self, request_id):
        row = self.db.execute("SELECT payload,content_hash FROM btl.command_reviews WHERE workspace_id=%s AND session_id=%s AND request_id=%s",
                              (self.scope.workspace_id, self.session_id, request_id)).fetchone()
        return unpack(*row, ReviewedRequest) if row else None

    def put_review(self, reviewed):
        command = reviewed.command
        require((command.workspace_id, command.session_id) == (self.scope.workspace_id, self.session_id), "scope", "SCOPE_MISMATCH")
        payload = pack(reviewed)
        self.db.execute("INSERT INTO btl.command_reviews VALUES (%s,%s,%s,%s,%s)",
                        (self.scope.workspace_id, self.session_id, command.request_id, payload, fingerprint(payload)))

    def find_receipt(self, request_id):
        row = self.db.execute("SELECT payload,content_hash FROM btl.intakes WHERE workspace_id=%s AND session_id=%s AND request_id=%s",
                              (self.scope.workspace_id, self.session_id, request_id)).fetchone()
        return unpack(*row, IntakeResult) if row else None

    def next_sequence(self):
        return self.sequence

    def commit_intake(self, confirmed, receipt, event):
        validate_confirmation(confirmed, self.context)
        validate_event_context(event, self.context)
        require(self.find_review(receipt.request_id) == confirmed.reviewed, "review", "RESOURCE_UNAVAILABLE")
        require(event.sequence == self.sequence, "sequence", "STALE_REVISION")
        payload = pack(IntakeResult(confirmed, receipt, event))
        self.db.execute("INSERT INTO btl.intakes VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (self.scope.workspace_id, self.session_id, receipt.request_id, receipt.receipt_id, event.event_id, payload, fingerprint(payload)))
        evidence = pack(event)
        self.db.execute("INSERT INTO btl.evidence VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (self.scope.workspace_id, self.session_id, receipt.request_id, event.event_id, event.sequence, evidence, fingerprint(evidence)))
        self.db.execute("UPDATE btl.session_contexts SET next_sequence=next_sequence+1 WHERE workspace_id=%s AND session_id=%s",
                        (self.scope.workspace_id, self.session_id))
        self.sequence += 1


class PostgresWorkflow:
    def __init__(self, dsn):
        self.dsn = dsn

    def run(self, scope, session_id, operation):
        require(type(scope) is TrustedScope, "scope", "SCOPE_REQUIRED")
        with connect(self.dsn) as db:
            return operation(PostgresUnit(db, scope, session_id))

    def create_context(self, scope, context):
        require(type(scope) is TrustedScope and type(context) is SessionContext and scope.workspace_id == context.workspace_id,
                "scope", "SCOPE_MISMATCH")
        payload = pack(context)
        with connect(self.dsn) as db:
            db.execute("INSERT INTO btl.session_contexts (workspace_id,session_id,session_revision,quote_revision,payload,content_hash) VALUES (%s,%s,%s,%s,%s,%s)",
                (context.workspace_id, context.session_id, context.session_revision, context.quote_revision, payload, fingerprint(payload)))

    def advance_context(self, scope, context, expected_session_revision, expected_quote_revision):
        def operation(unit):
            old = unit.context
            require((old.session_revision, old.quote_revision) == (expected_session_revision, expected_quote_revision), "revisions", "STALE_REVISION")
            require(context.workspace_id == scope.workspace_id and context.session_id == old.session_id and
                    context.method == old.method and context.instrument_id == old.instrument_id and context.feed_id == old.feed_id and
                    context.profile_hash == old.profile_hash and context.revealed_time >= old.revealed_time and
                    context.session_revision >= old.session_revision and context.quote_revision >= old.quote_revision and
                    (context.session_revision, context.quote_revision) != (old.session_revision, old.quote_revision), "contextAdvance")
            payload = pack(context)
            unit.db.execute("UPDATE btl.session_contexts SET session_revision=%s,quote_revision=%s,payload=%s,content_hash=%s WHERE workspace_id=%s AND session_id=%s",
                (context.session_revision, context.quote_revision, payload, fingerprint(payload), scope.workspace_id, context.session_id))
        return self.run(scope, context.session_id, operation)


class ProvenanceStore:
    def __init__(self, dsn):
        self.dsn = dsn

    @staticmethod
    def _scope(scope, record):
        require(type(scope) is TrustedScope and record.workspace_id == scope.workspace_id, "scope", "SCOPE_MISMATCH")

    def append_passport(self, scope, passport):
        require(type(passport) is Passport, "passport")
        self._scope(scope, passport)
        payload = pack(passport)
        with connect(self.dsn) as db:
            db.execute("INSERT INTO btl.passports VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                (scope.workspace_id, passport.experiment_id, passport.passport_revision, content_hash(passport.identity_payload()), payload, fingerprint(payload)))
            row = db.execute("SELECT payload,content_hash FROM btl.passports WHERE workspace_id=%s AND experiment_id=%s AND revision=%s",
                (scope.workspace_id, passport.experiment_id, passport.passport_revision)).fetchone()
            require(unpack(*row, Passport) == passport, "passportRevision", "IDEMPOTENCY_CONFLICT")

    def get_passport(self, scope, experiment_id, revision):
        require(type(scope) is TrustedScope, "scope", "SCOPE_REQUIRED")
        with connect(self.dsn) as db:
            row = db.execute("SELECT payload,content_hash FROM btl.passports WHERE workspace_id=%s AND experiment_id=%s AND revision=%s",
                (scope.workspace_id, experiment_id, revision)).fetchone()
            require(row is not None, "passport", "RESOURCE_UNAVAILABLE")
            result = unpack(*row, Passport)
            self._scope(scope, result)
            return result

    def append_lineage(self, scope, lineage):
        require(type(lineage) is LineageEntry, "lineage")
        self._scope(scope, lineage)
        payload = pack(lineage)
        with connect(self.dsn) as db:
            db.execute("INSERT INTO btl.lineage VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                (scope.workspace_id, lineage.trial_id, lineage.experiment_id, lineage.parent_trial_id, payload, fingerprint(payload)))
            row = db.execute("SELECT payload,content_hash FROM btl.lineage WHERE workspace_id=%s AND trial_id=%s",
                (scope.workspace_id, lineage.trial_id)).fetchone()
            require(unpack(*row, LineageEntry) == lineage, "trialIdentity", "IDEMPOTENCY_CONFLICT")

    def get_lineage(self, scope, trial_id):
        require(type(scope) is TrustedScope, "scope", "SCOPE_REQUIRED")
        with connect(self.dsn) as db:
            row = db.execute("SELECT payload,content_hash FROM btl.lineage WHERE workspace_id=%s AND trial_id=%s",
                (scope.workspace_id, trial_id)).fetchone()
            require(row is not None, "lineage", "RESOURCE_UNAVAILABLE")
            result = unpack(*row, LineageEntry)
            self._scope(scope, result)
            return result

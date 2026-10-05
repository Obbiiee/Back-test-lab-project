CREATE SCHEMA btl;
CREATE TABLE btl.session_contexts (
    workspace_id text NOT NULL, session_id text NOT NULL,
    session_revision bigint NOT NULL CHECK (session_revision >= 0),
    quote_revision bigint NOT NULL CHECK (quote_revision >= 0),
    next_sequence bigint NOT NULL DEFAULT 0 CHECK (next_sequence >= 0),
    payload bytea NOT NULL CHECK (octet_length(payload) <= 1048576),
    content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
    PRIMARY KEY (workspace_id, session_id)
);
CREATE TABLE btl.command_reviews (
    workspace_id text NOT NULL, session_id text NOT NULL, request_id text NOT NULL,
    payload bytea NOT NULL CHECK (octet_length(payload) <= 1048576),
    content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
    PRIMARY KEY (workspace_id, session_id, request_id),
    FOREIGN KEY (workspace_id, session_id) REFERENCES btl.session_contexts
);
CREATE TABLE btl.intakes (
    workspace_id text NOT NULL, session_id text NOT NULL, request_id text NOT NULL,
    receipt_id text NOT NULL, event_id text NOT NULL,
    payload bytea NOT NULL CHECK (octet_length(payload) <= 1048576),
    content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
    PRIMARY KEY (workspace_id, session_id, request_id),
    UNIQUE (workspace_id, receipt_id), UNIQUE (workspace_id, event_id),
    UNIQUE (workspace_id, session_id, request_id, event_id),
    FOREIGN KEY (workspace_id, session_id, request_id) REFERENCES btl.command_reviews
);
CREATE TABLE btl.evidence (
    workspace_id text NOT NULL, session_id text NOT NULL, request_id text NOT NULL,
    event_id text NOT NULL, sequence bigint NOT NULL CHECK (sequence >= 0),
    payload bytea NOT NULL CHECK (octet_length(payload) <= 1048576),
    content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
    PRIMARY KEY (workspace_id, session_id, event_id),
    UNIQUE (workspace_id, session_id, sequence),
    UNIQUE (workspace_id, session_id, request_id, event_id),
    FOREIGN KEY (workspace_id, session_id, request_id, event_id)
        REFERENCES btl.intakes(workspace_id, session_id, request_id, event_id) DEFERRABLE INITIALLY DEFERRED
);
ALTER TABLE btl.intakes ADD CONSTRAINT intake_has_evidence
    FOREIGN KEY (workspace_id, session_id, request_id, event_id)
    REFERENCES btl.evidence(workspace_id, session_id, request_id, event_id) DEFERRABLE INITIALLY DEFERRED;
CREATE TABLE btl.passports (
    workspace_id text NOT NULL, experiment_id text NOT NULL, revision bigint NOT NULL CHECK (revision >= 0),
    identity_hash text NOT NULL CHECK (identity_hash ~ '^[0-9a-f]{64}$'),
    payload bytea NOT NULL CHECK (octet_length(payload) <= 1048576),
    content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
    PRIMARY KEY (workspace_id, experiment_id, revision)
);
CREATE TABLE btl.lineage (
    workspace_id text NOT NULL, trial_id text NOT NULL,
    experiment_id text NOT NULL, parent_trial_id text,
    payload bytea NOT NULL CHECK (octet_length(payload) <= 1048576),
    content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
    PRIMARY KEY (workspace_id, trial_id),
    FOREIGN KEY (workspace_id, parent_trial_id) REFERENCES btl.lineage
);
CREATE FUNCTION btl.deny_evidence_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'Canonical evidence is append-only' USING ERRCODE = '23000';
END;
$$;
CREATE TRIGGER immutable_reviews BEFORE UPDATE OR DELETE OR TRUNCATE ON btl.command_reviews
    FOR EACH STATEMENT EXECUTE FUNCTION btl.deny_evidence_mutation();
CREATE TRIGGER immutable_intakes BEFORE UPDATE OR DELETE OR TRUNCATE ON btl.intakes
    FOR EACH STATEMENT EXECUTE FUNCTION btl.deny_evidence_mutation();
CREATE TRIGGER immutable_events BEFORE UPDATE OR DELETE OR TRUNCATE ON btl.evidence
    FOR EACH STATEMENT EXECUTE FUNCTION btl.deny_evidence_mutation();
CREATE TRIGGER immutable_passports BEFORE UPDATE OR DELETE OR TRUNCATE ON btl.passports
    FOR EACH STATEMENT EXECUTE FUNCTION btl.deny_evidence_mutation();
CREATE TRIGGER immutable_lineage BEFORE UPDATE OR DELETE OR TRUNCATE ON btl.lineage
    FOR EACH STATEMENT EXECUTE FUNCTION btl.deny_evidence_mutation();

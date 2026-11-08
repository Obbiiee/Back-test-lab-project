-- Periodic hash-verified recovery bases keep compact-v1 cold recovery bounded.
CREATE TABLE btl.tick_recovery_bases (
    workspace_id text NOT NULL,
    session_id text NOT NULL,
    revision bigint NOT NULL CHECK (revision >= 0),
    state_hash text NOT NULL CHECK (state_hash ~ '^[0-9a-f]{64}$'),
    chain_hash text NOT NULL CHECK (chain_hash ~ '^[0-9a-f]{64}$'),
    record_hash text NOT NULL CHECK (record_hash ~ '^[0-9a-f]{64}$'),
    payload bytea NOT NULL CHECK (octet_length(payload) <= 16777216),
    content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
    PRIMARY KEY (workspace_id, session_id, revision),
    FOREIGN KEY (workspace_id, session_id) REFERENCES btl.tick_sessions
);
CREATE INDEX tick_recovery_bases_latest
    ON btl.tick_recovery_bases (workspace_id, session_id, revision DESC);
CREATE TRIGGER immutable_tick_recovery_bases
    BEFORE UPDATE OR DELETE OR TRUNCATE ON btl.tick_recovery_bases
    FOR EACH STATEMENT EXECUTE FUNCTION btl.deny_evidence_mutation();

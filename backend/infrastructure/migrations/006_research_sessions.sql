-- Local alpha metadata/review evidence only. Existing tick financial tables own truth.
CREATE TABLE btl.tick_methods (
    workspace_id text NOT NULL, method_id text NOT NULL,
    payload bytea NOT NULL CHECK (octet_length(payload) <= 32768),
    content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
    PRIMARY KEY(workspace_id,method_id)
);
CREATE TABLE btl.tick_research_sessions (
    workspace_id text NOT NULL, session_id text NOT NULL, method_id text NOT NULL,
    payload bytea NOT NULL CHECK (octet_length(payload) <= 32768),
    content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
    PRIMARY KEY(workspace_id,session_id),
    FOREIGN KEY(workspace_id,method_id) REFERENCES btl.tick_methods,
    FOREIGN KEY(workspace_id,session_id) REFERENCES btl.tick_sessions
);
CREATE TABLE btl.tick_order_reviews (
    workspace_id text NOT NULL, session_id text NOT NULL, review_id text NOT NULL,
    payload bytea NOT NULL CHECK (octet_length(payload) <= 32768),
    content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
    PRIMARY KEY(workspace_id,session_id,review_id),
    FOREIGN KEY(workspace_id,session_id) REFERENCES btl.tick_research_sessions
);
CREATE TRIGGER immutable_tick_methods BEFORE UPDATE OR DELETE OR TRUNCATE ON btl.tick_methods
    FOR EACH STATEMENT EXECUTE FUNCTION btl.deny_evidence_mutation();
CREATE TRIGGER immutable_tick_research_sessions BEFORE UPDATE OR DELETE OR TRUNCATE ON btl.tick_research_sessions
    FOR EACH STATEMENT EXECUTE FUNCTION btl.deny_evidence_mutation();
CREATE TRIGGER immutable_tick_order_reviews BEFORE UPDATE OR DELETE OR TRUNCATE ON btl.tick_order_reviews
    FOR EACH STATEMENT EXECUTE FUNCTION btl.deny_evidence_mutation();

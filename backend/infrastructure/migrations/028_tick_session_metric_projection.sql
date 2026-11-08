-- Replaceable exact analytics aggregate. Only Sessions created after this
-- version receive an initialized row; older formats retain version dispatch.
CREATE TABLE btl.tick_session_metric_projections (
    workspace_id text NOT NULL,
    session_id text NOT NULL,
    payload bytea NOT NULL CHECK (octet_length(payload) <= 65536),
    content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
    PRIMARY KEY (workspace_id, session_id),
    FOREIGN KEY (workspace_id, session_id) REFERENCES btl.tick_sessions
);

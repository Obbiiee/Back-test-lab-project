-- Mutable research notes; never financial events or account state.
CREATE TABLE btl.tick_journal_notes (
    workspace_id text NOT NULL,
    session_id text NOT NULL,
    order_id text NOT NULL,
    note_revision bigint NOT NULL CHECK (note_revision > 0),
    payload bytea NOT NULL CHECK (octet_length(payload) <= 32768),
    content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
    PRIMARY KEY(workspace_id,session_id,order_id),
    FOREIGN KEY(workspace_id,session_id) REFERENCES btl.tick_research_sessions
);

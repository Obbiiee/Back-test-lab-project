-- Rebuildable per-order index over the immutable tick event ledger.
-- Legacy Sessions without a projection-head row keep the existing read path.
CREATE TABLE btl.tick_journal_projection_heads (
    workspace_id text NOT NULL,
    session_id text NOT NULL,
    format_version smallint NOT NULL CHECK (format_version = 1),
    through_sequence bigint NOT NULL CHECK (through_sequence >= 0),
    event_hash text NOT NULL CHECK (event_hash ~ '^[0-9a-f]{64}$'),
    order_count bigint NOT NULL DEFAULT 0 CHECK (order_count >= 0),
    PRIMARY KEY (workspace_id, session_id),
    FOREIGN KEY (workspace_id, session_id) REFERENCES btl.tick_sessions
);

CREATE TABLE btl.tick_journal_order_events (
    workspace_id text NOT NULL,
    session_id text NOT NULL,
    order_id text NOT NULL CHECK (length(order_id) BETWEEN 1 AND 128),
    sequence bigint NOT NULL CHECK (sequence >= 0),
    event_id text NOT NULL CHECK (event_id ~ '^[0-9a-f]{64}$'),
    event_kind text NOT NULL CHECK (length(event_kind) BETWEEN 1 AND 64),
    projection_hash text NOT NULL CHECK (projection_hash ~ '^[0-9a-f]{64}$'),
    PRIMARY KEY (workspace_id, session_id, order_id, sequence),
    UNIQUE (workspace_id, session_id, order_id, sequence, event_id),
    FOREIGN KEY (workspace_id, session_id, sequence)
        REFERENCES btl.tick_events (workspace_id, session_id, sequence)
);

CREATE INDEX tick_journal_order_events_page
    ON btl.tick_journal_order_events (workspace_id, session_id, order_id, sequence);
CREATE UNIQUE INDEX tick_journal_order_events_one_acceptance
    ON btl.tick_journal_order_events (workspace_id, session_id, order_id)
    WHERE event_kind = 'ORDER_ACCEPTED';

CREATE TRIGGER immutable_tick_journal_order_events
    BEFORE UPDATE OR DELETE OR TRUNCATE ON btl.tick_journal_order_events
    FOR EACH STATEMENT EXECUTE FUNCTION btl.deny_evidence_mutation();

-- Replaceable current Journal projection. This is a read model, not financial
-- authority; rows are rebuilt from the immutable ledger when verified.
CREATE TABLE btl.tick_journal_order_projection (
    workspace_id text NOT NULL,
    session_id text NOT NULL,
    order_id text NOT NULL CHECK (length(order_id) BETWEEN 1 AND 128),
    order_status text NOT NULL CHECK (order_status IN
        ('PENDING','ACTIVE','CLOSED','CANCELLED','EXPIRED','UNRESOLVED')),
    last_sequence bigint NOT NULL CHECK (last_sequence >= 0),
    event_id text NOT NULL CHECK (event_id ~ '^[0-9a-f]{64}$'),
    payload bytea NOT NULL CHECK (octet_length(payload) <= 1048576),
    content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
    PRIMARY KEY (workspace_id, session_id, order_id),
    FOREIGN KEY (workspace_id, session_id) REFERENCES btl.tick_sessions,
    FOREIGN KEY (workspace_id, session_id, last_sequence)
        REFERENCES btl.tick_events (workspace_id, session_id, sequence),
    FOREIGN KEY (workspace_id, session_id, order_id, last_sequence, event_id)
        REFERENCES btl.tick_journal_order_events
            (workspace_id, session_id, order_id, sequence, event_id)
);
CREATE INDEX tick_journal_order_projection_status
    ON btl.tick_journal_order_projection
       (workspace_id, session_id, order_status, order_id);

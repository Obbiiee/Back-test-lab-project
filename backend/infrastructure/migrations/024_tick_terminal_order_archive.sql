-- Immutable terminal-order read model for tick Sessions. Financial event rows
-- remain authoritative; this table is an indexed, versioned archive projection.
CREATE TABLE btl.tick_terminal_orders (
    workspace_id text NOT NULL,
    session_id text NOT NULL,
    sequence bigint NOT NULL CHECK (sequence >= 0),
    order_id text NOT NULL,
    finalized_revision bigint NOT NULL CHECK (finalized_revision > 0),
    record_hash text NOT NULL CHECK (record_hash ~ '^[0-9a-f]{64}$'),
    payload bytea NOT NULL CHECK (octet_length(payload) <= 1048576),
    content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
    PRIMARY KEY (workspace_id, session_id, sequence),
    UNIQUE (workspace_id, session_id, order_id),
    FOREIGN KEY (workspace_id, session_id) REFERENCES btl.tick_sessions,
    CHECK (length(order_id) BETWEEN 1 AND 128)
);
CREATE INDEX tick_terminal_orders_order_lookup
    ON btl.tick_terminal_orders (workspace_id, session_id, order_id);

CREATE TRIGGER immutable_tick_terminal_orders
    BEFORE UPDATE OR DELETE OR TRUNCATE ON btl.tick_terminal_orders
    FOR EACH STATEMENT EXECUTE FUNCTION btl.deny_evidence_mutation();

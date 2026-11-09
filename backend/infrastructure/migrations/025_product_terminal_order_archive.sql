CREATE TABLE btl.tick_terminal_order_archive_v1 (
    workspace_id text NOT NULL,
    session_id text NOT NULL,
    sequence bigint NOT NULL,
    order_id text NOT NULL,
    finalized_revision bigint NOT NULL,
    record_hash text NOT NULL,
    payload bytea NOT NULL,
    content_hash text NOT NULL,
    PRIMARY KEY (workspace_id, session_id, sequence),
    UNIQUE (workspace_id, session_id, order_id),
    FOREIGN KEY (workspace_id, session_id)
        REFERENCES btl.tick_sessions(workspace_id, session_id),
    CHECK (sequence >= 0),
    CHECK (finalized_revision > 0),
    CHECK (record_hash ~ '^[0-9a-f]{64}$'),
    CHECK (content_hash ~ '^[0-9a-f]{64}$'),
    CHECK (octet_length(payload) <= 1048576)
);

CREATE FUNCTION btl.reject_terminal_order_archive_mutation_v1()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'TERMINAL_ORDER_ARCHIVE_IMMUTABLE';
    RETURN NULL;
END $$;

CREATE TRIGGER tick_terminal_order_archive_immutable_v1
    BEFORE UPDATE OR DELETE ON btl.tick_terminal_order_archive_v1
    FOR EACH ROW EXECUTE FUNCTION btl.reject_terminal_order_archive_mutation_v1();

CREATE TRIGGER tick_terminal_order_archive_no_truncate_v1
    BEFORE TRUNCATE ON btl.tick_terminal_order_archive_v1
    FOR EACH STATEMENT EXECUTE FUNCTION btl.reject_terminal_order_archive_mutation_v1();

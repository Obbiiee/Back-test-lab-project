-- Isolated opt-in tick domain. Existing intake and legacy account remain unchanged.
CREATE TABLE btl.tick_sessions (
    workspace_id text NOT NULL, session_id text NOT NULL,
    dataset_version text NOT NULL, profile_hash text NOT NULL,
    revision bigint NOT NULL CHECK (revision >= 0),
    payload bytea NOT NULL CHECK (octet_length(payload) <= 1048576),
    content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
    PRIMARY KEY (workspace_id, session_id)
);
CREATE TABLE btl.tick_commands (
    workspace_id text NOT NULL, session_id text NOT NULL, command_id text NOT NULL,
    revision bigint NOT NULL CHECK (revision > 0),
    command_hash text NOT NULL CHECK (command_hash ~ '^[0-9a-f]{64}$'),
    payload bytea NOT NULL CHECK (octet_length(payload) <= 1048576),
    content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
    PRIMARY KEY (workspace_id, session_id, command_id),
    UNIQUE (workspace_id, session_id, revision),
    FOREIGN KEY (workspace_id, session_id) REFERENCES btl.tick_sessions
);
CREATE TABLE btl.tick_events (
    workspace_id text NOT NULL, session_id text NOT NULL, command_id text NOT NULL,
    event_id text NOT NULL, sequence bigint NOT NULL CHECK (sequence >= 0),
    payload bytea NOT NULL CHECK (octet_length(payload) <= 1048576),
    content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
    PRIMARY KEY (workspace_id, session_id, event_id),
    UNIQUE (workspace_id, session_id, sequence),
    FOREIGN KEY (workspace_id, session_id, command_id) REFERENCES btl.tick_commands DEFERRABLE INITIALLY DEFERRED
);
CREATE TABLE btl.tick_checkpoints (
    workspace_id text NOT NULL, session_id text NOT NULL, revision bigint NOT NULL CHECK (revision >= 0),
    payload bytea NOT NULL CHECK (octet_length(payload) <= 1048576),
    content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
    PRIMARY KEY (workspace_id, session_id, revision),
    FOREIGN KEY (workspace_id, session_id) REFERENCES btl.tick_sessions
);
CREATE TRIGGER immutable_tick_commands BEFORE UPDATE OR DELETE OR TRUNCATE ON btl.tick_commands
    FOR EACH STATEMENT EXECUTE FUNCTION btl.deny_evidence_mutation();
CREATE TRIGGER immutable_tick_events BEFORE UPDATE OR DELETE OR TRUNCATE ON btl.tick_events
    FOR EACH STATEMENT EXECUTE FUNCTION btl.deny_evidence_mutation();
CREATE TRIGGER immutable_tick_checkpoints BEFORE UPDATE OR DELETE OR TRUNCATE ON btl.tick_checkpoints
    FOR EACH STATEMENT EXECUTE FUNCTION btl.deny_evidence_mutation();
CREATE FUNCTION btl.guard_tick_session() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.workspace_id <> OLD.workspace_id OR NEW.session_id <> OLD.session_id
       OR NEW.dataset_version <> OLD.dataset_version OR NEW.profile_hash <> OLD.profile_hash
       OR NEW.revision <> OLD.revision + 1 THEN
        RAISE EXCEPTION 'Immutable tick identity or invalid revision' USING ERRCODE = '23000';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER guard_tick_session BEFORE UPDATE ON btl.tick_sessions
    FOR EACH ROW EXECUTE FUNCTION btl.guard_tick_session();

-- Storage prerequisite for explicitly versioned observed replay progress.
-- One replaceable row per Session, anchored to immutable financial evidence.
CREATE TABLE btl.observed_replay_progress (
    workspace_id text NOT NULL,
    session_id text NOT NULL,
    base_revision bigint NOT NULL CHECK (base_revision >= 0),
    base_hash text NOT NULL CHECK (base_hash ~ '^[0-9a-f]{64}$'),
    revision bigint NOT NULL CHECK (revision >= base_revision),
    through_ns numeric NOT NULL CHECK (
        through_ns BETWEEN 0 AND 10000000000000000000000 AND through_ns = trunc(through_ns)
    ),
    next_group_index numeric NOT NULL CHECK (
        next_group_index BETWEEN 0 AND 10000000000000000000000 AND next_group_index = trunc(next_group_index)
    ),
    payload bytea NOT NULL CHECK (octet_length(payload) BETWEEN 1 AND 1048576),
    content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
    PRIMARY KEY (workspace_id, session_id),
    FOREIGN KEY (workspace_id, session_id, base_revision)
        REFERENCES btl.tick_checkpoints (workspace_id, session_id, revision)
);

CREATE FUNCTION btl.guard_observed_replay_progress() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    checkpoint_hash text;
BEGIN
    IF TG_OP = 'UPDATE' THEN
        IF (NEW.workspace_id, NEW.session_id) IS DISTINCT FROM (OLD.workspace_id, OLD.session_id)
            OR NEW.revision <= OLD.revision
            OR NEW.base_revision < OLD.base_revision
            OR NEW.through_ns < OLD.through_ns
            OR NEW.next_group_index < OLD.next_group_index THEN
            RAISE EXCEPTION 'Invalid observed replay progress transition' USING ERRCODE = '23000';
        END IF;
    END IF;

    SELECT content_hash INTO checkpoint_hash
    FROM btl.tick_checkpoints
    WHERE workspace_id = NEW.workspace_id AND session_id = NEW.session_id AND revision = NEW.base_revision;
    IF checkpoint_hash IS DISTINCT FROM NEW.base_hash THEN
        RAISE EXCEPTION 'Observed replay progress base mismatch' USING ERRCODE = '23000';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER guard_observed_replay_progress
    BEFORE INSERT OR UPDATE ON btl.observed_replay_progress
    FOR EACH ROW EXECUTE FUNCTION btl.guard_observed_replay_progress();

CREATE TRIGGER deny_observed_replay_progress_removal
    BEFORE DELETE OR TRUNCATE ON btl.observed_replay_progress
    FOR EACH STATEMENT EXECUTE FUNCTION btl.deny_evidence_mutation();

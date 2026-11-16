-- A financial commit can fold a replaceable progress frontier into its next
-- immutable revision. Legacy Sessions continue to advance by exactly one.
CREATE OR REPLACE FUNCTION btl.guard_tick_session() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
DECLARE
    progress_base bigint;
    progress_revision bigint;
BEGIN
    IF (NEW.workspace_id, NEW.session_id, NEW.dataset_version, NEW.profile_hash)
       IS DISTINCT FROM (OLD.workspace_id, OLD.session_id, OLD.dataset_version, OLD.profile_hash) THEN
        RAISE EXCEPTION 'Immutable tick identity' USING ERRCODE = '23000';
    END IF;

    SELECT base_revision, revision INTO progress_base, progress_revision
    FROM btl.observed_replay_progress
    WHERE workspace_id = OLD.workspace_id AND session_id = OLD.session_id;
    IF NOT FOUND THEN
        IF NEW.revision <> OLD.revision + 1 THEN
            RAISE EXCEPTION 'Invalid tick revision' USING ERRCODE = '23000';
        END IF;
    ELSIF progress_base <> OLD.revision OR NEW.revision <> progress_revision + 1
       OR NOT EXISTS (
            SELECT 1 FROM btl.tick_checkpoints
            WHERE workspace_id = NEW.workspace_id AND session_id = NEW.session_id AND revision = NEW.revision
       ) OR NOT EXISTS (
            SELECT 1 FROM btl.tick_commands
            WHERE workspace_id = NEW.workspace_id AND session_id = NEW.session_id AND revision = NEW.revision
       ) THEN
        RAISE EXCEPTION 'Missing or stale observed replay consolidation' USING ERRCODE = '23000';
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION btl.guard_observed_progress_current_base() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    current_revision bigint;
BEGIN
    SELECT revision INTO current_revision
    FROM btl.tick_sessions
    WHERE workspace_id = NEW.workspace_id AND session_id = NEW.session_id
    FOR NO KEY UPDATE;
    IF current_revision IS DISTINCT FROM NEW.base_revision OR NEW.revision <= NEW.base_revision THEN
        RAISE EXCEPTION 'Observed replay progress must extend the current Session' USING ERRCODE = '23000';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER guard_observed_progress_current_base
    BEFORE INSERT OR UPDATE ON btl.observed_replay_progress
    FOR EACH ROW EXECUTE FUNCTION btl.guard_observed_progress_current_base();

DROP TRIGGER deny_observed_replay_progress_removal ON btl.observed_replay_progress;

CREATE TRIGGER deny_observed_replay_progress_truncate
    BEFORE TRUNCATE ON btl.observed_replay_progress
    FOR EACH STATEMENT EXECUTE FUNCTION btl.deny_evidence_mutation();

CREATE FUNCTION btl.guard_observed_progress_consumption() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM btl.tick_sessions
        WHERE workspace_id = OLD.workspace_id AND session_id = OLD.session_id
          AND revision = OLD.revision + 1
    ) THEN
        RAISE EXCEPTION 'Observed replay progress has not been consolidated' USING ERRCODE = '23000';
    END IF;
    RETURN OLD;
END;
$$;

CREATE TRIGGER guard_observed_progress_consumption
    BEFORE DELETE ON btl.observed_replay_progress
    FOR EACH ROW EXECUTE FUNCTION btl.guard_observed_progress_consumption();

CREATE FUNCTION btl.consume_observed_replay_progress() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
BEGIN
    IF NEW.revision > OLD.revision + 1 THEN
        DELETE FROM btl.observed_replay_progress
        WHERE workspace_id = NEW.workspace_id AND session_id = NEW.session_id;
    END IF;
    RETURN NULL;
END;
$$;

CREATE TRIGGER consume_observed_replay_progress
    AFTER UPDATE ON btl.tick_sessions
    FOR EACH ROW EXECUTE FUNCTION btl.consume_observed_replay_progress();

REVOKE EXECUTE ON FUNCTION btl.guard_tick_session() FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION btl.consume_observed_replay_progress() FROM PUBLIC;

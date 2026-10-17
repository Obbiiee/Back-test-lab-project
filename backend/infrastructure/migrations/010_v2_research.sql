-- Additive opaque v2 product metadata; old v1 rows/queries stay unchanged.
CREATE TABLE btl.tick_v2_research_sessions (
 workspace_id text NOT NULL, session_id text NOT NULL, method_id text NOT NULL,
 payload bytea NOT NULL CHECK (octet_length(payload)<=32768),
 content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
 PRIMARY KEY(workspace_id,session_id),
 FOREIGN KEY(workspace_id,session_id) REFERENCES btl.tick_sessions,
 FOREIGN KEY(workspace_id,method_id) REFERENCES btl.tick_methods
);
CREATE INDEX tick_v2_session_method ON btl.tick_v2_research_sessions(workspace_id,method_id,session_id);
CREATE TABLE btl.tick_v2_order_reviews (
 workspace_id text NOT NULL, session_id text NOT NULL, review_id text NOT NULL,
 basis_revision bigint NOT NULL CHECK(basis_revision>=0),
 basis_checkpoint_hash text NOT NULL CHECK(basis_checkpoint_hash ~ '^[0-9a-f]{64}$'),
 command_hash text NOT NULL CHECK(command_hash ~ '^[0-9a-f]{64}$'),
 payload bytea NOT NULL CHECK(octet_length(payload)<=32768),
 content_hash text NOT NULL CHECK(content_hash ~ '^[0-9a-f]{64}$'),
 PRIMARY KEY(workspace_id,session_id,review_id),
 FOREIGN KEY(workspace_id,session_id) REFERENCES btl.tick_v2_research_sessions,
 FOREIGN KEY(workspace_id,session_id,basis_revision) REFERENCES btl.tick_checkpoints
);
CREATE INDEX tick_v2_review_basis ON btl.tick_v2_order_reviews(workspace_id,session_id,basis_revision);
CREATE TABLE btl.tick_v2_journal_notes (
 workspace_id text NOT NULL, session_id text NOT NULL, order_id text NOT NULL,
 note_revision bigint NOT NULL CHECK(note_revision>0),
 payload bytea NOT NULL CHECK(octet_length(payload)<=32768),
 content_hash text NOT NULL CHECK(content_hash ~ '^[0-9a-f]{64}$'),
 PRIMARY KEY(workspace_id,session_id,order_id),
 FOREIGN KEY(workspace_id,session_id) REFERENCES btl.tick_v2_research_sessions
);
CREATE TRIGGER immutable_v2_research_sessions BEFORE UPDATE OR DELETE OR TRUNCATE ON btl.tick_v2_research_sessions
 FOR EACH STATEMENT EXECUTE FUNCTION btl.deny_evidence_mutation();
CREATE TRIGGER immutable_v2_order_reviews BEFORE UPDATE OR DELETE OR TRUNCATE ON btl.tick_v2_order_reviews
 FOR EACH STATEMENT EXECUTE FUNCTION btl.deny_evidence_mutation();
CREATE FUNCTION btl.guard_v2_review_basis() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE current_revision bigint; checkpoint_hash text;
BEGIN
 SELECT revision INTO current_revision FROM btl.tick_sessions
 WHERE workspace_id=NEW.workspace_id AND session_id=NEW.session_id FOR SHARE;
 SELECT content_hash INTO checkpoint_hash FROM btl.tick_checkpoints
 WHERE workspace_id=NEW.workspace_id AND session_id=NEW.session_id AND revision=NEW.basis_revision;
 IF current_revision IS DISTINCT FROM NEW.basis_revision OR checkpoint_hash IS DISTINCT FROM NEW.basis_checkpoint_hash
 OR EXISTS(SELECT 1 FROM btl.tick_commands WHERE workspace_id=NEW.workspace_id AND session_id=NEW.session_id AND command_id=NEW.review_id) THEN
  RAISE EXCEPTION 'Review must precede confirmation at exact committed basis' USING ERRCODE='23000';
 END IF;
 RETURN NEW;
END; $$;
CREATE TRIGGER guard_v2_review_basis BEFORE INSERT ON btl.tick_v2_order_reviews
 FOR EACH ROW EXECUTE FUNCTION btl.guard_v2_review_basis();
CREATE FUNCTION btl.guard_v2_note_revision() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF (NEW.workspace_id,NEW.session_id,NEW.order_id) IS DISTINCT FROM (OLD.workspace_id,OLD.session_id,OLD.order_id)
 OR NEW.note_revision<>OLD.note_revision+1 THEN
  RAISE EXCEPTION 'Immutable note identity or stale revision' USING ERRCODE='23000';
 END IF;
 RETURN NEW;
END; $$;
CREATE TRIGGER guard_v2_note_revision BEFORE UPDATE ON btl.tick_v2_journal_notes
 FOR EACH ROW EXECUTE FUNCTION btl.guard_v2_note_revision();

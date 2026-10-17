-- Sandbox capacity/entitlement metadata only; no financial or identity rewrite.
CREATE TABLE btl.v2_access_accounts (
 actor_id uuid PRIMARY KEY REFERENCES btl.users(id), reset_timezone text NOT NULL CHECK(reset_timezone IN ('UTC','Asia/Jakarta'))
);
CREATE TABLE btl.v2_access_sessions (
 workspace_id text NOT NULL, session_id text NOT NULL,
 actor_id uuid NOT NULL REFERENCES btl.users(id), trashed_at timestamptz,
 PRIMARY KEY(workspace_id,session_id),
 FOREIGN KEY(workspace_id,session_id) REFERENCES btl.tick_v2_research_sessions
);
CREATE INDEX v2_access_owner_saved ON btl.v2_access_sessions(actor_id) WHERE trashed_at IS NULL;
CREATE TABLE btl.v2_access_windows (
 actor_id uuid NOT NULL REFERENCES btl.users(id), entitlement_day date NOT NULL, free_day date,
 workspace_id text NOT NULL, session_id text NOT NULL, period text NOT NULL,
 payload bytea NOT NULL CHECK(octet_length(payload)<=32768),
 content_hash text NOT NULL CHECK(content_hash ~ '^[0-9a-f]{64}$'),
 PRIMARY KEY(actor_id,workspace_id,session_id,period),
 UNIQUE(actor_id,free_day),
 FOREIGN KEY(workspace_id,session_id) REFERENCES btl.v2_access_sessions
);
CREATE INDEX v2_access_window_session ON btl.v2_access_windows(workspace_id,session_id,entitlement_day DESC);
CREATE TABLE btl.sandbox_access_events (
 event_id text PRIMARY KEY, actor_id uuid NOT NULL REFERENCES btl.users(id),
 sequence bigint NOT NULL CHECK(sequence>0), payload bytea NOT NULL CHECK(octet_length(payload)<=4096),
 content_hash text NOT NULL CHECK(content_hash ~ '^[0-9a-f]{64}$'),
 UNIQUE(actor_id,sequence)
);
CREATE TRIGGER immutable_access_windows BEFORE UPDATE OR DELETE OR TRUNCATE ON btl.v2_access_windows
 FOR EACH STATEMENT EXECUTE FUNCTION btl.deny_evidence_mutation();
CREATE TRIGGER immutable_sandbox_access_events BEFORE UPDATE OR DELETE OR TRUNCATE ON btl.sandbox_access_events
 FOR EACH STATEMENT EXECUTE FUNCTION btl.deny_evidence_mutation();

CREATE TRIGGER immutable_v2_access_accounts BEFORE UPDATE OR DELETE OR TRUNCATE ON btl.v2_access_accounts
 FOR EACH STATEMENT EXECUTE FUNCTION btl.deny_evidence_mutation();
CREATE FUNCTION btl.guard_v2_access_session_identity() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF (NEW.workspace_id,NEW.session_id,NEW.actor_id) IS DISTINCT FROM (OLD.workspace_id,OLD.session_id,OLD.actor_id) THEN
  RAISE EXCEPTION 'Immutable sandbox Session owner' USING ERRCODE='23000';
 END IF;
 RETURN NEW;
END; $$;
CREATE TRIGGER guard_v2_access_session_identity BEFORE UPDATE ON btl.v2_access_sessions
 FOR EACH ROW EXECUTE FUNCTION btl.guard_v2_access_session_identity();

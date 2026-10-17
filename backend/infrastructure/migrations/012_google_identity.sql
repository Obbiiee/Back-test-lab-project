ALTER TABLE btl.users ADD COLUMN password_enabled boolean NOT NULL DEFAULT true;
CREATE FUNCTION btl.guard_user_password_kind() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.password_enabled IS DISTINCT FROM OLD.password_enabled THEN
  RAISE EXCEPTION 'Credential kind requires separate enrollment' USING ERRCODE='23000';
 END IF;
 RETURN NEW;
END; $$;
CREATE TRIGGER guard_user_password_kind BEFORE UPDATE OF password_enabled ON btl.users
 FOR EACH ROW EXECUTE FUNCTION btl.guard_user_password_kind();
CREATE TABLE btl.google_identities (
 subject text PRIMARY KEY CHECK(length(subject) BETWEEN 1 AND 255),
 user_id uuid NOT NULL UNIQUE REFERENCES btl.users(id),
 initial_email text NOT NULL, created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TRIGGER immutable_google_identities BEFORE UPDATE OR DELETE OR TRUNCATE ON btl.google_identities
 FOR EACH STATEMENT EXECUTE FUNCTION btl.deny_evidence_mutation();
CREATE TABLE btl.google_login_states (
 state_hash text PRIMARY KEY CHECK(state_hash ~ '^[0-9a-f]{64}$'),
 browser_hash text NOT NULL CHECK(browser_hash ~ '^[0-9a-f]{64}$'),
 config_hash text NOT NULL CHECK(config_hash ~ '^[0-9a-f]{64}$'),
 nonce text NOT NULL CHECK(length(nonce) BETWEEN 32 AND 128),
 verifier text NOT NULL CHECK(length(verifier) BETWEEN 43 AND 128),
 phase text NOT NULL CHECK(phase IN ('NEW','CLAIMED','READY','EXCHANGED')),
 user_id uuid REFERENCES btl.users(id), handoff_hash text UNIQUE,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 expires_at timestamptz NOT NULL DEFAULT clock_timestamp()+interval '5 minutes',
 CHECK((phase IN ('NEW','CLAIMED') AND user_id IS NULL AND handoff_hash IS NULL)
    OR (phase IN ('READY','EXCHANGED') AND user_id IS NOT NULL AND handoff_hash ~ '^[0-9a-f]{64}$'))
);
CREATE INDEX google_state_expiry ON btl.google_login_states(expires_at);
CREATE FUNCTION btl.guard_google_state_transition() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF (NEW.state_hash,NEW.browser_hash,NEW.config_hash,NEW.nonce,NEW.verifier,NEW.created_at,NEW.expires_at)
 IS DISTINCT FROM (OLD.state_hash,OLD.browser_hash,OLD.config_hash,OLD.nonce,OLD.verifier,OLD.created_at,OLD.expires_at)
 OR NOT ((OLD.phase='NEW' AND NEW.phase='CLAIMED') OR (OLD.phase='CLAIMED' AND NEW.phase='READY') OR (OLD.phase='READY' AND NEW.phase='EXCHANGED'))
 OR (OLD.phase='READY' AND (NEW.user_id,NEW.handoff_hash) IS DISTINCT FROM (OLD.user_id,OLD.handoff_hash)) THEN
  RAISE EXCEPTION 'Invalid Google state transition' USING ERRCODE='23000';
 END IF;
 RETURN NEW;
END; $$;
CREATE TRIGGER guard_google_state_transition BEFORE UPDATE ON btl.google_login_states
 FOR EACH ROW EXECUTE FUNCTION btl.guard_google_state_transition();

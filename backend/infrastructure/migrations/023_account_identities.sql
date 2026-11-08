-- Canonical, additive provider mapping. Internal users/workspaces/Sessions keep
-- their existing IDs; email equality is never an account-linking signal.
CREATE TABLE btl.account_identities (
    provider text NOT NULL CHECK (provider IN ('EMAIL_PASSWORD','GOOGLE')),
    provider_subject text NOT NULL CHECK (length(provider_subject) BETWEEN 1 AND 320),
    user_id uuid NOT NULL REFERENCES btl.users(id),
    linked_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    linked_by text NOT NULL CHECK (linked_by IN ('BACKFILL','EMAIL_VERIFICATION','GOOGLE_SIGNUP','GOOGLE_LINK')),
    PRIMARY KEY (provider, provider_subject),
    UNIQUE (provider, user_id)
);
CREATE INDEX account_identities_user ON btl.account_identities(user_id);

CREATE FUNCTION btl.deny_account_identity_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'Account identity ownership is immutable' USING ERRCODE='23000';
END;
$$;
CREATE TRIGGER immutable_account_identities
    BEFORE UPDATE OR DELETE OR TRUNCATE ON btl.account_identities
    FOR EACH STATEMENT EXECUTE FUNCTION btl.deny_account_identity_mutation();

-- Backfill only verified password identities and existing Google subject pins.
INSERT INTO btl.account_identities(provider,provider_subject,user_id,linked_by)
SELECT 'EMAIL_PASSWORD',lower(email),id,'BACKFILL'
FROM btl.users WHERE is_verified AND password_enabled;
INSERT INTO btl.account_identities(provider,provider_subject,user_id,linked_by)
SELECT 'GOOGLE',subject,user_id,'BACKFILL' FROM btl.google_identities;

-- The OAuth state is one-use and browser-bound. LINK is initiated only after
-- password reauthentication; target_user_id can never be supplied by Google.
ALTER TABLE btl.google_login_states
    ADD COLUMN purpose text NOT NULL DEFAULT 'LOGIN' CHECK (purpose IN ('LOGIN','LINK')),
    ADD COLUMN target_user_id uuid REFERENCES btl.users(id);
ALTER TABLE btl.google_login_states
    ADD CONSTRAINT google_state_purpose_target CHECK (
       (purpose='LOGIN' AND target_user_id IS NULL)
       OR (purpose='LINK' AND target_user_id IS NOT NULL)
    );

CREATE OR REPLACE FUNCTION btl.guard_google_state_transition() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF (NEW.state_hash,NEW.browser_hash,NEW.config_hash,NEW.nonce,NEW.verifier,NEW.created_at,NEW.expires_at,
     NEW.purpose,NEW.target_user_id)
 IS DISTINCT FROM (OLD.state_hash,OLD.browser_hash,OLD.config_hash,OLD.nonce,OLD.verifier,OLD.created_at,OLD.expires_at,
                   OLD.purpose,OLD.target_user_id)
 OR NOT ((OLD.phase='NEW' AND NEW.phase='CLAIMED') OR (OLD.phase='CLAIMED' AND NEW.phase='READY') OR (OLD.phase='READY' AND NEW.phase='EXCHANGED'))
 OR (OLD.phase='READY' AND (NEW.user_id,NEW.handoff_hash)
     IS DISTINCT FROM (OLD.user_id,OLD.handoff_hash)) THEN
  RAISE EXCEPTION 'Invalid Google state transition' USING ERRCODE='23000';
 END IF;
 RETURN NEW;
END; $$;


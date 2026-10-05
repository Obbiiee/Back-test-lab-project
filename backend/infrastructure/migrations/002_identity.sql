CREATE TABLE btl.users (
    id uuid PRIMARY KEY, email text NOT NULL UNIQUE CHECK (length(email) <= 320),
    hashed_password text NOT NULL CHECK (length(hashed_password) <= 2048),
    is_active boolean NOT NULL DEFAULT true,
    is_superuser boolean NOT NULL DEFAULT false,
    is_verified boolean NOT NULL DEFAULT false
);
CREATE TABLE btl.auth_sessions (
    token_hash text PRIMARY KEY CHECK (token_hash ~ '^[0-9a-f]{64}$'),
    user_id uuid NOT NULL REFERENCES btl.users,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX auth_sessions_user ON btl.auth_sessions(user_id);
CREATE TABLE btl.auth_rate_limits (
    key text NOT NULL, bucket bigint NOT NULL, attempts int NOT NULL CHECK (attempts > 0),
    PRIMARY KEY(key,bucket)
);
CREATE INDEX auth_rate_window ON btl.auth_rate_limits(bucket);
CREATE TABLE btl.security_events (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id uuid REFERENCES btl.users, code text NOT NULL CHECK (length(code) <= 64),
    recorded_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TRIGGER immutable_security_events BEFORE UPDATE OR DELETE OR TRUNCATE ON btl.security_events
    FOR EACH STATEMENT EXECUTE FUNCTION btl.deny_evidence_mutation();

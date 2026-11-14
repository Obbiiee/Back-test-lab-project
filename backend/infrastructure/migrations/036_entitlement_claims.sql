-- Replaces the 033 per-day claim table (QA-only data, never released) by a two-quota, durable reservation ledger.
-- kind SESSION : one new Session per UTC calendar month for Free (period = 'YYYY-MM').
-- kind WINDOW  : one newly activated historical month per UTC day for Free (period = 'YYYY-MM-DD'); claim_key identifies the (source, month).
-- status: RESERVED (admitted, not yet proven) -> COMMITTED (the Session exists) | RELEASED (failed before commit; the token is available again).
DROP TABLE btl.entitlement_windows;
CREATE TABLE btl.entitlement_claims (
 actor_id uuid NOT NULL REFERENCES btl.users(id),
 kind text NOT NULL CHECK(kind IN ('SESSION','WINDOW')),
 claim_key text NOT NULL CHECK(claim_key ~ '^[0-9a-f]{64}$'),
 period text NOT NULL,
 tier text NOT NULL CHECK(tier IN ('FREE','PRO')),
 status text NOT NULL CHECK(status IN ('RESERVED','COMMITTED','RELEASED')),
 workspace_id text NOT NULL, session_id text NOT NULL, job_id uuid,
 window_start_ns bigint NOT NULL, window_end_ns bigint NOT NULL CHECK(window_end_ns>window_start_ns),
 reserved_at timestamptz NOT NULL DEFAULT clock_timestamp(), settled_at timestamptz,
 PRIMARY KEY(actor_id,kind,claim_key)
);
CREATE UNIQUE INDEX entitlement_free_one_active ON btl.entitlement_claims(actor_id,kind,period) WHERE tier='FREE' AND status IN ('RESERVED','COMMITTED');
CREATE INDEX entitlement_session_lookup ON btl.entitlement_claims(workspace_id,session_id) WHERE kind='SESSION';

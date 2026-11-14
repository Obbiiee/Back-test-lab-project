-- Server-side Free/Pro research-window claims for the default Session path (opt-in by BTL_ENTITLEMENT_ENFORCE; no financial data).
-- A claim is one activated research window. Free: at most one claim per entitlement day; Pro: unlimited. The claim key makes a retry of the same request idempotent.
CREATE TABLE btl.entitlement_windows (
 actor_id uuid NOT NULL REFERENCES btl.users(id),
 entitlement_day date NOT NULL,
 claim_key text NOT NULL CHECK(claim_key ~ '^[0-9a-f]{64}$'),
 tier text NOT NULL CHECK(tier IN ('FREE','PRO')),
 workspace_id text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(actor_id,claim_key)
);
-- Free: the database itself refuses a second window on the same day, independent of application races.
CREATE UNIQUE INDEX entitlement_free_one_per_day ON btl.entitlement_windows(actor_id,entitlement_day) WHERE tier='FREE';

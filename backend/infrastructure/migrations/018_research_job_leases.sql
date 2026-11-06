-- Durable operational ownership only. Canonical command/evidence tables are unchanged.
ALTER TABLE btl.research_jobs
    ADD COLUMN lease_owner uuid,
    ADD COLUMN lease_until timestamptz,
    ADD COLUMN heartbeat_at timestamptz,
    ADD COLUMN attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    ADD COLUMN cancel_requested_at timestamptz;

ALTER TABLE btl.research_jobs DROP CONSTRAINT research_jobs_state_check;
ALTER TABLE btl.research_jobs ADD CONSTRAINT research_jobs_state_check
    CHECK (state IN ('QUEUED','RUNNING','SUCCEEDED','FAILED','CANCELLED','EXPIRED','RECONCILE_REQUIRED'));
ALTER TABLE btl.research_jobs ADD CONSTRAINT research_jobs_lease_state_check
    CHECK ((state = 'RUNNING' AND lease_owner IS NOT NULL AND lease_until IS NOT NULL AND heartbeat_at IS NOT NULL)
        OR (state <> 'RUNNING' AND lease_owner IS NULL AND lease_until IS NULL AND heartbeat_at IS NULL));
CREATE INDEX research_jobs_expired_lease ON btl.research_jobs(lease_until,id)
    WHERE state = 'RUNNING';

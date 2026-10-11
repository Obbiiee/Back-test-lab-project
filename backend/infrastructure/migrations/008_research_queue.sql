-- Operational queue, not financial/event/evidence authority. Explicit migration only.
CREATE TABLE btl.research_jobs (
    id uuid PRIMARY KEY,
    actor_id uuid NOT NULL REFERENCES btl.users(id),
    workspace_id uuid NOT NULL REFERENCES btl.workspaces(id),
    operation text NOT NULL CHECK (operation IN ('workspace','bootstrap')),
    input bytea NOT NULL CHECK (octet_length(input) <= 16384),
    input_hash text NOT NULL CHECK (input_hash ~ '^[0-9a-f]{64}$'),
    state text NOT NULL CHECK (state IN ('QUEUED','SUCCEEDED','FAILED','CANCELLED','EXPIRED')),
    result bytea CHECK (octet_length(result) <= 8388608),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    expires_at timestamptz NOT NULL DEFAULT clock_timestamp() + interval '60 seconds',
    finished_at timestamptz,
    CHECK ((state = 'SUCCEEDED') = (result IS NOT NULL))
);
CREATE INDEX research_jobs_pending ON btl.research_jobs(created_at,id) WHERE state='QUEUED';
CREATE INDEX research_jobs_actor_pending ON btl.research_jobs(actor_id,created_at) WHERE state='QUEUED';

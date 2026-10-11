-- Operational scheduling only. Canonical financial transactions stay unchanged.
ALTER TABLE btl.research_jobs DROP CONSTRAINT research_jobs_operation_check;
ALTER TABLE btl.research_jobs ADD CONSTRAINT research_jobs_operation_check
    CHECK (operation IN ('workspace','bootstrap','replay'));
ALTER TABLE btl.research_jobs DROP CONSTRAINT research_jobs_state_check;
ALTER TABLE btl.research_jobs ADD CONSTRAINT research_jobs_state_check
    CHECK (state IN ('QUEUED','SUCCEEDED','FAILED','CANCELLED','EXPIRED','RECONCILE_REQUIRED'));

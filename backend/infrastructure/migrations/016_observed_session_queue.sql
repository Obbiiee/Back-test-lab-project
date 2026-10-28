-- Bounded controller job for hash-pinned observed Session initialization.
ALTER TABLE btl.research_jobs DROP CONSTRAINT research_jobs_operation_check;
ALTER TABLE btl.research_jobs ADD CONSTRAINT research_jobs_operation_check
    CHECK (operation IN ('create_session','workspace','bootstrap','replay','chart_history'));

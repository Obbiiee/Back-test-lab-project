-- Bounded read-only historical context is an operational job, not a financial command.
ALTER TABLE btl.research_jobs DROP CONSTRAINT research_jobs_operation_check;
ALTER TABLE btl.research_jobs ADD CONSTRAINT research_jobs_operation_check
    CHECK (operation IN ('workspace','bootstrap','replay','chart_history'));

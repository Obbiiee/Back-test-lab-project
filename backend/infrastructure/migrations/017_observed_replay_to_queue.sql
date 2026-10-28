-- One bounded controller replay-to-UTC batch for the observed family.
ALTER TABLE btl.research_jobs DROP CONSTRAINT research_jobs_operation_check;
ALTER TABLE btl.research_jobs ADD CONSTRAINT research_jobs_operation_check
    CHECK (operation IN ('create_session','workspace','bootstrap','replay','replay_to','chart_history'));

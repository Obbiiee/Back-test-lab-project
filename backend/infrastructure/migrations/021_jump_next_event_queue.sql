-- A jump is a durable orchestration over ordinary canonical ADVANCE receipts.
-- It is mutating because each bounded chunk advances the Session frontier.
ALTER TABLE btl.research_jobs DROP CONSTRAINT research_jobs_operation_check;
ALTER TABLE btl.research_jobs ADD CONSTRAINT research_jobs_operation_check
    CHECK (operation IN ('create_session','workspace','bootstrap','replay','replay_to','chart_history','jump_next_event'));

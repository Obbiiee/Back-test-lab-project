-- Durable multi-chunk replay ("replay run"): one more operation kind for the durable queue. The continuation segment of a run is a normal job row
-- created in the same transaction that finalises the previous segment (cloud/queue.py); nothing about financial tables changes.
ALTER TABLE btl.research_jobs DROP CONSTRAINT research_jobs_operation_check;
ALTER TABLE btl.research_jobs ADD CONSTRAINT research_jobs_operation_check
    CHECK (operation IN ('create_session','workspace','bootstrap','replay','replay_to','replay_run','chart_history','jump_next_event'));

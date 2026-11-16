-- First-claim admission latency is operational telemetry, never job/finance truth.
ALTER TABLE btl.research_jobs
    ADD COLUMN queue_metrics bytea,
    ADD COLUMN queue_metrics_hash text;

ALTER TABLE btl.research_jobs
    ADD CONSTRAINT research_jobs_queue_metrics_pair_check CHECK (
        (queue_metrics IS NULL AND queue_metrics_hash IS NULL) OR
        (queue_metrics IS NOT NULL AND octet_length(queue_metrics) <= 1024 AND
         queue_metrics_hash ~ '^[0-9a-f]{64}$')
    );

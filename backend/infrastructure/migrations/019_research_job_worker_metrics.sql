-- Bounded operational measurements; never financial or command authority.
ALTER TABLE btl.research_jobs
    ADD COLUMN worker_metrics bytea,
    ADD COLUMN worker_metrics_hash text;

ALTER TABLE btl.research_jobs
    ADD CONSTRAINT research_jobs_worker_metrics_pair_check CHECK (
        (worker_metrics IS NULL AND worker_metrics_hash IS NULL) OR
        (worker_metrics IS NOT NULL AND octet_length(worker_metrics) <= 4096 AND
         worker_metrics_hash ~ '^[0-9a-f]{64}$')
    );

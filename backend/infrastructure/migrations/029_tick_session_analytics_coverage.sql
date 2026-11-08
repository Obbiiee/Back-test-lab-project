-- Mark Sessions whose committed-event analytics aggregate is transactionally
-- maintained. Older indexed Sessions remain on the verified legacy fallback.
ALTER TABLE btl.tick_journal_projection_heads
    ADD COLUMN analytics_format_version smallint NOT NULL DEFAULT 0
        CHECK (analytics_format_version IN (0, 1));

UPDATE btl.tick_journal_projection_heads h
SET analytics_format_version = 1
FROM btl.tick_session_metric_projections a
WHERE (a.workspace_id, a.session_id) = (h.workspace_id, h.session_id);

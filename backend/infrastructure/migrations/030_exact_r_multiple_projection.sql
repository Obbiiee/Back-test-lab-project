ALTER TABLE btl.tick_journal_projection_heads
    DROP CONSTRAINT tick_journal_projection_heads_analytics_format_version_check;

ALTER TABLE btl.tick_journal_projection_heads
    ADD CONSTRAINT tick_journal_projection_heads_analytics_format_version_check
    CHECK (analytics_format_version IN (0, 1, 2));

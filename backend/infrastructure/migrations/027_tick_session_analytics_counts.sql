-- Exact committed position counts are maintained with each event commit.
-- Existing indexed Sessions are backfilled once from their replaceable
-- per-order projection; immutable financial events remain authoritative.
ALTER TABLE btl.tick_journal_projection_heads
    ADD COLUMN closed_order_count bigint NOT NULL DEFAULT 0
        CHECK (closed_order_count >= 0);

UPDATE btl.tick_journal_projection_heads h
SET closed_order_count = (
    SELECT count(*)
    FROM btl.tick_journal_order_projection p
    WHERE p.workspace_id = h.workspace_id
      AND p.session_id = h.session_id
      AND p.order_status = 'CLOSED'
);

-- Session analytics pages traverse only terminal trades and resume from the
-- immutable event sequence plus order id. Keep existing Journal indexes intact.
CREATE INDEX tick_journal_order_projection_analytics_c
    ON btl.tick_journal_order_projection
       (workspace_id, session_id, last_sequence, (order_id COLLATE "C"))
    WHERE order_status = 'CLOSED';

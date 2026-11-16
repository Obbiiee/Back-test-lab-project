-- Keep Journal keyset pagination in the same deterministic ASCII order as
-- the legacy Python fallback, independent of the database's default locale.
CREATE INDEX tick_journal_order_projection_page_c
    ON btl.tick_journal_order_projection
       (workspace_id, session_id, (order_id COLLATE "C"));

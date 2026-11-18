-- QA MI reviews bind to an immutable revision of the financial checkpoint.
CREATE TABLE btl.tick_mi_order_reviews (
    workspace_id text NOT NULL,
    session_id text NOT NULL,
    review_id text NOT NULL,
    basis_revision bigint NOT NULL CHECK (basis_revision >= 0),
    payload bytea NOT NULL CHECK (octet_length(payload) <= 32768),
    content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
    PRIMARY KEY (workspace_id, session_id, review_id),
    FOREIGN KEY (workspace_id, session_id, basis_revision) REFERENCES btl.tick_checkpoints
);
CREATE TRIGGER immutable_mi_order_reviews BEFORE UPDATE OR DELETE OR TRUNCATE ON btl.tick_mi_order_reviews
    FOR EACH STATEMENT EXECUTE FUNCTION btl.deny_evidence_mutation();

-- Explicit pre-execution refusals remain distinct from successful receipts.
ALTER TABLE btl.research_jobs ADD COLUMN mi_refusal_code text
    CHECK (mi_refusal_code IS NULL OR (state = 'RECONCILE_REQUIRED' AND operation = 'replay'
           AND mi_refusal_code IN ('WINDOW_BOUNDARY', 'WINDOW_ENDED', 'WINDOW_ENDED_CONTINUATION_ONLY',
               'PENDING_AT_WINDOW_END', 'WINDOW_COMPLETED', 'MI_REVIEW_REQUIRED',
               'MI_REVIEW_EXPIRED', 'MI_REVIEW_MISMATCH', 'REFUSED_STALE_REVISION')));

-- One bounded exact aggregate per immutable Method. Historical Methods are
-- marked for a verified rebuild; new Methods may start from an empty snapshot.
CREATE TABLE btl.tick_method_metric_projections (
    workspace_id text NOT NULL,
    method_id text NOT NULL,
    format_version smallint NOT NULL CHECK (format_version = 1),
    rollup_state text NOT NULL CHECK (rollup_state IN ('READY', 'REBUILD_REQUIRED')),
    session_count bigint NOT NULL CHECK (session_count >= 0),
    payload bytea,
    content_hash text,
    PRIMARY KEY (workspace_id, method_id),
    FOREIGN KEY (workspace_id, method_id)
        REFERENCES btl.tick_methods(workspace_id, method_id),
    CHECK (
        (rollup_state = 'READY' AND payload IS NOT NULL
            AND octet_length(payload) <= 262144
            AND content_hash IS NOT NULL
            AND content_hash ~ '^[0-9a-f]{64}$')
        OR
        (rollup_state = 'REBUILD_REQUIRED' AND payload IS NULL
            AND content_hash IS NULL)
    )
);

INSERT INTO btl.tick_method_metric_projections
    (workspace_id, method_id, format_version, rollup_state, session_count,
     payload, content_hash)
SELECT m.workspace_id, m.method_id, 1, 'REBUILD_REQUIRED', count(s.session_id),
       NULL, NULL
FROM btl.tick_methods m
LEFT JOIN btl.tick_research_sessions s
  ON (s.workspace_id, s.method_id) = (m.workspace_id, m.method_id)
GROUP BY m.workspace_id, m.method_id;

-- Default-path Session lifecycle: a trashed Session disappears from the list and can be restored for 30 days. Financial evidence is never changed or deleted here.
CREATE TABLE btl.session_lifecycle (
 workspace_id text NOT NULL, session_id text NOT NULL,
 trashed_at timestamptz,
 PRIMARY KEY(workspace_id,session_id),
 FOREIGN KEY(workspace_id,session_id) REFERENCES btl.tick_sessions(workspace_id,session_id)
);

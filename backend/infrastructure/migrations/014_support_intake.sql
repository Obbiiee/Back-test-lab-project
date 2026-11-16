-- Durable user-authored support intake; never execution or billing authority.
CREATE TABLE btl.support_requests (
 id uuid PRIMARY KEY, actor_id uuid NOT NULL REFERENCES btl.users(id), request_id uuid NOT NULL,
 title text NOT NULL CHECK(length(title) BETWEEN 1 AND 160),
 message text NOT NULL CHECK(length(message) BETWEEN 1 AND 4000),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(actor_id,request_id)
);
CREATE INDEX support_actor_recent ON btl.support_requests(actor_id,created_at DESC,id);
CREATE TRIGGER immutable_support_requests BEFORE UPDATE OR DELETE OR TRUNCATE ON btl.support_requests
 FOR EACH STATEMENT EXECUTE FUNCTION btl.deny_evidence_mutation();
REVOKE ALL ON btl.support_requests FROM PUBLIC;

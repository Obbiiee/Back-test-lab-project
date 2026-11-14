-- Append-only audit trail of account/product actions (who, what, when). No payload content, no secrets, no financial values.
CREATE TABLE btl.audit_events (
 event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 occurred_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 actor_id uuid NOT NULL, workspace_id text,
 action text NOT NULL CHECK(action ~ '^[A-Z_]{3,48}$'),
 target text CHECK(target IS NULL OR length(target)<=200),
 outcome text NOT NULL CHECK(outcome IN ('OK','REFUSED'))
);
CREATE INDEX audit_events_actor ON btl.audit_events(actor_id,event_id DESC);
CREATE TRIGGER immutable_audit_events BEFORE UPDATE OR DELETE OR TRUNCATE ON btl.audit_events
 FOR EACH STATEMENT EXECUTE FUNCTION btl.deny_evidence_mutation();

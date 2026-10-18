-- Separate sandbox provider ledger. No test-event insertion or financial grants.
CREATE TABLE btl.sandbox_billing_orders (
 order_id text PRIMARY KEY CHECK(order_id ~ '^btl-sbx-[0-9a-f]{32}$'),
 actor_id uuid NOT NULL REFERENCES btl.users(id), request_id uuid NOT NULL,
 merchant_id text NOT NULL CHECK(length(merchant_id) BETWEEN 1 AND 64),
 plan_version text NOT NULL CHECK(length(plan_version) BETWEEN 1 AND 128),
 amount_idr bigint NOT NULL CHECK(amount_idr BETWEEN 1 AND 1000000000),
 duration_seconds bigint NOT NULL CHECK(duration_seconds BETWEEN 1 AND 31622400),
 phase text NOT NULL CHECK(phase IN ('CREATED','CHECKOUT_STARTED','PENDING','FAILED','PAID','REVERSED','HOLD')),
 transaction_id text UNIQUE CHECK(length(transaction_id) BETWEEN 1 AND 128),
 paid_at bigint, expires_at bigint, revision bigint NOT NULL CHECK(revision>=0),
 CHECK((paid_at IS NULL)=(expires_at IS NULL)),
 CHECK(paid_at IS NULL OR (paid_at>=0 AND expires_at=paid_at+duration_seconds AND transaction_id IS NOT NULL AND phase IN ('PAID','REVERSED','HOLD'))),
 CHECK(phase<>'PAID' OR paid_at IS NOT NULL),
 UNIQUE(actor_id,request_id)
);
CREATE INDEX sandbox_billing_active ON btl.sandbox_billing_orders(actor_id,expires_at) WHERE phase='PAID';
CREATE TABLE btl.sandbox_billing_events (
 order_id text NOT NULL REFERENCES btl.sandbox_billing_orders(order_id), revision bigint NOT NULL CHECK(revision>0),
 payload bytea NOT NULL CHECK(octet_length(payload)<=8192),
 content_hash text NOT NULL CHECK(content_hash ~ '^[0-9a-f]{64}$'),
 PRIMARY KEY(order_id,revision)
);
CREATE TRIGGER immutable_sandbox_billing_events BEFORE UPDATE OR DELETE OR TRUNCATE ON btl.sandbox_billing_events
 FOR EACH STATEMENT EXECUTE FUNCTION btl.deny_evidence_mutation();
CREATE TRIGGER no_remove_sandbox_billing_orders BEFORE DELETE OR TRUNCATE ON btl.sandbox_billing_orders
 FOR EACH STATEMENT EXECUTE FUNCTION btl.deny_evidence_mutation();
CREATE FUNCTION btl.guard_sandbox_billing_order() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF (NEW.order_id,NEW.actor_id,NEW.request_id,NEW.plan_version,NEW.amount_idr,NEW.duration_seconds,NEW.merchant_id) IS DISTINCT FROM
    (OLD.order_id,OLD.actor_id,OLD.request_id,OLD.plan_version,OLD.amount_idr,OLD.duration_seconds,OLD.merchant_id)
    OR NEW.revision<>OLD.revision+1
    OR (OLD.transaction_id IS NOT NULL AND NEW.transaction_id IS DISTINCT FROM OLD.transaction_id)
    OR (OLD.paid_at IS NOT NULL AND (NEW.paid_at,NEW.expires_at) IS DISTINCT FROM (OLD.paid_at,OLD.expires_at))
    OR OLD.phase='REVERSED' THEN
  RAISE EXCEPTION 'Billing identity/state refused' USING ERRCODE='23000';
 END IF;
 RETURN NEW;
END; $$;
CREATE TRIGGER guard_sandbox_billing_order BEFORE UPDATE ON btl.sandbox_billing_orders
 FOR EACH ROW EXECUTE FUNCTION btl.guard_sandbox_billing_order();

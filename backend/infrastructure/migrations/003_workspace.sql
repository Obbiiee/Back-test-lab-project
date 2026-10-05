CREATE TABLE btl.workspaces (
    id uuid PRIMARY KEY, owner_id uuid NOT NULL REFERENCES btl.users,
    name text NOT NULL CHECK (length(name) BETWEEN 1 AND 128)
);
CREATE TABLE btl.memberships (
    workspace_id uuid NOT NULL REFERENCES btl.workspaces,
    user_id uuid NOT NULL REFERENCES btl.users,
    role text NOT NULL CHECK (role IN ('OWNER','MEMBER')),
    PRIMARY KEY (workspace_id,user_id)
);
ALTER TABLE btl.workspaces ADD CONSTRAINT workspace_has_owner_membership
    FOREIGN KEY (id,owner_id) REFERENCES btl.memberships(workspace_id,user_id) DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX memberships_user ON btl.memberships(user_id,workspace_id);
CREATE TABLE btl.resources (
    id uuid PRIMARY KEY, workspace_id uuid NOT NULL REFERENCES btl.workspaces,
    creator_id uuid NOT NULL REFERENCES btl.users,
    kind text NOT NULL CHECK (kind IN ('BACKTEST','STRATEGY','DRAWING','INDICATOR','PREFERENCE','EXPERIMENT','REPORT','RESEARCH_JOB')),
    name text NOT NULL CHECK (length(name) BETWEEN 1 AND 128),
    revision bigint NOT NULL DEFAULT 0 CHECK (revision BETWEEN 0 AND 9007199254740991),
    archived boolean NOT NULL DEFAULT false,
    definition_hash text CHECK (definition_hash ~ '^[0-9a-f]{64}$'),
    UNIQUE(workspace_id,id)
);
CREATE INDEX resources_workspace ON btl.resources(workspace_id,id) WHERE NOT archived;
ALTER TABLE btl.security_events ADD COLUMN workspace_id uuid REFERENCES btl.workspaces;
ALTER TABLE btl.security_events ADD COLUMN resource_id uuid REFERENCES btl.resources;
CREATE FUNCTION btl.guard_membership() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE owner uuid;
BEGIN
    IF TG_OP = 'DELETE' THEN
        SELECT owner_id INTO owner FROM btl.workspaces WHERE id=OLD.workspace_id;
        IF OLD.user_id=owner THEN RAISE EXCEPTION 'Owner membership required' USING ERRCODE='23000'; END IF;
        RETURN OLD;
    END IF;
    SELECT owner_id INTO owner FROM btl.workspaces WHERE id=NEW.workspace_id;
    IF (NEW.role='OWNER') <> (NEW.user_id=owner) THEN
        RAISE EXCEPTION 'Owner identity mismatch' USING ERRCODE='23000';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER guard_membership BEFORE INSERT OR UPDATE OR DELETE ON btl.memberships
    FOR EACH ROW EXECUTE FUNCTION btl.guard_membership();
CREATE FUNCTION btl.guard_resource_identity() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF (NEW.id,NEW.workspace_id,NEW.creator_id,NEW.kind,NEW.definition_hash)
        IS DISTINCT FROM (OLD.id,OLD.workspace_id,OLD.creator_id,OLD.kind,OLD.definition_hash) THEN
        RAISE EXCEPTION 'Resource identity immutable' USING ERRCODE='23000';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER guard_resource_identity BEFORE UPDATE ON btl.resources
    FOR EACH ROW EXECUTE FUNCTION btl.guard_resource_identity();

-- PostgreSQL row locks require UPDATE permission on at least one column.
-- Runtime receives only immutable key-column permission, never owner/role edits.
CREATE FUNCTION btl.guard_workspace_identity() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF (NEW.id,NEW.owner_id) IS DISTINCT FROM (OLD.id,OLD.owner_id) THEN
        RAISE EXCEPTION 'Workspace identity immutable' USING ERRCODE='23000';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER guard_workspace_identity BEFORE UPDATE ON btl.workspaces
    FOR EACH ROW EXECUTE FUNCTION btl.guard_workspace_identity();
CREATE FUNCTION btl.guard_membership_identity() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF (NEW.workspace_id,NEW.user_id,NEW.role) IS DISTINCT FROM (OLD.workspace_id,OLD.user_id,OLD.role) THEN
        RAISE EXCEPTION 'Membership identity immutable' USING ERRCODE='23000';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER guard_membership_identity BEFORE UPDATE ON btl.memberships
    FOR EACH ROW EXECUTE FUNCTION btl.guard_membership_identity();

-- Product Method lifecycle metadata is separate from immutable financial Method
-- payloads and Session pins. Existing Methods become version 1 of their own
-- stable family; their IDs, bytes and hashes are not changed.
CREATE TABLE btl.product_method_families (
    workspace_id text NOT NULL,
    family_id text NOT NULL,
    revision bigint NOT NULL CHECK (revision BETWEEN 1 AND 9007199254740991),
    archived boolean NOT NULL DEFAULT false,
    latest_version integer NOT NULL CHECK (latest_version BETWEEN 1 AND 2147483647),
    latest_method_id text NOT NULL,
    PRIMARY KEY (workspace_id, family_id),
    FOREIGN KEY (workspace_id, latest_method_id)
        REFERENCES btl.tick_methods(workspace_id, method_id)
);

CREATE TABLE btl.product_method_versions (
    workspace_id text NOT NULL,
    family_id text NOT NULL,
    version integer NOT NULL CHECK (version BETWEEN 1 AND 2147483647),
    method_id text NOT NULL,
    PRIMARY KEY (workspace_id, family_id, version),
    UNIQUE (workspace_id, family_id, version, method_id),
    UNIQUE (workspace_id, method_id),
    FOREIGN KEY (workspace_id, family_id)
        REFERENCES btl.product_method_families(workspace_id, family_id),
    FOREIGN KEY (workspace_id, method_id)
        REFERENCES btl.tick_methods(workspace_id, method_id)
);

CREATE FUNCTION btl.deny_method_version_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'Method version identity is immutable' USING ERRCODE='23000';
END;
$$;
CREATE TRIGGER immutable_product_method_versions
    BEFORE UPDATE OR DELETE OR TRUNCATE ON btl.product_method_versions
    FOR EACH STATEMENT EXECUTE FUNCTION btl.deny_method_version_mutation();

CREATE FUNCTION btl.guard_product_method_family() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE version_method text;
BEGIN
    IF TG_OP <> 'UPDATE' THEN
        RAISE EXCEPTION 'Method family identity cannot be deleted' USING ERRCODE='23000';
    END IF;
    IF (NEW.workspace_id, NEW.family_id) IS DISTINCT FROM (OLD.workspace_id, OLD.family_id)
       OR NEW.revision <> OLD.revision + 1 THEN
        RAISE EXCEPTION 'Method family identity or revision conflict' USING ERRCODE='23000';
    END IF;
    IF NEW.latest_version = OLD.latest_version THEN
        IF NEW.latest_method_id IS DISTINCT FROM OLD.latest_method_id
           OR NEW.archived = OLD.archived THEN
            RAISE EXCEPTION 'Invalid Method lifecycle transition' USING ERRCODE='23000';
        END IF;
    ELSIF NEW.latest_version = OLD.latest_version + 1 THEN
        IF NEW.latest_method_id = OLD.latest_method_id OR NEW.archived IS DISTINCT FROM OLD.archived THEN
            RAISE EXCEPTION 'Invalid Method version transition' USING ERRCODE='23000';
        END IF;
        SELECT method_id INTO version_method FROM btl.product_method_versions
        WHERE workspace_id=NEW.workspace_id AND family_id=NEW.family_id AND version=NEW.latest_version;
        IF version_method IS DISTINCT FROM NEW.latest_method_id THEN
            RAISE EXCEPTION 'Method family pointer mismatch' USING ERRCODE='23000';
        END IF;
    ELSE
        RAISE EXCEPTION 'Method versions must advance one at a time' USING ERRCODE='23000';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER guard_product_method_family_update
    BEFORE UPDATE OR DELETE ON btl.product_method_families
    FOR EACH ROW EXECUTE FUNCTION btl.guard_product_method_family();
CREATE TRIGGER deny_product_method_family_truncate
    BEFORE TRUNCATE ON btl.product_method_families
    FOR EACH STATEMENT EXECUTE FUNCTION btl.deny_method_version_mutation();

-- Additive compatibility mapping: each existing immutable Method is the first
-- version of its own family until an owner explicitly creates a successor.
INSERT INTO btl.product_method_families
    (workspace_id, family_id, revision, archived, latest_version, latest_method_id)
SELECT workspace_id, method_id, 1, false, 1, method_id FROM btl.tick_methods;
INSERT INTO btl.product_method_versions (workspace_id, family_id, version, method_id)
SELECT workspace_id, method_id, 1, method_id FROM btl.tick_methods;
ALTER TABLE btl.product_method_families
    ADD CONSTRAINT product_method_family_latest_version_fk
    FOREIGN KEY (workspace_id, family_id, latest_version, latest_method_id)
    REFERENCES btl.product_method_versions(workspace_id, family_id, version, method_id)
    DEFERRABLE INITIALLY DEFERRED;

-- Issue #883 Phase 2 PR 4a
-- Install a PL/pgSQL function that clones the LIF schema structure + data
-- from public into a target tenant schema. Invoked by the MDR API's
-- POST /tenants/provision endpoint; eventually called from the Cognito
-- post-confirmation Lambda (PR 4b) to give each new registrant an isolated
-- workspace seeded with the current LIF data model.
--
-- Design notes:
--
-- - Uses CREATE TABLE ... LIKE ... INCLUDING ALL for DDL. This copies
--   defaults, CHECK constraints, NOT NULL, primary keys, unique keys,
--   indexes, statistics, storage params, identity columns — but NOT foreign
--   keys. We reapply FKs explicitly after every table is created so cross-
--   table references resolve against the target schema.
--
-- - ENUM types (AccessType, DataModelType, etc.) are NOT cloned per-tenant.
--   Every tenant table continues to reference public.typename via the fully
--   qualified column definitions that LIKE INCLUDING ALL preserves. This is
--   correct as long as public continues to exist — PR 3's cutover MOVES
--   data out of public but does not DROP the schema.
--
-- - Stored procedures/functions are NOT cloned. Public has one PROCEDURE
--   (deletedatamodelrecords) that hardcodes public.* references in its
--   body; cloning it would produce a tenant procedure that still deletes
--   from public. Left as a known limitation; callers that want a
--   per-tenant version will need to create it explicitly.
--
-- - Sequences are synced to the source's last_value so cloned data doesn't
--   collide with subsequent inserts.
--
-- - The function itself lives in public schema, deliberately: it needs
--   cross-schema visibility and is a service utility, not tenant data.

-- SECURITY DEFINER: the MDR API's DB role generally does not have CREATE
-- privilege on the database, while Flyway (the function owner) does.
-- Running as the definer lets the API call this function without us
-- having to broaden the API role's DDL privileges. The explicit search_path
-- pin closes the usual SECURITY DEFINER hijack vector (an attacker who
-- controls their own search_path can't redirect our unqualified names).
CREATE OR REPLACE FUNCTION public.clone_lif_schema(
    target_schema text,
    include_data boolean DEFAULT true
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    tbl_name text;
    seq_name text;
    seq_value bigint;
    fk_def text;
    fk_rec record;
BEGIN
    -- Defense in depth: API already sanitizes to tenant_{...}, but this
    -- function is callable directly via SQL so re-validate. The pattern
    -- matches the tenant_schema_for_group output shape exactly: must start
    -- with the tenant_ prefix, followed by a lowercase letter, then any
    -- mix of lowercase/digit/underscore. This is stricter than a generic
    -- PG identifier regex — it rejects e.g. clone_lif_schema('public_foo').
    IF target_schema !~ '^tenant_[a-z][a-z0-9_]*$' THEN
        RAISE EXCEPTION 'clone_lif_schema: target_schema must match tenant_[a-z][a-z0-9_]* (got %)', target_schema;
    END IF;
    IF length(target_schema) > 63 THEN
        RAISE EXCEPTION 'clone_lif_schema: target_schema exceeds PG''s 63-char identifier limit (%)', target_schema;
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.schemata WHERE schema_name = target_schema) THEN
        RAISE EXCEPTION 'clone_lif_schema: target schema % already exists', target_schema
            USING ERRCODE = 'duplicate_schema';
    END IF;

    EXECUTE format('CREATE SCHEMA %I', target_schema);

    -- Tables: copy structure (columns, defaults, PKs, indexes, NOT NULL,
    -- CHECK constraints, identity columns, storage). LIKE INCLUDING ALL
    -- omits foreign keys — those come next.
    FOR tbl_name IN
        SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename
    LOOP
        EXECUTE format(
            'CREATE TABLE %I.%I (LIKE public.%I INCLUDING ALL)',
            target_schema, tbl_name, tbl_name
        );
    END LOOP;

    -- Foreign keys: lift each FK constraint from public and reattach it to
    -- the equivalent target table. pg_get_constraintdef emits unqualified
    -- REFERENCES clauses for same-schema refs, which PG resolves via
    -- search_path at constraint-check time — but we explicitly qualify to
    -- target_schema to avoid ambiguity.
    FOR fk_rec IN
        SELECT
            src.relname AS source_table,
            con.conname AS constraint_name,
            pg_get_constraintdef(con.oid) AS definition
        FROM pg_constraint con
        JOIN pg_class src ON con.conrelid = src.oid
        JOIN pg_namespace ns ON src.relnamespace = ns.oid
        WHERE ns.nspname = 'public' AND con.contype = 'f'
    LOOP
        -- Rewrite bare REFERENCES to point at the target schema. Public
        -- refs appear as either REFERENCES "Table"(...) (no schema) or
        -- REFERENCES public."Table"(...) depending on PG version.
        fk_def := regexp_replace(
            fk_rec.definition,
            'REFERENCES (public\.)?',
            format('REFERENCES %I.', target_schema)
        );
        EXECUTE format(
            'ALTER TABLE %I.%I ADD CONSTRAINT %I %s',
            target_schema, fk_rec.source_table, fk_rec.constraint_name, fk_def
        );
    END LOOP;

    -- Data: copy every row from public.{t} into target.{t}. Done after FKs
    -- are in place so PK/FK/CHECK constraints are validated on the way in
    -- — if source data violates a constraint (it shouldn't), we want the
    -- clone to fail loudly rather than silently produce a tenant schema
    -- whose data doesn't match its own constraints.
    --
    -- Data clone is opt-in via `include_data`. The post-confirmation
    -- Lambda passes TRUE (tenants start with the current LIF model +
    -- demo rows); the one-time public → tenant_lif_team migration in PR 3
    -- will also pass TRUE. Callers that want a bare-structure clone
    -- (e.g., a future "reset to empty workspace") pass FALSE.
    IF include_data THEN
        FOR tbl_name IN
            SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename
        LOOP
            EXECUTE format(
                'INSERT INTO %I.%I SELECT * FROM public.%I',
                target_schema, tbl_name, tbl_name
            );
        END LOOP;
    END IF;

    -- Sequences: sync last_value so the next nextval() in the tenant
    -- schema starts after the copied data, not from 1. LIKE INCLUDING ALL
    -- creates per-tenant sequences (they're owned by identity columns in
    -- the cloned tables), so we just need to set their starting point.
    -- Only bother when we actually copied data; otherwise the tenant
    -- sequences are already at their defaults.
    IF include_data THEN
        FOR seq_name IN
            SELECT sequence_name FROM information_schema.sequences
            WHERE sequence_schema = target_schema
        LOOP
            EXECUTE format('SELECT last_value FROM public.%I', seq_name) INTO seq_value;
            EXECUTE format('SELECT setval(%L, %s, true)', target_schema || '.' || seq_name, seq_value);
        END LOOP;
    END IF;
END;
$$;

COMMENT ON FUNCTION public.clone_lif_schema(text, boolean) IS
    'Clones the LIF schema from public into the given target schema (DDL + FKs, plus data + sequences when include_data=true). Raises duplicate_schema if target exists. Called by POST /tenants/provision when a new user registers.';

-- Allow the MDR API role to invoke the function. PUBLIC is broader than
-- needed but matches how the existing deletedatamodelrecords procedure is
-- exposed; we can tighten to a named role later if RBAC is introduced.
GRANT EXECUTE ON FUNCTION public.clone_lif_schema(text, boolean) TO PUBLIC;

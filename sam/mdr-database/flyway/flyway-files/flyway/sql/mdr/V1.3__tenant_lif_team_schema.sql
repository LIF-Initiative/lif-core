-- Issue #883 Phase 2 PR 3: Cut over — provision tenant_lif_team schema.
--
-- This is the destination for the internal "lif-team" Cognito group (added
-- to the Cognito stack in this PR) and the default target for API-key
-- service callers once MDR__TENANT_ROUTING__ENABLED is flipped to true.
--
-- The clone copies every public row into tenant_lif_team, so the team's
-- workspace carries the full current demo data model. Public is left
-- intact: the feature flag can be flipped back to false for emergency
-- rollback, at which point traffic resumes hitting public directly. A
-- later cleanup migration may empty public's data tables once we're
-- confident in the cutover — not this PR.
--
-- Idempotent per the CLAUDE.md "MDR Schema Migrations (V1.2+)" convention:
-- safe to re-run after local `docker compose down -v` cycles.
--
-- 2026-05-26 patch: V1.4's corrected clone_lif_schema function definition
-- is folded in here as a prefix because Flyway runs migrations in version
-- order (V1.3 then V1.4). V1.2's original function had four bugs
-- (GENERATED ALWAYS / FK ordering / identity sequences / setval quoting)
-- that all surfaced on the first invocation against a fresh DB. Without
-- this prefix V1.3 raised "cannot insert a non-DEFAULT value into column
-- 'Id'" and rolled back, leaving tenant_lif_team uncreated. V1.4 still
-- runs after this migration and is now a no-op (CREATE OR REPLACE with
-- identical content). Long-term cleanup: collapse V1.2, V1.3, V1.4 into
-- a single corrected migration once we're confident the deployed envs
-- have caught up; tracked in a follow-up.

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
    -- CHECK constraints, identity columns, storage). FKs come after data
    -- so the per-row order of inserts doesn't matter.
    FOR tbl_name IN
        SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename
    LOOP
        EXECUTE format(
            'CREATE TABLE %I.%I (LIKE public.%I INCLUDING ALL)',
            target_schema, tbl_name, tbl_name
        );
    END LOOP;

    -- Data: copy every row before FKs exist. OVERRIDING SYSTEM VALUE is
    -- required for the GENERATED ALWAYS "Id" columns; we deliberately
    -- preserve source Ids so cross-table refs stay intact in the clone.
    IF include_data THEN
        FOR tbl_name IN
            SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename
        LOOP
            EXECUTE format(
                'INSERT INTO %I.%I OVERRIDING SYSTEM VALUE SELECT * FROM public.%I',
                target_schema, tbl_name, tbl_name
            );
        END LOOP;
    END IF;

    -- FKs: lift each constraint from public and reattach to the equivalent
    -- target table. ADD CONSTRAINT FOREIGN KEY validates every existing row
    -- in one shot, so if source data violates referential integrity the
    -- clone still fails loudly here rather than silently producing a tenant
    -- whose data doesn't match its own constraints.
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

    -- Sequences: sync last_value so the next nextval() in the tenant schema
    -- starts after the copied data, not from 1. Only relevant when data
    -- was copied; otherwise the per-tenant sequences are at their defaults.
    IF include_data THEN
        FOR seq_name IN
            SELECT sequencename FROM pg_sequences WHERE schemaname = target_schema
        LOOP
            EXECUTE format('SELECT last_value FROM public.%I', seq_name) INTO seq_value;
            -- setval() takes the regclass name as a text literal; PG folds
            -- unquoted identifiers to lowercase, so the LIF mixed-case
            -- sequences (e.g. Entities_Id_seq) need the %I.%I double-quoting.
            EXECUTE format('SELECT setval(%L, %s, true)', format('%I.%I', target_schema, seq_name), seq_value);
        END LOOP;
    END IF;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'tenant_lif_team') THEN
        PERFORM public.clone_lif_schema('tenant_lif_team', TRUE);
    END IF;
END
$$;

-- Issue #883 Phase 2 follow-up: fix four bugs in clone_lif_schema (V1.2).
--
-- 1. GENERATED ALWAYS identity columns
--    Every LIF "Id" column is GENERATED ALWAYS AS IDENTITY (V1.1 baseline).
--    LIKE INCLUDING ALL propagates that to the clone, so INSERT ... SELECT *
--    must include OVERRIDING SYSTEM VALUE; without it Postgres raises
--    GeneratedAlways and the whole call rolls back.
--
-- 2. FK ordering during data copy
--    V1.2 created FK constraints before copying data, then iterated tables
--    alphabetically. "Attributes" was loaded before "DataModels", and
--    Attribute rows reference DataModelId values that didn't exist yet, so
--    the copy raised ForeignKeyViolation on the first table.
--
--    Fix: reorder to DDL -> data -> FKs. ADD CONSTRAINT FOREIGN KEY validates
--    all rows in one shot after the copy, which still fails loudly if source
--    data violates referential integrity, just at the right moment.
--
-- 3. Identity sequences invisible to information_schema.sequences
--    Sequences owned by GENERATED ALWAYS columns don't appear in the
--    SQL-standard view (they're attached to a column, not user-created).
--    V1.2's seq-sync loop iterated information_schema.sequences and got
--    zero rows, so target sequences were left at last_value=1. The next
--    insert into a cloned table tried to reuse Id=1 and hit a UniqueViolation.
--
--    Fix: iterate pg_sequences (PG-specific, includes identity-owned sequences).
--
-- 4. setval() target identifier was not double-quoted
--    The mixed-case sequence names (e.g. Entities_Id_seq) were passed to
--    setval() as bare schema.name strings via concatenation, which Postgres
--    folds to lowercase before regclass resolution -- so it looked for
--    entities_id_seq and raised UndefinedTable. Fix: build the regclass
--    argument with format('%I.%I', ...) so each identifier is quoted.
--
-- All four would surface on the first invocation against any fresh DB:
-- V1.3's tenant_lif_team cutover, the Cognito post-confirmation Lambda's
-- POST /tenants/provision call, or a local docker compose down -v && up.
-- The function never ran successfully against real data, so this fix is
-- purely a forward correction; no existing tenant schemas need rebuilding.
--
-- Re-defines the function via CREATE OR REPLACE; same signature. Idempotent.

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

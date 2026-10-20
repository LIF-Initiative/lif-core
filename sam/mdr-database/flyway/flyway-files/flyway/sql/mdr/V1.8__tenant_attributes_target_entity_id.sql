-- Issue #1386 follow-up: V1.6's Attributes.TargetEntityId in every tenant schema.
--
-- V1.6 added the column, its FK and its index to public only. Migrations reach only public unless
-- they loop over the tenant schemas (#1265), so a tenant schema that already existed never got them.
-- Locally that is tenant_lif_team, which backup.sql carries, and every MDR query on its Attributes
-- fails on the missing column. Tenants cloned after V1.6 are already complete: clone_lif_schema copies
-- public's columns and indexes with LIKE ... INCLUDING ALL, and re-creates its FKs against the tenant.
--
-- On dev and demo this is a no-op: every tenant schema there was fixed by hand on 2026-09-24.
--
-- Not backfilled, as in that fix: V1.6's values are public's Open Badges v3 targets, and a tenant's
-- rows are its own copy that may have diverged, so there is nothing to copy without guessing.
--
-- The FK guard looks the constraint up on this schema's table. V1.6's guard matches the name across
-- the whole database, so run per tenant it would find public's constraint and skip the tenant's FK.
-- The FK points at the tenant's own Entities.
--
-- Idempotent per the CLAUDE.md "MDR migrations (V1.2+)" convention: local docker-compose replays
-- every V1.*.sql through psql with no Flyway history.

DO $$
DECLARE
    s text;
BEGIN
    FOR s IN
        SELECT nspname FROM pg_namespace WHERE nspname = 'public' OR nspname ~ '^tenant_' ORDER BY nspname
    LOOP
        EXECUTE format('ALTER TABLE %I."Attributes" ADD COLUMN IF NOT EXISTS "TargetEntityId" bigint', s);

        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'Fk_Attributes_TargetEntityId'
              AND conrelid = format('%I."Attributes"', s)::regclass
        ) THEN
            EXECUTE format(
                'ALTER TABLE %1$I."Attributes" ADD CONSTRAINT "Fk_Attributes_TargetEntityId" '
                'FOREIGN KEY ("TargetEntityId") REFERENCES %1$I."Entities"("Id") ON DELETE SET NULL',
                s
            );
        END IF;

        EXECUTE format(
            'CREATE INDEX IF NOT EXISTS "ix_Attributes_TargetEntityId" ON %I."Attributes" ("TargetEntityId")',
            s
        );

        EXECUTE format(
            'COMMENT ON COLUMN %I."Attributes"."TargetEntityId" IS %L',
            s,
            'For DataType = ''entity'', the Entities.Id this attribute refers to. Null means the '
            'target has not been recorded. Do not infer the binding from attribute or entity names.'
        );
    END LOOP;
END $$;

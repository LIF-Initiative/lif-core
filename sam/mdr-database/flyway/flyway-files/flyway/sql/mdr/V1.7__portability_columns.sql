-- Issue #1386: columns the portable file format needs (docs/specs/mdr-portable-file-format.md).
-- cspell:ignore accesstype
--
--   Entities, Attributes             LevelOfAccess, Queryable, Modifiable (spec §5.3). Today these
--                                    flags exist only on ExtInclusionsFromBaseDM rows.
--   EntityAssociation,               Name: the key the child appears under in its parent, and
--   EntityAttributeAssociation       Array: whether the child is a list under this parent (§5.4, Q7).
--   DataModels                       CopiedFromName, CopiedFromVersion, CopiedFromContributorOrganization:
--                                    lineage (§5.2). Plain text with no FK, because the model a copy
--                                    came from need not be installed. Not backfilled: no model is a copy
--                                    until #1388 converts the overlays.
--
-- The backfill follows the spec's §11 "Migration defaults", which reproduce what the schema
-- generator emits today (components/lif/mdr_services/schema_generation_service.py):
--
--   Flags   From the live inclusion row a model holds on its own element; otherwise Public / false /
--           false. Rows on another model's elements (only models 17 and 18) are left to #1388.
--   Name    Entity child, Reference placement: 'Ref' + child Name, or Relationship + 'Ref' + child Name
--           (add_ref's key). Otherwise embedded_property_key: the bare child Name, or Relationship +
--           child Name. A NULL Relationship, or one starting with 'has' or 'relevant', gives the bare
--           form. Attribute child: the attribute's Name. Case is kept as stored (§5.4: migrated names
--           keep today's keys).
--   Array   The child's Array = 'Yes'.
--
-- Name and Array have no default: NULL means "not computed yet", so a later backfill can find rows
-- that were created by an MDR image that does not write them yet. The flags default to the
-- migration default, so rows created by such an image still get the value today's output implies.
--
-- No unique index on (parent, Name): flattening model 17 creates two collisions that #1388 resolves.
--
-- Migrations reach only public unless they loop over the tenant schemas (#1265), so every step runs
-- in public and in every tenant_* schema. New tenants get the columns from clone_lif_schema, which
-- copies public's tables with LIKE ... INCLUDING ALL.
--
-- Idempotent per the CLAUDE.md "MDR migrations (V1.2+)" convention: local docker-compose replays
-- every V1.*.sql through psql with no Flyway history. Columns are added without a default and
-- backfilled WHERE ... IS NULL before the defaults are set, because ADD COLUMN ... DEFAULT would
-- fill every existing row at once and hide them from the backfill. A replay finds no NULLs.

DO $$
DECLARE
    s text;
BEGIN
    FOR s IN
        SELECT nspname FROM pg_namespace WHERE nspname = 'public' OR nspname ~ '^tenant_' ORDER BY nspname
    LOOP
        -- 1. Columns, nullable and without defaults.
        EXECUTE format(
            'ALTER TABLE %1$I."Entities"
                 ADD COLUMN IF NOT EXISTS "LevelOfAccess" public.accesstype,
                 ADD COLUMN IF NOT EXISTS "Queryable" boolean,
                 ADD COLUMN IF NOT EXISTS "Modifiable" boolean;
             ALTER TABLE %1$I."Attributes"
                 ADD COLUMN IF NOT EXISTS "LevelOfAccess" public.accesstype,
                 ADD COLUMN IF NOT EXISTS "Queryable" boolean,
                 ADD COLUMN IF NOT EXISTS "Modifiable" boolean;
             ALTER TABLE %1$I."EntityAssociation"
                 ADD COLUMN IF NOT EXISTS "Name" varchar,
                 ADD COLUMN IF NOT EXISTS "Array" boolean;
             ALTER TABLE %1$I."EntityAttributeAssociation"
                 ADD COLUMN IF NOT EXISTS "Name" varchar,
                 ADD COLUMN IF NOT EXISTS "Array" boolean;
             ALTER TABLE %1$I."DataModels"
                 ADD COLUMN IF NOT EXISTS "CopiedFromName" varchar,
                 ADD COLUMN IF NOT EXISTS "CopiedFromVersion" varchar,
                 ADD COLUMN IF NOT EXISTS "CopiedFromContributorOrganization" varchar;',
            s
        );

        -- 2a. Flags from the model's own live inclusion row. If an element ever has more than one,
        --     the most recent (highest Id) wins, so the result does not depend on row order.
        EXECUTE format(
            'UPDATE %1$I."Entities" e
                SET "LevelOfAccess" = i."LevelOfAccess", "Queryable" = i."Queryable", "Modifiable" = i."Modifiable"
               FROM (SELECT DISTINCT ON ("IncludedElementId", "ExtDataModelId")
                            "IncludedElementId", "ExtDataModelId", "LevelOfAccess", "Queryable", "Modifiable"
                       FROM %1$I."ExtInclusionsFromBaseDM"
                      WHERE "ElementType" = ''Entity'' AND NOT coalesce("Deleted", false)
                      ORDER BY "IncludedElementId", "ExtDataModelId", "Id" DESC) i
              WHERE i."IncludedElementId" = e."Id" AND i."ExtDataModelId" = e."DataModelId"
                AND e."LevelOfAccess" IS NULL;
             UPDATE %1$I."Attributes" a
                SET "LevelOfAccess" = i."LevelOfAccess", "Queryable" = i."Queryable", "Modifiable" = i."Modifiable"
               FROM (SELECT DISTINCT ON ("IncludedElementId", "ExtDataModelId")
                            "IncludedElementId", "ExtDataModelId", "LevelOfAccess", "Queryable", "Modifiable"
                       FROM %1$I."ExtInclusionsFromBaseDM"
                      WHERE "ElementType" = ''Attribute'' AND NOT coalesce("Deleted", false)
                      ORDER BY "IncludedElementId", "ExtDataModelId", "Id" DESC) i
              WHERE i."IncludedElementId" = a."Id" AND i."ExtDataModelId" = a."DataModelId"
                AND a."LevelOfAccess" IS NULL;',
            s
        );

        -- 2b. Every other element gets the migration default.
        EXECUTE format(
            'UPDATE %1$I."Entities"
                SET "LevelOfAccess" = ''Public'', "Queryable" = false, "Modifiable" = false
              WHERE "LevelOfAccess" IS NULL;
             UPDATE %1$I."Attributes"
                SET "LevelOfAccess" = ''Public'', "Queryable" = false, "Modifiable" = false
              WHERE "LevelOfAccess" IS NULL;',
            s
        );

        -- 3. Association Name and Array.
        EXECUTE format(
            'UPDATE %1$I."EntityAssociation" ea
                SET "Name" = CASE
                        WHEN ea."Placement" = ''Reference'' THEN
                            CASE WHEN ea."Relationship" IS NULL
                                      OR ea."Relationship" LIKE ''has%%''
                                      OR ea."Relationship" LIKE ''relevant%%''
                                 THEN ''Ref'' || c."Name"
                                 ELSE ea."Relationship" || ''Ref'' || c."Name" END
                        ELSE
                            CASE WHEN ea."Relationship" IS NULL
                                      OR ea."Relationship" LIKE ''has%%''
                                      OR ea."Relationship" LIKE ''relevant%%''
                                 THEN c."Name"
                                 ELSE ea."Relationship" || c."Name" END
                    END,
                    "Array" = coalesce(c."Array" = ''Yes'', false)
               FROM %1$I."Entities" c
              WHERE c."Id" = ea."ChildEntityId" AND ea."Name" IS NULL;
             UPDATE %1$I."EntityAttributeAssociation" x
                SET "Name" = a."Name",
                    "Array" = coalesce(a."Array" = ''Yes'', false)
               FROM %1$I."Attributes" a
              WHERE a."Id" = x."AttributeId" AND x."Name" IS NULL;',
            s
        );

        -- 4. Flag defaults, set only after the backfill (see the header).
        EXECUTE format(
            'ALTER TABLE %1$I."Entities"
                 ALTER COLUMN "LevelOfAccess" SET DEFAULT ''Public'',
                 ALTER COLUMN "Queryable" SET DEFAULT false,
                 ALTER COLUMN "Modifiable" SET DEFAULT false;
             ALTER TABLE %1$I."Attributes"
                 ALTER COLUMN "LevelOfAccess" SET DEFAULT ''Public'',
                 ALTER COLUMN "Queryable" SET DEFAULT false,
                 ALTER COLUMN "Modifiable" SET DEFAULT false;',
            s
        );
    END LOOP;
END $$;

-- Issue #1395: copy element flags from inclusion rows once more, just before the generator reads them.
--
-- V1.7 copied LevelOfAccess, Queryable and Modifiable onto Entities and Attributes from the live
-- inclusion row a model holds on its own element. Nothing keeps the two in step since: MDR still
-- edits inclusion rows, and ADR data_model/0004 is retiring them, so they get no sync code (#1386).
-- The schema generator starts reading the element flags with #1395, so this re-copies them from the
-- inclusion rows (V1.7's step 2a without its IS NULL guard). Apply it after the MDR image that reads
-- the element flags is deployed, so inclusion edits made before the deploy are carried over.
--
-- Same source rows as V1.7: a model's live inclusion row on its own element, the most recent (highest
-- Id) when there is more than one. Elements without one keep their flags. Rows on another model's
-- elements (only models 17 and 18) are left to #1388. Looped over public and every tenant_* schema
-- (#1265).
--
-- Idempotent per the CLAUDE.md "MDR migrations (V1.2+)" convention: only rows that differ from their
-- inclusion row are updated, so a replay changes nothing. No DDL.

DO $$
DECLARE
    s text;
BEGIN
    FOR s IN
        SELECT nspname FROM pg_namespace WHERE nspname = 'public' OR nspname ~ '^tenant_' ORDER BY nspname
    LOOP
        EXECUTE format(
            'UPDATE %1$I."Entities" e
                SET "LevelOfAccess" = i."LevelOfAccess", "Queryable" = i."Queryable", "Modifiable" = i."Modifiable"
               FROM (SELECT DISTINCT ON ("IncludedElementId", "ExtDataModelId")
                            "IncludedElementId", "ExtDataModelId", "LevelOfAccess", "Queryable", "Modifiable"
                       FROM %1$I."ExtInclusionsFromBaseDM"
                      WHERE "ElementType" = ''Entity'' AND NOT coalesce("Deleted", false)
                      ORDER BY "IncludedElementId", "ExtDataModelId", "Id" DESC) i
              WHERE i."IncludedElementId" = e."Id" AND i."ExtDataModelId" = e."DataModelId"
                AND (e."LevelOfAccess", e."Queryable", e."Modifiable")
                    IS DISTINCT FROM (i."LevelOfAccess", i."Queryable", i."Modifiable");
             UPDATE %1$I."Attributes" a
                SET "LevelOfAccess" = i."LevelOfAccess", "Queryable" = i."Queryable", "Modifiable" = i."Modifiable"
               FROM (SELECT DISTINCT ON ("IncludedElementId", "ExtDataModelId")
                            "IncludedElementId", "ExtDataModelId", "LevelOfAccess", "Queryable", "Modifiable"
                       FROM %1$I."ExtInclusionsFromBaseDM"
                      WHERE "ElementType" = ''Attribute'' AND NOT coalesce("Deleted", false)
                      ORDER BY "IncludedElementId", "ExtDataModelId", "Id" DESC) i
              WHERE i."IncludedElementId" = a."Id" AND i."ExtDataModelId" = a."DataModelId"
                AND (a."LevelOfAccess", a."Queryable", a."Modifiable")
                    IS DISTINCT FROM (i."LevelOfAccess", i."Queryable", i."Modifiable");',
            s
        );
    END LOOP;
END $$;

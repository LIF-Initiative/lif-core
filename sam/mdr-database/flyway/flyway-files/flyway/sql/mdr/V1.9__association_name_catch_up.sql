-- Issue #1386: fill association Name/Array on rows created between V1.7's apply and PR B's deploy.
--
-- V1.7 backfilled EntityAssociation.Name / EntityAttributeAssociation.Name and their Array columns,
-- but the MDR image that was running when V1.7 was applied does not write them, so every association
-- it creates has a NULL Name and Array. PR B's image computes them on create
-- (components/lif/mdr_services/association_name.py). Apply this migration after PR B is deployed in
-- an environment: rows created before that are filled here, and rows created after it are already
-- filled by the image. Applied before the deploy, it misses rows created in between, and Flyway
-- won't run it again.
--
-- This is V1.7's step 3 verbatim (same Name and Array rules, same WHERE "Name" IS NULL), looped over
-- public and every tenant_* schema (#1265). Only NULL Names are filled. A non-NULL Name either came
-- from the rule or was set on purpose (a model import writes it from the file, #1388 resolves
-- collisions), and local docker-compose replays this file over backup.sql, so it must not overwrite
-- one. Rows made stale by an old-image rename or Array change keep their stale value.
--
-- Idempotent per the CLAUDE.md "MDR migrations (V1.2+)" convention: a replay finds no NULLs. No DDL.

DO $$
DECLARE
    s text;
BEGIN
    FOR s IN
        SELECT nspname FROM pg_namespace WHERE nspname = 'public' OR nspname ~ '^tenant_' ORDER BY nspname
    LOOP
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
    END LOOP;
END $$;

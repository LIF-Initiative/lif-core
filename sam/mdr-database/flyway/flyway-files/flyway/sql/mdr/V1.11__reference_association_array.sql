-- Issue #1471: a Reference association is single unless it is set otherwise.
--
-- V1.7 (and V1.9, for rows it caught up) set every association's Array from its child entity's Array,
-- Reference associations included. The schema generator emits a Reference child as a single object
-- and ignores that Array, but the portable export writes it, so a file says a reference is a list
-- that the schema says isn't. #1471 decided that a Reference association can be a list, but only when
-- someone sets it that way; the values V1.7 copied onto references were no such decision. MDR's
-- create and edit paths now give a Reference association Array false
-- (lif.mdr_services.association_name.entity_association_array).
--
-- This resets V1.7's copies: a Reference association with Array true whose child entity's Array is
-- 'Yes', the value V1.7's rule gives. A reference stored true with a child that isn't a list was set
-- some other way (CTDL's, generated from its vocabulary; a model import's, from its file) and is
-- left as is. Deleted rows are reset too, so a restored row carries the current rule. Looped over
-- public and every tenant_* schema (#1265).
--
-- Idempotent per the CLAUDE.md "MDR migrations (V1.2+)" convention: a replay finds no rows. A
-- reference later set to a list on purpose, to a child that is also a list, looks the same as V1.7's
-- copy and a local replay would reset it; until #1472 adds a way to set one, the only such rows come
-- from importing a file. No DDL.

DO $$
DECLARE
    s text;
BEGIN
    FOR s IN
        SELECT nspname FROM pg_namespace WHERE nspname = 'public' OR nspname ~ '^tenant_' ORDER BY nspname
    LOOP
        EXECUTE format(
            'UPDATE %1$I."EntityAssociation" ea
                SET "Array" = false
               FROM %1$I."Entities" c
              WHERE c."Id" = ea."ChildEntityId"
                AND ea."Placement" = ''Reference''
                AND ea."Array" IS TRUE
                AND c."Array" = ''Yes'';',
            s
        );
    END LOOP;
END $$;

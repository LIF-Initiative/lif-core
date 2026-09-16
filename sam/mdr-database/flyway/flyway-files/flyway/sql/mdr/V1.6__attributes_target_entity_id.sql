-- Issue: record which entity an entity-typed attribute points at.
--
-- Attributes.DataType = 'entity' says an attribute refers to another entity but never
-- says which one. Nothing in the schema or the exporter records or infers the binding:
-- the attribute is emitted as a leaf keyed by its own name, and the target entity is
-- emitted separately by find_children / add_ref keyed by the entity name. Where the two
-- names happen to look alike (image -> Image) a human reads a connection that the data
-- does not contain; where they do not (Profile.parentOrg -> Profile) there is nothing to
-- read at all.
--
-- This column is the place to record it. It is nullable because the target is unknown for
-- most existing rows -- that information was never captured and cannot be recovered
-- automatically without guessing. Backfilled here only for Open Badges v3, whose targets
-- are recoverable from the published 1EdTech JSON Schema.
--
-- Idempotent per the CLAUDE.md "MDR migrations (V1.2+)" convention: local docker-compose
-- replays every V1.*.sql through psql with no Flyway history.

ALTER TABLE public."Attributes"
  ADD COLUMN IF NOT EXISTS "TargetEntityId" bigint;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'Fk_Attributes_TargetEntityId'
  ) THEN
    ALTER TABLE public."Attributes"
      ADD CONSTRAINT "Fk_Attributes_TargetEntityId"
      FOREIGN KEY ("TargetEntityId") REFERENCES public."Entities"("Id") ON DELETE SET NULL;
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS "ix_Attributes_TargetEntityId"
  ON public."Attributes" ("TargetEntityId");

COMMENT ON COLUMN public."Attributes"."TargetEntityId" IS
  'For DataType = ''entity'', the Entities.Id this attribute refers to. Null means the '
  'target has not been recorded. Do not infer the binding from attribute or entity names.';

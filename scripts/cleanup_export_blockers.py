#!/usr/bin/env python3
"""One-time cleanup of the data that keeps models and mapping groups from exporting (#1393), through asyncpg.

Applies the cleanup rules decided on #1393, in `public` and then every `tenant_*` schema with a
DataModels table, in this order:

    unassociated      soft-delete a live attribute that is in no live association (§11: dropped on
                      migration). One that a live mapping row or a live inclusion row still uses
                      is skipped and listed.
    no_data_type      set DataType to 'string' where it is NULL (§11), after the deletes above. One
                      with a TargetEntityId is left: under §11 it becomes an association to the
                      entity, not a string
    group_name        set a blank group Name to '<source model Name>_<target model Name>', the
                      pattern every named group follows. Blank means what the exporter's
                      str.strip() leaves empty. Only when both models are live and not overlays,
                      and neither model's Name is blank
    model_26_org      set model 26 (R1 Demo Source Data Model) ContributorOrganization to 'LIF'
    transformation_1189
                      soft-delete transformation 1189 in group 3: no expression, no source, no target
    value_3649_extension
                      clear Extension on value 3649 (Kindergarten, model 1): a stray flag with no
                      notes, which its twin in model 4 and every other Kindergarten value don't have
    transformation_1761
                      soft-delete transformation 1761 in group 3, and its mapping rows: a copy of
                      1760, so two mappings write one target. Only while it still matches 1760 in
                      every column but Id, Deleted and CreationDate, and its mapping rows map the
                      same attributes at the same paths. The rows' own metadata (Notes,
                      Contributor, dates, Extension) is not compared: on dev, 1761's target row
                      carries placeholder values 1760's doesn't. The rule prints what it drops
    transformations_through_deleted
                      soft-delete transformations 1590-1595 (group 28) and 1600 (group 29), and their
                      mapping rows: mappings into overlay 17 whose paths go through entity 391 or
                      attribute 1961, both soft-deleted, so #1388's conversion would refuse on them
                      (decided on #1388). Only while one of the transformation's live mapping rows
                      still goes through a soft-deleted entity or attribute. Prints what it drops

Overlay models (a BaseDataModelId, or live inclusion rows) are left alone in every rule but the
last, which clears #1388's way: converting them is #1388's. The ExtendedBy, cross-model and ownerless associations export also refuses are
#1388's too, and are not touched.

One transaction for every schema. Each rule prints the Ids it changed, with the old value where
it overwrote one, which is what an undo restores. ROLLBACK unless --apply. Re-running it changes
nothing, since every rule only matches rows it hasn't fixed. Run measure_export_blockers.py before
and after for the counts.

Usage:
    POSTGRESQL_HOST=... POSTGRESQL_USER=... POSTGRESQL_PASSWORD=... POSTGRESQL_DB=... \\
        python3 cleanup_export_blockers.py [--apply]

POSTGRESQL_PORT defaults to 5432. These are the names the MDR API's own env uses.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import os
import sys

import asyncpg

SCHEMAS_SQL = r"""
SELECT table_schema FROM information_schema.tables
WHERE table_name = 'DataModels'
  AND (table_schema = 'public' OR table_schema LIKE 'tenant\_%')
ORDER BY table_schema <> 'public', table_schema
"""

# The models a rule may change: live, and not overlays (model_converter.is_overlay).
_OWN_MODELS = """
SELECT m."Id" FROM {schema}."DataModels" m
WHERE m."Deleted" IS NOT TRUE
  AND m."BaseDataModelId" IS NULL
  AND NOT EXISTS (
      SELECT 1 FROM {schema}."ExtInclusionsFromBaseDM" i WHERE i."ExtDataModelId" = m."Id" AND i."Deleted" = false
  )
"""

# A live attribute in no live association to a live entity, as the converter reads them.
_UNASSOCIATED = (
    """
SELECT a."Id", a."DataModelId" FROM {schema}."Attributes" a
WHERE a."Deleted" = false
  AND a."DataModelId" IN ("""
    + _OWN_MODELS
    + """)
  AND NOT EXISTS (
      SELECT 1 FROM {schema}."EntityAttributeAssociation" x
      JOIN {schema}."Entities" e ON e."Id" = x."EntityId" AND e."Deleted" = false
      WHERE x."AttributeId" = a."Id" AND x."Deleted" = false
  )
"""
)

# Still in use, so the first rule keeps it: a live mapping row maps it, or an overlay includes it.
_IN_USE = """
(EXISTS (
    SELECT 1 FROM {schema}."TransformationAttributes" ta
    WHERE ta."AttributeId" = u."Id" AND ta."Deleted" = false
) OR EXISTS (
    SELECT 1 FROM {schema}."ExtInclusionsFromBaseDM" i
    WHERE i."ElementType" = 'Attribute' AND i."IncludedElementId" = u."Id" AND i."Deleted" = false
))
"""

# The characters str.strip() strips, as regex escapes for a bracket expression. The exporter
# refuses a group when `not (group.Name or "").strip()` (mapping_group_converter.py).
_PY_WHITESPACE = "".join(f"\\u{ord(c):04x}" for c in map(chr, range(0x110000)) if c.isspace())

# (rule, SQL). Each statement returns one row per changed row.
RULES: list[tuple[str, str]] = [
    (
        "unassociated",
        """
WITH unassociated AS ("""
        + _UNASSOCIATED
        + """)
UPDATE {schema}."Attributes" a SET "Deleted" = true
FROM unassociated u
WHERE a."Id" = u."Id" AND NOT """
        + _IN_USE
        + """
RETURNING a."Id", a."DataModelId"
""",
    ),
    (
        "no_data_type",
        """
UPDATE {schema}."Attributes" a SET "DataType" = 'string'
WHERE a."Deleted" = false AND a."DataType" IS NULL AND a."TargetEntityId" IS NULL
  AND a."DataModelId" IN ("""
        + _OWN_MODELS
        + """)
RETURNING a."Id", a."DataModelId"
""",
    ),
    (
        "group_name",
        """
WITH blank AS (
    SELECT g."Id", g."Name" AS old_name, s."Name" || '_' || t."Name" AS new_name
    FROM {schema}."TransformationsGroup" g
    JOIN {schema}."DataModels" s ON s."Id" = g."SourceDataModelId"
    JOIN {schema}."DataModels" t ON t."Id" = g."TargetDataModelId"
    WHERE g."Deleted" IS NOT TRUE
      AND g."Name" ~ '^["""
        + _PY_WHITESPACE
        + """]*$'
      AND coalesce(s."Name", '') !~ '^["""
        + _PY_WHITESPACE
        + """]*$'
      AND coalesce(t."Name", '') !~ '^["""
        + _PY_WHITESPACE
        + """]*$'
      AND s."Id" IN ("""
        + _OWN_MODELS
        + """)
      AND t."Id" IN ("""
        + _OWN_MODELS
        + """)
)
UPDATE {schema}."TransformationsGroup" g SET "Name" = blank.new_name
FROM blank
WHERE g."Id" = blank."Id"
RETURNING g."Id", blank.old_name, g."Name"
""",
    ),
    (
        "model_26_org",
        """
WITH target AS (
    SELECT "Id", "ContributorOrganization" AS old_org FROM {schema}."DataModels"
    WHERE "Id" = 26 AND "Name" = 'R1 Demo Source Data Model' AND "Deleted" IS NOT TRUE
      AND trim(coalesce("ContributorOrganization", '')) = ''
)
UPDATE {schema}."DataModels" m SET "ContributorOrganization" = 'LIF'
FROM target
WHERE m."Id" = target."Id"
RETURNING m."Id", target.old_org
""",
    ),
    (
        "transformation_1189",
        """
UPDATE {schema}."Transformations" t SET "Deleted" = true
WHERE t."Id" = 1189 AND t."TransformationGroupId" = 3 AND t."Deleted" = false
  AND trim(coalesce(t."Expression", '')) = ''
  AND NOT EXISTS (
      SELECT 1 FROM {schema}."TransformationAttributes" ta WHERE ta."TransformationId" = t."Id" AND ta."Deleted" = false
  )
RETURNING t."Id", t."TransformationGroupId"
""",
    ),
    (
        "value_3649_extension",
        """
UPDATE {schema}."ValueSetValues" v SET "Extension" = false
WHERE v."Id" = 3649 AND v."ValueSetId" = 290 AND v."DataModelId" = 1 AND v."Value" = 'Kindergarten'
  AND v."Deleted" IS NOT TRUE AND v."Extension" = true
  AND trim(coalesce(v."ExtensionNotes", '')) = ''
RETURNING v."Id", v."ValueSetId"
""",
    ),
    (
        "transformation_1761",
        """
WITH copy AS (
    SELECT t."Id" FROM {schema}."Transformations" t
    JOIN {schema}."Transformations" o ON o."Id" = 1760 AND o."TransformationGroupId" = 3 AND o."Deleted" = false
    WHERE t."Id" = 1761 AND t."TransformationGroupId" = 3 AND t."Deleted" = false
      AND to_jsonb(t) - '{{Id,Deleted,CreationDate}}'::text[] = to_jsonb(o) - '{{Id,Deleted,CreationDate}}'::text[]
      AND ARRAY(
          SELECT ROW(ta."AttributeType"::text, ta."AttributeId", ta."EntityId", ta."EntityIdPath")::text
          FROM {schema}."TransformationAttributes" ta WHERE ta."TransformationId" = t."Id" AND ta."Deleted" = false ORDER BY 1
      ) = ARRAY(
          SELECT ROW(ta."AttributeType"::text, ta."AttributeId", ta."EntityId", ta."EntityIdPath")::text
          FROM {schema}."TransformationAttributes" ta WHERE ta."TransformationId" = o."Id" AND ta."Deleted" = false ORDER BY 1
      )
),
rows AS (
    UPDATE {schema}."TransformationAttributes" ta SET "Deleted" = true
    FROM copy WHERE ta."TransformationId" = copy."Id" AND ta."Deleted" = false
    RETURNING ta."Id", jsonb_strip_nulls(jsonb_build_object(
        'Notes', ta."Notes", 'Contributor', ta."Contributor", 'ContributorOrganization', ta."ContributorOrganization",
        'ActivationDate', ta."ActivationDate", 'DeprecationDate', ta."DeprecationDate",
        'Extension', NULLIF(ta."Extension", false), 'ExtensionNotes', ta."ExtensionNotes"
    )) AS metadata
),
transformation AS (
    UPDATE {schema}."Transformations" t SET "Deleted" = true
    FROM copy WHERE t."Id" = copy."Id"
    RETURNING t."Id", t."TransformationGroupId"
)
SELECT transformation."Id", transformation."TransformationGroupId",
       ARRAY(SELECT rows."Id" FROM rows ORDER BY rows."Id") AS "MappingRowIds",
       (SELECT jsonb_object_agg(rows."Id", rows.metadata) FROM rows WHERE rows.metadata <> '{{}}') AS "DroppedRowMetadata"
FROM transformation
""",
    ),
    (
        "transformations_through_deleted",
        """
WITH broken AS (
    SELECT t."Id" FROM {schema}."Transformations" t
    WHERE t."Deleted" = false
      AND ((t."TransformationGroupId" = 28 AND t."Id" BETWEEN 1590 AND 1595)
           OR (t."TransformationGroupId" = 29 AND t."Id" = 1600))
      AND EXISTS (
          SELECT 1 FROM {schema}."TransformationAttributes" ta
          CROSS JOIN LATERAL (
              -- A path is entity Ids and negated attribute Ids. Old rows hold dotted names instead;
              -- CASE keeps the cast from running on them.
              SELECT CASE WHEN trim(node) ~ '^-?[0-9]+$' THEN trim(node)::bigint END AS id
              FROM unnest(string_to_array(ta."EntityIdPath", ',')) AS node
          ) n
          WHERE ta."TransformationId" = t."Id" AND ta."Deleted" = false
            AND (EXISTS (SELECT 1 FROM {schema}."Entities" e WHERE e."Id" = n.id AND n.id > 0 AND e."Deleted" = true)
                 OR EXISTS (SELECT 1 FROM {schema}."Attributes" a WHERE a."Id" = -n.id AND n.id < 0 AND a."Deleted" = true))
      )
),
rows AS (
    UPDATE {schema}."TransformationAttributes" ta SET "Deleted" = true
    FROM broken WHERE ta."TransformationId" = broken."Id" AND ta."Deleted" = false
    RETURNING ta."Id", ta."TransformationId", jsonb_strip_nulls(jsonb_build_object(
        'Notes', ta."Notes", 'Contributor', ta."Contributor", 'ContributorOrganization', ta."ContributorOrganization",
        'ActivationDate', ta."ActivationDate", 'DeprecationDate', ta."DeprecationDate",
        'Extension', NULLIF(ta."Extension", false), 'ExtensionNotes', ta."ExtensionNotes"
    )) AS metadata
),
transformation AS (
    UPDATE {schema}."Transformations" t SET "Deleted" = true
    FROM broken WHERE t."Id" = broken."Id"
    RETURNING t."Id", t."TransformationGroupId"
)
SELECT transformation."Id", transformation."TransformationGroupId",
       ARRAY(SELECT rows."Id" FROM rows WHERE rows."TransformationId" = transformation."Id" ORDER BY rows."Id") AS "MappingRowIds",
       (SELECT jsonb_object_agg(rows."Id", rows.metadata) FROM rows
        WHERE rows."TransformationId" = transformation."Id" AND rows.metadata <> '{{}}') AS "DroppedRowMetadata"
FROM transformation
ORDER BY transformation."Id"
""",
    ),
]

# Unassociated attributes the first rule skips, because they are still in use.
SKIPPED_SQL = (
    """
WITH unassociated AS ("""
    + _UNASSOCIATED
    + """)
SELECT u."Id", u."DataModelId" FROM unassociated u WHERE """
    + _IN_USE
    + """ ORDER BY u."Id"
"""
)


def _quote(schema: str) -> str:
    return '"' + schema.replace('"', '""') + '"'


async def clean_schema(conn: asyncpg.Connection, schema: str) -> dict[str, list[asyncpg.Record]]:
    """Run every rule in one schema, in order; return each rule's changed rows, and the skipped ones."""
    identifier = _quote(schema)
    # Read before the first rule deletes anything.
    results = {"unassociated_skipped": await conn.fetch(SKIPPED_SQL.format(schema=identifier))}
    for rule, sql in RULES:
        results[rule] = await conn.fetch(sql.format(schema=identifier))
    return results


async def cleanup(conn: asyncpg.Connection, apply: bool) -> dict[str, dict[str, list[asyncpg.Record]]]:
    """Run the cleanup in every schema in one transaction; commit only when apply."""
    transaction = conn.transaction()
    await transaction.start()
    try:
        schemas = [row["table_schema"] for row in await conn.fetch(SCHEMAS_SQL)]
        if not schemas:
            raise RuntimeError("No schema has a DataModels table")
        results = {schema: await clean_schema(conn, schema) for schema in schemas}
    except BaseException:
        # Keep the error that got us here: a failed rollback (the connection dropped, say) would
        # replace it, and PostgreSQL rolls the transaction back anyway when the connection goes.
        with contextlib.suppress(Exception):
            await transaction.rollback()
        raise
    if apply:
        await transaction.commit()
    else:
        await transaction.rollback()
    return results


def format_ids(ids: list[int]) -> str:
    """Sorted Ids with runs folded: 1, 2, 3, 7 -> '1-3, 7'."""
    runs: list[list[int]] = []
    for value in sorted(ids):
        if runs and value == runs[-1][1] + 1:
            runs[-1][1] = value
        else:
            runs.append([value, value])
    return ", ".join(str(start) if start == end else f"{start}-{end}" for start, end in runs)


def format_rows(rows: list[asyncpg.Record]) -> list[str]:
    """Attribute rows as Ids per model; every other row in full, with its old value."""
    if rows and set(rows[0].keys()) == {"Id", "DataModelId"}:
        by_model: dict[int, list[int]] = {}
        for row in rows:
            by_model.setdefault(row["DataModelId"], []).append(row["Id"])
        return [f"model {model}: {format_ids(ids)}" for model, ids in sorted(by_model.items())]
    return [", ".join(f"{key}={value!r}" for key, value in row.items()) for row in rows]


async def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="commit (default: run, print, roll back)")
    args = parser.parse_args(argv)

    missing = [name for name in ("POSTGRESQL_HOST", "POSTGRESQL_USER", "POSTGRESQL_DB") if not os.getenv(name)]
    if missing:
        print(f"Missing required env vars: {', '.join(missing)}", file=sys.stderr)
        return 1

    conn = await asyncpg.connect(
        host=os.environ["POSTGRESQL_HOST"],
        port=int(os.getenv("POSTGRESQL_PORT") or 5432),
        user=os.environ["POSTGRESQL_USER"],
        password=os.getenv("POSTGRESQL_PASSWORD"),
        database=os.environ["POSTGRESQL_DB"],
    )
    try:
        print("APPLY: the changes are committed" if args.apply else "DRY RUN: the changes run and are rolled back")
        results = await cleanup(conn, args.apply)
    finally:
        await conn.close()

    for schema, rules in results.items():
        print(f"=== {schema}: " + ", ".join(f"{rule} {len(rows)}" for rule, rows in rules.items()))
        for rule, rows in rules.items():
            if rows:
                print(f"  {rule}:")
                print("\n".join(f"    {line}" for line in format_rows(rows)))
    print("Committed" if args.apply else "Rolled back. Run with --apply to commit")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))

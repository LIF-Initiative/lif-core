#!/usr/bin/env python3
"""One-time removal of the MDR's test data before #1388 converts the overlays, through asyncpg.

Decided on #1388: nobody uses the UI-test rows in the default or team schemas, so they go before the
conversion, and the conversion's schema baseline is taken after this runs. Soft-deletes, in `public`
and then every `tenant_*` schema with a DataModels table:

    entities, attributes
                      the pinned test rows below. A pin matches only on its Id, DataModelId and
                      UniqueName together: the dev-only Ids are reused for other rows on demo
    model_25          model 25 (Test2UpdatedSourceModel) and everything it owns: its entities,
                      attributes, value sets and values, then the model itself. Only while its Name
                      is still Test2UpdatedSourceModel
    entity_associations, attribute_associations, inclusions, constraints
                      live rows that point at a removed entity or attribute: either end of an
                      association, an overlay's inclusion of it, a constraint on it
    value_mappings    live value mappings and mapped value sets that use a removed value set or value
    transformations   a live mapping with a live row that maps a removed attribute or entity, or whose
                      path goes through one, and that mapping's rows; also every mapping in a group
                      on model 25
    groups            a live group on model 25, or one this run empties: it lost a live mapping above
                      and has none left. A group that keeps a live mapping, or was already empty, is
                      kept

Left alone: StateUExtensionEntity.stateUPrivateTestAttr (1826), which the conversion drops (decided
on #1388); models 1, 17 and 18 themselves; and every row the pins and model 25 don't reach.

One transaction for every schema. Each rule prints the Ids it changed. ROLLBACK unless --apply.
Re-running it changes nothing, since every rule only matches live rows.

Usage:
    POSTGRESQL_HOST=... POSTGRESQL_USER=... POSTGRESQL_PASSWORD=... POSTGRESQL_DB=... \\
        python3 remove_test_data.py [--apply]

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

# (Id, DataModelId, UniqueName). In the seed: the Aug 2025 UI-test rows that describe themselves as
# tests, inventoried on #1388.
SEED_ENTITIES = [
    (342, 17, "TestOrgEntity"),
    (344, 18, "TestPartnerEntity"),
    (345, 18, "TestPartnerChildEntity"),
    (349, 18, "TestEntity"),
    (350, 18, "TestEntity2"),
    (351, 18, "TestEntity3"),
    (352, 18, "TestEntity4"),
    (353, 18, "TestEntity5"),
    (354, 18, "TestEntity6"),
    (355, 18, "TestEntity7"),
]
SEED_ATTRIBUTES = [
    (1832, 1, "testNewLIFAttribute"),
    (1833, 17, "testNewOrgAttribute"),
    (1835, 18, "TestNewPartnerAttribute"),
    *((1840 + n, 18, f"TestAttribute{n if n > 1 else ''}") for n in range(1, 11)),
]
# Only on dev: the beach rows (partner.beach and its base and source-schema copies) and three more
# partner test entities. Demo reuses some of these Ids for other rows, which the UniqueName keeps out.
DEV_ENTITIES = [
    (380, 1, "base.beach.ent_a"),
    (381, 18, "partner.beach.ent_a"),
    (382, 18, "partner.beach.ent_b"),
    (383, 18, "partner.beach.ent_c"),
    (384, 1, "base.beach.ent_b"),
    (385, 1, "base.beach.ent_c"),
    (386, 1, "TammieTestEntity"),
    (387, 1, "TammeTestLvl1"),
    (388, 1, "TammeTestLvl2"),
    (389, 1, "TammeTestLvl3"),
    (390, 1, "TammeTestLvl4"),
    (392, 18, "TestPartnerEntity1"),
    (393, 18, "TestPartnerEntity2"),
    (394, 18, "TestPartnerEntity3"),
    (396, 18, "partner.org2.beachent1"),
]
DEV_ATTRIBUTES = [
    (1956, 1, "base.beach.att.a_a"),
    (1957, 18, "partner.beach.att_abc"),
    (1958, 1, "base.beach.att_abc"),
    (1959, 1, "TammieTestAttribute"),
    (1960, 1, "TammieTestAttLvl4"),
    (1963, 18, "TestPartnerAttribute4"),
    (1964, 18, "added.from.partner.lif.flow.beach.ent2"),
    (1965, 18, "partner.addedliteral.beachattb"),
]
TEST_MODEL = (25, "Test2UpdatedSourceModel")


def _pins(rows: list[tuple[int, int, str]]) -> str:
    return ", ".join(f"({i}, {m}, '{u.replace(chr(39), chr(39) * 2)}')" for i, m, u in rows)


# The rows this run removes, live or already deleted (so a re-run, or a dependent row left behind by
# an earlier delete, resolves the same way). Built into temp tables once per schema.
SETUP_SQL = f"""
CREATE TEMP TABLE _model ON COMMIT DROP AS
SELECT m."Id" FROM {{schema}}."DataModels" m WHERE m."Id" = {TEST_MODEL[0]} AND m."Name" = '{TEST_MODEL[1]}';
CREATE TEMP TABLE _entity ON COMMIT DROP AS
SELECT e."Id" FROM {{schema}}."Entities" e
JOIN (VALUES {_pins(SEED_ENTITIES + DEV_ENTITIES)}) p (id, model, name)
  ON e."Id" = p.id AND e."DataModelId" = p.model AND e."UniqueName" = p.name
UNION SELECT e."Id" FROM {{schema}}."Entities" e WHERE e."DataModelId" IN (SELECT "Id" FROM _model);
CREATE TEMP TABLE _attribute ON COMMIT DROP AS
SELECT a."Id" FROM {{schema}}."Attributes" a
JOIN (VALUES {_pins(SEED_ATTRIBUTES + DEV_ATTRIBUTES)}) p (id, model, name)
  ON a."Id" = p.id AND a."DataModelId" = p.model AND a."UniqueName" = p.name
UNION SELECT a."Id" FROM {{schema}}."Attributes" a WHERE a."DataModelId" IN (SELECT "Id" FROM _model);
CREATE TEMP TABLE _value_set ON COMMIT DROP AS
SELECT v."Id" FROM {{schema}}."ValueSets" v WHERE v."DataModelId" IN (SELECT "Id" FROM _model);
CREATE TEMP TABLE _value ON COMMIT DROP AS
SELECT v."Id" FROM {{schema}}."ValueSetValues" v
WHERE v."DataModelId" IN (SELECT "Id" FROM _model) OR v."ValueSetId" IN (SELECT "Id" FROM _value_set);
"""
TEARDOWN_SQL = "DROP TABLE _model, _entity, _attribute, _value_set, _value, _transformation"

# A mapping that touches a removed row: one of its rows (live or not) maps a removed attribute or
# entity, or has a removed one on its path. Paths are entity Ids and negated attribute Ids; old rows
# hold dotted names, which the CASE skips.
_TOUCHES = """
SELECT 1 FROM {schema}."TransformationAttributes" ta
LEFT JOIN LATERAL (
    SELECT CASE WHEN trim(node) ~ '^-?[0-9]+$' THEN trim(node)::bigint END AS id
    FROM unnest(string_to_array(ta."EntityIdPath", ',')) AS node
) n ON true
WHERE ta."TransformationId" = t."Id" {live}
  AND (ta."AttributeId" IN (SELECT "Id" FROM _attribute)
       OR ta."EntityId" IN (SELECT "Id" FROM _entity)
       OR n.id IN (SELECT "Id" FROM _entity)
       OR -n.id IN (SELECT "Id" FROM _attribute))
"""

_ON_MODEL = '(g."SourceDataModelId" IN (SELECT "Id" FROM _model) OR g."TargetDataModelId" IN (SELECT "Id" FROM _model))'

# The live mappings this run removes. Kept for the groups rule, which removes a group only when this
# run empties it.
SETUP_SQL += (
    """
CREATE TEMP TABLE _transformation ON COMMIT DROP AS
SELECT t."Id", t."TransformationGroupId" FROM {schema}."Transformations" t
WHERE t."Deleted" = false
  AND (EXISTS ("""
    + _TOUCHES.replace("{live}", 'AND ta."Deleted" = false')
    + """)
       OR t."TransformationGroupId" IN (SELECT g."Id" FROM {schema}."TransformationsGroup" g WHERE """
    + _ON_MODEL
    + """));
"""
)

# (rule, SQL). Each statement returns one row per changed row.
RULES: list[tuple[str, str]] = [
    (
        "transformations",
        """
WITH doomed AS (SELECT "Id" FROM _transformation),
rows AS (
    UPDATE {schema}."TransformationAttributes" ta SET "Deleted" = true
    FROM doomed WHERE ta."TransformationId" = doomed."Id" AND ta."Deleted" = false
    RETURNING ta."Id", ta."TransformationId"
),
transformation AS (
    UPDATE {schema}."Transformations" t SET "Deleted" = true
    FROM doomed WHERE t."Id" = doomed."Id"
    RETURNING t."Id", t."TransformationGroupId"
)
SELECT transformation."Id", transformation."TransformationGroupId",
       ARRAY(SELECT rows."Id" FROM rows WHERE rows."TransformationId" = transformation."Id" ORDER BY rows."Id") AS "MappingRowIds"
FROM transformation ORDER BY transformation."Id"
""",
    ),
    (
        "groups",
        """
UPDATE {schema}."TransformationsGroup" g SET "Deleted" = true
WHERE g."Deleted" = false
  AND ("""
        + _ON_MODEL
        + """
       OR (g."Id" IN (SELECT "TransformationGroupId" FROM _transformation)
           AND NOT EXISTS (SELECT 1 FROM {schema}."Transformations" t WHERE t."TransformationGroupId" = g."Id" AND t."Deleted" = false)))
RETURNING g."Id", g."Name", g."SourceDataModelId", g."TargetDataModelId"
""",
    ),
    (
        "value_mappings",
        """
UPDATE {schema}."ValueSetValueMapping" m SET "Deleted" = true
WHERE m."Deleted" = false
  AND (m."SourceValueId" IN (SELECT "Id" FROM _value) OR m."TargetValueId" IN (SELECT "Id" FROM _value)
       OR m."SourceValueSetId" IN (SELECT "Id" FROM _value_set) OR m."TargetValueSetId" IN (SELECT "Id" FROM _value_set))
RETURNING m."Id", m."SourceValueId", m."TargetValueId"
""",
    ),
    (
        "mapped_value_sets",
        """
UPDATE {schema}."ExtMappedValueSet" m SET "Deleted" = true
WHERE m."Deleted" = false
  AND (m."ValueSetId" IN (SELECT "Id" FROM _value_set) OR m."MappedValueSetId" IN (SELECT "Id" FROM _value_set))
RETURNING m."Id", m."ValueSetId", m."MappedValueSetId"
""",
    ),
    (
        "inclusions",
        """
UPDATE {schema}."ExtInclusionsFromBaseDM" i SET "Deleted" = true
WHERE i."Deleted" = false
  AND ((i."ElementType"::text = 'Entity' AND i."IncludedElementId" IN (SELECT "Id" FROM _entity))
       OR (i."ElementType"::text = 'Attribute' AND i."IncludedElementId" IN (SELECT "Id" FROM _attribute)))
RETURNING i."Id", i."ExtDataModelId", i."ElementType"::text AS "ElementType", i."IncludedElementId"
""",
    ),
    (
        "entity_associations",
        """
UPDATE {schema}."EntityAssociation" x SET "Deleted" = true
WHERE x."Deleted" = false
  AND (x."ParentEntityId" IN (SELECT "Id" FROM _entity) OR x."ChildEntityId" IN (SELECT "Id" FROM _entity))
RETURNING x."Id", x."ParentEntityId", x."ChildEntityId"
""",
    ),
    (
        "attribute_associations",
        """
UPDATE {schema}."EntityAttributeAssociation" x SET "Deleted" = true
WHERE x."Deleted" = false
  AND (x."EntityId" IN (SELECT "Id" FROM _entity) OR x."AttributeId" IN (SELECT "Id" FROM _attribute))
RETURNING x."Id", x."EntityId", x."AttributeId"
""",
    ),
    (
        "constraints",
        """
UPDATE {schema}."Constraints" c SET "Deleted" = true
WHERE c."Deleted" = false AND c."AttributeId" IN (SELECT "Id" FROM _attribute)
RETURNING c."Id", c."AttributeId"
""",
    ),
    (
        "model_constraints",
        """
UPDATE {schema}."DataModelConstraints" c SET "Deleted" = true
WHERE c."Deleted" = false
  AND (c."ForDataModelId" IN (SELECT "Id" FROM _model)
       OR (c."ElementType"::text = 'Entity' AND c."ElementId" IN (SELECT "Id" FROM _entity))
       OR (c."ElementType"::text = 'Attribute' AND c."ElementId" IN (SELECT "Id" FROM _attribute)))
RETURNING c."Id", c."ForDataModelId", c."ElementType"::text AS "ElementType", c."ElementId"
""",
    ),
    (
        "values",
        """
UPDATE {schema}."ValueSetValues" v SET "Deleted" = true
WHERE v."Deleted" = false AND v."Id" IN (SELECT "Id" FROM _value)
RETURNING v."Id", v."DataModelId"
""",
    ),
    (
        "value_sets",
        """
UPDATE {schema}."ValueSets" v SET "Deleted" = true
WHERE v."Deleted" = false AND v."Id" IN (SELECT "Id" FROM _value_set)
RETURNING v."Id", v."DataModelId"
""",
    ),
    (
        "attributes",
        """
UPDATE {schema}."Attributes" a SET "Deleted" = true
WHERE a."Deleted" = false AND a."Id" IN (SELECT "Id" FROM _attribute)
RETURNING a."Id", a."DataModelId"
""",
    ),
    (
        "entities",
        """
UPDATE {schema}."Entities" e SET "Deleted" = true
WHERE e."Deleted" = false AND e."Id" IN (SELECT "Id" FROM _entity)
RETURNING e."Id", e."DataModelId"
""",
    ),
    (
        "model_25",
        """
UPDATE {schema}."DataModels" m SET "Deleted" = true
WHERE m."Deleted" = false AND m."Id" IN (SELECT "Id" FROM _model)
RETURNING m."Id", m."Name"
""",
    ),
]


def _quote(schema: str) -> str:
    return '"' + schema.replace('"', '""') + '"'


async def clean_schema(conn: asyncpg.Connection, schema: str) -> dict[str, list[asyncpg.Record]]:
    """Run every rule in one schema, in order; return each rule's changed rows."""
    identifier = _quote(schema)
    await conn.execute(SETUP_SQL.format(schema=identifier))
    try:
        return {rule: await conn.fetch(sql.format(schema=identifier)) for rule, sql in RULES}
    finally:
        await conn.execute(TEARDOWN_SQL)


async def cleanup(conn: asyncpg.Connection, apply: bool) -> dict[str, dict[str, list[asyncpg.Record]]]:
    """Run the removal in every schema in one transaction; commit only when apply."""
    transaction = conn.transaction()
    await transaction.start()
    try:
        schemas = [row["table_schema"] for row in await conn.fetch(SCHEMAS_SQL)]
        if not schemas:
            raise RuntimeError("No schema has a DataModels table")
        results = {schema: await clean_schema(conn, schema) for schema in schemas}
    except BaseException:
        # Keep the error that got us here: a failed rollback would replace it, and PostgreSQL rolls
        # the transaction back anyway when the connection goes.
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
    """Rows owned by a model as Ids per model; every other row in full."""
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

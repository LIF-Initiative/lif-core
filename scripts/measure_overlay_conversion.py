#!/usr/bin/env python3
"""Read-only count of what converting each overlay model would touch (#1388).

ADR data_model/0004 retires overlays: each overlay model (one with a base model, or typed OrgLIF or
PartnerLIF) is converted once into a self-contained model. This sizes that conversion per schema
before any of it is designed against real data. For each overlay model it reports:

    incl own        live inclusion rows on the model's own elements (become flags on the element)
    incl foreign    live inclusion rows on another model's elements (those elements get copied in)
    incl absent     live inclusion rows naming a missing or soft-deleted element (count as absent)
    dup incl        live inclusion rows that repeat an earlier row for the same element
    overrides       own elements reusing the UniqueName of a live element of the base model
    clashes         UniqueNames held twice once the foreign included elements are copied in
    vs foreign      own live attributes using another model's value set
    vs to copy      value sets of the foreign included attributes
    extended by     live association rows whose ExtendedByDataModelId is the model
    unassociated    own live attributes in no live entity-attribute association
    groups/rules/mapping rows
                    live transformation groups with the model as source or target, their live
                    rules, and those rules' live TransformationAttributes rows (to re-point)

Counts are entity/attribute where both apply. After the table it lists the override and clash
names, and any ExtendedBy links declared by a model that is not an overlay.

A second table holds the checks the conversion's write side needs. The "render set" is what the
model's schema shows: the live elements its live inclusion rows name.

    odd types       kept attributes (included, or own and associated) with a NULL DataType, an
                    'entity' DataType, or a TargetEntityId; export refuses these
    flag conflicts  elements with several live inclusion rows that disagree on the flags
    ext base        ExtendedBy rows of the model with both ends in its base (copied with the model)
    ext own         ExtendedBy rows of the model with an end in the model itself
    ext other       ExtendedBy rows of the model with both ends in one other model, which owns them
    ext no owner    ExtendedBy rows of the model with ends in two models, neither of them this one
    ext absent      ExtendedBy rows of the model with a missing or soft-deleted end
    ... shown       of those, the ones the render set displays (both ends in it)
    cross overlay   ExtendedBy rows of another overlay with both ends in this model's render set
    paths outside   live mapping rows on the model's side with a node outside the render set
    paths invalid   live mapping rows on the model's side whose EntityIdPath is not a list of IDs

After it, each "ext no owner" row is listed with its ends, since the conversion recreates each one.

Reads `public` and every `tenant_*` schema with a DataModels table in one read-only transaction.
It changes nothing and exits 0; it exits 1 only when it cannot connect or find a schema.

Usage:
    POSTGRESQL_HOST=... POSTGRESQL_USER=... POSTGRESQL_PASSWORD=... POSTGRESQL_DB=... \\
        python3 measure_overlay_conversion.py

POSTGRESQL_PORT defaults to 5432. These are the names the MDR API's own env uses.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections import Counter

import asyncpg

SCHEMAS_SQL = r"""
SELECT table_schema FROM information_schema.tables
WHERE table_name = 'DataModels'
  AND (table_schema = 'public' OR table_schema LIKE 'tenant\_%')
ORDER BY table_schema <> 'public', table_schema
"""

OVERLAYS_SQL = """
SELECT "Id", "Name", "Type"::text AS "Type", "BaseDataModelId"
FROM {schema}."DataModels"
WHERE "Deleted" IS NOT TRUE AND ("BaseDataModelId" IS NOT NULL OR "Type"::text IN ('OrgLIF', 'PartnerLIF'))
ORDER BY "Id"
"""

# One row per live inclusion row of the model, with the element it names. Constraint and
# Transformation inclusions name no element here, so they count as absent (there are none today).
INCLUSIONS_SQL = """
SELECT i."ElementType"::text AS "ElementType",
       i."IncludedElementId" AS "ElementId",
       COALESCE(e."DataModelId", a."DataModelId") AS "OwnerId",
       COALESCE(e."Deleted", a."Deleted") AS "ElementDeleted",
       COALESCE(e."UniqueName", a."UniqueName") AS "UniqueName",
       a."ValueSetId"
FROM {schema}."ExtInclusionsFromBaseDM" i
LEFT JOIN {schema}."Entities" e ON i."ElementType"::text = 'Entity' AND e."Id" = i."IncludedElementId"
LEFT JOIN {schema}."Attributes" a ON i."ElementType"::text = 'Attribute' AND a."Id" = i."IncludedElementId"
WHERE i."ExtDataModelId" = $1 AND i."Deleted" IS NOT TRUE
"""

OWN_ELEMENTS_SQL = """
SELECT 'Entity' AS "ElementType", "UniqueName", NULL::bigint AS "ValueSetModelId", true AS "Associated"
FROM {schema}."Entities" WHERE "DataModelId" = $1 AND "Deleted" IS NOT TRUE
UNION ALL
SELECT 'Attribute', a."UniqueName", v."DataModelId",
       EXISTS (SELECT 1 FROM {schema}."EntityAttributeAssociation" x
               WHERE x."AttributeId" = a."Id" AND x."Deleted" IS NOT TRUE)
FROM {schema}."Attributes" a
LEFT JOIN {schema}."ValueSets" v ON v."Id" = a."ValueSetId"
WHERE a."DataModelId" = $1 AND a."Deleted" IS NOT TRUE
"""

BASE_NAMES_SQL = """
SELECT 'Entity' AS "ElementType", "UniqueName" FROM {schema}."Entities" WHERE "DataModelId" = $1 AND "Deleted" IS NOT TRUE
UNION ALL
SELECT 'Attribute', "UniqueName" FROM {schema}."Attributes" WHERE "DataModelId" = $1 AND "Deleted" IS NOT TRUE
"""

EXTENDED_BY_SQL = """
SELECT 'Entity' AS "ElementType", "ExtendedByDataModelId", count(*) AS n
FROM {schema}."EntityAssociation" WHERE "Deleted" IS NOT TRUE AND "ExtendedByDataModelId" IS NOT NULL
GROUP BY "ExtendedByDataModelId"
UNION ALL
SELECT 'Attribute', "ExtendedByDataModelId", count(*)
FROM {schema}."EntityAttributeAssociation" WHERE "Deleted" IS NOT TRUE AND "ExtendedByDataModelId" IS NOT NULL
GROUP BY "ExtendedByDataModelId"
"""

MAPPINGS_SQL = """
SELECT count(DISTINCT g."Id") AS groups, count(DISTINCT t."Id") AS rules, count(DISTINCT ta."Id") AS rows
FROM {schema}."TransformationsGroup" g
LEFT JOIN {schema}."Transformations" t ON t."TransformationGroupId" = g."Id" AND t."Deleted" IS NOT TRUE
LEFT JOIN {schema}."TransformationAttributes" ta ON ta."TransformationId" = t."Id" AND ta."Deleted" IS NOT TRUE
WHERE g."Deleted" IS NOT TRUE AND $1 IN (g."SourceDataModelId", g."TargetDataModelId")
"""

# Attributes the conversion keeps: the live ones the model includes, and its own associated ones
# (its own unassociated ones are dropped, Q1).
ODD_TYPES_SQL = """
SELECT count(*) FILTER (WHERE a."DataType" IS NULL) AS null_type,
       count(*) FILTER (WHERE a."DataType" = 'entity') AS entity_type,
       count(*) FILTER (WHERE a."TargetEntityId" IS NOT NULL) AS target
FROM {schema}."Attributes" a
WHERE a."Deleted" IS NOT TRUE
  AND (a."Id" IN (SELECT i."IncludedElementId" FROM {schema}."ExtInclusionsFromBaseDM" i
                  WHERE i."ExtDataModelId" = $1 AND i."ElementType"::text = 'Attribute' AND i."Deleted" IS NOT TRUE)
       OR (a."DataModelId" = $1
           AND EXISTS (SELECT 1 FROM {schema}."EntityAttributeAssociation" x
                       WHERE x."AttributeId" = a."Id" AND x."Deleted" IS NOT TRUE)))
"""

FLAG_CONFLICTS_SQL = """
SELECT count(*) AS n FROM (
    SELECT 1 FROM {schema}."ExtInclusionsFromBaseDM"
    WHERE "ExtDataModelId" = $1 AND "Deleted" IS NOT TRUE
    GROUP BY "ElementType", "IncludedElementId"
    HAVING count(DISTINCT concat_ws('|', COALESCE("LevelOfAccess"::text, '-'),
                                         COALESCE("Queryable"::text, '-'), COALESCE("Modifiable"::text, '-'))) > 1
) conflicts
"""

# Every live ExtendedBy association with the models of its ends. An end that is missing or
# soft-deleted has no model, and such a row counts as absent.
EXTENDED_ASSOCIATIONS_SQL = """
SELECT 'Entity' AS "ElementType", x."Id", x."ExtendedByDataModelId",
       x."ParentEntityId" AS "ParentId", p."DataModelId" AS "ParentModelId",
       x."ChildEntityId" AS "ChildId", c."DataModelId" AS "ChildModelId"
FROM {schema}."EntityAssociation" x
LEFT JOIN {schema}."Entities" p ON p."Id" = x."ParentEntityId" AND p."Deleted" IS NOT TRUE
LEFT JOIN {schema}."Entities" c ON c."Id" = x."ChildEntityId" AND c."Deleted" IS NOT TRUE
WHERE x."Deleted" IS NOT TRUE AND x."ExtendedByDataModelId" IS NOT NULL
UNION ALL
SELECT 'Attribute', x."Id", x."ExtendedByDataModelId",
       x."EntityId", p."DataModelId", x."AttributeId", c."DataModelId"
FROM {schema}."EntityAttributeAssociation" x
LEFT JOIN {schema}."Entities" p ON p."Id" = x."EntityId" AND p."Deleted" IS NOT TRUE
LEFT JOIN {schema}."Attributes" c ON c."Id" = x."AttributeId" AND c."Deleted" IS NOT TRUE
WHERE x."Deleted" IS NOT TRUE AND x."ExtendedByDataModelId" IS NOT NULL
ORDER BY 1, 2
"""

# The live mapping rows on the model's side of each live group it is in.
MAPPING_ROWS_SQL = """
SELECT ta."Id", ta."EntityId", ta."AttributeId", ta."EntityIdPath"
FROM {schema}."TransformationsGroup" g
JOIN {schema}."Transformations" t ON t."TransformationGroupId" = g."Id" AND t."Deleted" IS NOT TRUE
JOIN {schema}."TransformationAttributes" ta ON ta."TransformationId" = t."Id" AND ta."Deleted" IS NOT TRUE
WHERE g."Deleted" IS NOT TRUE
  AND $1 = CASE ta."AttributeType"::text WHEN 'Source' THEN g."SourceDataModelId" WHEN 'Target' THEN g."TargetDataModelId" END
"""

COLUMNS = (
    "schema",
    "model",
    "type",
    "base",
    "incl own",
    "incl foreign",
    "incl absent",
    "dup incl",
    "overrides",
    "clashes",
    "vs foreign",
    "vs to copy",
    "extended by",
    "unassociated",
    "groups",
    "rules",
    "mapping rows",
)

CHECK_COLUMNS = (
    "schema",
    "model",
    "odd types",
    "flag conflicts",
    "ext base",
    "ext own",
    "ext other",
    "ext other shown",
    "ext no owner",
    "ext no owner shown",
    "ext absent",
    "cross overlay",
    "paths outside",
    "paths invalid",
)


def _pair(counts: Counter) -> str:
    return f"{counts['Entity']}/{counts['Attribute']}"


def measure_model(model_id: int, base_id: int | None, inclusions: list, own: list, base_names: list) -> dict:
    """The per-model counts that need no further query (see the module docstring)."""
    kinds: dict[str, Counter] = {"own": Counter(), "foreign": Counter(), "absent": Counter()}
    foreign: dict[tuple[str, int], str] = {}
    value_sets_to_copy = set()
    seen = Counter((row["ElementType"], row["ElementId"]) for row in inclusions)
    for row in inclusions:
        if row["OwnerId"] is None or row["ElementDeleted"]:
            kind = "absent"
        elif row["OwnerId"] == model_id:
            kind = "own"
        else:
            kind = "foreign"
            # Keyed by element, so a repeated inclusion row is not a second copy.
            foreign[(row["ElementType"], row["ElementId"])] = row["UniqueName"]
            if row["ValueSetId"] is not None:
                value_sets_to_copy.add(row["ValueSetId"])
        kinds[kind][row["ElementType"]] += 1

    own_names = [(row["ElementType"], row["UniqueName"]) for row in own]
    base = {(row["ElementType"], row["UniqueName"]) for row in base_names} if base_id is not None else set()
    overrides = sorted({name for name in own_names if name in base})
    held = Counter(own_names + [(kind, name) for (kind, _), name in foreign.items()])
    clashes = sorted(name for name, n in held.items() if n > 1)
    return {
        "incl own": _pair(kinds["own"]),
        "incl foreign": _pair(kinds["foreign"]),
        "incl absent": _pair(kinds["absent"]),
        "dup incl": sum(n - 1 for n in seen.values()),
        "overrides": len(overrides),
        "clashes": len(clashes),
        "vs foreign": sum(
            1 for row in own if row["ElementType"] == "Attribute" and row["ValueSetModelId"] not in (None, model_id)
        ),
        "vs to copy": len(value_sets_to_copy),
        "unassociated": sum(1 for row in own if row["ElementType"] == "Attribute" and not row["Associated"]),
        "override names": overrides,
        "clash names": clashes,
    }


def _path_nodes(row) -> list[tuple[str, int]] | None:
    """The (kind, Id) nodes a mapping row names, or None when its EntityIdPath is not a list of IDs.
    With no path, the row names its entity and attribute directly."""
    if not row["EntityIdPath"]:
        return [
            (kind, row[column])
            for kind, column in (("Entity", "EntityId"), ("Attribute", "AttributeId"))
            if row[column] is not None
        ]
    try:
        ids = [int(segment) for segment in row["EntityIdPath"].split(",")]
    except ValueError:
        return None
    # A negative Id is the attribute that ends the path.
    return [("Attribute", -i) if i < 0 else ("Entity", i) for i in ids]


def check_model(
    model_id: int, base_id: int | None, overlay_ids: set, inclusions: list, associations: list, mapping_rows: list
) -> dict:
    """The write-side checks that need no further query (see the module docstring)."""
    shown = {
        (row["ElementType"], row["ElementId"])
        for row in inclusions
        if row["OwnerId"] is not None and not row["ElementDeleted"]
    }
    kinds = {
        name: Counter() for name in ("base", "own", "other", "other shown", "no owner", "no owner shown", "absent")
    }
    cross_overlay = Counter()
    no_owner = []
    for row in associations:
        kind, parent_model, child_model = row["ElementType"], row["ParentModelId"], row["ChildModelId"]
        displayed = ("Entity", row["ParentId"]) in shown and (kind, row["ChildId"]) in shown
        if row["ExtendedByDataModelId"] != model_id:
            if row["ExtendedByDataModelId"] in overlay_ids and displayed:
                cross_overlay[kind] += 1
            continue
        if parent_model is None or child_model is None:
            kinds["absent"][kind] += 1
        elif model_id in (parent_model, child_model):
            kinds["own"][kind] += 1
        elif parent_model == child_model == base_id:
            kinds["base"][kind] += 1
        elif parent_model == child_model:
            kinds["other"][kind] += 1
            kinds["other shown"][kind] += displayed
        else:
            kinds["no owner"][kind] += 1
            kinds["no owner shown"][kind] += displayed
            no_owner.append(row)

    outside = invalid = 0
    for row in mapping_rows:
        nodes = _path_nodes(row)
        if nodes is None:
            invalid += 1
        elif any(node not in shown for node in nodes):
            outside += 1
    return {
        **{f"ext {name}": _pair(counts) for name, counts in kinds.items()},
        "cross overlay": _pair(cross_overlay),
        "paths outside": outside,
        "paths invalid": invalid,
        "no owner rows": no_owner,
    }


async def measure_schema(conn: asyncpg.Connection, schema: str) -> tuple[list[dict], dict[int, Counter]]:
    """One result per overlay model in the schema, plus ExtendedBy counts by declaring model."""
    identifier = '"' + schema.replace('"', '""') + '"'
    extended: dict[int, Counter] = {}
    for row in await conn.fetch(EXTENDED_BY_SQL.format(schema=identifier)):
        extended.setdefault(row["ExtendedByDataModelId"], Counter())[row["ElementType"]] += row["n"]

    associations = await conn.fetch(EXTENDED_ASSOCIATIONS_SQL.format(schema=identifier))
    overlays = await conn.fetch(OVERLAYS_SQL.format(schema=identifier))
    overlay_ids = {model["Id"] for model in overlays}
    results = []
    for model in overlays:
        model_id, base_id = model["Id"], model["BaseDataModelId"]
        inclusions = await conn.fetch(INCLUSIONS_SQL.format(schema=identifier), model_id)
        result = measure_model(
            model_id,
            base_id,
            inclusions,
            await conn.fetch(OWN_ELEMENTS_SQL.format(schema=identifier), model_id),
            await conn.fetch(BASE_NAMES_SQL.format(schema=identifier), base_id) if base_id is not None else [],
        )
        result.update(
            check_model(
                model_id,
                base_id,
                overlay_ids,
                inclusions,
                associations,
                await conn.fetch(MAPPING_ROWS_SQL.format(schema=identifier), model_id),
            )
        )
        odd = (await conn.fetch(ODD_TYPES_SQL.format(schema=identifier), model_id))[0]
        result["odd types"] = f"{odd['null_type']}/{odd['entity_type']}/{odd['target']}"
        result["flag conflicts"] = (await conn.fetch(FLAG_CONFLICTS_SQL.format(schema=identifier), model_id))[0]["n"]
        mappings = (await conn.fetch(MAPPINGS_SQL.format(schema=identifier), model_id))[0]
        result.update(
            {
                "schema": schema,
                "model": f"{model_id} {model['Name']}",
                "type": model["Type"],
                "base": "" if base_id is None else base_id,
                "extended by": _pair(extended.get(model_id, Counter())),
                "groups": mappings["groups"],
                "rules": mappings["rules"],
                "mapping rows": mappings["rows"],
            }
        )
        results.append(result)
    return results, {m: c for m, c in extended.items() if m not in overlay_ids}


async def measure(conn: asyncpg.Connection) -> dict[str, tuple[list[dict], dict[int, Counter]]]:
    """Every schema's results, read in one read-only snapshot."""
    async with conn.transaction(isolation="repeatable_read", readonly=True):
        schemas = [row["table_schema"] for row in await conn.fetch(SCHEMAS_SQL)]
        if not schemas:
            raise RuntimeError("No schema has a DataModels table")
        return {schema: await measure_schema(conn, schema) for schema in schemas}


def format_rows(rows: list[dict], columns: tuple[str, ...] = COLUMNS) -> str:
    """An aligned table with a row count, like psql's default output."""
    cells = [columns] + [tuple(str(row[c]) for c in columns) for row in rows]
    widths = [max(len(line[i]) for line in cells) for i in range(len(columns))]
    lines = [" | ".join(value.ljust(width) for value, width in zip(line, widths)).rstrip() for line in cells]
    lines.insert(1, "-+-".join("-" * width for width in widths))
    lines.append(f"({len(rows)} row{'' if len(rows) == 1 else 's'})")
    return "\n".join(lines)


async def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.parse_args(argv)

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
        results = await measure(conn)
    finally:
        await conn.close()

    for schema, (models, other_extended) in results.items():
        print(f"=== {schema}: {len(models)} overlay model{'' if len(models) == 1 else 's'}")
        if models:
            print(format_rows(models))
            print(format_rows(models, CHECK_COLUMNS))
        for row in models:
            for label, title in (("override names", "overrides"), ("clash names", "clashes")):
                if row[label]:
                    names = ", ".join(f"{kind} {name}" for kind, name in row[label])
                    print(f"{row['model']} {title}: {names}")
            for association in row["no owner rows"]:
                print(
                    f"{row['model']} no-owner {association['ElementType']} association {association['Id']}: "
                    f"entity {association['ParentId']} (model {association['ParentModelId']}) -> "
                    f"{association['ElementType'].lower()} {association['ChildId']} (model {association['ChildModelId']})"
                )
        for model_id, counts in sorted(other_extended.items()):
            print(f"ExtendedBy links declared by non-overlay model {model_id}: {_pair(counts)}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))

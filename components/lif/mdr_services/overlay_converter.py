"""Convert overlay models into self-contained models, in place (#1388, ADR data_model/0004).

An overlay (models 17 and 18 today) shows elements of other models through inclusion rows, and adds its
own through ExtendedBy associations. Converting it copies every foreign element its schema shows into
the model, moves the inclusion rows' flags onto the elements, and leaves rows that describe the model
on their own, so export can read it.

What the schema shows is read from the generator's own output, not restated: the full-metadata schema
names every entity, attribute and association it renders, so clashes, overrides and the dropped
``Common`` root come out the way the schema already has them.

The conversion checks itself before the caller commits. It generates every live model it touches in all
16 flag combinations before and after, and the "after" must equal the "before" rewritten through the
conversion's Id map (decided on #1388: D1, per key), with `required` compared regardless of order
(a name listed twice still counts twice). Every caller runs it in one transaction and rolls
back on ``ConversionFailed``.

The comparison covers only the models it generates, so the conversion also refuses when a live row of
any other model still uses a row it soft-deleted or changed in place, and when any live mapping row
still goes through a row it soft-deleted (``outside_references``).

Per overlay, after step 0 has run once for all of them:

    1  render set     the entities, attributes and associations the overlay's schema shows
    2  own elements   flags from the inclusion row, Extension cleared
    3  copies         every foreign element shown, inserted in Id order, with the inclusion row's flags
    4  value sets     every value set a shown attribute uses from another model, copied with its values
    5  associations   rewritten or copied between the model's own rows; every ExtendedBy row of the
                      model, and every own row the schema doesn't show, is soft-deleted
    6  drops          own entities and attributes the schema doesn't show are soft-deleted
    7  model row      BaseDataModelId cleared, CopiedFrom set to the base model, inclusion rows deleted
    8  mapping rows   every live mapping row on the model's side re-pointed through the Id map
"""

from __future__ import annotations

import difflib
import itertools
import json
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from lif.mdr_services.mapping_group_converter import export_mapping_group
from lif.mdr_services.model_converter import export_model
from lif.mdr_services.schema_generation_service import generate_openapi_schema

FLAG_NAMES = ("include_attr_md", "include_entity_md", "public_only", "full_export")
FLAG_MATRIX = [dict(zip(FLAG_NAMES, values)) for values in itertools.product([False, True], repeat=4)]
# The combination that names every row the schema renders: element Ids, association Ids, value sets.
FULL = "attr1-entity1-public0-full1"

ENTITY_COLUMNS = (
    "Name", "UniqueName", "Description", "UseConsiderations", "Required", "Array", "SourceModel", "Notes",
    "CreationDate", "ActivationDate", "DeprecationDate", "Contributor", "ContributorOrganization", "Tags",
    "Common",
)  # fmt: skip
ATTRIBUTE_COLUMNS = (
    "Name", "UniqueName", "Description", "UseConsiderations", "DataType", "ValueSetId", "Required", "Array",
    "SourceModel", "Notes", "CreationDate", "ActivationDate", "DeprecationDate", "Contributor",
    "ContributorOrganization", "Tags", "Example", "Common", "TargetEntityId",
)  # fmt: skip
VALUE_SET_COLUMNS = (
    "Name", "Description", "UseConsiderations", "Notes", "CreationDate", "ActivationDate", "DeprecationDate",
    "Contributor", "ContributorOrganization", "Extension", "ExtensionNotes", "Tags",
)  # fmt: skip
VALUE_COLUMNS = (
    "Description", "UseConsiderations", "Value", "ValueName", "OriginalValueId", "Source", "Notes",
    "CreationDate", "ActivationDate", "DeprecationDate", "Contributor", "ContributorOrganization", "Extension",
    "ExtensionNotes",
)  # fmt: skip
ENTITY_ASSOCIATION_COLUMNS = (
    "Relationship", "Placement", "Notes", "CreationDate", "ActivationDate", "DeprecationDate", "Contributor",
    "ContributorOrganization", "Name", "Array",
)  # fmt: skip
ATTRIBUTE_ASSOCIATION_COLUMNS = (
    "Notes", "CreationDate", "ActivationDate", "DeprecationDate", "Contributor", "ContributorOrganization",
    "Name", "Array",
)  # fmt: skip


class ConversionFailed(Exception):
    """The conversion refused, or one of its checks failed. Every reason is in ``reasons``."""

    def __init__(self, reasons: list[str]):
        super().__init__(f"{len(reasons)} reason(s): " + "; ".join(reasons[:5]))
        self.reasons = reasons


@dataclass
class RenderSet:
    entities: set[int] = field(default_factory=set)
    attributes: set[int] = field(default_factory=set)
    entity_associations: set[int] = field(default_factory=set)
    attribute_associations: set[int] = field(default_factory=set)


@dataclass
class IdMap:
    """Old Id -> new Id, per kind. Rows the model keeps map to themselves."""

    entities: dict[int, int] = field(default_factory=dict)
    attributes: dict[int, int] = field(default_factory=dict)
    entity_associations: dict[int, int] = field(default_factory=dict)
    attribute_associations: dict[int, int] = field(default_factory=dict)
    value_sets: dict[int, int] = field(default_factory=dict)
    values: dict[int, int] = field(default_factory=dict)


@dataclass
class Changes:
    """Every row the conversion writes, for the undo record: inserted copies, soft-deleted rows, and the
    old values of every column it updates in place."""

    inserted: dict[str, list[int]] = field(default_factory=dict)
    soft_deleted: dict[str, list[int]] = field(default_factory=dict)
    updated: dict[str, list[dict]] = field(default_factory=dict)


@dataclass
class ModelReport:
    model_id: int
    id_map: IdMap
    copied: dict[str, int]
    soft_deleted: dict[str, list[int]]
    updated_mapping_rows: list[int]


@dataclass
class Report:
    moved_attributes: dict[int, int]  # attribute Id -> the base model step 0 moved it to
    models: list[ModelReport]
    compared: dict[int, list[str]]  # model -> combinations compared
    changes: Changes


def flag_key(flags: dict) -> str:
    return "attr{:d}-entity{:d}-public{:d}-full{:d}".format(*(flags[name] for name in FLAG_NAMES))


def _required_sorted(node: Any) -> Any:
    if isinstance(node, dict):
        return {
            k: sorted(v) if k == "required" and isinstance(v, list) else _required_sorted(v) for k, v in node.items()
        }
    if isinstance(node, list):
        return [_required_sorted(v) for v in node]
    return node


def canonical(schema: Any) -> str:
    """The schema as compared: every `required` list sorted, since own elements keep their Ids and the
    copies get new ones, so the order `required` lists them in can change (decided on #1388). Sorting
    keeps duplicates, so a name listed twice on one side and once on the other is a difference. That
    keeps to #1388's reading of D1 as "the same schema as JSON Schema", which requires the items in
    `required` to be unique, so a duplicate is a defect in that schema, not noise (#1506). Every other
    list keeps its order."""
    return json.dumps(_required_sorted(schema), indent=2, sort_keys=True, ensure_ascii=False, default=str)


def duplicate_required(schema: Any, path: str = "") -> list[str]:
    """Every `required` list that names something more than once, as `path: name x count`, so the
    self-check can say why two schemas differ when the diff alone only shows a repeated line (#1506)."""
    found: list[str] = []
    if isinstance(schema, dict):
        for k, v in schema.items():
            here = f"{path}.{k}" if path else str(k)
            if k == "required" and isinstance(v, list):
                counts = Counter(name for name in v if isinstance(name, str))
                found += [f"{here}: {name} x{n}" for name, n in sorted(counts.items()) if n > 1]
            else:
                found += duplicate_required(v, here)
    elif isinstance(schema, list):
        for i, v in enumerate(schema):
            found += duplicate_required(v, f"{path}[{i}]")
    return found


def duplicates_note(expected: Any, after: Any) -> str:
    """The self-check's line naming repeated `required` names, only when the two sides repeat different
    ones, so a duplicate both sides share isn't mistaken for why they differ (#1506)."""
    sides = (("expected", duplicate_required(expected)), ("after", duplicate_required(after)))
    if sides[0][1] == sides[1][1]:
        return ""
    return "".join(f"\n{side} repeats a name in required: {', '.join(found)}" for side, found in sides if found)


def _diff(expected: Any, actual: Any, limit: int = 30) -> str:
    lines = list(
        difflib.unified_diff(
            canonical(expected).splitlines(), canonical(actual).splitlines(), "expected", "after", lineterm=""
        )
    )
    return "\n".join(lines[:limit]) + (f"\n... {len(lines) - limit} more diff lines" if len(lines) > limit else "")


async def generate_matrix(session: AsyncSession, data_model_id: int) -> dict[str, Any]:
    """Every flag combination of the model's generated schema, JSON-encoded as the endpoint encodes it.

    A combination that fails is recorded as its error, as the schema snapshots do (#1387).
    """
    schemas = {}
    for flags in FLAG_MATRIX:
        session.expunge_all()
        try:
            schema = jsonable_encoder(await generate_openapi_schema(session, data_model_id, **flags))
        except HTTPException as e:
            schema = {"x-http-error": {"status_code": e.status_code, "detail": e.detail}}
        schemas[flag_key(flags)] = schema
    session.expunge_all()
    return schemas


def _child_nodes(node: dict) -> Iterable[dict]:
    for child in (node.get("properties") or {}).values():
        if isinstance(child, dict):
            yield child


def _is_entity_node(node: dict) -> bool:
    return "properties" in node


def render_set(full_schema: dict) -> RenderSet:
    """The entities, attributes and embedded / attribute associations a FULL schema renders."""
    rendered = RenderSet()

    def visit(node: dict) -> None:
        if node.get("Id") is not None:
            rendered.entities.add(node["Id"])
        if node.get("EntityAssociationId") is not None:
            rendered.entity_associations.add(node["EntityAssociationId"])
        for child in _child_nodes(node):
            if _is_entity_node(child):
                visit(child)
            elif child.get("Id") is not None:
                rendered.attributes.add(child["Id"])
                if child.get("EntityAttributeAssociationId") is not None:
                    rendered.attribute_associations.add(child["EntityAttributeAssociationId"])

    for node in full_schema["components"]["schemas"].values():
        visit(node)
    return rendered


# --- Rewriting a "before" schema into what the converted model must generate --------------------------


def rewrite_overlay_schema(schema: Any, model_id: int, ids: IdMap) -> Any:
    """The schema the converted overlay must generate, given what it generated before (D1, per key).

    Every element and value set becomes the model's, Ids go through their own kind's map, ExtendedBy is
    cleared, and the elements' and associations' Extension is cleared (§11 Flags).
    """
    schema = json.loads(json.dumps(schema))
    if "components" not in schema:
        return schema

    def rewrite_value_set(value_set: dict) -> None:
        value_set["Id"] = ids.value_sets.get(value_set["Id"], value_set["Id"])
        value_set["DataModelId"] = model_id
        for value in value_set.get("Values") or []:
            value["Id"] = ids.values.get(value["Id"], value["Id"])
            value["ValueSetId"] = ids.value_sets.get(value["ValueSetId"], value["ValueSetId"])
            value["DataModelId"] = model_id

    def rewrite_attribute(node: dict) -> None:
        if "Id" in node:
            node["Id"] = ids.attributes[node["Id"]]
            node["DataModelId"] = model_id
            node["Extension"] = False
            node["ExtensionNotes"] = None
        if node.get("ValueSetId") is not None:
            node["ValueSetId"] = ids.value_sets.get(node["ValueSetId"], node["ValueSetId"])
        if node.get("TargetEntityId") is not None:
            node["TargetEntityId"] = ids.entities[node["TargetEntityId"]]
        if node.get("EntityId") is not None:
            node["EntityId"] = ids.entities[node["EntityId"]]
        if node.get("EntityAttributeAssociationId") is not None:
            node["EntityAttributeAssociationId"] = ids.attribute_associations[node["EntityAttributeAssociationId"]]
        if "AssociationExtendedByDataModelId" in node:
            node["AssociationExtendedByDataModelId"] = None
        if isinstance(node.get("ValueSet"), dict):
            rewrite_value_set(node["ValueSet"])

    def rewrite_entity(node: dict) -> None:
        if "Id" in node:
            node["Id"] = ids.entities[node["Id"]]
            node["DataModelId"] = model_id
            node["Extension"] = False
            node["ExtensionNotes"] = None
        if node.get("EntityAssociationId") is not None:
            node["EntityAssociationId"] = ids.entity_associations[node["EntityAssociationId"]]
            node["EntityAssociationParentEntityId"] = ids.entities[node["EntityAssociationParentEntityId"]]
            node["EntityAssociationExtendedByDataModelId"] = None
            node["EntityAssociationExtension"] = False
            node["EntityAssociationExtensionNotes"] = None
        for child in _child_nodes(node):
            if _is_entity_node(child):
                rewrite_entity(child)
            else:
                rewrite_attribute(child)

    for node in schema["components"]["schemas"].values():
        rewrite_entity(node)
    return schema


def rewrite_base_schema(schema: Any, moved_attributes: dict[int, int]) -> Any:
    """The schema a model the conversion doesn't convert must generate: unchanged, except that step 0's
    moved attributes (attribute Id -> the base model it moved to) now belong to their base."""
    schema = json.loads(json.dumps(schema))
    if "components" not in schema:
        return schema

    def visit(node: dict) -> None:
        for child in _child_nodes(node):
            if _is_entity_node(child):
                visit(child)
            elif child.get("Id") in moved_attributes and "DataModelId" in child:
                child["DataModelId"] = moved_attributes[child["Id"]]

    for node in schema["components"]["schemas"].values():
        visit(node)
    return schema


# --- SQL helpers --------------------------------------------------------------------------------------


async def _rows(session: AsyncSession, sql: str, **params) -> list[dict]:
    result = await session.execute(text(sql), params)
    return [dict(row._mapping) for row in result]


async def _scalar(session: AsyncSession, sql: str, **params) -> Any:
    return (await session.execute(text(sql), params)).scalar()


def _quoted(columns: Iterable[str]) -> str:
    return ", ".join(f'"{column}"' for column in columns)


async def _copy_row(
    session: AsyncSession,
    changes: Changes,
    table: str,
    columns: tuple[str, ...],
    row_id: int,
    overrides: dict[str, Any],
) -> int:
    """Insert a copy of one row with ``overrides`` set; return the new Id. Copies soft-deleted rows too."""
    names = list(columns) + list(overrides)
    selected = [f'"{c}"' for c in columns] + [f":o_{i}" for i in range(len(overrides))]
    params = {f"o_{i}": value for i, value in enumerate(overrides.values())}
    sql = (
        f'INSERT INTO "{table}" ({_quoted(names)}, "Deleted") '
        f'SELECT {", ".join(selected)}, false FROM "{table}" WHERE "Id" = :row_id RETURNING "Id"'
    )
    new_id = await _scalar(session, sql, row_id=row_id, **params)
    changes.inserted.setdefault(table, []).append(new_id)
    return new_id


async def _soft_delete(session: AsyncSession, changes: Changes, table: str, where: str, **params) -> list[int]:
    rows = await _rows(
        session, f'UPDATE "{table}" SET "Deleted" = true WHERE "Deleted" = false AND ({where}) RETURNING "Id"', **params
    )
    deleted = sorted(row["Id"] for row in rows)
    changes.soft_deleted.setdefault(table, []).extend(deleted)
    return deleted


async def _update_row(session: AsyncSession, changes: Changes, table: str, row_id: int, values: dict[str, Any]) -> None:
    """Update one row in place, recording the columns' old values."""
    old = (await _rows(session, f'SELECT "Id", {_quoted(values)} FROM "{table}" WHERE "Id" = :row_id', row_id=row_id))[
        0
    ]
    changes.updated.setdefault(table, []).append(old)
    sets = ", ".join(f'"{name}" = :v_{i}' for i, name in enumerate(values))
    params = {f"v_{i}": value for i, value in enumerate(values.values())}
    await session.execute(text(f'UPDATE "{table}" SET {sets} WHERE "Id" = :row_id'), {**params, "row_id": row_id})


# --- Step 0: move overlay-owned base content to the base ----------------------------------------------


async def move_base_content(session: AsyncSession, changes: Changes, overlay_ids: list[int]) -> dict[int, int]:
    """Step 0 (v3 §2): attributes an overlay owns but its base associates directly (ExtendedBy NULL) are
    base content with the wrong DataModelId (§11). Move them to the base; return attribute Id -> base.
    Refuses any that don't fit."""
    moved: dict[int, int] = {}
    reasons: list[str] = []
    claimed: dict[tuple[int, str], str] = {}  # (base, UniqueName) -> the candidate that moves there first
    for overlay_id in overlay_ids:
        base_id = await _scalar(session, 'SELECT "BaseDataModelId" FROM "DataModels" WHERE "Id" = :m', m=overlay_id)
        candidates = await _rows(
            session,
            """
            SELECT a."Id", a."UniqueName", a."ValueSetId", v."DataModelId" AS "ValueSetModelId",
                   a."TargetEntityId", a."DataType"
            FROM "Attributes" a LEFT JOIN "ValueSets" v ON v."Id" = a."ValueSetId"
            WHERE a."Deleted" = false AND a."DataModelId" = :overlay
              AND EXISTS (SELECT 1 FROM "EntityAttributeAssociation" x
                          JOIN "Entities" e ON e."Id" = x."EntityId" AND e."Deleted" = false
                          WHERE x."AttributeId" = a."Id" AND x."Deleted" = false
                            AND x."ExtendedByDataModelId" IS NULL AND e."DataModelId" = :base)
            ORDER BY a."Id"
            """,
            overlay=overlay_id,
            base=base_id,
        )
        for attribute in candidates:
            attribute_id = attribute["Id"]
            name = f"attribute {attribute_id} {attribute['UniqueName']!r} (model {overlay_id})"
            if await _scalar(
                session,
                'SELECT count(*) FROM "Attributes" WHERE "Deleted" = false AND "DataModelId" = :base '
                'AND "UniqueName" = :unique_name',
                base=base_id,
                unique_name=attribute["UniqueName"],
            ):
                reasons.append(f"{name}: its UniqueName is already live in base model {base_id}")
            if (base_id, attribute["UniqueName"]) in claimed:
                reasons.append(
                    f"{name}: {claimed[(base_id, attribute['UniqueName'])]} would also move to base model {base_id} "
                    "with the same UniqueName"
                )
            claimed.setdefault((base_id, attribute["UniqueName"]), f"attribute {attribute_id} (model {overlay_id})")
            if attribute["ValueSetId"] is not None and attribute["ValueSetModelId"] != base_id:
                reasons.append(f"{name}: uses value set {attribute['ValueSetId']} from outside the base model")
            if attribute["TargetEntityId"] is not None or (attribute["DataType"] or "").lower() == "entity":
                reasons.append(f"{name}: is entity-typed")
            others = await _scalar(
                session,
                """
                SELECT count(*) FROM "EntityAttributeAssociation" x
                JOIN "Entities" e ON e."Id" = x."EntityId"
                WHERE x."AttributeId" = :a AND x."Deleted" = false
                  AND NOT (x."ExtendedByDataModelId" IS NULL AND e."DataModelId" = :base AND e."Deleted" = false)
                """,
                a=attribute_id,
                base=base_id,
            )
            if others:
                reasons.append(f"{name}: has {others} other live association(s)")
            if not await _scalar(
                session,
                'SELECT count(*) FROM "ExtInclusionsFromBaseDM" WHERE "Deleted" = false AND "ExtDataModelId" = :m '
                'AND "ElementType"::text = \'Attribute\' AND "IncludedElementId" = :a',
                m=overlay_id,
                a=attribute_id,
            ):
                reasons.append(f"{name}: its overlay doesn't include it")
            moved[attribute_id] = base_id
    if reasons:
        raise ConversionFailed(reasons)
    for attribute_id, base_id in moved.items():
        await _update_row(session, changes, "Attributes", attribute_id, {"DataModelId": base_id})
    return moved


# --- Steps 1-8 for one overlay ------------------------------------------------------------------------


async def _reference_associations(session: AsyncSession, model_id: int, entity_ids: set[int]) -> set[int]:
    """The Reference associations the overlay's generator reads (both ends shown; own or no ExtendedBy)."""
    rows = await _rows(
        session,
        """
        SELECT "Id" FROM "EntityAssociation"
        WHERE "Deleted" = false AND "Placement" = 'Reference'
          AND "ParentEntityId" = ANY(:ids) AND "ChildEntityId" = ANY(:ids)
          AND ("ExtendedByDataModelId" = :m OR "ExtendedByDataModelId" IS NULL)
        """,
        ids=list(entity_ids),
        m=model_id,
    )
    return {row["Id"] for row in rows}


async def _inclusion_flags(session: AsyncSession, model_id: int) -> dict[tuple[str, int], dict]:
    rows = await _rows(
        session,
        """
        SELECT "ElementType"::text AS kind, "IncludedElementId" AS id,
               "LevelOfAccess"::text AS "LevelOfAccess", "Queryable", "Modifiable"
        FROM "ExtInclusionsFromBaseDM" WHERE "ExtDataModelId" = :m AND "Deleted" = false ORDER BY "Id"
        """,
        m=model_id,
    )
    flags: dict[tuple[str, int], dict] = {}
    for row in rows:
        key = (row["kind"], row["id"])
        value = {k: row[k] for k in ("LevelOfAccess", "Queryable", "Modifiable")}
        if key in flags and flags[key] != value:
            raise ConversionFailed([f"model {model_id}: inclusion rows for {key[0]} {key[1]} disagree on flags"])
        flags.setdefault(key, value)
    return flags


async def _owners(session: AsyncSession, table: str, ids: Iterable[int]) -> dict[int, int]:
    rows = await _rows(session, f'SELECT "Id", "DataModelId" FROM "{table}" WHERE "Id" = ANY(:ids)', ids=list(ids))
    return {row["Id"]: row["DataModelId"] for row in rows}


def _map_path(path: str, ids: IdMap) -> Optional[str]:
    """Re-point an EntityIdPath (entity Ids, negated attribute Ids). None when a node isn't in the map."""
    nodes = []
    for raw in path.split(","):
        node = raw.strip()
        if not node.lstrip("-").isdigit():
            return None
        value = int(node)
        mapped = ids.entities.get(value) if value > 0 else ids.attributes.get(-value)
        if mapped is None:
            return None
        nodes.append(str(mapped if value > 0 else -mapped))
    return ",".join(nodes)


async def convert_model(session: AsyncSession, changes: Changes, model_id: int, full_schema: dict) -> ModelReport:
    """Steps 1-8 for one overlay. ``full_schema`` is its FULL schema from before the conversion."""
    reasons: list[str] = []
    model = (await _rows(session, 'SELECT * FROM "DataModels" WHERE "Id" = :m', m=model_id))[0]
    if model["BaseDataModelId"] is None:
        raise ConversionFailed([f"model {model_id}: has inclusion rows but no BaseDataModelId (#1445)"])
    base = (await _rows(session, 'SELECT * FROM "DataModels" WHERE "Id" = :m', m=model["BaseDataModelId"]))[0]

    # Step 1: what the schema shows.
    rendered = render_set(full_schema)
    rendered.entity_associations |= await _reference_associations(session, model_id, rendered.entities)
    flags = await _inclusion_flags(session, model_id)
    entity_owner = await _owners(session, "Entities", rendered.entities)
    attribute_owner = await _owners(session, "Attributes", rendered.attributes)
    for kind, ids in (("Entity", rendered.entities), ("Attribute", rendered.attributes)):
        for element_id in sorted(ids):
            if (kind, element_id) not in flags:
                reasons.append(f"model {model_id}: {kind} {element_id} is shown but has no inclusion row")
    if reasons:
        raise ConversionFailed(reasons)

    ids = IdMap()
    soft_deleted: dict[str, list[int]] = {}
    copied = {"entities": 0, "attributes": 0, "value_sets": 0, "values": 0, "entity_associations": 0,
              "attribute_associations": 0}  # fmt: skip

    def element_overrides(kind: str, element_id: int) -> dict:
        return {**flags[(kind, element_id)], "DataModelId": model_id, "Extension": False, "ExtensionNotes": None}

    # Step 6 first: own elements the schema doesn't show are soft-deleted before anything is copied, so a
    # copy can't collide with one of them on UniqueName (an override's hidden side, say).
    own_shown_entities = [e for e, owner in entity_owner.items() if owner == model_id]
    own_shown_attributes = [a for a, owner in attribute_owner.items() if owner == model_id]
    soft_deleted["Entities"] = await _soft_delete(
        session,
        changes,
        "Entities",
        '"DataModelId" = :m AND NOT ("Id" = ANY(:ids))',
        m=model_id,
        ids=own_shown_entities,
    )
    soft_deleted["Attributes"] = await _soft_delete(
        session,
        changes,
        "Attributes",
        '"DataModelId" = :m AND NOT ("Id" = ANY(:ids))',
        m=model_id,
        ids=own_shown_attributes,
    )
    for kind, table, owner in (("Entity", "Entities", entity_owner), ("Attribute", "Attributes", attribute_owner)):
        rows = await _rows(
            session,
            f'SELECT "Id", "UniqueName", "DataModelId" FROM "{table}" '
            'WHERE "Id" = ANY(:ids) OR ("DataModelId" = :m AND "Deleted" = false)',
            ids=list(owner),
            m=model_id,
        )
        by_name: dict[str, list[int]] = {}
        for row in rows:
            if row["Id"] in owner or row["DataModelId"] == model_id:
                by_name.setdefault(row["UniqueName"], []).append(row["Id"])
        for unique_name, holders in sorted(by_name.items()):
            if len(set(holders)) > 1:
                reasons.append(
                    f"model {model_id}: {kind} UniqueName {unique_name!r} would be held by {sorted(set(holders))}"
                )
    if reasons:
        raise ConversionFailed(reasons)

    # Steps 2 and 3: own elements keep their Ids and take their flags; foreign ones are copied in Id order.
    for kind, table, columns, owner, id_map in (
        ("Entity", "Entities", ENTITY_COLUMNS, entity_owner, ids.entities),
        ("Attribute", "Attributes", ATTRIBUTE_COLUMNS, attribute_owner, ids.attributes),
    ):
        for element_id in sorted(owner):
            overrides = element_overrides(kind, element_id)
            if owner[element_id] == model_id:
                await _update_row(session, changes, table, element_id, overrides)
                id_map[element_id] = element_id
            else:
                id_map[element_id] = await _copy_row(session, changes, table, columns, element_id, overrides)
                copied["entities" if kind == "Entity" else "attributes"] += 1

    # Step 4: value sets used from another model, then entity targets.
    shown_attributes = await _rows(
        session,
        """
        SELECT a."Id", a."ValueSetId", v."DataModelId" AS "ValueSetModelId", a."TargetEntityId"
        FROM "Attributes" a LEFT JOIN "ValueSets" v ON v."Id" = a."ValueSetId"
        WHERE a."Id" = ANY(:ids) ORDER BY a."Id"
        """,
        ids=list(ids.attributes.values()),
    )
    for value_set_id in sorted(
        {a["ValueSetId"] for a in shown_attributes if a["ValueSetId"] and a["ValueSetModelId"] != model_id}
    ):
        new_id = await _copy_row(
            session, changes, "ValueSets", VALUE_SET_COLUMNS, value_set_id, {"DataModelId": model_id}
        )
        ids.value_sets[value_set_id] = new_id
        copied["value_sets"] += 1
        for value in await _rows(
            session,
            'SELECT "Id" FROM "ValueSetValues" WHERE "ValueSetId" = :v AND "Deleted" = false ORDER BY "Id"',
            v=value_set_id,
        ):
            ids.values[value["Id"]] = await _copy_row(
                session,
                changes,
                "ValueSetValues",
                VALUE_COLUMNS,
                value["Id"],
                {"ValueSetId": new_id, "DataModelId": model_id},
            )
            copied["values"] += 1
    for attribute in shown_attributes:
        updates: dict[str, Any] = {}
        if attribute["ValueSetId"] in ids.value_sets:
            updates["ValueSetId"] = ids.value_sets[attribute["ValueSetId"]]
        if attribute["TargetEntityId"] is not None:
            if attribute["TargetEntityId"] not in ids.entities:
                reasons.append(
                    f"model {model_id}: attribute {attribute['Id']} targets entity {attribute['TargetEntityId']}, "
                    "which the schema doesn't show"
                )
                continue
            updates["TargetEntityId"] = ids.entities[attribute["TargetEntityId"]]
        if updates:
            await _update_row(session, changes, "Attributes", attribute["Id"], updates)

    # Step 5: associations. One whose parent is the model's own is rewritten in place; any other is
    # copied between the model's rows, and the original is soft-deleted only if the model declared it.
    for table, parent, child, columns, shown, id_map, extension in (
        ("EntityAssociation", "ParentEntityId", "ChildEntityId", ENTITY_ASSOCIATION_COLUMNS,
         rendered.entity_associations, ids.entity_associations, True),
        ("EntityAttributeAssociation", "EntityId", "AttributeId", ATTRIBUTE_ASSOCIATION_COLUMNS,
         rendered.attribute_associations, ids.attribute_associations, False),
    ):  # fmt: skip
        child_map = ids.entities if table == "EntityAssociation" else ids.attributes
        for row in await _rows(
            session,
            f'SELECT "Id", "{parent}" AS parent, "{child}" AS child, "ExtendedByDataModelId" AS extended_by '
            f'FROM "{table}" WHERE "Id" = ANY(:ids) ORDER BY "Id"',
            ids=list(shown),
        ):
            if row["parent"] not in ids.entities or row["child"] not in child_map:
                reasons.append(f"model {model_id}: {table} {row['Id']} is shown but an end isn't")
                continue
            overrides: dict[str, Any] = {
                parent: ids.entities[row["parent"]],
                child: child_map[row["child"]],
                "ExtendedByDataModelId": None,
            }
            if extension:
                overrides.update({"Extension": False, "ExtensionNotes": None})
            if entity_owner.get(row["parent"]) == model_id:
                await _update_row(session, changes, table, row["Id"], overrides)
                id_map[row["Id"]] = row["Id"]
            else:
                id_map[row["Id"]] = await _copy_row(session, changes, table, columns, row["Id"], overrides)
                copied["entity_associations" if table == "EntityAssociation" else "attribute_associations"] += 1
        kept = [old for old, new in id_map.items() if old == new]
        copies = [new for old, new in id_map.items() if old != new]
        soft_deleted[table] = await _soft_delete(
            session,
            changes,
            table,
            f'("ExtendedByDataModelId" = :m OR "{parent}" IN (SELECT "Id" FROM "Entities" WHERE "DataModelId" = :m)) '
            'AND NOT ("Id" = ANY(:kept)) AND NOT ("Id" = ANY(:copies))',
            m=model_id,
            kept=kept,
            copies=copies,
        )
    if reasons:
        raise ConversionFailed(reasons)

    # Step 7: the model row and its inclusion rows.
    soft_deleted["ExtInclusionsFromBaseDM"] = await _soft_delete(
        session, changes, "ExtInclusionsFromBaseDM", '"ExtDataModelId" = :m', m=model_id
    )
    await _update_row(
        session,
        changes,
        "DataModels",
        model_id,
        {
            "BaseDataModelId": None,
            "CopiedFromName": base["Name"],
            "CopiedFromVersion": base["DataModelVersion"],
            "CopiedFromContributorOrganization": base["ContributorOrganization"],
        },
    )

    # Step 8: mapping rows on the model's side.
    updated = []
    for row in await _rows(
        session,
        """
        SELECT ta."Id", ta."EntityId", ta."AttributeId", ta."EntityIdPath", t."Id" AS rule, g."Id" AS "group"
        FROM "TransformationsGroup" g
        JOIN "Transformations" t ON t."TransformationGroupId" = g."Id" AND t."Deleted" = false
        JOIN "TransformationAttributes" ta ON ta."TransformationId" = t."Id" AND ta."Deleted" = false
        WHERE g."Deleted" = false
          AND :m = CASE ta."AttributeType"::text WHEN 'Source' THEN g."SourceDataModelId"
                                                 WHEN 'Target' THEN g."TargetDataModelId" END
        ORDER BY ta."Id"
        """,
        m=model_id,
    ):
        where = f"model {model_id}: mapping row {row['Id']} (group {row['group']}, rule {row['rule']})"
        path = _map_path(row["EntityIdPath"], ids) if row["EntityIdPath"] else row["EntityIdPath"]
        entity_id = ids.entities.get(row["EntityId"]) if row["EntityId"] is not None else None
        attribute_id = ids.attributes.get(row["AttributeId"]) if row["AttributeId"] is not None else None
        if (
            (row["EntityIdPath"] and path is None)
            or (row["EntityId"] is not None and entity_id is None)
            or (row["AttributeId"] is not None and attribute_id is None)
        ):
            reasons.append(f"{where}: path {row['EntityIdPath']!r} goes through a row the schema doesn't show")
            continue
        await _update_row(
            session,
            changes,
            "TransformationAttributes",
            row["Id"],
            {"EntityId": entity_id, "AttributeId": attribute_id, "EntityIdPath": path},
        )
        updated.append(row["Id"])
    if reasons:
        raise ConversionFailed(reasons)

    return ModelReport(model_id, ids, copied, soft_deleted, updated)


# --- The whole conversion ------------------------------------------------------------------------------


async def _models_to_compare(session: AsyncSession, overlay_ids: list[int], renders: dict[int, RenderSet]) -> list[int]:
    """The overlays, their bases, and every model owning an element an overlay shows."""
    models = set(overlay_ids)
    for overlay_id in overlay_ids:
        models.add(await _scalar(session, 'SELECT "BaseDataModelId" FROM "DataModels" WHERE "Id" = :m', m=overlay_id))
        models |= set((await _owners(session, "Entities", renders[overlay_id].entities)).values())
        models |= set((await _owners(session, "Attributes", renders[overlay_id].attributes)).values())
    return sorted(m for m in models if m is not None)


async def outside_references(session: AsyncSession, changes: Changes, compared_ids: list[int]) -> list[str]:
    """Live rows, after the conversion, that use a row it soft-deleted or changed in place, where the
    self-check can't see the effect: their model isn't one it compares. A mapping row using a
    soft-deleted element is always reported, since the comparison doesn't read mapping rows.

    A row belongs to the model that declares it: an association to its ``ExtendedByDataModelId``, or
    with none to its parent's model; an inclusion row to its overlay; an attribute to its model.
    """
    inserted = {table: set(ids) for table, ids in changes.inserted.items()}

    def touched(table: str) -> list[int]:
        updated = {row["Id"] for row in changes.updated.get(table, [])} - inserted.get(table, set())
        return sorted(updated | set(changes.soft_deleted.get(table, [])))

    entities, attributes = touched("Entities"), touched("Attributes")
    deleted_entities = changes.soft_deleted.get("Entities", [])
    deleted_attributes = changes.soft_deleted.get("Attributes", [])
    params = {"e": entities, "a": attributes, "compared": compared_ids}
    queries = (
        """
        SELECT 'EntityAssociation ' || x."Id" AS what, coalesce(x."ExtendedByDataModelId", p."DataModelId") AS owner,
               'uses entity ' || CASE WHEN x."ParentEntityId" = ANY(:e) THEN x."ParentEntityId"
                                      ELSE x."ChildEntityId" END AS how
        FROM "EntityAssociation" x JOIN "Entities" p ON p."Id" = x."ParentEntityId"
        WHERE x."Deleted" = false AND (x."ParentEntityId" = ANY(:e) OR x."ChildEntityId" = ANY(:e))
        """,
        """
        SELECT 'EntityAttributeAssociation ' || x."Id" AS what,
               coalesce(x."ExtendedByDataModelId", e."DataModelId") AS owner,
               CASE WHEN x."AttributeId" = ANY(:a) THEN 'uses attribute ' || x."AttributeId"
                    ELSE 'uses entity ' || x."EntityId" END AS how
        FROM "EntityAttributeAssociation" x JOIN "Entities" e ON e."Id" = x."EntityId"
        WHERE x."Deleted" = false AND (x."EntityId" = ANY(:e) OR x."AttributeId" = ANY(:a))
        """,
        """
        SELECT 'attribute ' || "Id" AS what, "DataModelId" AS owner, 'targets entity ' || "TargetEntityId" AS how
        FROM "Attributes" WHERE "Deleted" = false AND "TargetEntityId" = ANY(:e)
        """,
        """
        SELECT 'inclusion row ' || "Id" AS what, "ExtDataModelId" AS owner,
               'includes ' || lower("ElementType"::text) || ' ' || "IncludedElementId" AS how
        FROM "ExtInclusionsFromBaseDM"
        WHERE "Deleted" = false AND (("ElementType"::text = 'Entity' AND "IncludedElementId" = ANY(:e))
                                  OR ("ElementType"::text = 'Attribute' AND "IncludedElementId" = ANY(:a)))
        """,
    )
    reasons = []
    for sql in queries:
        for row in await _rows(
            session,
            f"SELECT * FROM ({sql}) r WHERE NOT (coalesce(r.owner, 0) = ANY(:compared)) ORDER BY r.what",
            **params,
        ):
            reasons.append(f"{row['what']} (model {row['owner']}) {row['how']}, which the conversion changes")

    # A soft-deleted association whose model the self-check doesn't compare.
    for table, parent in (("EntityAssociation", "ParentEntityId"), ("EntityAttributeAssociation", "EntityId")):
        for row in await _rows(
            session,
            f"""
            SELECT x."Id", coalesce(x."ExtendedByDataModelId", p."DataModelId") AS owner
            FROM "{table}" x JOIN "Entities" p ON p."Id" = x."{parent}"
            WHERE x."Id" = ANY(:ids)
              AND NOT (coalesce(x."ExtendedByDataModelId", p."DataModelId", 0) = ANY(:compared))
            ORDER BY x."Id"
            """,
            ids=changes.soft_deleted.get(table, []),
            compared=compared_ids,
        ):
            reasons.append(f"{table} {row['Id']} (model {row['owner']}) is soft-deleted by the conversion")

    # A live mapping row on any side that still goes through a soft-deleted element.
    path_nodes = [str(e) for e in deleted_entities] + [f"-{a}" for a in deleted_attributes]
    for row in await _rows(
        session,
        """
        SELECT ta."Id", g."Id" AS "group", ta."EntityIdPath" FROM "TransformationAttributes" ta
        JOIN "Transformations" t ON t."Id" = ta."TransformationId" AND t."Deleted" = false
        JOIN "TransformationsGroup" g ON g."Id" = t."TransformationGroupId" AND g."Deleted" = false
        WHERE ta."Deleted" = false
          AND (ta."EntityId" = ANY(:e) OR ta."AttributeId" = ANY(:a)
               OR EXISTS (SELECT 1 FROM unnest(string_to_array(replace(ta."EntityIdPath", ' ', ''), ',')) n
                          WHERE n = ANY(:nodes)))
        ORDER BY ta."Id"
        """,
        e=deleted_entities,
        a=deleted_attributes,
        nodes=path_nodes,
    ):
        reasons.append(
            f"mapping row {row['Id']} (group {row['group']}) goes through {row['EntityIdPath']!r}, "
            "a row the conversion soft-deletes"
        )
    return reasons


async def convert_overlays(session: AsyncSession, overlay_ids: list[int]) -> Report:
    """Convert the overlays, in order, and check the result. Raises ``ConversionFailed`` with every
    reason; the caller rolls back. Commits nothing."""
    baseline = {model_id: await generate_matrix(session, model_id) for model_id in overlay_ids}
    for model_id, schemas in baseline.items():
        errors = [key for key, schema in schemas.items() if "x-http-error" in schema]
        if errors:
            raise ConversionFailed([f"model {model_id}: its schema fails today in {', '.join(errors)}"])
    renders = {model_id: render_set(baseline[model_id][FULL]) for model_id in overlay_ids}
    compared_ids = await _models_to_compare(session, overlay_ids, renders)
    for model_id in compared_ids:
        if model_id not in baseline:
            baseline[model_id] = await generate_matrix(session, model_id)

    changes = Changes()
    moved = await move_base_content(session, changes, overlay_ids)
    reports = [await convert_model(session, changes, model_id, baseline[model_id][FULL]) for model_id in overlay_ids]

    failures = await outside_references(session, changes, compared_ids)
    expected_by_model = {}
    for report in reports:
        expected_by_model[report.model_id] = {
            key: rewrite_overlay_schema(schema, report.model_id, report.id_map)
            for key, schema in baseline[report.model_id].items()
        }
    for model_id in compared_ids:
        if model_id not in expected_by_model:
            expected_by_model[model_id] = {
                key: rewrite_base_schema(schema, moved) for key, schema in baseline[model_id].items()
            }
    for model_id in compared_ids:
        after = await generate_matrix(session, model_id)
        for key, expected in expected_by_model[model_id].items():
            if canonical(after[key]) != canonical(expected):
                duplicates = duplicates_note(expected, after[key])
                failures.append(
                    f"model {model_id}: {key} differs from the rewritten baseline{duplicates}\n"
                    f"{_diff(expected, after[key])}"
                )

    for model_id in overlay_ids:
        try:
            await export_model(session, model_id)
        except Exception as e:  # noqa: BLE001 - every refusal is reported
            failures.append(f"model {model_id}: export refuses: {e}")
    for group in await _rows(
        session,
        'SELECT "Id" FROM "TransformationsGroup" WHERE "Deleted" = false '
        'AND ("SourceDataModelId" = ANY(:ids) OR "TargetDataModelId" = ANY(:ids)) ORDER BY "Id"',
        ids=list(overlay_ids),
    ):
        try:
            await export_mapping_group(session, group["Id"])
        except Exception as e:  # noqa: BLE001 - every refusal is reported
            failures.append(f"group {group['Id']}: export refuses: {e}")
    if failures:
        raise ConversionFailed(failures)
    compared = {model_id: sorted(expected_by_model[model_id]) for model_id in compared_ids}
    return Report(moved, reports, compared, changes)

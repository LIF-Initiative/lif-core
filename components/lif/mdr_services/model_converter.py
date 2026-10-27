"""Convert between a data model's rows and a portable model file (issue #1333).

Portability Spec §5 and §8: export_model reads a model into a ModelFile, and import_model writes one as
a new model. Neither function commits; the caller owns the transaction.

Export refuses a model that still uses a construct §11 deprecates (NOT_MIGRATED), naming the
construct and the element, rather than turning old content into new. Such a model is refused before
its file is built, since the file could not describe it faithfully. Otherwise the file goes through
parse_model_file and check_model_file, so export never produces a file that import would refuse, and
stored values the format does not allow (a blank Name, a NULL ValueName) are refused by name.

Callers reach it through portability_converter, the converter module for every file kind (§8).
"""

import json
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from typing import Any, NamedTuple, Optional, Union

from lif.mdr_portability import (
    ModelFile,
    PortabilityError,
    PortabilityErrorCode,
    PortabilityErrorGroup,
    check_model_file,
    parse_model_file,
)
from lif.mdr_portability.v1.models import Association as FileAssociation
from lif.mdr_portability.v1.models import AttributeKey, EntityKey
from lif.mdr_portability.errors import error_group
from lif.mdr_sql_model.core import (
    Attribute,
    Constraint,
    DataModel,
    DataModelConstraints,
    DataModelType,
    Entity,
    EntityAssociation,
    EntityAttributeAssociation,
    EntityPlacementType,
    ExtInclusionsFromBaseDM,
    ValueSet,
    ValueSetValue,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import func, or_, select

Code = PortabilityErrorCode

AnyAssociation = Union[EntityAssociation, EntityAttributeAssociation]


class _ResolvedElement(NamedTuple):
    # An element an association or attribute names: its model, and the key the file names it by.
    model_id: int
    key: str


@dataclass(frozen=True)
class _ModelRows:
    """One model's live rows, and the live associations that touch its entities or attributes."""

    model_id: int
    value_sets: list[ValueSet]
    values: dict[int, list[ValueSetValue]]  # value set Id -> its values
    entities: list[Entity]
    attributes: list[Attribute]
    entity_associations: list[EntityAssociation]
    attribute_associations: list[EntityAttributeAssociation]
    # The last four fields guard export against content the format cannot hold (§11).
    #
    # Every live entity, attribute and value set those rows name, from any model, resolved from its Id.
    # An element in another model is refused as NOT_MIGRATED, unless the association belongs to that
    # other model, such as an overlay's addition, which is left out. The key is what the file names it by.
    resolved_entities: dict[int, _ResolvedElement]
    resolved_attributes: dict[int, _ResolvedElement]
    resolved_value_sets: dict[int, _ResolvedElement]
    # Constraint and DataModelConstraints rows; any at all are refused as NOT_MIGRATED.
    constraint_count: int


async def export_model(session: AsyncSession, data_model_id: int) -> ModelFile:
    """Read a live model into a portable file, or refuse with every reason at once."""
    model = await session.get(DataModel, data_model_id)
    if model is None or model.Deleted:
        raise error_group([PortabilityError(Code.MODEL_MISSING, "Details", f"model {data_model_id} is not installed")])
    # An overlay is refused on that alone: converting it replaces every row the other checks would name.
    overlay = await _check_for_overlay(session, model)
    if overlay:
        raise error_group(overlay)
    rows = await _load_rows(session, data_model_id)
    not_migrated = list(_check_for_deprecated_content(rows))
    if not_migrated:
        raise error_group(not_migrated)

    content = {
        "Format": {"Type": "lif-mdr-model", "Version": 1},
        "Details": _export_details(model),
        "ValueSets": [_export_value_set(value_set, rows.values.get(value_set.Id, [])) for value_set in rows.value_sets],
        "Entities": [_export_entity(entity) for entity in rows.entities],
        "Attributes": [_export_attribute(attribute, rows) for attribute in rows.attributes],
        "Associations": [_export_association(association, rows) for association in _list_own_associations(rows)],
    }
    # Through the parser, so stored values the format does not allow are refused by name.
    file = parse_model_file(json.dumps(_without_nulls(content), default=_to_json).encode("utf-8"))
    check_model_file(file)
    return file


async def _load_rows(session: AsyncSession, data_model_id: int) -> _ModelRows:
    async def all_rows(statement) -> list:
        return list((await session.execute(statement)).scalars())

    value_sets = await all_rows(
        select(ValueSet).where(ValueSet.DataModelId == data_model_id, ValueSet.Deleted == False).order_by(ValueSet.Id)
    )
    values: dict[int, list[ValueSetValue]] = {}
    for value in await all_rows(
        select(ValueSetValue)
        .where(ValueSetValue.ValueSetId.in_([value_set.Id for value_set in value_sets]), ValueSetValue.Deleted == False)
        .order_by(ValueSetValue.Id)
    ):
        values.setdefault(value.ValueSetId, []).append(value)
    entities = await all_rows(
        select(Entity).where(Entity.DataModelId == data_model_id, Entity.Deleted == False).order_by(Entity.Id)
    )
    attributes = await all_rows(
        select(Attribute)
        .where(Attribute.DataModelId == data_model_id, Attribute.Deleted == False)
        .order_by(Attribute.Id)
    )
    entity_ids = [entity.Id for entity in entities]
    attribute_ids = [attribute.Id for attribute in attributes]
    entity_associations = await all_rows(
        select(EntityAssociation)
        .where(
            or_(EntityAssociation.ParentEntityId.in_(entity_ids), EntityAssociation.ChildEntityId.in_(entity_ids)),
            EntityAssociation.Deleted == False,
        )
        .order_by(EntityAssociation.Id)
    )
    attribute_associations = await all_rows(
        select(EntityAttributeAssociation)
        .where(
            or_(
                EntityAttributeAssociation.EntityId.in_(entity_ids),
                EntityAttributeAssociation.AttributeId.in_(attribute_ids),
            ),
            EntityAttributeAssociation.Deleted == False,
        )
        .order_by(EntityAttributeAssociation.Id)
    )

    # The ends of those associations, and the value sets attributes use, may be in other models.
    entity_ids_to_resolve = {association.ParentEntityId for association in entity_associations}
    entity_ids_to_resolve |= {association.ChildEntityId for association in entity_associations}
    entity_ids_to_resolve |= {association.EntityId for association in attribute_associations}
    attribute_ids_to_resolve = {association.AttributeId for association in attribute_associations}
    used_value_set_ids = {attribute.ValueSetId for attribute in attributes if attribute.ValueSetId is not None}

    async def resolve(model_class, key_column, ids) -> dict[int, _ResolvedElement]:
        found = await session.execute(
            select(model_class.Id, model_class.DataModelId, key_column.label("key")).where(
                model_class.Id.in_(ids), model_class.Deleted == False
            )
        )
        return {row.Id: _ResolvedElement(row.DataModelId, row.key) for row in found}

    constraint_count = (
        await session.execute(
            select(func.count())
            .select_from(Constraint)
            .where(Constraint.AttributeId.in_(attribute_ids), Constraint.Deleted == False)
        )
    ).scalar_one()
    constraint_count += (
        await session.execute(
            select(func.count())
            .select_from(DataModelConstraints)
            .where(DataModelConstraints.ForDataModelId == data_model_id, DataModelConstraints.Deleted == False)
        )
    ).scalar_one()

    resolved_entities = await resolve(Entity, Entity.UniqueName, entity_ids_to_resolve)
    resolved_attributes = await resolve(Attribute, Attribute.UniqueName, attribute_ids_to_resolve)
    # An association to a soft-deleted element counts as absent (§2), so only those are dropped here.
    # Ends in other models are kept for the ownership and NOT_MIGRATED checks.
    return _ModelRows(
        model_id=data_model_id,
        value_sets=value_sets,
        values=values,
        entities=entities,
        attributes=attributes,
        entity_associations=[
            association
            for association in entity_associations
            if association.ParentEntityId in resolved_entities and association.ChildEntityId in resolved_entities
        ],
        attribute_associations=[
            association
            for association in attribute_associations
            if association.EntityId in resolved_entities and association.AttributeId in resolved_attributes
        ],
        resolved_entities=resolved_entities,
        resolved_attributes=resolved_attributes,
        resolved_value_sets=await resolve(ValueSet, ValueSet.Name, used_value_set_ids),
        constraint_count=constraint_count,
    )


def _get_association_elements(
    rows: _ModelRows, association: AnyAssociation
) -> tuple[_ResolvedElement, _ResolvedElement]:
    # The parent entity, and the child, entity or attribute.
    if isinstance(association, EntityAssociation):
        return rows.resolved_entities[association.ParentEntityId], rows.resolved_entities[association.ChildEntityId]
    return rows.resolved_entities[association.EntityId], rows.resolved_attributes[association.AttributeId]


def _get_association_owner(rows: _ModelRows, association: AnyAssociation) -> Optional[int]:
    # The model an association belongs to (§11). Undeclared, it is its parent's. Declared
    # (ExtendedByDataModelId) by a model that owns one of its ends, it is the declarer's, as an
    # overlay's additions to its base model are. Declared by a model that owns neither end, it belongs
    # to the model both ends are in, and to no model if the ends are in two.
    parent, child = _get_association_elements(rows, association)
    declared_by = association.ExtendedByDataModelId
    if declared_by is None:
        return parent.model_id
    if declared_by in (parent.model_id, child.model_id):
        return declared_by
    return parent.model_id if parent.model_id == child.model_id else None


def _get_association_path(rows: _ModelRows, association: AnyAssociation) -> str:
    parent, _ = _get_association_elements(rows, association)
    return f"Associations[{parent.key}, {association.Name or ''}]"


def _list_own_associations(rows: _ModelRows) -> Iterator[AnyAssociation]:
    # Associations another model owns, such as an overlay's additions to this model's entities, are
    # that model's content, and are left out.
    for association in [*rows.entity_associations, *rows.attribute_associations]:
        if _get_association_owner(rows, association) == rows.model_id:
            yield association


async def _check_for_overlay(session: AsyncSession, model: DataModel) -> list[PortabilityError]:
    # An overlay reads its elements through its base model and inclusion rows, so its own rows don't
    # describe it. It is detected by those, not by its Type (§8: no type names).
    inclusion = (
        await session.execute(
            select(ExtInclusionsFromBaseDM.Id)
            .where(ExtInclusionsFromBaseDM.ExtDataModelId == model.Id, ExtInclusionsFromBaseDM.Deleted == False)
            .limit(1)
        )
    ).first()
    if model.BaseDataModelId is None and inclusion is None:
        return []
    return [_not_migrated("Details", f"{model.Name!r} is an overlay; convert it to a copy first (ADR data_model/0004)")]


def _check_for_deprecated_content(rows: _ModelRows) -> Iterator[PortabilityError]:
    # Each §11 construct a self-contained model's own rows can still hold.
    for value_set in rows.value_sets:
        if _uses_extension(value_set):
            yield _not_migrated(f"ValueSets[{value_set.Name}]", "the value set uses Extension")
        for value in rows.values.get(value_set.Id, []):
            if _uses_extension(value):
                yield _not_migrated(
                    f"ValueSets[{value_set.Name}].Values[{value.ValueName}]", "the value uses Extension"
                )
    for entity in rows.entities:
        if _uses_extension(entity):
            yield _not_migrated(f"Entities[{entity.UniqueName}]", "the entity uses Extension")

    own_associations = list(_list_own_associations(rows))
    associated_attribute_ids = {
        association.AttributeId
        for association in own_associations
        if isinstance(association, EntityAttributeAssociation)
    }
    for attribute in rows.attributes:
        element = f"Attributes[{attribute.UniqueName}]"
        if _uses_extension(attribute):
            yield _not_migrated(element, "the attribute uses Extension")
        if attribute.DataType is None:
            yield _not_migrated(element, "the attribute has no DataType; migration sets string")
        elif attribute.DataType.lower() == "entity" or attribute.TargetEntityId is not None:
            yield _not_migrated(element, "the attribute has DataType entity; it becomes an association to the entity")
        value_set = rows.resolved_value_sets.get(attribute.ValueSetId) if attribute.ValueSetId is not None else None
        if value_set is not None and value_set.model_id != rows.model_id:
            yield _not_migrated(f"{element}.ValueSet", f"the value set {value_set.key!r} is in another model")
        if attribute.Id not in associated_attribute_ids:
            yield _not_migrated(element, "the attribute is in no association; migration drops it")

    for association in own_associations:
        element = _get_association_path(rows, association)
        parent, child = _get_association_elements(rows, association)
        if association.ExtendedByDataModelId is not None:
            yield _not_migrated(element, "the association is declared with ExtendedByDataModelId")
        if parent.model_id != child.model_id:
            yield _not_migrated(element, f"the child {child.key!r} is in another model")
        if isinstance(association, EntityAssociation) and _uses_extension(association):
            yield _not_migrated(element, "the association uses Extension")
        if not association.Name:
            yield _not_migrated(element, f"the association to {child.key!r} has no Name; V1.7 sets one")

    if rows.constraint_count:
        yield _not_migrated("Details", f"the model has {rows.constraint_count} constraint rows")


def _uses_extension(row: Any) -> bool:
    return bool(row.Extension) or bool(row.ExtensionNotes)


def _not_migrated(element: str, reason: str) -> PortabilityError:
    return PortabilityError(Code.NOT_MIGRATED, element, reason)


def _export_details(model: DataModel) -> dict:
    copied_from = {
        "Name": model.CopiedFromName,
        "Version": model.CopiedFromVersion,
        "ContributorOrganization": model.CopiedFromContributorOrganization,
    }
    return {
        "Name": model.Name,
        "Version": model.DataModelVersion,
        "ContributorOrganization": model.ContributorOrganization,
        # Left out when none is set; one or two set is refused as MODEL_IDENTITY_INCOMPLETE.
        "CopiedFrom": copied_from if any(value is not None for value in copied_from.values()) else None,
        "Description": model.Description,
        "UseConsiderations": model.UseConsiderations,
        "Notes": model.Notes,
        "Contributor": model.Contributor,
        "State": model.State.value if model.State else None,
        "Tags": model.Tags,
        "ActivationDate": model.ActivationDate,
        "DeprecationDate": model.DeprecationDate,
    }


def _export_value_set(value_set: ValueSet, values: list[ValueSetValue]) -> dict:
    return {
        "Name": value_set.Name,
        "Values": [
            {
                "ValueName": value.ValueName,
                "Value": value.Value,
                "Description": value.Description,
                "UseConsiderations": value.UseConsiderations,
                "Source": value.Source,
                "Notes": value.Notes,
                "Contributor": value.Contributor,
                "ContributorOrganization": value.ContributorOrganization,
                "ActivationDate": value.ActivationDate,
                "DeprecationDate": value.DeprecationDate,
            }
            for value in values
        ],
        "Description": value_set.Description,
        "UseConsiderations": value_set.UseConsiderations,
        "Notes": value_set.Notes,
        "Contributor": value_set.Contributor,
        "ContributorOrganization": value_set.ContributorOrganization,
        "Tags": value_set.Tags,
        "ActivationDate": value_set.ActivationDate,
        "DeprecationDate": value_set.DeprecationDate,
    }


def _export_element_fields(element: Union[Entity, Attribute]) -> dict:
    # The fields entities and attributes share. Required is free text; only "Yes" is true, as the
    # schema generator reads it (§11), and false is left out.
    return {
        "UniqueName": element.UniqueName,
        "Name": element.Name,
        "LevelOfAccess": element.LevelOfAccess.value,
        "Queryable": element.Queryable,
        "Modifiable": element.Modifiable,
        "Required": True if element.Required == "Yes" else None,
        "Description": element.Description,
        "UseConsiderations": element.UseConsiderations,
        "SourceModel": element.SourceModel,
        "Notes": element.Notes,
        "Contributor": element.Contributor,
        "ContributorOrganization": element.ContributorOrganization,
        "Tags": element.Tags,
        "Common": element.Common,
        "ActivationDate": element.ActivationDate,
        "DeprecationDate": element.DeprecationDate,
    }


def _export_entity(entity: Entity) -> dict:
    return _export_element_fields(entity)


def _export_attribute(attribute: Attribute, rows: _ModelRows) -> dict:
    value_set = rows.resolved_value_sets.get(attribute.ValueSetId) if attribute.ValueSetId is not None else None
    return {
        **_export_element_fields(attribute),
        "DataType": attribute.DataType,
        "ValueSet": {"ValueSet": value_set.key} if value_set is not None else None,
        "Example": attribute.Example,
    }


def _export_association(association: AnyAssociation, rows: _ModelRows) -> dict:
    parent_element, child_element = _get_association_elements(rows, association)
    if isinstance(association, EntityAssociation):
        child = {"Entity": child_element.key}
        # A NULL Placement is Embedded, as the schema generator reads it (§11).
        reference = True if association.Placement == EntityPlacementType.Reference else None
    else:
        child, reference = {"Attribute": child_element.key}, None
    return {
        "Parent": {"Entity": parent_element.key},
        "Child": child,
        "Name": association.Name,
        "Array": True if association.Array else None,
        "Reference": reference,
        "Notes": association.Notes,
        "Contributor": association.Contributor,
        "ContributorOrganization": association.ContributorOrganization,
        "ActivationDate": association.ActivationDate,
        "DeprecationDate": association.DeprecationDate,
    }


def _without_nulls(item: Any) -> Any:
    # Optional fields are left out when NULL, as the canonical form writes them (§9).
    if isinstance(item, dict):
        return {key: _without_nulls(value) for key, value in item.items() if value is not None}
    if isinstance(item, list):
        return [_without_nulls(entry) for entry in item]
    return item


def _to_json(value: Any) -> str:
    # Stored timestamps are timezone-aware, so isoformat writes an RFC 3339 offset (§9).
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"{type(value).__name__} is not JSON serializable")


async def import_model(session: AsyncSession, file: ModelFile) -> int:
    """Write a portable file as a new model, and return its Id.

    Create-only: a live model with the same identity is refused with MODEL_EXISTS (§5.2). Every rule is
    checked before the first row is written, so a refusal writes nothing.
    """
    errors: list[PortabilityError] = []
    try:
        check_model_file(file)
    except PortabilityErrorGroup as group:
        errors.extend(group.exceptions)
    details = file.Details
    existing = (
        await session.execute(
            select(DataModel.Id).where(
                DataModel.Name == details.Name,
                DataModel.DataModelVersion == details.Version,
                DataModel.ContributorOrganization == details.ContributorOrganization,
                DataModel.Deleted.is_not(True),
            )
        )
    ).first()
    if existing is not None:
        errors.append(
            PortabilityError(
                Code.MODEL_EXISTS,
                "Details",
                f"model {existing.Id} already has this Name, Version and ContributorOrganization",
            )
        )
    if errors:
        raise error_group(errors)

    copied_from = details.CopiedFrom
    model = DataModel(
        Name=details.Name,
        DataModelVersion=details.Version,
        ContributorOrganization=details.ContributorOrganization,
        # Type is required by the table but no longer means anything (§11): every model is one kind.
        Type=DataModelType.SourceSchema,
        CopiedFromName=copied_from.Name if copied_from else None,
        CopiedFromVersion=copied_from.Version if copied_from else None,
        CopiedFromContributorOrganization=copied_from.ContributorOrganization if copied_from else None,
        Description=details.Description,
        UseConsiderations=details.UseConsiderations,
        Notes=details.Notes,
        Contributor=details.Contributor,
        State=details.State,
        Tags=details.Tags,
        ActivationDate=details.ActivationDate,
        DeprecationDate=details.DeprecationDate,
        Deleted=False,
    )
    session.add(model)
    await session.flush()

    value_set_ids = await _import_value_sets(session, file, model.Id)
    entity_ids, attribute_ids = await _import_elements(session, file, model.Id, value_set_ids)
    for association in file.Associations:
        session.add(_import_association(association, entity_ids, attribute_ids))
    await session.flush()
    return model.Id


async def _import_value_sets(session: AsyncSession, file: ModelFile, data_model_id: int) -> dict[str, int]:
    value_set_rows = [
        ValueSet(
            Name=value_set.Name,
            DataModelId=data_model_id,
            Description=value_set.Description,
            UseConsiderations=value_set.UseConsiderations,
            Notes=value_set.Notes,
            Contributor=value_set.Contributor,
            ContributorOrganization=value_set.ContributorOrganization,
            Tags=value_set.Tags,
            ActivationDate=value_set.ActivationDate,
            DeprecationDate=value_set.DeprecationDate,
        )
        for value_set in file.ValueSets
    ]
    session.add_all(value_set_rows)
    await session.flush()
    for value_set, value_set_row in zip(file.ValueSets, value_set_rows):
        session.add_all(
            ValueSetValue(
                ValueSetId=value_set_row.Id,
                DataModelId=data_model_id,
                ValueName=value.ValueName,
                Value=value.Value,
                Description=value.Description,
                UseConsiderations=value.UseConsiderations,
                Source=value.Source,
                Notes=value.Notes,
                Contributor=value.Contributor,
                ContributorOrganization=value.ContributorOrganization,
                ActivationDate=value.ActivationDate,
                DeprecationDate=value.DeprecationDate,
            )
            for value in value_set.Values
        )
    return {value_set_row.Name: value_set_row.Id for value_set_row in value_set_rows}


def _to_yes_no(flag: bool) -> str:
    # Required and Array are free text on the element rows; "Yes" is the only true value (§11).
    return "Yes" if flag else "No"


async def _import_elements(
    session: AsyncSession, file: ModelFile, data_model_id: int, value_set_ids: dict[str, int]
) -> tuple[dict[str, int], dict[str, int]]:
    # The schema generator still reads Array from the element, not from the association, so an element
    # is stored as an array when any association places it as one. An element that is a list under one
    # parent and single under another can't be generated that way until the generator reads the
    # association.
    entities_in_arrays = {
        association.Child.Entity
        for association in file.Associations
        if isinstance(association.Child, EntityKey) and association.Array
    }
    attributes_in_arrays = {
        association.Child.Attribute
        for association in file.Associations
        if isinstance(association.Child, AttributeKey) and association.Array
    }

    def element_fields(element: Any, in_array: bool) -> dict:
        return {
            "UniqueName": element.UniqueName,
            "Name": element.Name,
            "DataModelId": data_model_id,
            "LevelOfAccess": element.LevelOfAccess,
            "Queryable": element.Queryable,
            "Modifiable": element.Modifiable,
            "Required": _to_yes_no(element.Required),
            "Array": _to_yes_no(in_array),
            "Description": element.Description,
            "UseConsiderations": element.UseConsiderations,
            "SourceModel": element.SourceModel,
            "Notes": element.Notes,
            "Contributor": element.Contributor,
            "ContributorOrganization": element.ContributorOrganization,
            "Tags": element.Tags,
            "Common": element.Common,
            "ActivationDate": element.ActivationDate,
            "DeprecationDate": element.DeprecationDate,
        }

    entities = [Entity(**element_fields(entity, entity.UniqueName in entities_in_arrays)) for entity in file.Entities]
    attributes = [
        Attribute(
            **element_fields(attribute, attribute.UniqueName in attributes_in_arrays),
            DataType=attribute.DataType,
            ValueSetId=value_set_ids[attribute.ValueSet.ValueSet] if attribute.ValueSet else None,
            Example=attribute.Example,
        )
        for attribute in file.Attributes
    ]
    session.add_all([*entities, *attributes])
    await session.flush()
    return (
        {entity.UniqueName: entity.Id for entity in entities},
        {attribute.UniqueName: attribute.Id for attribute in attributes},
    )


def _import_association(
    association: FileAssociation, entity_ids: dict[str, int], attribute_ids: dict[str, int]
) -> AnyAssociation:
    # Relationship is left NULL: the association's Name replaces it (§11), and the generator moves to
    # reading Name in #1395.
    fields = {
        "Name": association.Name,
        "Array": association.Array,
        "Notes": association.Notes,
        "Contributor": association.Contributor,
        "ContributorOrganization": association.ContributorOrganization,
        "ActivationDate": association.ActivationDate,
        "DeprecationDate": association.DeprecationDate,
    }
    parent_id = entity_ids[association.Parent.Entity]
    child = association.Child
    if isinstance(child, EntityKey):
        return EntityAssociation(
            ParentEntityId=parent_id,
            ChildEntityId=entity_ids[child.Entity],
            Placement=EntityPlacementType.Reference if association.Reference else EntityPlacementType.Embedded,
            **fields,
        )
    return EntityAttributeAssociation(EntityId=parent_id, AttributeId=attribute_ids[child.Attribute], **fields)

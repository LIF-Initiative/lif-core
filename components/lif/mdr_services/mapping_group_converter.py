"""Convert between a transformation group's rows and a portable mapping-group file (issue #1389).

Portability Spec §6 and §8: export_mapping_group reads a group into a MappingGroupFile, and
import_mapping_group writes one as a new group. Paths are translated by lif.mdr_portability.mapping_paths
over each model's own live rows. Neither function commits; the caller owns the transaction. Import
checks every rule and resolves every path before it writes the first row, so a refusal writes nothing.

Callers reach it through portability_converter, the converter module for every file kind (§8).
"""

from typing import Optional

from lif.mdr_portability import MappingGroupFile, PortabilityError, PortabilityErrorCode, PortabilityErrorGroup
from lif.mdr_portability.mapping_group_rules import check_mapping_group_file
from lif.mdr_portability.mapping_paths import (
    AssociationEnd,
    ModelPaths,
    ResolvedPath,
    check_path_syntax,
    to_entity_id_path,
    to_file_path,
)
from lif.mdr_dto.transformation_group_dto import GROUP_VERSION_PATTERN
from lif.mdr_portability.v1.models import ModelIdentity
from lif.mdr_services.transformation_service import get_transformation_group_by_id
from lif.mdr_sql_model.core import (
    Attribute,
    AttributeType,
    DataModel,
    Entity,
    EntityAssociation,
    EntityAttributeAssociation,
    EntityPlacementType,
    ExpressionLanguageType,
    ExtInclusionsFromBaseDM,
    Transformation,
    TransformationAttribute,
    TransformationGroup,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

Code = PortabilityErrorCode


def _error_group(errors: list[PortabilityError]) -> PortabilityErrorGroup:
    return PortabilityErrorGroup(f"{len(errors)} portability error{'s' if len(errors) != 1 else ''}", errors)


async def load_model_paths(session: AsyncSession, data_model_id: int) -> ModelPaths:
    """One model's own live entities, attributes and associations, for path translation.

    Associations an overlay added to this model's elements (ExtendedByDataModelId set) belong to the
    overlay, so they are left out. A NULL Placement is Embedded, as the generator reads it.
    """
    entities = (
        await session.execute(
            select(Entity.Id, Entity.UniqueName).where(Entity.DataModelId == data_model_id, Entity.Deleted == False)
        )
    ).all()
    attributes = (
        await session.execute(
            select(Attribute.Id, Attribute.UniqueName).where(
                Attribute.DataModelId == data_model_id, Attribute.Deleted == False
            )
        )
    ).all()
    entity_names = {row.Id: row.UniqueName for row in entities}
    attribute_names = {row.Id: row.UniqueName for row in attributes}

    entity_associations = (
        await session.execute(
            select(
                EntityAssociation.ParentEntityId,
                EntityAssociation.ChildEntityId,
                EntityAssociation.Name,
                EntityAssociation.Placement,
            ).where(
                EntityAssociation.ParentEntityId.in_(entity_names),
                EntityAssociation.ChildEntityId.in_(entity_names),
                EntityAssociation.Deleted == False,
                EntityAssociation.ExtendedByDataModelId.is_(None),
            )
        )
    ).all()
    attribute_associations = (
        await session.execute(
            select(
                EntityAttributeAssociation.EntityId,
                EntityAttributeAssociation.AttributeId,
                EntityAttributeAssociation.Name,
            ).where(
                EntityAttributeAssociation.EntityId.in_(entity_names),
                EntityAttributeAssociation.AttributeId.in_(attribute_names),
                EntityAttributeAssociation.Deleted == False,
                EntityAttributeAssociation.ExtendedByDataModelId.is_(None),
            )
        )
    ).all()

    associations: dict[int, list[AssociationEnd]] = {}
    contained = set()
    for row in entity_associations:
        associations.setdefault(row.ParentEntityId, []).append(AssociationEnd(row.Name, row.ChildEntityId, False))
        if row.Placement != EntityPlacementType.Reference:
            contained.add(row.ChildEntityId)
    for row in attribute_associations:
        associations.setdefault(row.EntityId, []).append(AssociationEnd(row.Name, row.AttributeId, True))

    return ModelPaths(
        entity_names=entity_names,
        attribute_names=attribute_names,
        top_level_entity_ids=frozenset(entity_names.keys() - contained),
        associations=associations,
    )


async def _is_overlay(session: AsyncSession, data_model_id: int) -> bool:
    # An overlay still reads its elements through inclusion rows (ADR data_model/0004), so its paths
    # don't resolve in its own rows. It is detected by those rows, not by its Type (§8: no type names).
    inclusion = (
        await session.execute(
            select(ExtInclusionsFromBaseDM.Id)
            .where(ExtInclusionsFromBaseDM.ExtDataModelId == data_model_id, ExtInclusionsFromBaseDM.Deleted == False)
            .limit(1)
        )
    ).first()
    return inclusion is not None


def _identity(model: DataModel, element: str) -> tuple[Optional[dict], list[PortabilityError]]:
    identity = {
        "Name": model.Name,
        "Version": model.DataModelVersion,
        "ContributorOrganization": model.ContributorOrganization,
    }
    missing = [field for field, value in identity.items() if not (value or "").strip()]
    if missing:
        return None, [
            PortabilityError(Code.MODEL_IDENTITY_INCOMPLETE, element, f"the model has no {', '.join(missing)}")
        ]
    return identity, []


def _path_entry(row: TransformationAttribute, path: str) -> dict:
    return {
        "Path": path,
        "Notes": row.Notes,
        "Contributor": row.Contributor,
        "ContributorOrganization": row.ContributorOrganization,
        "ActivationDate": row.ActivationDate,
        "DeprecationDate": row.DeprecationDate,
    }


async def export_mapping_group(session: AsyncSession, group_id: int) -> MappingGroupFile:
    """Read a live transformation group into a portable file, or refuse with every reason at once."""
    group = await get_transformation_group_by_id(session=session, id=group_id)
    errors: list[PortabilityError] = []

    details: dict = {}
    models: dict[str, ModelPaths] = {}
    for side, model_id in (("Source", group.SourceDataModelId), ("Target", group.TargetDataModelId)):
        element = f"Details.{side}"
        model = await session.get(DataModel, model_id)
        if model is None or model.Deleted:
            errors.append(PortabilityError(Code.MODEL_MISSING, element, f"model {model_id} is not installed"))
            continue
        identity, identity_errors = _identity(model, element)
        errors.extend(identity_errors)
        details[side] = identity
        if await _is_overlay(session, model_id):
            errors.append(
                PortabilityError(
                    Code.NOT_MIGRATED, element, f"{model.Name!r} is an overlay; convert it first (ADR data_model/0004)"
                )
            )
            continue
        models[side] = await load_model_paths(session, model_id)

    if not GROUP_VERSION_PATTERN.fullmatch(group.GroupVersion or ""):
        errors.append(
            PortabilityError(Code.FIELD_INVALID, "Details.Version", f"{group.GroupVersion!r} is not dotted integers")
        )
    if not (group.Name or "").strip():
        errors.append(PortabilityError(Code.FIELD_INVALID, "Details.Name", "the group has no Name"))
    details |= {
        "Version": group.GroupVersion,
        "Name": group.Name,
        "Description": group.Description,
        "Notes": group.Notes,
        "Contributor": group.Contributor,
        "ContributorOrganization": group.ContributorOrganization,
        "Tags": group.Tags,
    }

    transformations = (
        await session.execute(
            select(Transformation)
            .where(Transformation.TransformationGroupId == group.Id, Transformation.Deleted == False)
            .order_by(Transformation.Id)
        )
    ).scalars()
    mappings = []
    for transformation in transformations:
        element = f"Transformations[{transformation.Id}]"
        attributes = (
            await session.execute(
                select(TransformationAttribute)
                .where(
                    TransformationAttribute.TransformationId == transformation.Id,
                    TransformationAttribute.Deleted == False,
                )
                .order_by(TransformationAttribute.Id)
            )
        ).scalars()
        targets, sources = [], []
        for attribute in attributes:
            (targets if attribute.AttributeType == AttributeType.Target else sources).append(attribute)

        if len(targets) != 1:
            code = Code.MAPPING_TARGET_MISSING if not targets else Code.MAPPING_TARGET_MULTIPLE
            errors.append(PortabilityError(code, element, f"the transformation has {len(targets)} targets"))
            continue
        target_path = _export_path(targets[0], models.get("Target"), element, errors)
        if target_path is not None:
            element = f"Mappings[{target_path}]"
        source_paths = [_export_path(source, models.get("Source"), element, errors) for source in sources]

        if transformation.ExpressionLanguage != ExpressionLanguageType.JSONata:
            # Export never quietly drops a rule it cannot carry (§6.2).
            errors.append(
                PortabilityError(
                    Code.EXPRESSION_LANGUAGE_NOT_PORTABLE,
                    element,
                    f"the rule is written in {getattr(transformation.ExpressionLanguage, 'value', transformation.ExpressionLanguage)}, not JSONata",
                )
            )
        if transformation.Expression is None:
            errors.append(PortabilityError(Code.FIELD_INVALID, element, "the transformation has no Expression"))
        if target_path is None or None in source_paths:
            continue

        mappings.append(
            {
                "Target": _path_entry(targets[0], target_path),
                "Sources": [_path_entry(source, path) for source, path in zip(sources, source_paths)],
                "ExpressionLanguage": "JSONata",
                "Expression": transformation.Expression,
                "Name": transformation.Name,
                "Description": transformation.Description,
                "UseConsiderations": transformation.UseConsiderations,
                "Alignment": transformation.Alignment,
                "Notes": transformation.Notes,
                "Contributor": transformation.Contributor,
                "ContributorOrganization": transformation.ContributorOrganization,
                "ActivationDate": transformation.ActivationDate,
                "DeprecationDate": transformation.DeprecationDate,
            }
        )

    if errors:
        raise _error_group(errors)
    file = MappingGroupFile.model_validate(
        {
            "Format": {"Type": "lif-mdr-mapping-group", "Version": 1},
            "Details": _without_nulls(details),
            "Mappings": [_without_nulls(mapping) for mapping in mappings],
        }
    )
    # Two stored transformations writing one target, or a source listed twice, can't be written out.
    check_mapping_group_file(file)
    return file


def _export_path(
    row: TransformationAttribute, model: Optional[ModelPaths], element: str, errors: list[PortabilityError]
) -> Optional[str]:
    if model is None:
        return None  # the model was already refused
    if not row.EntityIdPath:
        errors.append(PortabilityError(Code.PATH_INVALID, element, f"attribute row {row.Id} has no stored path"))
        return None
    try:
        return to_file_path(row.EntityIdPath, model, element)
    except PortabilityError as error:
        errors.append(error)
        return None


def _without_nulls(item: dict) -> dict:
    # Optional fields are left out when NULL, as the canonical form writes them (§9).
    cleaned = {}
    for key, value in item.items():
        if isinstance(value, dict):
            value = _without_nulls(value)
        elif isinstance(value, list):
            value = [_without_nulls(entry) if isinstance(entry, dict) else entry for entry in value]
        if value is not None:
            cleaned[key] = value
    return cleaned


async def _find_model(session: AsyncSession, identity: ModelIdentity) -> Optional[DataModel]:
    return (
        (
            await session.execute(
                select(DataModel).where(
                    DataModel.Name == identity.Name,
                    DataModel.DataModelVersion == identity.Version,
                    DataModel.ContributorOrganization == identity.ContributorOrganization,
                    DataModel.Deleted.is_not(True),
                )
            )
        )
        .scalars()
        .first()
    )


async def import_mapping_group(session: AsyncSession, file: MappingGroupFile) -> int:
    """Write a portable file as a new, inactive transformation group, and return its Id.

    Create-only: a live group with the same models and Version is refused with GROUP_EXISTS. The group
    gets no ActivationDate, so it is not active until someone activates it (#1350).
    """
    errors: list[PortabilityError] = []
    try:
        check_mapping_group_file(file)
    except PortabilityErrorGroup as group:
        errors.extend(group.exceptions)

    models: dict[str, DataModel] = {}
    paths: dict[str, ModelPaths] = {}
    for side, identity in (("Source", file.Details.Source), ("Target", file.Details.Target)):
        model = await _find_model(session, identity)
        if model is None:
            errors.append(
                PortabilityError(
                    Code.MODEL_MISSING,
                    f"Details.{side}",
                    f"no installed model is {identity.Name!r} {identity.Version} by {identity.ContributorOrganization!r}",
                )
            )
            continue
        models[side] = model
        paths[side] = await load_model_paths(session, model.Id)

    if len(models) == 2:
        existing = (
            await session.execute(
                select(TransformationGroup.Id).where(
                    TransformationGroup.SourceDataModelId == models["Source"].Id,
                    TransformationGroup.TargetDataModelId == models["Target"].Id,
                    TransformationGroup.GroupVersion == file.Details.Version,
                    TransformationGroup.Deleted.is_not(True),
                )
            )
        ).first()
        if existing is not None:
            errors.append(
                PortabilityError(
                    Code.GROUP_EXISTS, "Details.Version", f"group {existing.Id} already has these models and Version"
                )
            )

    resolved: list[tuple[ResolvedPath, list[ResolvedPath]]] = []
    for mapping in file.Mappings:
        element = f"Mappings[{mapping.Target.Path}]"
        target = _import_path(mapping.Target.Path, paths.get("Target"), f"{element}.Target.Path", errors)
        sources = [
            _import_path(source.Path, paths.get("Source"), f"{element}.Sources[{source.Path}].Path", errors)
            for source in mapping.Sources
        ]
        if target is not None and None not in sources:
            resolved.append((target, sources))

    if errors:
        raise _error_group(errors)

    details = file.Details
    group = TransformationGroup(
        SourceDataModelId=models["Source"].Id,
        TargetDataModelId=models["Target"].Id,
        Name=details.Name,
        Description=details.Description,
        GroupVersion=details.Version,
        Notes=details.Notes,
        Contributor=details.Contributor,
        ContributorOrganization=details.ContributorOrganization,
        Tags=details.Tags,
    )
    session.add(group)
    await session.flush()

    for mapping, (target, sources) in zip(file.Mappings, resolved):
        transformation = Transformation(
            TransformationGroupId=group.Id,
            Name=mapping.Name,
            Description=mapping.Description,
            UseConsiderations=mapping.UseConsiderations,
            Alignment=mapping.Alignment,
            Expression=mapping.Expression,
            ExpressionLanguage=ExpressionLanguageType.JSONata,
            Notes=mapping.Notes,
            ActivationDate=mapping.ActivationDate,
            DeprecationDate=mapping.DeprecationDate,
            Contributor=mapping.Contributor,
            ContributorOrganization=mapping.ContributorOrganization,
        )
        session.add(transformation)
        await session.flush()
        for entry, path, attribute_type in [
            (mapping.Target, target, AttributeType.Target),
            *((source, path, AttributeType.Source) for source, path in zip(mapping.Sources, sources)),
        ]:
            session.add(
                TransformationAttribute(
                    TransformationId=transformation.Id,
                    EntityId=path.entity_id,
                    AttributeId=path.attribute_id,
                    AttributeType=attribute_type,
                    EntityIdPath=path.entity_id_path,
                    Notes=entry.Notes,
                    ActivationDate=entry.ActivationDate,
                    DeprecationDate=entry.DeprecationDate,
                    Contributor=entry.Contributor,
                    ContributorOrganization=entry.ContributorOrganization,
                )
            )
    await session.flush()
    return group.Id


def _import_path(
    path: str, model: Optional[ModelPaths], element: str, errors: list[PortabilityError]
) -> Optional[ResolvedPath]:
    if model is None or check_path_syntax(path, element):
        return None  # the model, or the path's syntax, was already refused
    try:
        return to_entity_id_path(path, model, element)
    except PortabilityError as error:
        errors.append(error)
        return None

"""Convert between the value mappings of one value-set pair and a portable crosswalk file (issue #1390).

Portability Spec §7 and §8: export_crosswalk reads the live value mappings from one value set to another
into a CrosswalkFile, and import_crosswalk writes one as new value mappings. Values are addressed by
ValueName, and each value set by its model's identity and its Name. Neither function commits; the caller
owns the transaction. Import checks every rule and resolves every value before it writes the first row,
so a refusal writes nothing.

A crosswalk has no group (§7), so imported value mappings get no TransformationGroupId, like most of the
seed's. A value mapping counts as live only when it, both of its values, and its group (if it has one)
are live (§2).

This lives here, beside the existing value-mapping services, until the converter module for every file
kind (§8) exists; it moves there then.
"""

from typing import Optional

from lif.mdr_portability import CrosswalkFile, PortabilityError, PortabilityErrorCode, PortabilityErrorGroup
from lif.mdr_portability.crosswalk_rules import check_crosswalk_file, duplicate_source_errors
from lif.mdr_portability.errors import error_group
from lif.mdr_services.mapping_group_converter import _find_model, _identity, _without_nulls
from lif.mdr_services.valueset_service import get_value_set_by_id
from lif.mdr_sql_model.core import DataModel, TransformationGroup, ValueSet, ValueSetValue, ValueSetValueMapping
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from sqlmodel import select

Code = PortabilityErrorCode


async def _live_mappings(
    session: AsyncSession, source_value_set_id: int, target_value_set_id: int, limit: Optional[int] = None
):
    """The live value mappings from one value set to another, with both values' names.

    The pair is read from the values, not from the mapping's SourceValueSetId and TargetValueSetId,
    which are NULL on most of the seed's rows.
    """
    source_value, target_value = aliased(ValueSetValue), aliased(ValueSetValue)
    query = (
        select(ValueSetValueMapping, source_value.ValueName, target_value.ValueName)
        .join(source_value, source_value.Id == ValueSetValueMapping.SourceValueId)
        .join(target_value, target_value.Id == ValueSetValueMapping.TargetValueId)
        .outerjoin(TransformationGroup, TransformationGroup.Id == ValueSetValueMapping.TransformationGroupId)
        .where(
            source_value.ValueSetId == source_value_set_id,
            target_value.ValueSetId == target_value_set_id,
            ValueSetValueMapping.Deleted.is_not(True),
            source_value.Deleted.is_not(True),
            target_value.Deleted.is_not(True),
            # A mapping with no group joins no row, so this holds for it too.
            TransformationGroup.Deleted.is_not(True),
        )
        .order_by(ValueSetValueMapping.Id)
        .limit(limit)
    )
    return (await session.execute(query)).all()


async def export_crosswalk(session: AsyncSession, source_value_set_id: int, target_value_set_id: int) -> CrosswalkFile:
    """Read the live value mappings between two value sets into a portable file.

    A value set that is missing or deleted raises a 404, as export_mapping_group does for its group.
    Anything else that can't be written out is refused with every reason at once.
    """
    errors: list[PortabilityError] = []

    details: dict = {}
    for side, value_set_id in (("Source", source_value_set_id), ("Target", target_value_set_id)):
        element = f"Details.{side}"
        value_set = await get_value_set_by_id(session=session, id=value_set_id)
        model = await session.get(DataModel, value_set.DataModelId)
        if model is None or model.Deleted:
            errors.append(
                PortabilityError(Code.MODEL_MISSING, element, f"model {value_set.DataModelId} is not installed")
            )
            continue
        identity, identity_errors = _identity(model, f"{element}.Model")
        errors.extend(identity_errors)
        if not (value_set.Name or "").strip():
            errors.append(PortabilityError(Code.FIELD_INVALID, f"{element}.ValueSet", "the value set has no Name"))
        details[side] = {"Model": identity, "ValueSet": value_set.Name}

    entries = []
    for mapping, source_name, target_name in await _live_mappings(session, source_value_set_id, target_value_set_id):
        element = f"ValueMappings[{mapping.Id}]"
        unnamed = [
            side for side, name in (("source", source_name), ("target", target_name)) if not (name or "").strip()
        ]
        if unnamed:
            errors.append(
                PortabilityError(Code.FIELD_INVALID, element, f"the {' and '.join(unnamed)} value has no ValueName")
            )
            continue
        entries.append(
            {
                "Source": source_name,
                "Target": target_name,
                "Description": mapping.Description,
                "UseConsiderations": mapping.UseConsiderations,
                "Notes": mapping.Notes,
                "Contributor": mapping.Contributor,
                "ContributorOrganization": mapping.ContributorOrganization,
                "ActivationDate": mapping.ActivationDate,
                "DeprecationDate": mapping.DeprecationDate,
            }
        )

    # A source value with two live mappings into the pair can't be written out (§7).
    errors.extend(duplicate_source_errors(entry["Source"] for entry in entries))
    if errors:
        raise error_group(errors)
    return CrosswalkFile.model_validate(
        {
            "Format": {"Type": "lif-mdr-crosswalk", "Version": 1},
            "Details": details,
            "Entries": [_without_nulls(entry) for entry in entries],
        }
    )


async def import_crosswalk(session: AsyncSession, file: CrosswalkFile) -> int:
    """Write a portable file as new value mappings, and return how many were created.

    Create-only: if any live value mapping already maps the source value set to the target one, the
    file is refused with CROSSWALK_EXISTS. That check takes no lock, so a caller that can run two
    imports of one pair at once must serialize them, as for import_mapping_group's GROUP_EXISTS.
    """
    errors: list[PortabilityError] = []
    try:
        check_crosswalk_file(file)
    except PortabilityErrorGroup as group:
        errors.extend(group.exceptions)

    value_sets: dict[str, ValueSet] = {}
    value_ids: dict[str, dict[Optional[str], int]] = {}
    for side, key in (("Source", file.Details.Source), ("Target", file.Details.Target)):
        element = f"Details.{side}"
        identity = key.Model
        model = await _find_model(session, identity)
        if model is None:
            errors.append(
                PortabilityError(
                    Code.MODEL_MISSING,
                    element,
                    f"no installed model is {identity.Name!r} {identity.Version} by {identity.ContributorOrganization!r}",
                )
            )
            continue
        value_set = (
            (
                await session.execute(
                    select(ValueSet).where(
                        ValueSet.DataModelId == model.Id, ValueSet.Name == key.ValueSet, ValueSet.Deleted.is_not(True)
                    )
                )
            )
            .scalars()
            .first()
        )
        if value_set is None:
            errors.append(
                PortabilityError(
                    Code.ELEMENT_REFERENCE_UNRESOLVED,
                    f"{element}.ValueSet",
                    f"{model.Name!r} has no live value set {key.ValueSet!r}",
                )
            )
            continue
        value_sets[side] = value_set
        values = await session.execute(
            select(ValueSetValue.Id, ValueSetValue.ValueName).where(
                ValueSetValue.ValueSetId == value_set.Id, ValueSetValue.Deleted.is_not(True)
            )
        )
        value_ids[side] = {row.ValueName: row.Id for row in values}

    if len(value_sets) == 2:
        existing = await _live_mappings(session, value_sets["Source"].Id, value_sets["Target"].Id, limit=1)
        if existing:
            errors.append(
                PortabilityError(
                    Code.CROSSWALK_EXISTS,
                    "Details",
                    f"value mapping {existing[0][0].Id} already maps {value_sets['Source'].Name!r} to {value_sets['Target'].Name!r}",
                )
            )

    resolved: list[tuple[Optional[int], Optional[int]]] = []
    for entry in file.Entries:
        ids = []
        for side, name in (("Source", entry.Source), ("Target", entry.Target)):
            if side not in value_ids:
                ids.append(None)  # the value set was already refused
                continue
            value_id = value_ids[side].get(name)
            if value_id is None:
                errors.append(
                    PortabilityError(
                        Code.ELEMENT_REFERENCE_UNRESOLVED,
                        f"Entries[{entry.Source}].{side}",
                        f"value set {value_sets[side].Name!r} has no live value {name!r}",
                    )
                )
            ids.append(value_id)
        resolved.append((ids[0], ids[1]))

    if errors:
        raise error_group(errors)

    for entry, (source_value_id, target_value_id) in zip(file.Entries, resolved):
        session.add(
            ValueSetValueMapping(
                SourceValueId=source_value_id,
                TargetValueId=target_value_id,
                # Filled as the API fills them on create, though export reads the pair from the values.
                SourceValueSetId=value_sets["Source"].Id,
                TargetValueSetId=value_sets["Target"].Id,
                Description=entry.Description,
                UseConsiderations=entry.UseConsiderations,
                Notes=entry.Notes,
                Contributor=entry.Contributor,
                ContributorOrganization=entry.ContributorOrganization,
                ActivationDate=entry.ActivationDate,
                DeprecationDate=entry.DeprecationDate,
            )
        )
    await session.flush()
    return len(file.Entries)

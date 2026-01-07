from datetime import datetime, timezone
from typing import Dict, Optional

from lif.datatypes.mdr_sql_model import (
    Attribute,
    DataModel,
    Entity,
    EntityAssociation,
    EntityAttributeAssociation,
    ExtInclusionsFromBaseDM,
    ValueSet,
    ValueSetValue,
)
from lif.mdr_dto.datamodel_dto import DataModelDTO
from lif.mdr_services.entity_association_service import get_entity_association_by_parent_child_relationship
from lif.mdr_services.entity_attribute_association_service import check_existing_association
from lif.mdr_services.entity_service import get_unique_entity
from lif.mdr_services.inclusions_service import check_inclusion_exists
from lif.mdr_utils.logger_config import get_logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

logger = get_logger(__name__)

# ---------------Helper Functions---------------


def parse_dt(val):
    """Return a timezone-aware datetime or None."""
    if val in (None, ""):
        return None
    if isinstance(val, datetime):
        # ensure tz-aware; make UTC if naive
        return val if val.tzinfo else val.replace(tzinfo=timezone.utc)
    if isinstance(val, str):
        # handle 'Z' suffix and ISO formats with offsets like +00:00
        v = val[:-1] + "+00:00" if val.endswith("Z") else val
        return datetime.fromisoformat(v)  # preserves offset if present
    raise TypeError(f"Unsupported date value: {val!r}")


async def create_reference_entity_association_if_needed(
    session: AsyncSession, ref_name, referenced_entity, parent_entity_id, data_model_id
):
    # relationship = the text prepended on ref_name that is not part of the referenced entity name
    # e.g. for "issuedByOrganization" if referenced_entity.Name is "Organization", relationship is "issuedBy"
    relationship = ref_name[: ref_name.index(referenced_entity.Name)]
    # Check if an EntityAssociation already exists
    entity_association = await get_entity_association_by_parent_child_relationship(
        session, parent_entity_id, referenced_entity.Id, relationship, data_model_id
    )

    if not entity_association:
        entity_association = EntityAssociation(
            ParentEntityId=parent_entity_id,
            ChildEntityId=referenced_entity.Id,
            Relationship=relationship,
            Placement="Reference",
            Notes=None,
            Contributor=None,
            ContributorOrganization=None,
            Deleted=False,
            Extension=False,
            ExtensionNotes=None,
            ExtendedByDataModelId=None,
        )
        session.add(entity_association)


async def create_reference_associations_for_children(
    session: AsyncSession, entity_md: Dict, data_model_id: int, openapi_schema: Dict, data_model_type: str
):
    entity_properties = entity_md.get("properties", {})
    for prop_name, prop in entity_properties.items():
        if "$ref" in prop:  # This is a reference to another entity
            ref_path = prop[
                "$ref"
            ]  # Assume path is always in format like #/components/schemas/EntityName or #/components/schemas/ParentEntityName/properties/ChildEntityName (this could continue for deeper nesting)
            # 1. Find where it is in the openapi_schema
            referenced_entity_md = resolve_ref(openapi_schema, ref_path)
            # 2. Determine its Entity Id
            referenced_entity = await get_unique_entity(
                session,
                referenced_entity_md.get("UniqueName"),
                data_model_id,
                referenced_entity_md.get("DataModelId"),
                data_model_type,
            )
            logger.info(f"Referenced entity unique name: {referenced_entity_md.get('UniqueName')}")
            # Determine parent entity id
            logger.info(f"Parent entity: {entity_md}")
            parent_entity = await get_unique_entity(
                session, entity_md.get("UniqueName"), data_model_id, entity_md.get("DataModelId"), data_model_type
            )
            parent_entity_id = parent_entity.Id
            # 3. Create an EntityAssociation if needed
            await create_reference_entity_association_if_needed(
                session, prop_name, referenced_entity, parent_entity_id, data_model_id
            )
        # Go through this process recursively
        if "properties" in prop:
            await create_reference_associations_for_children(
                session, prop, data_model_id, openapi_schema, data_model_type
            )


def resolve_ref(openapi_schema: dict, ref_path: str):
    """
    Resolve an RFC 6901 JSON Pointer against `doc`.
    Supports fragments that begin with '#/' (common in OpenAPI $ref).
    """

    # Strip leading '#' if present (OpenAPI $ref is usually a fragment)
    if ref_path.startswith("#"):
        # allow '#', '#/', '#/a/b'
        ref_path = ref_path[1:]  # drop '#'

    if ref_path == "":
        return openapi_schema

    if not ref_path.startswith("/"):
        raise ValueError(f"Unsupported $ref (likely external file): {ref_path!r}")

    parts = ref_path.split("/")[1:]  # first element is empty due to leading '/'

    # Per RFC 6901, ~1 => '/', ~0 => '~'
    def unescape(token: str) -> str:
        return token.replace("~1", "/").replace("~0", "~")

    cur = openapi_schema
    for raw in parts:
        key = unescape(raw)
        try:
            cur = cur[key]
        except (KeyError, TypeError):
            raise KeyError(f"Key {key!r} not found while resolving {ref_path!r}")
    return cur


async def create_value(session, value, value_set_id, data_model_id, contributor, contributor_organization):
    value_data = {
        "ValueSetId": value_set_id,
        "DataModelId": data_model_id,
        "Description": value.get("Description", None),
        "UseConsiderations": value.get("UseConsiderations", None),
        "Value": value.get("Value", None),
        "ValueName": value.get("ValueName", None),
        "OriginalValueId": value.get("OriginalValueId", None),
        "Source": value.get("Source", None),
        "Notes": value.get("Notes", None),
        "Contributor": value.get("Contributor", contributor),
        "ContributorOrganization": value.get("ContributorOrganization", contributor_organization),
        "Extension": value.get("Extension", False),
        "ExtensionNotes": value.get("ExtensionNotes", None),
        "Deleted": False,
    }

    value_creation_date = parse_dt(value.get("CreationDate"))
    value_activation_date = parse_dt(value.get("ActivationDate"))
    value_deprecation_date = parse_dt(value.get("DeprecationDate"))

    if value_creation_date is not None:
        value_data["CreationDate"] = value_creation_date
    if value_activation_date is not None:
        value_data["ActivationDate"] = value_activation_date
    if value_deprecation_date is not None:
        value_data["DeprecationDate"] = value_deprecation_date

    value_set_value = ValueSetValue(**value_data)

    session.add(value_set_value)


async def create_value_if_needed(
    session: AsyncSession, value, value_set_id, data_model_id, data_model_type, contributor, contributor_organization
):
    existing_value = None
    if data_model_type in ["OrgLIF", "PartnerLIF"]:
        # Check if ValueSetValue already exists
        existing_value = await session.get(ValueSetValue, value.get("Id"))
    else:  # For other data model types, check by ValueSetId, Value, and DataModelId
        statement = select(ValueSetValue).where(
            ValueSetValue.ValueSetId == value_set_id,
            ValueSetValue.Value == value.get("Value"),
            ValueSetValue.DataModelId == data_model_id,
        )
        result = await session.execute(statement)
        existing_value = result.scalar_one_or_none()

    # If it does not exist or is deleted or has different value, create it
    if not existing_value or existing_value.Deleted or value.get("Value") != existing_value.Value:
        await create_value(session, value, value_set_id, data_model_id, contributor, contributor_organization)


async def create_attribute_if_needed(
    session: AsyncSession,
    attribute_name,
    attribute_md,
    data_model_id,
    data_model_type,
    contributor,
    contributor_organization,
    parent_entity_id=None,
):
    attribute = None
    if data_model_type in ["OrgLIF", "PartnerLIF"]:
        # Check if an attribute with the given Id and UniqueName already exists
        attribute = await session.get(Attribute, attribute_md.get("Id"))
    else:  # For other data model types, check by UniqueName and DataModelId
        statement = select(Attribute).where(
            Attribute.UniqueName == attribute_md.get("UniqueName", attribute_name),
            Attribute.DataModelId == data_model_id,
            Attribute.Deleted == False,
        )
        result = await session.execute(statement)
        attribute = result.scalar_one_or_none()

    # If it does not exist or is deleted or has different UniqueName, create it
    if not attribute or attribute.Deleted or attribute.UniqueName != attribute_md.get("UniqueName", attribute_name):
        attribute_data = {
            "Name": attribute_md.get("Name", attribute_name),
            "UniqueName": attribute_md.get("UniqueName", attribute_name),
            "Description": attribute_md.get("Description", None),
            "UseConsiderations": attribute_md.get("UseConsiderations", None),
            "DataModelId": data_model_id,
            "DataType": attribute_md.get("DataType", "string"),
            "ValueSetId": attribute_md.get("ValueSetId", None),
            "Required": attribute_md.get("Required", "No"),
            "Array": attribute_md.get("Array", "Yes"),
            "SourceModel": attribute_md.get("SourceModel", None),
            "Notes": attribute_md.get("Notes", None),
            "Contributor": attribute_md.get("Contributor", contributor),
            "ContributorOrganization": attribute_md.get("ContributorOrganization", contributor_organization),
            "Extension": attribute_md.get("Extension", False),
            "ExtensionNotes": attribute_md.get("ExtensionNotes", None),
            "Deleted": False,
            "Tags": attribute_md.get("Tags", None),
            "Example": attribute_md.get("Example", None),
            "Common": attribute_md.get("Common", False),
        }

        attr_creation_date = parse_dt(attribute_md.get("CreationDate"))
        attr_activation_date = parse_dt(attribute_md.get("ActivationDate"))
        attr_deprecation_date = parse_dt(attribute_md.get("DeprecationDate"))

        if attr_creation_date is not None:
            attribute_data["CreationDate"] = attr_creation_date
        if attr_activation_date is not None:
            attribute_data["ActivationDate"] = attr_activation_date
        if attr_deprecation_date is not None:
            attribute_data["DeprecationDate"] = attr_deprecation_date

        attribute = Attribute(**attribute_data)
        session.add(attribute)
        await session.flush()  # Ensure the attribute gets an ID

    # if data_model_type is OrgLIF or PartnerLIF, create ExtInclusion for this attribute
    if data_model_type in ["OrgLIF", "PartnerLIF"]:
        # Check if an inclusion already exists
        inclusion = await check_inclusion_exists(session, data_model_id, "Attribute", attribute.Id)

        if not inclusion:  # if no inclusion exists, create one
            inclusion = ExtInclusionsFromBaseDM(
                ExtDataModelId=data_model_id,
                ElementType="Attribute",
                IncludedElementId=attribute.Id,
                Notes=None,
                Contributor=contributor,
                ContributorOrganization=contributor_organization,
                Deleted=False,
                LevelOfAccess="Public",
                Queryable=attribute_md.get("x-queryable", False),
                Modifiable=attribute_md.get("x-mutable", False),
            )
            session.add(inclusion)

    # If needed, create EntityAttributeAssociation
    if parent_entity_id:
        # Check if an EntityAttributeAssociation already exists
        association = await check_existing_association(session, parent_entity_id, attribute.Id, data_model_id)
        if not association:  # If the EntityAttributeAssociation does not exist, create it
            association_data = {
                "EntityId": parent_entity_id,
                "AttributeId": attribute.Id,
                "Notes": attribute_md.get("AssociationNotes", None),
                "Contributor": attribute_md.get("AssociationContributor", contributor),
                "ContributorOrganization": attribute_md.get(
                    "AssociationContributorOrganization", contributor_organization
                ),
                "Deleted": False,
                "ExtendedByDataModelId": data_model_id
                if attribute_md.get("AssociationExtendedByDataModelId", None)
                and data_model_type in ["OrgLIF", "PartnerLIF"]
                else None,
            }

            assoc_creation_date = parse_dt(attribute_md.get("AssociationCreationDate"))
            assoc_activation_date = parse_dt(attribute_md.get("AssociationActivationDate"))
            assoc_deprecation_date = parse_dt(attribute_md.get("AssociationDeprecationDate"))

            if assoc_creation_date is not None:
                association_data["CreationDate"] = assoc_creation_date
            if assoc_activation_date is not None:
                association_data["ActivationDate"] = assoc_activation_date
            if assoc_deprecation_date is not None:
                association_data["DeprecationDate"] = assoc_deprecation_date

            association = EntityAttributeAssociation(**association_data)
            session.add(association)

    # Create ValueSet if needed
    if attribute_md.get("ValueSet", None):
        attribute_md_value_set = attribute_md.get("ValueSet", {})
        value_set = None
        if data_model_type in ["OrgLIF", "PartnerLIF"]:
            # Check if ValueSet already exists
            value_set = await session.get(ValueSet, attribute_md_value_set.get("Id"))
        else:  # For other data model types, check by Name and DataModelId
            statement = select(ValueSet).where(
                ValueSet.Name == attribute_md_value_set.get("Name"),
                ValueSet.DataModelId == data_model_id,
                ValueSet.Deleted == False,
            )
            result = await session.execute(statement)
            value_set = result.scalar_one_or_none()
        # If ValueSet does not exist, create it
        if (
            not value_set or value_set.Deleted or value_set.Name != attribute_md_value_set.get("Name")
        ):  # If it does not exist or is deleted or has different Name, create it
            value_set_data = {
                "Name": attribute_md_value_set.get("Name"),
                "Description": attribute_md_value_set.get("Description", None),
                "UseConsiderations": attribute_md_value_set.get("UseConsiderations", None),
                "DataModelId": data_model_id,
                "Notes": attribute_md_value_set.get("Notes", None),
                "Contributor": attribute_md_value_set.get("Contributor", contributor),
                "ContributorOrganization": attribute_md_value_set.get(
                    "ContributorOrganization", contributor_organization
                ),
                "Extension": attribute_md_value_set.get("Extension", False),
                "ExtensionNotes": attribute_md_value_set.get("ExtensionNotes", None),
                "Deleted": False,
                "Tags": attribute_md_value_set.get("Tags", None),
            }

            vs_creation_date = parse_dt(attribute_md_value_set.get("CreationDate"))
            vs_activation_date = parse_dt(attribute_md_value_set.get("ActivationDate"))
            vs_deprecation_date = parse_dt(attribute_md_value_set.get("DeprecationDate"))

            if vs_creation_date is not None:
                value_set_data["CreationDate"] = vs_creation_date
            if vs_activation_date is not None:
                value_set_data["ActivationDate"] = vs_activation_date
            if vs_deprecation_date is not None:
                value_set_data["DeprecationDate"] = vs_deprecation_date

            value_set = ValueSet(**value_set_data)
            session.add(value_set)
            await session.flush()  # Ensure the ValueSet gets an ID
            attribute.ValueSetId = value_set.Id

            # Create ValueSetValues
            values = attribute_md_value_set.get("Values", [])
            for value in values:
                await create_value(session, value, value_set.Id, data_model_id, contributor, contributor_organization)
        else:  # ValueSet exists, check if its values exist
            for value in attribute_md_value_set.get("Values", []):
                await create_value_if_needed(
                    session, value, value_set.Id, data_model_id, data_model_type, contributor, contributor_organization
                )


async def create_entity_if_needed(
    session: AsyncSession, entity_name, entity_md, data_model_id, data_model_type, contributor, contributor_organization
):
    entity = None
    # Check if an entity with the given Id and UniqueName already exists
    if data_model_type in ["OrgLIF", "PartnerLIF"]:
        entity = await session.get(Entity, entity_md.get("Id"))
    else:  # For other data model types, check by UniqueName and DataModelId
        entity = await get_unique_entity(
            session,
            entity_md.get("UniqueName", entity_name),
            data_model_id,
            entity_md.get("DataModelId"),
            data_model_type,
        )
    if (
        not entity or entity.Deleted or entity.UniqueName != entity_md.get("UniqueName", entity_name)
    ):  # if the entity does not exist or has a different UniqueName or is deleted, create it
        logger.info(
            f"Creating entity with unique name: {entity_md.get('UniqueName', entity_name)} and data model id: {data_model_id}"
        )
        entity_data = {
            "Name": entity_md.get("Name", entity_name),
            "UniqueName": entity_md.get("UniqueName", entity_name),
            "Description": entity_md.get("Description"),
            "UseConsiderations": entity_md.get("UseConsiderations"),
            "Required": entity_md.get("Required", "No"),
            "Array": entity_md.get("Array", "Yes"),
            "SourceModel": entity_md.get("SourceModel"),
            "DataModelId": data_model_id,
            "Notes": entity_md.get("Notes"),
            "Contributor": entity_md.get("Contributor", contributor),
            "ContributorOrganization": entity_md.get("ContributorOrganization", contributor_organization),
            "Extension": entity_md.get("Extension", False),
            "ExtensionNotes": entity_md.get("ExtensionNotes"),
            "Tags": entity_md.get("Tags"),
            "Common": entity_md.get("Common", False),
        }

        # Only set these if present; otherwise let DB defaults apply.
        cd = parse_dt(entity_md.get("CreationDate"))
        ad = parse_dt(entity_md.get("ActivationDate"))
        dd = parse_dt(entity_md.get("DeprecationDate"))
        if cd is not None:
            entity_data["CreationDate"] = cd
        if ad is not None:
            entity_data["ActivationDate"] = ad
        if dd is not None:
            entity_data["DeprecationDate"] = dd

        entity = Entity(**entity_data)
        session.add(entity)
        await session.flush()  # Ensure the entity gets an ID

    # if data_model_type is OrgLIF or PartnerLIF, create ExtInclusion for this entity
    if data_model_type in ["OrgLIF", "PartnerLIF"]:
        # Check if an inclusion already exists
        inclusion = await check_inclusion_exists(session, data_model_id, "Entity", entity.Id)

        if not inclusion:  # if no inclusion exists, create one
            inclusion = ExtInclusionsFromBaseDM(
                ExtDataModelId=data_model_id,
                ElementType="Entity",
                IncludedElementId=entity.Id,
                Notes=None,
                Contributor=contributor,
                ContributorOrganization=contributor_organization,
                Deleted=False,
                LevelOfAccess="Public",
                Queryable=entity_md.get("x-queryable", False),
                Modifiable=entity_md.get("x-mutable", False),
            )
            session.add(inclusion)

    return entity


async def create_entity_and_children_if_needed(
    session: AsyncSession, entity_name, entity_md, data_model_id, contributor, contributor_organization, data_model_type
):
    parent_entity = await create_entity_if_needed(
        session, entity_name, entity_md, data_model_id, data_model_type, contributor, contributor_organization
    )
    # Process child entities if any
    entity_properties = entity_md.get("properties", {})
    for prop_name, prop in entity_properties.items():
        if "$ref" in prop:
            continue  # Skip $ref properties for now; we need to make sure all entities are created to reference to first.
        if "ValueSetId" not in prop:  # It's a child entity
            child_entity = await create_entity_and_children_if_needed(
                session, prop_name, prop, data_model_id, contributor, contributor_organization, data_model_type
            )
            # Check if an EntityAssociation already exists, and create it if not
            entity_association = await get_entity_association_by_parent_child_relationship(
                session,
                parent_entity.Id,
                child_entity.Id,
                prop.get("EntityAssociationRelationship", None),
                data_model_id,
            )
            if not entity_association:
                association_data = {
                    "ParentEntityId": parent_entity.Id,
                    "ChildEntityId": child_entity.Id,
                    "Relationship": prop.get("EntityAssociationRelationship", None),
                    "Placement": prop.get("EntityAssociationPlacement", "Embedded"),
                    "Notes": prop.get("EntityAssociationNotes", None),
                    "Contributor": prop.get("EntityAssociationContributor", contributor),
                    "ContributorOrganization": prop.get(
                        "EntityAssociationContributorOrganization", contributor_organization
                    ),
                    "Deleted": False,
                    "Extension": prop.get("EntityAssociationExtension", False),
                    "ExtensionNotes": prop.get("EntityAssociationExtensionNotes", None),
                    "ExtendedByDataModelId": data_model_id
                    if prop.get("EntityAssociationExtendedByDataModelId", None)
                    and data_model_type in ["OrgLIF", "PartnerLIF"]
                    else None,
                }

                ea_creation_date = parse_dt(prop.get("EntityAssociationCreationDate"))
                ea_activation_date = parse_dt(prop.get("EntityAssociationActivationDate"))
                ea_deprecation_date = parse_dt(prop.get("EntityAssociationDeprecationDate"))

                if ea_creation_date is not None:
                    association_data["CreationDate"] = ea_creation_date
                if ea_activation_date is not None:
                    association_data["ActivationDate"] = ea_activation_date
                if ea_deprecation_date is not None:
                    association_data["DeprecationDate"] = ea_deprecation_date

                entity_association = EntityAssociation(**association_data)
                session.add(entity_association)
        else:  # It's an attribute (has top-level 'ValueSetId')
            await create_attribute_if_needed(
                session,
                prop_name,
                prop,
                data_model_id,
                data_model_type,
                contributor,
                contributor_organization,
                parent_entity.Id,
            )

    return parent_entity


# ---------------Main Function---------------


async def create_data_model_from_openapi_schema(
    session: AsyncSession,
    openapi_schema: Dict,
    data_model_name: str,
    data_model_version: str,
    data_model_type: str,
    data_model_description: Optional[str],
    base_data_model_id: Optional[int],
    use_considerations: Optional[str],
    notes: Optional[str],
    activation_date: Optional[str],
    deprecation_date: Optional[str],
    contributor: Optional[str],
    contributor_organization: Optional[str],
    state: Optional[str] = "Draft",
    tags: Optional[str] = None,
) -> DataModelDTO:
    # Check if DataModel with same Name, DataModelVersion, and ContributorOrganization already exists
    existing_dm_stmt = select(DataModel).where(
        DataModel.Name == data_model_name,
        DataModel.DataModelVersion == data_model_version,
        DataModel.ContributorOrganization == contributor_organization,
        DataModel.Deleted == False,
    )
    existing_dm_result = await session.execute(existing_dm_stmt)
    existing_dm = existing_dm_result.scalar_one_or_none()
    if existing_dm:
        raise ValueError(
            f"A DataModel with Name '{data_model_name}', Version '{data_model_version}', and "
            f"ContributorOrganization '{contributor_organization}' already exists."
        )

    # Create the DataModel instance
    new_data_model = DataModel(
        Name=data_model_name,
        Description=data_model_description,
        UseConsiderations=use_considerations,
        Type=data_model_type,
        BaseDataModelId=base_data_model_id,
        Notes=notes,
        DataModelVersion=data_model_version,
        ActivationDate=activation_date,
        DeprecationDate=deprecation_date,
        Contributor=contributor,
        ContributorOrganization=contributor_organization,
        Deleted=False,
        State=state,
        Tags=tags,
    )
    session.add(new_data_model)
    await session.flush()  # Ensure the new_data_model gets an ID

    # Process the OpenAPI schema to extract entities and attributes
    components = openapi_schema.get("components", {})
    schemas = components.get("schemas", {})

    for schema_name, schema in schemas.items():
        # Entities first (anything that lacks a top-level 'ValueSetId'); attributes afterward.
        if "$ref" in schema:
            continue  # Skip $ref schemas for now. We need to make sure all entities are created to reference to first.
        if "ValueSetId" not in schema:  # It's an entity
            await create_entity_and_children_if_needed(
                session, schema_name, schema, new_data_model.Id, contributor, contributor_organization, data_model_type
            )
        else:  # It's an attribute (has top-level 'ValueSetId')
            await create_attribute_if_needed(
                session, schema_name, schema, new_data_model.Id, data_model_type, contributor, contributor_organization
            )

    ## After everything has been created, process references
    for schema_name, schema in schemas.items():
        await create_reference_associations_for_children(
            session, schema, new_data_model.Id, openapi_schema, data_model_type
        )

    await session.commit()
    await session.refresh(new_data_model)
    return DataModelDTO.from_orm(new_data_model)


async def update_data_model_from_openapi_schema(
    session: AsyncSession, data_model: DataModel, openapi_schema: Dict
) -> None:
    # Process the OpenAPI schema to extract entities and attributes
    components = openapi_schema.get("components", {})
    schemas = components.get("schemas", {})
    logger.info(f"Updating data model {data_model.Id} with schemas: {list(schemas.keys())} ")

    for schema_name, schema in schemas.items():
        # Entities first (anything that lacks a top-level 'ValueSetId'); attributes afterward.
        if "$ref" in schema:
            continue  # Skip $ref schemas for now. We need to make sure all entities are created to reference to first.
        if "ValueSetId" not in schema:  # It's an entity
            logger.info(f"Updating entity and children for schema: {schema_name}")
            # await update_entity_and_children_if_needed(
            #     session,
            #     schema_name,
            #     schema,
            #     data_model.Id,
            #     data_model.Contributor,
            #     data_model.ContributorOrganization,
            #     data_model.Type,
            # )
        else:  # It's an attribute (has top-level 'ValueSetId')
            logger.info(f"Updating attribute for schema: {schema_name}")
            # await create_attribute_if_needed(
            #     session,
            #     schema_name,
            #     schema,
            #     data_model.Id,
            #     data_model.Type,
            #     data_model.Contributor,
            #     data_model.ContributorOrganization,
            # )

    ## After everything has been updated, process references
    for schema_name, schema in schemas.items():
        logger.info(f"Updating reference associations for schema: {schema_name}")
        # await update_reference_associations_for_children(
        #     session, schema, data_model.Id, openapi_schema, data_model.Type
        # )

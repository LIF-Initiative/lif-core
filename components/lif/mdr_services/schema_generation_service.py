from copy import deepcopy
from fastapi import HTTPException
from lif.datatypes.mdr_sql_model import Entity, EntityAssociation, ExtInclusionsFromBaseDM, ValueSet, ValueSetValue
from lif.mdr_services.attribute_service import get_attributes_with_association_metadata_for_entity
from lif.mdr_services.datamodel_service import get_datamodel_by_id
from lif.mdr_services.entity_service import get_entity_by_id
from lif.mdr_utils.logger_config import get_logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from sqlalchemy import and_, or_
import pandas as pd

logger = get_logger(__name__)

INCLUDED_FIELDS_MAP = {
    "Description": "description",
    "UseConsiderations": "use_recommendations",
    "Example": "example",
    "Format": "format",
    "DataType": "type",
}

ATTRIBUTE_ASSOCIATION_FIELDS = [
    "EntityAttributeAssociationId",
    "EntityId",
    "AssociationContributorOrganization",
    "AssociationExtendedByDataModelId",
    "AssociationCreationDate",
    "AssociationActivationDate",
    "AssociationDeprecationDate",
    "AssociationNotes",
    "AssociationContributor",
    "AssociationContributorOrganization",
    "AssociationExtendedByDataModelId",
]


async def find_children(
    tree,
    parent,
    parent_schema,
    df_entity,
    session,
    include_attr_md,
    data_model_id,
    data_model,
    include_entity_md,
    public_only,
    full_export,
):
    if parent in tree:
        parent_properties = parent_schema["properties"]
        for x in tree[parent]:
            if data_model.Type in ["OrgLIF", "PartnerLIF"]:
                child_association_query = select(EntityAssociation).where(
                    EntityAssociation.ParentEntityId == parent,
                    EntityAssociation.ChildEntityId == x,
                    EntityAssociation.Deleted == False,
                    or_(
                        EntityAssociation.ExtendedByDataModelId == data_model_id,
                        EntityAssociation.ExtendedByDataModelId.is_(None),
                    ),
                )
            else:
                child_association_query = select(EntityAssociation).where(
                    EntityAssociation.ParentEntityId == parent,
                    EntityAssociation.ChildEntityId == x,
                    EntityAssociation.Deleted == False,
                    EntityAssociation.ExtendedByDataModelId.is_(None),
                )
            child_association_result = await session.execute(child_association_query)
            child_associations = child_association_result.scalars().all()

            for child_association in child_associations:
                entity_name = ""
                if child_association.Relationship is not None and not (
                    child_association.Relationship.startswith("has")
                    or child_association.Relationship.startswith("relevant")
                ):
                    entity_name = child_association.Relationship

                entity_data = await get_entity_by_id(session=session, id=x)

                entity_name = entity_name + entity_data.Name

                parent_properties[entity_name] = {}
                parent_properties[entity_name]["type"] = "array" if entity_data.Array == "Yes" else "object"
                parent_properties[entity_name]["required"] = []
                parent_properties[entity_name]["use_recommendations"] = (
                    entity_data.UseConsiderations if entity_data.UseConsiderations else ""
                )  # Using empty string instead of null to make it easier to diff w/ P1 lif.json schema
                required_elements = []
                for key, value in entity_data.__dict__.items():
                    if include_entity_md:
                        parent_properties[entity_name][key] = value
                    if key == "Required" and value == "Yes" and entity_name not in parent_schema["required"]:
                        parent_schema["required"].append(entity_name)
                if include_entity_md:
                    if full_export:
                        parent_properties[entity_name]["EntityAssociationId"] = child_association.Id
                        parent_properties[entity_name]["EntityAssociationParentEntityId"] = (
                            child_association.ParentEntityId
                        )
                        parent_properties[entity_name]["EntityAssociationRelationship"] = child_association.Relationship
                        parent_properties[entity_name]["EntityAssociationPlacement"] = child_association.Placement
                        parent_properties[entity_name]["EntityAssociationNotes"] = child_association.Notes
                        parent_properties[entity_name]["EntityAssociationCreationDate"] = child_association.CreationDate
                        parent_properties[entity_name]["EntityAssociationActivationDate"] = (
                            child_association.ActivationDate
                        )
                        parent_properties[entity_name]["EntityAssociationDeprecationDate"] = (
                            child_association.DeprecationDate
                        )
                        parent_properties[entity_name]["EntityAssociationContributor"] = child_association.Contributor
                        parent_properties[entity_name]["EntityAssociationContributorOrganization"] = (
                            child_association.ContributorOrganization
                        )
                        parent_properties[entity_name]["EntityAssociationExtension"] = child_association.Extension
                        parent_properties[entity_name]["EntityAssociationExtensionNotes"] = (
                            child_association.ExtensionNotes
                        )
                        parent_properties[entity_name]["EntityAssociationExtendedByDataModelId"] = (
                            child_association.ExtendedByDataModelId
                        )

                if data_model.Type in ["OrgLIF", "PartnerLIF"]:
                    inclusions_query = select(ExtInclusionsFromBaseDM).where(
                        ExtInclusionsFromBaseDM.ExtDataModelId == data_model_id,
                        ExtInclusionsFromBaseDM.IncludedElementId == x,
                        ExtInclusionsFromBaseDM.ElementType == "Entity",
                        ExtInclusionsFromBaseDM.Deleted == False,
                    )
                    if public_only:
                        inclusions_query = inclusions_query.where(ExtInclusionsFromBaseDM.LevelOfAccess == "Public")
                    inclusions_result = await session.execute(inclusions_query)
                    inclusion = inclusions_result.scalars().first()
                    if inclusion:
                        parent_properties[entity_name]["x-mutable"] = inclusion.Modifiable
                        parent_properties[entity_name]["x-queryable"] = inclusion.Queryable
                    else:
                        raise HTTPException(
                            status_code=404,
                            detail=f"Inclusion not found for Entity ID {parent} in Extension Data Model ID {data_model_id}",
                        )

                parent_properties[entity_name]["properties"] = {}

                attributes_with_assoc_md = await get_attributes_with_association_metadata_for_entity(
                    session=session,
                    entity_id=x,
                    data_model_id=data_model_id,
                    data_model_type=data_model.Type,
                    public_only=public_only,
                )
                logger.info(f"attributes for entity id {x} : {attributes_with_assoc_md}")

                if data_model.Type in ["OrgLIF", "PartnerLIF"]:
                    inclusions_query = select(ExtInclusionsFromBaseDM).where(
                        ExtInclusionsFromBaseDM.ExtDataModelId == data_model_id,
                        ExtInclusionsFromBaseDM.ElementType == "Attribute",
                        ExtInclusionsFromBaseDM.Deleted == False,
                    )
                    if public_only:
                        inclusions_query = inclusions_query.where(ExtInclusionsFromBaseDM.LevelOfAccess == "Public")
                    inclusions_result = await session.execute(inclusions_query)
                    inclusion_attributes = inclusions_result.scalars().all()

                if len(attributes_with_assoc_md) > 0:
                    for attribute_with_assoc_md in attributes_with_assoc_md:
                        attribute_dict = attribute_with_assoc_md.dict()
                        if attribute_with_assoc_md.Required == "Yes":
                            required_elements.append(attribute_with_assoc_md.Name)
                        if attribute_with_assoc_md.DataType != "Entity":
                            if not include_attr_md:
                                if attribute_with_assoc_md.Array == "Yes":
                                    attribute_dict["Format"] = attribute_dict["DataType"]
                                    attribute_dict["DataType"] = "array"
                                else:
                                    attribute_dict["Format"] = (
                                        ""  # Using empty string instead of null to make it easier to diff w/ P1 lif.json schema
                                    )
                                # Remove all fields except those whose keys match the keys of the INCLUDED_FIELDS_MAP
                                attribute_dict = {k: v for k, v in attribute_dict.items() if k in INCLUDED_FIELDS_MAP}
                                # Convert keys in attribute_dict to the corresponding value in the INCLUDED_FIELDS_MAP
                                attribute_dict = {INCLUDED_FIELDS_MAP[k]: v for k, v in attribute_dict.items()}
                                # If a value is null, replace it with an empty string
                                attribute_dict = {
                                    k: (v if v is not None else "") for k, v in attribute_dict.items()
                                }  # Using empty string instead of null to make it easier to diff w/ P1 lif.json schema
                            elif data_model.Type in ["OrgLIF", "PartnerLIF"]:
                                # Find value in inclusion_attributes where IncludedElementId matches attribute.Id
                                inclusion_attribute = next(
                                    (
                                        inclusion
                                        for inclusion in inclusion_attributes
                                        if inclusion.IncludedElementId == attribute_with_assoc_md.Id
                                    ),
                                    None,
                                )
                                if inclusion_attribute:
                                    attribute_dict["x-mutable"] = inclusion_attribute.Modifiable
                                    attribute_dict["x-queryable"] = inclusion_attribute.Queryable
                                else:
                                    raise HTTPException(
                                        status_code=404,
                                        detail=f"Inclusion not found for Attribute ID {attribute_with_assoc_md.Id} in Extension Data Model ID {data_model_id}",
                                    )
                            if not full_export:
                                # Remove fields related to association metadata
                                for field in ATTRIBUTE_ASSOCIATION_FIELDS:
                                    if field in attribute_dict:
                                        del attribute_dict[field]
                            parent_properties[entity_name]["properties"][attribute_with_assoc_md.Name] = attribute_dict
                            # Adding enums
                            if attribute_with_assoc_md.ValueSetId:
                                # cur.execute('select "Value" FROM public."ValueSetValues"  where "ValueSetId" = ' + str(attribute_data["ValueSetId"]))
                                # rows = cur.fetchall()
                                # valueset_values = [row[0] for row in rows]
                                query = select(ValueSetValue.Value).where(
                                    ValueSetValue.ValueSetId == attribute_with_assoc_md.ValueSetId,
                                    ValueSetValue.Deleted == False,
                                )
                                result = await session.execute(query)
                                values = result.scalars().all()
                                parent_properties[entity_name]["properties"][attribute_with_assoc_md.Name]["enum"] = (
                                    values
                                )
                                if full_export:
                                    query = select(ValueSet).where(
                                        ValueSet.Id == attribute_with_assoc_md.ValueSetId, ValueSet.Deleted == False
                                    )
                                    result = await session.execute(query)
                                    valueset = result.scalars().first()
                                    if valueset:
                                        parent_properties[entity_name]["properties"][attribute_with_assoc_md.Name][
                                            "ValueSet"
                                        ] = {}
                                        for key, value in valueset.__dict__.items():
                                            if key != "Deleted":
                                                parent_properties[entity_name]["properties"][
                                                    attribute_with_assoc_md.Name
                                                ]["ValueSet"][key] = value
                                        query = select(ValueSetValue).where(
                                            ValueSetValue.ValueSetId == attribute_with_assoc_md.ValueSetId,
                                            ValueSetValue.Deleted == False,
                                        )
                                        result = await session.execute(query)
                                        valueset_values_full = result.scalars().all()
                                        parent_properties[entity_name]["properties"][attribute_with_assoc_md.Name][
                                            "ValueSet"
                                        ]["Values"] = valueset_values_full
                    parent_properties[entity_name]["required"] = required_elements

                await find_children(
                    tree,
                    x,
                    parent_properties[entity_name],
                    df_entity=df_entity,
                    session=session,
                    include_attr_md=include_attr_md,
                    data_model_id=data_model_id,
                    data_model=data_model,
                    include_entity_md=include_entity_md,
                    public_only=public_only,
                    full_export=full_export,
                )


async def find_ancestors(session, child_id, data_model_type, data_model_id, included_entity_ids):
    """
    Recursively fetch every ancestor chain for a given entity.

    Args:
        session: Async database session used to query `EntityAssociation` records.
        child_id: Identifier of the entity whose ancestors should be discovered.
        data_model_type: Data model variant (e.g. `OrgLIF`, `PartnerLIF`) that determines
            which associations are valid in the lookup.
        data_model_id: Identifier of the active data model to respect extension rules.
        included_entity_ids: Entity ids that are eligible to act as parents when
            resolving Org/Partner LIF hierarchies.

    Returns:
        list[list[int]]: Each list contains ancestor entity ids ordered from the root
        ancestor to the direct parent of `child_id`. An empty list indicates that the
        entity has no qualifying ancestors.
    """
    ancestors = []
    ancestor_id = child_id
    if data_model_type in ["OrgLIF", "PartnerLIF"]:
        query = select(EntityAssociation).where(
            EntityAssociation.ParentEntityId.in_(included_entity_ids),
            EntityAssociation.ChildEntityId == ancestor_id,
            EntityAssociation.Deleted == False,
            or_(EntityAssociation.Placement.is_(None), EntityAssociation.Placement == "Embedded"),
            or_(
                EntityAssociation.ExtendedByDataModelId == data_model_id,
                EntityAssociation.ExtendedByDataModelId.is_(None),
            ),
        )
    else:
        query = select(EntityAssociation).where(
            EntityAssociation.ChildEntityId == ancestor_id,
            EntityAssociation.Deleted == False,
            or_(EntityAssociation.Placement.is_(None), EntityAssociation.Placement == "Embedded"),
            EntityAssociation.ExtendedByDataModelId.is_(None),
        )
    result = await session.execute(query)
    entity_associations = result.scalars().all()
    # First set of ancestors is ParentEntityId of all associations
    for entity_association in entity_associations:
        parent_id = entity_association.ParentEntityId
        logger.debug(f"Finding ancestors for parent_id : {parent_id}")
        parent_ancestors = await find_ancestors(session, parent_id, data_model_type, data_model_id, included_entity_ids)
        logger.debug(f"Found ancestors for parent_id {parent_id} : {parent_ancestors}")
        if len(parent_ancestors) == 0:
            ancestors.append([parent_id])
        else:
            for parent_ancestor_line in parent_ancestors:
                # The recursive call already returns each line ordered root -> parent, so the
                # parent id appends straight onto the end. Reversing here scrambled any line
                # longer than one element, which made add_ref look for a nested entity name at
                # the top level of components.schemas and raise a KeyError. A single-element
                # line was unaffected, which is why this only surfaced for a Reference whose
                # target sits three or more levels deep.
                parent_ancestor_line.append(parent_id)
                logger.debug(f"parent_ancestor_line: {parent_ancestor_line}")
                ancestors.append(parent_ancestor_line)

    return ancestors


async def add_ref(
    parent_ancestors, child_ancestors, df_entity, parent_entity_name, child_entity_name, openapi_spec, key
):
    """
    Inline the schema for a referenced child entity under the parent's OpenAPI schema entry.

    Follows the child's ancestor path within `openapi_spec`, clones the referenced schema, narrows the child
    `properties` to the fields enumerated in its `required` list, forces the type to `object`, and assigns the
    result to `key` within the parent schema's properties.

    Args:
        parent_ancestors: Ancestor paths for the parent entity used to locate the parent schema container.
        child_ancestors: Ancestor path for the child entity used to locate the referenced schema.
        df_entity: DataFrame that maps entity IDs to their names.
        parent_entity_name: Name of the parent entity receiving the reference.
        child_entity_name: Name of the child entity being referenced.
        openapi_spec: Mutable OpenAPI specification dictionary being populated.
        key: Property name under which to store the inlined child schema.
    """
    logger.info("In add ref")
    ref_data = {}
    if len(child_ancestors) > 1:
        logger.error("Child has multiple ancestor lines. This means the child is not unique.")
        raise HTTPException(
            status_code=400,
            detail=f"Child entity {child_entity_name} has multiple ancestor lines. This means the child is not unique.",
        )
    schema_container = openapi_spec["components"]["schemas"]
    referenced_schema = None
    if len(child_ancestors) == 1 and len(child_ancestors[0]) > 0:
        for index, child_ancestor_id in enumerate(child_ancestors[0]):
            logger.info(f"child_ancestor_id : {child_ancestor_id}")
            entity_name = (df_entity[df_entity["Id"] == child_ancestor_id])["Name"].unique().tolist()[0]
            schema_container = schema_container[entity_name]["properties"]
    referenced_schema = schema_container[child_entity_name]
    ref_data = deepcopy(referenced_schema)
    properties = ref_data.get("properties")
    if isinstance(properties, dict):
        # In LIF, "Reference" is intended to be instantiated as only the required fields of the referenced entity.
        # These can be used to look up the full entity.
        required_fields = ref_data.get("required", [])
        if isinstance(required_fields, list) and required_fields:
            required_fields_set = set(required_fields)
            ref_data["properties"] = {
                prop_name: prop_value
                for prop_name, prop_value in properties.items()
                if prop_name in required_fields_set
            }
        else:
            ref_data["properties"] = {}
    ref_data["type"] = "object"  # A reference should always be to a single object, not an array of objects.
    logger.info(f"ref_data : {ref_data}")

    if len(parent_ancestors) == 0:
        # No Parent - root entity
        openapi_spec["components"]["schemas"][parent_entity_name]["properties"][key] = ref_data
    else:
        for ancestor_line in parent_ancestors:
            # Getting root property
            root_property = (df_entity[df_entity["Id"] == ancestor_line[0]])["Name"].unique().tolist()[0]
            logger.info(f"root_property : {root_property}")
            current_dict = openapi_spec["components"]["schemas"][root_property]
            for parent_ancestors_id in ancestor_line[1:]:  # Skip the root property
                sub_root = (df_entity[df_entity["Id"] == parent_ancestors_id])["Name"].unique().tolist()[0]
                current_dict = current_dict["properties"][sub_root]
            current_dict = current_dict["properties"][parent_entity_name]
            current_dict["properties"][key] = ref_data


async def get_all_entity_data_frame(session: AsyncSession):
    entity_query = select(Entity.Id, Entity.Name).where(Entity.Deleted == False)
    execution = await session.execute(entity_query)
    result = execution.fetchall()
    column_names = result[0]._fields if result else []
    df_entity = pd.DataFrame(result, columns=column_names)
    logger.info(f"df_entity : {df_entity}")
    return df_entity


async def generate_openapi_schema(
    session: AsyncSession,
    data_model_id: int,
    include_attr_md: bool,
    include_entity_md: bool,
    public_only: bool = False,
    full_export: bool = False,
):
    tree = {}
    top_level_parents = []

    # Getting data model details
    data_model = await get_datamodel_by_id(session=session, id=data_model_id)
    logger.info(f"-- data_model : {data_model}")

    data_model_name = data_model.Name
    data_model_version = data_model.DataModelVersion

    # Initialize the OpenAPI specification as a dictionary
    openapi_spec = {
        "openapi": "3.0.0",  # The version of the OpenAPI Specification
        "info": {
            "title": "Machine-Readable Schema for " + data_model_name,  # The title of the API
            "version": data_model_version,  # The version of the API
            "description": "OpenAPI Spec",  # A brief description of the API
        },
        "paths": {},  # The available paths and operations for the API
        "components": {"schemas": {}},  # The reusable schemas for the API
    }

    query = None
    included_entity_ids = []
    # If data model type is OrgLIF or PartnerLIF, find only included entity ids
    if data_model.Type in ["OrgLIF", "PartnerLIF"]:
        ext_inclusions_query = select(ExtInclusionsFromBaseDM.IncludedElementId).where(
            ExtInclusionsFromBaseDM.ExtDataModelId == data_model_id,
            ExtInclusionsFromBaseDM.ElementType == "Entity",
            ExtInclusionsFromBaseDM.Deleted == False,
        )
        if public_only:
            ext_inclusions_query = ext_inclusions_query.where(ExtInclusionsFromBaseDM.LevelOfAccess == "Public")
        execution = await session.execute(ext_inclusions_query)
        included_entity_ids = [row[0] for row in execution.fetchall()]
        logger.info(f"included_entity_ids : {included_entity_ids}")
        # where Placement is either "Embedded" or null
        query = (
            select(EntityAssociation.ParentEntityId, EntityAssociation.ChildEntityId)
            .select_from(EntityAssociation)
            .join(Entity, Entity.Id == EntityAssociation.ParentEntityId)
            .where(
                EntityAssociation.ParentEntityId.in_(included_entity_ids),
                EntityAssociation.ChildEntityId.in_(included_entity_ids),
                EntityAssociation.Deleted.is_(False),
                or_(EntityAssociation.Placement.is_(None), EntityAssociation.Placement == "Embedded"),
                # Not checking by data model id because OrgLIF and PartnerLIF can have entities from multiple base data models
            )
        )
    else:
        # Query for associations where the parent entity belongs to the given data model
        query = (
            select(EntityAssociation.ParentEntityId, EntityAssociation.ChildEntityId)
            .join(Entity, Entity.Id == EntityAssociation.ParentEntityId)
            .where(
                Entity.DataModelId == data_model_id,
                EntityAssociation.Deleted == False,
                EntityAssociation.ExtendedByDataModelId.is_(None),
                or_(EntityAssociation.Placement.is_(None), EntityAssociation.Placement == "Embedded"),
            )
        )

    result = await session.execute(query)
    entity_associations = result.fetchall()

    parent_id_list = []
    child_id_list = []
    for row in entity_associations:
        logger.info(f"row : {row}")
        parent = row[0]
        child = row[1]

        if parent not in parent_id_list:
            parent_id_list.append(parent)

        if child not in child_id_list:
            child_id_list.append(child)
        if parent in tree:
            tree[parent].append(child)
        else:
            tree[parent] = [child]

    logger.info(f"Final tree : {tree}")
    top_level_parents = [p for p in parent_id_list if p not in child_id_list]
    logger.info(f"top_level_parents: {top_level_parents}")

    # Combine both columns of entity_associations into a single list
    all_entity_ids_with_embedded_associations = list(set(parent_id_list + child_id_list))
    logger.info(f"All entity IDs with embedded associations: {all_entity_ids_with_embedded_associations}")

    # Main query
    # Combine both columns of entity_associations into a single list
    all_entity_ids_with_embedded_associations = list(set(parent_id_list + child_id_list))
    logger.info(f"All entity IDs with embedded associations: {all_entity_ids_with_embedded_associations}")

    # Main query
    if data_model.Type in ["OrgLIF", "PartnerLIF"]:
        query = select(Entity.Id).where(
            and_(
                Entity.Id.notin_(
                    all_entity_ids_with_embedded_associations
                ),  # Exclude Entities that are already accounted for
                Entity.Deleted == False,
                # Not checking by data model id because OrgLIF and PartnerLIF can have entities from multiple base data models
            )
        )
    else:
        query = select(Entity.Id).where(
            and_(
                Entity.Id.notin_(
                    all_entity_ids_with_embedded_associations
                ),  # Exclude Entities that are already accounted for
                Entity.DataModelId == data_model_id,  # Filter by DataModelId
                Entity.Deleted == False,
            )
        )

    # Execute the query
    result = await session.execute(query)
    entities = result.fetchall()

    for row in entities:
        logger.info(f" --- row : {row}")
        parent = row[0]
        if data_model.Type in ["OrgLIF", "PartnerLIF"] and parent not in included_entity_ids:
            continue
        tree[parent] = []
        top_level_parents.append(parent)
    logger.info(f" ** top_level_parents: {top_level_parents}")
    logger.info(f" ** tree: {tree}")

    # Convert the result into a pandas DataFrame
    df_entity = await get_all_entity_data_frame(session=session)
    logger.info(f"df_entity :{df_entity}")

    tree_with_entity_names = {}
    for parent, child_list in tree.items():
        logger.info("----++++++++++++-----------++++++++++++")
        logger.info(f"parent :{parent}")
        parent_entity_name = (df_entity[df_entity["Id"] == parent])["Name"].unique().tolist()[0]
        # logger.info(f"parent_entity_name : {parent_entity_name}")
        if isinstance(child_list, list) and len(child_list) > 0:
            tree_with_entity_names[parent_entity_name] = []
            for child_entity_id in child_list:
                child_entity_name = (df_entity[df_entity["Id"] == child_entity_id])["Name"].unique().tolist()[0]
                # logger.info(f"child_entity_name : {child_entity_name}")
                tree_with_entity_names[parent_entity_name].append(child_entity_name)
    logger.info(f"tree_with_entity_names : {tree_with_entity_names}")

    top_level_entity_names = []
    for entity_id in top_level_parents:
        parent_entity_name = (df_entity[df_entity["Id"] == entity_id])["Name"].unique().tolist()[0]
        top_level_entity_names.append(parent_entity_name)
    logger.info(f"top_level_entity_names : {top_level_entity_names}")

    for parent in top_level_parents:
        parent_entity = await get_entity_by_id(session=session, id=parent)
        openapi_spec["components"]["schemas"][parent_entity.Name] = {}
        openapi_spec["components"]["schemas"][parent_entity.Name]["type"] = (
            "array" if parent_entity.Array == "Yes" else "object"
        )
        openapi_spec["components"]["schemas"][parent_entity.Name]["required"] = []
        openapi_spec["components"]["schemas"][parent_entity.Name]["use_recommendations"] = (
            parent_entity.UseConsiderations if parent_entity.UseConsiderations else ""
        )  # Using empty string instead of null to make it easier to diff w/ P1 lif.json schema
        required_elements = []
        if include_entity_md:
            for key, value in parent_entity.__dict__.items():
                openapi_spec["components"]["schemas"][parent_entity.Name][key] = value
                if key == "Required" and value == "Yes":
                    required_elements.append(parent_entity.Name)

        if data_model.Type in ["OrgLIF", "PartnerLIF"]:
            inclusions_query = select(ExtInclusionsFromBaseDM).where(
                ExtInclusionsFromBaseDM.ExtDataModelId == data_model_id,
                ExtInclusionsFromBaseDM.IncludedElementId == parent,
                ExtInclusionsFromBaseDM.ElementType == "Entity",
                ExtInclusionsFromBaseDM.Deleted == False,
            )
            if public_only:
                ext_inclusions_query = ext_inclusions_query.where(ExtInclusionsFromBaseDM.LevelOfAccess == "Public")
            inclusions_result = await session.execute(inclusions_query)
            inclusion = inclusions_result.scalars().first()
            if inclusion:
                openapi_spec["components"]["schemas"][parent_entity.Name]["x-mutable"] = inclusion.Modifiable
                openapi_spec["components"]["schemas"][parent_entity.Name]["x-queryable"] = inclusion.Queryable
            else:
                raise HTTPException(
                    status_code=404,
                    detail=f"Inclusion not found for Entity ID {parent} in Extension Data Model ID {data_model_id}",
                )

        attributes_with_assoc_md = await get_attributes_with_association_metadata_for_entity(
            session=session,
            entity_id=parent,
            data_model_id=data_model_id,
            data_model_type=data_model.Type,
            public_only=public_only,
        )
        logger.info(f"attributes for entity id {entity_id} : {attributes_with_assoc_md}")

        if data_model.Type in ["OrgLIF", "PartnerLIF"]:
            inclusions_query = select(ExtInclusionsFromBaseDM).where(
                ExtInclusionsFromBaseDM.ExtDataModelId == data_model_id,
                ExtInclusionsFromBaseDM.ElementType == "Attribute",
                ExtInclusionsFromBaseDM.Deleted == False,
            )
            if public_only:
                ext_inclusions_query = ext_inclusions_query.where(ExtInclusionsFromBaseDM.LevelOfAccess == "Public")
            inclusions_result = await session.execute(inclusions_query)
            inclusion_attributes = inclusions_result.scalars().all()

        # logger.info(f"attributes :{attributes}")
        openapi_spec["components"]["schemas"][parent_entity.Name]["properties"] = {}
        if len(attributes_with_assoc_md) > 0:
            for attribute_with_assoc_md in attributes_with_assoc_md:
                attribute_dict = attribute_with_assoc_md.dict()
                if attribute_with_assoc_md.Required == "Yes":
                    required_elements.append(attribute_with_assoc_md.Name)
                if attribute_with_assoc_md.DataType != "Entity":
                    if not include_attr_md:
                        if attribute_with_assoc_md.Array == "Yes":
                            attribute_dict["Format"] = attribute_dict["DataType"]
                            attribute_dict["DataType"] = "array"
                        else:
                            attribute_dict["Format"] = (
                                ""  # Using empty string instead of null to make it easier to diff w/ P1 lif.json schema
                            )
                        # Remove all fields except those whose keys match the keys of the INCLUDED_FIELDS_MAP
                        attribute_dict = {k: v for k, v in attribute_dict.items() if k in INCLUDED_FIELDS_MAP}
                        # Convert keys in attribute_dict to the corresponding value in the INCLUDED_FIELDS_MAP
                        attribute_dict = {INCLUDED_FIELDS_MAP[k]: v for k, v in attribute_dict.items()}
                        # If a value is null, replace it with an empty string
                        attribute_dict = {
                            k: (v if v is not None else "") for k, v in attribute_dict.items()
                        }  # Using empty string instead of null to make it easier to diff w/ P1 lif.json schema
                    elif data_model.Type in ["OrgLIF", "PartnerLIF"]:
                        # Find value in inclusion_attributes where IncludedElementId matches attribute.Id
                        inclusion_attribute = next(
                            (
                                inclusion
                                for inclusion in inclusion_attributes
                                if inclusion.IncludedElementId == attribute_with_assoc_md.Id
                            ),
                            None,
                        )
                        if inclusion_attribute:
                            attribute_dict["x-mutable"] = inclusion_attribute.Modifiable
                            attribute_dict["x-queryable"] = inclusion_attribute.Queryable
                        else:
                            raise HTTPException(
                                status_code=404,
                                detail=f"Inclusion not found for Attribute ID {attribute_with_assoc_md.Id} in Extension Data Model ID {data_model_id}",
                            )
                    if not full_export:
                        # Remove fields related to association metadata
                        for field in ATTRIBUTE_ASSOCIATION_FIELDS:
                            if field in attribute_dict:
                                del attribute_dict[field]
                    openapi_spec["components"]["schemas"][parent_entity.Name]["properties"][
                        attribute_with_assoc_md.Name
                    ] = attribute_dict
                    # Adding enums
                    if attribute_with_assoc_md.ValueSetId:
                        query = select(ValueSetValue.Value).where(
                            ValueSetValue.ValueSetId == attribute_with_assoc_md.ValueSetId,
                            ValueSetValue.Deleted == False,
                        )
                        result = await session.execute(query)
                        values = result.fetchall()
                        # logger.info(f"values :{values}")
                        valueset_values = [row[0] for row in values]
                        openapi_spec["components"]["schemas"][parent_entity.Name]["properties"][
                            attribute_with_assoc_md.Name
                        ]["enum"] = valueset_values
                        if full_export:
                            query = select(ValueSet).where(
                                ValueSet.Id == attribute_with_assoc_md.ValueSetId, ValueSet.Deleted == False
                            )
                            result = await session.execute(query)
                            valueset = result.scalars().first()
                            if valueset:
                                openapi_spec["components"]["schemas"][parent_entity.Name]["properties"][
                                    attribute_with_assoc_md.Name
                                ]["ValueSet"] = {}
                                for key, value in valueset.__dict__.items():
                                    if key != "Deleted":
                                        openapi_spec["components"]["schemas"][parent_entity.Name]["properties"][
                                            attribute_with_assoc_md.Name
                                        ]["ValueSet"][key] = value
                                query = select(ValueSetValue).where(
                                    ValueSetValue.ValueSetId == attribute_with_assoc_md.ValueSetId,
                                    ValueSetValue.Deleted == False,
                                )
                                result = await session.execute(query)
                                valueset_values_full = result.scalars().all()
                                openapi_spec["components"]["schemas"][parent_entity.Name]["properties"][
                                    attribute_with_assoc_md.Name
                                ]["ValueSet"]["Values"] = valueset_values_full

            openapi_spec["components"]["schemas"][parent_entity.Name]["required"] = required_elements

        await find_children(
            tree,
            parent,
            openapi_spec["components"]["schemas"][parent_entity.Name],
            session=session,
            df_entity=df_entity,
            include_attr_md=include_attr_md,
            data_model_id=data_model_id,
            data_model=data_model,
            include_entity_md=include_entity_md,
            public_only=public_only,
            full_export=full_export,
        )

    # logger.info("openapi_spec ----------- ")
    # logger.info(openapi_spec)

    # Processing Inter-entity links - Now Updated to just process Reference placement
    query = None
    if data_model.Type in ["OrgLIF", "PartnerLIF"]:
        query = (
            select(
                EntityAssociation.ParentEntityId,
                EntityAssociation.ChildEntityId,
                EntityAssociation.Relationship,
                EntityAssociation.Placement,
            )
            .join(Entity, Entity.Id == EntityAssociation.ParentEntityId)
            .where(
                EntityAssociation.ParentEntityId.in_(included_entity_ids),
                EntityAssociation.ChildEntityId.in_(included_entity_ids),
                EntityAssociation.Placement == "Reference",
                EntityAssociation.Deleted == False,
                or_(
                    EntityAssociation.ExtendedByDataModelId == data_model_id,
                    EntityAssociation.ExtendedByDataModelId.is_(None),
                ),
            )
        )
    else:
        query = (
            select(
                EntityAssociation.ParentEntityId,
                EntityAssociation.ChildEntityId,
                EntityAssociation.Relationship,
                EntityAssociation.Placement,
            )
            .join(Entity, Entity.Id == EntityAssociation.ParentEntityId)
            .where(
                Entity.DataModelId == data_model_id,
                EntityAssociation.Placement == "Reference",
                EntityAssociation.Deleted == False,
                EntityAssociation.ExtendedByDataModelId.is_(None),
            )
        )

    result = await session.execute(query)
    inter_entity_associations = result.fetchall()
    column_names = inter_entity_associations[0]._fields if inter_entity_associations else []
    # Convert the result into a pandas DataFrame
    df_inter_entity_links = pd.DataFrame(inter_entity_associations, columns=column_names)
    logger.info(f" df_inter_entity_links : {df_inter_entity_links}")
    refs = 0
    for index, row in df_inter_entity_links.iterrows():
        logger.info(" ------------------------------------------------- ")
        parent_id = row["ParentEntityId"]
        child_id = row["ChildEntityId"]
        relationship = row["Relationship"]
        placement = None
        if "Placement" in row:
            placement = row["Placement"]

        parent_entity_name = (df_entity[df_entity["Id"] == parent_id])["Name"].unique().tolist()[0]
        child_entity_name = (df_entity[df_entity["Id"] == child_id])["Name"].unique().tolist()[0]
        logger.info(f"parent_id : {parent_id}")
        logger.info(f"child_id : {child_id}")
        logger.info(f" parent_entity_name : {parent_entity_name}")
        logger.info(f" child_entity_name : {child_entity_name}")
        logger.info(f" relationship : {relationship}")
        logger.info(f" placement : {placement}")

        parent_ancestors = await find_ancestors(session, parent_id, data_model.Type, data_model_id, included_entity_ids)
        child_ancestors = await find_ancestors(session, child_id, data_model.Type, data_model_id, included_entity_ids)
        logger.info(f" parent_ancestors : {parent_ancestors}")
        logger.info(f" child_ancestors : {child_ancestors}")

        if relationship is None or relationship != None and relationship.startswith(("has", "relevant")):
            key = "Ref" + child_entity_name
        else:
            key = relationship + "Ref" + child_entity_name
        # logger.info(f"Key : {key}")

        if parent_id in child_ancestors:
            # Child is direct child or grandchild of parent. - no need to do anything.
            logger.info("Parent already has child.")
            continue

        await add_ref(
            parent_ancestors=parent_ancestors,
            child_ancestors=child_ancestors,
            df_entity=df_entity,
            parent_entity_name=parent_entity_name,
            child_entity_name=child_entity_name,
            openapi_spec=openapi_spec,
            key=key,
        )

    if "Common" in openapi_spec["components"]["schemas"]:
        del openapi_spec["components"]["schemas"]["Common"]

    return openapi_spec

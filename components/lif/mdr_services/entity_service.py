from typing import List

from fastapi import HTTPException
from lif.datatypes.mdr_sql_model import (
    Attribute,
    DataModelType,
    Entity,
    EntityAssociation,
    EntityAttributeAssociation,
    ExtInclusionsFromBaseDM,
)
from lif.mdr_dto.entity_dto import ChildEntityDTO, CreateEntityDTO, EntityDTO, UpdateEntityDTO
from lif.mdr_services.attribute_service import soft_delete_attribute
from lif.mdr_services.helper_service import check_datamodel_by_id
from lif.mdr_utils.logger_config import get_logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import func, or_, select

logger = get_logger(__name__)


async def get_all_entities(session: AsyncSession):
    result = await session.execute(select(Entity))
    return result.scalars().all()


async def get_paginated_entities(session: AsyncSession, offset: int = 0, limit: int = 10, pagination: bool = True):
    # Query to count total records
    total_query = select(func.count(Entity.Id)).where(Entity.Deleted == False)
    total_result = await session.execute(total_query)
    total_count = total_result.scalar()
    # Query to fetch paginated results
    if pagination:
        query = select(Entity).where(Entity.Deleted == False).offset(offset).limit(limit)
    else:
        query = select(Entity).where(Entity.Deleted == False)
    result = await session.execute(query)
    entities = result.scalars().all()
    # Convert the list of Attribute objects to AttributeDTO objects
    entities_dtos = [EntityDTO.from_orm(entity) for entity in entities]
    return total_count, entities_dtos


async def get_entity_by_id(session: AsyncSession, id: int):
    entity = await session.get(Entity, id)
    if not entity:
        raise HTTPException(status_code=404, detail=f"Entity with id {id}  not found")
    if entity.Deleted:
        raise HTTPException(status_code=404, detail=f"Entity with ID {id} is deleted")
    # return EntityDTO.from_orm(entity)
    return entity


async def get_entity_by_attribute_id(session: AsyncSession, attribute_id: int):
    association_query = select(EntityAttributeAssociation).where(
        EntityAttributeAssociation.AttributeId == attribute_id, EntityAttributeAssociation.Deleted == False
    )
    result = await session.execute(association_query)
    association = result.scalars().first()
    entity = await get_entity_by_id(session=session, id=association.EntityId)
    return EntityDTO.from_orm(entity)


async def create_entity(session: AsyncSession, data: CreateEntityDTO):
    # Checking if data model  exists or not
    data_model = await check_datamodel_by_id(session=session, id=data.DataModelId)

    # Check if entity with the same unique name exists in the given data model
    if await check_entity_exists(session, data.UniqueName, data.DataModelId):
        raise HTTPException(
            status_code=400,
            detail=f"Entity with unique name '{data.UniqueName}' already exists in the specified DataModel",
        )

    if data_model.BaseDataModelId and not data.Extension:
        data.Extension = True
    if not data_model.BaseDataModelId and data.Extension:
        logger.info("Data model is not extension so provided entity can not be an extension.")
        data.Extension = False

    entity = Entity(**data.dict())
    session.add(entity)
    await session.commit()
    await session.refresh(entity)
    return EntityDTO.from_orm(entity)


async def update_entity(session: AsyncSession, id: int, data: UpdateEntityDTO):
    # Checking if data model  exists or not
    if data.DataModelId:
        await check_datamodel_by_id(session=session, id=data.DataModelId)

    entity = await get_entity_by_id(session=session, id=id)

    if data.UniqueName or data.DataModelId:
        updated_unique_name = data.UniqueName if data.UniqueName else entity.UniqueName
        updated_data_model_id = data.DataModelId if data.DataModelId else entity.DataModelId
        existing_entity = await check_entity_exists(session, updated_unique_name, updated_data_model_id)
        logger.info(f"existing_entity : {existing_entity}")
        if existing_entity and existing_entity.Id != id:
            raise HTTPException(
                status_code=400,
                detail=f"Entity with UniqueName {updated_unique_name} already exists for DataModel {updated_data_model_id}.",
            )

    for key, value in data.dict(exclude_unset=True).items():
        setattr(entity, key, value)
    logger.info(f"Updated entity : {entity}")
    session.add(entity)
    await session.commit()
    await session.refresh(entity)
    return EntityDTO.from_orm(entity)


async def delete_entity(session: AsyncSession, id: int):
    # Fetch the entity by ID
    entity = await get_entity_by_id(session=session, id=id)

    try:
        # Step 1: Find all EntityAttributeAssociations for the entity and store the attribute IDs
        association_query = select(EntityAttributeAssociation).where(EntityAttributeAssociation.EntityId == id)
        result = await session.execute(association_query)
        entity_attribute_associations = result.scalars().all()

        # Extract attribute IDs from EntityAttributeAssociation
        attribute_ids = [assoc.AttributeId for assoc in entity_attribute_associations]

        # Step 2: Delete all EntityAttributeAssociation records for the entity
        for assoc in entity_attribute_associations:
            await session.delete(assoc)

        # Step 3: Delete all attributes using the stored attribute IDs
        if attribute_ids:
            attribute_query = select(Attribute).where(Attribute.Id.in_(attribute_ids))
            result = await session.execute(attribute_query)
            attributes = result.scalars().all()

            for attribute in attributes:
                await session.delete(attribute)

        # Step 4: Delete EntityAssociations where the entity is a parent or child
        entity_assoc_query = select(EntityAssociation).where(
            (EntityAssociation.ParentEntityId == id) | (EntityAssociation.ChildEntityId == id)
        )
        entity_assoc_result = await session.execute(entity_assoc_query)
        entity_associations = entity_assoc_result.scalars().all()

        for entity_assoc in entity_associations:
            await session.delete(entity_assoc)

        # TODO: remove all the transformations

        # Step 5: Delete the entity itself
        await session.delete(entity)
        await session.commit()

    except Exception as e:
        await session.rollback()  # Rollback in case of an error
        raise HTTPException(status_code=500, detail=f"Error deleting entity and related data: {str(e)}")

    return {"ok": True}


async def soft_delete_entity(session: AsyncSession, id: int):
    # Fetch the entity by ID
    entity = await get_entity_by_id(session=session, id=id)

    try:
        # Step 1: Find all EntityAttributeAssociations for the entity and store the attribute IDs
        association_query = select(EntityAttributeAssociation).where(
            EntityAttributeAssociation.EntityId == id, EntityAttributeAssociation.Deleted == False
        )
        result = await session.execute(association_query)
        entity_attribute_associations = result.scalars().all()

        # Extract attribute IDs from EntityAttributeAssociation
        attribute_ids = [assoc.AttributeId for assoc in entity_attribute_associations]
        logger.info(f"attribute_ids: {attribute_ids}")

        # Step 2: Delete all EntityAttributeAssociation records for the entity
        for assoc in entity_attribute_associations:
            assoc.Deleted = True
            session.add(assoc)

        # Step 3: Delete all attributes using the stored attribute IDs
        if attribute_ids:
            for attribute_id in attribute_ids:
                await soft_delete_attribute(session=session, id=attribute_id)

        # Step 4: Delete EntityAssociations where the entity is a parent or child
        entity_assoc_query = (
            select(EntityAssociation)
            .where((EntityAssociation.ParentEntityId == id) | (EntityAssociation.ChildEntityId == id))
            .where(EntityAssociation.Deleted == False)
        )
        entity_assoc_result = await session.execute(entity_assoc_query)
        entity_associations = entity_assoc_result.scalars().all()

        for entity_assoc in entity_associations:
            entity_assoc.Deleted = True
            session.add(entity_assoc)

        # Step 5: Delete Entity from Inclusions
        entity_inclusions_query = select(ExtInclusionsFromBaseDM).where(
            ExtInclusionsFromBaseDM.IncludedElementId == id, ExtInclusionsFromBaseDM.Deleted == False
        )
        entity_inclusions_result = await session.execute(entity_inclusions_query)
        entity_inclusions = entity_inclusions_result.scalars().all()

        for entity_inclusion in entity_inclusions:
            entity_inclusion.Deleted = True
            session.add(entity_inclusion)

        # Step 6: Delete the entity itself
        entity.Deleted = True
        session.add(entity)

        await session.commit()

    except Exception as e:
        await session.rollback()  # Rollback in case of an error
        raise HTTPException(status_code=500, detail=f"Error deleting entity and related data: {str(e)}")

    return {"ok": True}


async def check_entity_exists(session: AsyncSession, unique_name: str, data_model_id: int):
    # Query to check if an entity with the same name exists in the given data model
    logger.info(f"unique_name : {unique_name}")
    logger.info(f"data_model_id : {data_model_id}")
    query = select(Entity).where(
        Entity.UniqueName == unique_name, Entity.DataModelId == data_model_id, Entity.Deleted == False
    )
    result = await session.execute(query)
    existing_entity = result.scalars().first()
    return existing_entity
    # if existing_entity:
    #     return True  # Entity with the same name exists

    # return False  # No entity with the same name exists


# async def get_list_of_attribute(session: AsyncSession, id: int):
#     entity = await get_entity_by_id(session,id)
#     attribute_list = await get_list_of_attributes_for_entity(session=session, entity_id=id)
#     entity_attributes = EntityAttributeDTO(
#             Entity=entity,  # Use entity_id from DTO
#             Attributes=attribute_list
#         )
#     return entity_attributes


async def get_entities_by_ids(session: AsyncSession, ids: List[int]) -> List[EntityDTO]:
    # Query to get the entities for the provided list of IDs
    query = select(Entity).where(Entity.Id.in_(ids), Entity.Deleted == False)
    result = await session.execute(query)
    entities = result.scalars().all()

    # Convert the list of Entity objects to EntityDTO objects
    entity_dtos = [EntityDTO.from_orm(entity) for entity in entities]

    return entity_dtos


async def get_list_of_entities_for_data_model(
    session: AsyncSession,
    data_model_id: int,
    offset: int = 0,
    limit: int = 10,
    pagination: bool = True,
    partner_only: bool = False,
    org_ext_only: bool = False,
    this_organization: str = "LIF",
    public_only: bool = False,
):
    # Check for data model id and for extension
    data_model_id_list: List[int] = []
    data_model = await check_datamodel_by_id(session=session, id=data_model_id)
    data_model_id_list.append(data_model.Id)
    if data_model.Type == DataModelType.OrgLIF or data_model.Type == DataModelType.PartnerLIF:
        base_data_model = await check_datamodel_by_id(session=session, id=data_model.BaseDataModelId)
        data_model_id_list.append(base_data_model.Id)

    # Step 1: If this org's LIF or a partner's LIF, filter to only entities included for this org's data model
    if data_model.Type == DataModelType.OrgLIF or data_model.Type == DataModelType.PartnerLIF:
        # Query to fetch IncludedElementId from ExtInclusionsFromBaseDM table where ExtDataModelId in data_model_id_list and ElementType = Entity
        ext_inclusions_query = select(ExtInclusionsFromBaseDM.IncludedElementId).where(
            ExtInclusionsFromBaseDM.ExtDataModelId.in_(data_model_id_list),
            ExtInclusionsFromBaseDM.ElementType == "Entity",
            ExtInclusionsFromBaseDM.Deleted == False,
        )
        if org_ext_only:
            ext_inclusions_query = ext_inclusions_query.where(
                ExtInclusionsFromBaseDM.ContributorOrganization == this_organization
            )
        if partner_only:
            # ext_inclusions_query where ContributorOrganization doesn't equal this_organization or "LIF"
            ext_inclusions_query = ext_inclusions_query.where(
                (ExtInclusionsFromBaseDM.ContributorOrganization != "LIF")
                & (ExtInclusionsFromBaseDM.ContributorOrganization != this_organization)
            )
        if public_only:
            ext_inclusions_query = ext_inclusions_query.where(ExtInclusionsFromBaseDM.LevelOfAccess == "Public")
        # Step 2: Count total entities for pagination
        result = await session.execute(ext_inclusions_query)
        included_element_ids = result.scalars().all()
        total_count = len(included_element_ids)

        # Step 3: Fetch paginated entities
        if pagination:
            query = (
                select(Entity)
                .where((Entity.Id.in_(included_element_ids)), Entity.Deleted == False)
                .order_by(Entity.Id)
                .offset(offset)
                .limit(limit)
            )
        else:
            query = (
                select(Entity).where((Entity.Id.in_(included_element_ids)), Entity.Deleted == False).order_by(Entity.Id)
            )

        result = await session.execute(query)
        entities = result.scalars().all()

    else:  # For Base LIF or Source Schema
        # Query to count total entities for the given data model
        total_query = select(func.count(Entity.Id)).where(
            Entity.DataModelId.in_(data_model_id_list), Entity.Deleted == False
        )
        total_result = await session.execute(total_query)
        total_count = total_result.scalar()

        # Query to fetch paginated entities for the given data model, ordered by Id
        if pagination:
            query = (
                select(Entity)
                .where(Entity.DataModelId.in_(data_model_id_list), Entity.Deleted == False)
                .order_by(Entity.Id)
                .offset(offset)
                .limit(limit)
            )
        else:
            query = (
                select(Entity)
                .where(Entity.DataModelId.in_(data_model_id_list), Entity.Deleted == False)
                .order_by(Entity.Id)
            )
        result = await session.execute(query)
        entities = result.scalars().all()

    # Convert to EntityDTO list
    entity_dtos = [EntityDTO.from_orm(entity) for entity in entities]

    return total_count, entity_dtos


async def get_entity_by_name(session: AsyncSession, entity_name: str, data_model_id: int):
    query = select(Entity).where(Entity.DataModelId == data_model_id, Entity.Name == entity_name)
    result = await session.execute(query)
    entity = result.scalars().first()
    if not entity:
        raise HTTPException(status_code=404, detail=f"Entity with id {id}  not found")
    if entity.Deleted:
        raise HTTPException(status_code=404, detail=f"Entity with ID {id} is deleted")
    return EntityDTO.from_orm(entity)


# async def check_datamodel_by_id(session: AsyncSession, id: int):
#     datamodel = await session.get(DataModel, id)
#     if not datamodel:
#         raise HTTPException(status_code=404, detail="DataModel not found")
#     if datamodel.Deleted:
#         raise HTTPException(status_code=404, detail=f"Data Model with ID {id} is deleted")
#     return datamodel


async def get_entity_parents(session: AsyncSession, entity_id: int):
    # Query to count total records
    total_query = (
        select(EntityAssociation.ParentEntityId)
        .distinct()
        .where(EntityAssociation.Deleted == False, EntityAssociation.ChildEntityId == entity_id)
        .order_by(EntityAssociation.ParentEntityId)
    )
    result = await session.execute(total_query)
    entity_associations = result.scalars().all()
    total_count = len(entity_associations)
    parent_entities: List[EntityDTO] = []
    for parent_id in entity_associations:
        parent_entity = await get_entity_by_id(session=session, id=parent_id)
        parent_entities.append(EntityDTO.from_orm(parent_entity))
    return parent_entities


async def get_filtered_entity_parents(
    session: AsyncSession,
    entity_id: int,
    data_model_id: int,
    data_model_type: str,
    partner_only: bool = False,
    org_ext_only: bool = False,
    public_only: bool = False,
    this_organization: str = "LIF",
):
    # if more than one of partner_only, org_ext_only, or public_only is true, throw exception
    if (partner_only and org_ext_only) or (partner_only and public_only) or (org_ext_only and public_only):
        raise HTTPException(status_code=400, detail="Using more than one filter at once is not supported at this time.")

    # Query to count total records
    if data_model_type == DataModelType.OrgLIF or data_model_type == DataModelType.PartnerLIF:
        total_query = (
            select(EntityAssociation.ParentEntityId)
            .distinct()
            .where(
                EntityAssociation.Deleted == False,
                EntityAssociation.ChildEntityId == entity_id,
                or_(
                    EntityAssociation.ExtendedByDataModelId == data_model_id,
                    EntityAssociation.ExtendedByDataModelId.is_(None),
                ),
            )
            .order_by(EntityAssociation.ParentEntityId)
        )
    else:
        total_query = (
            select(EntityAssociation.ParentEntityId)
            .distinct()
            .where(
                EntityAssociation.Deleted == False,
                EntityAssociation.ChildEntityId == entity_id,
                EntityAssociation.ExtendedByDataModelId.is_(None),
            )
            .order_by(EntityAssociation.ParentEntityId)
        )
    # We need to select only the items from the above query which match the filtering criteria
    if (data_model_type == DataModelType.OrgLIF or data_model_type == DataModelType.PartnerLIF) and partner_only:
        total_query = total_query.join(
            ExtInclusionsFromBaseDM, EntityAssociation.ParentEntityId == ExtInclusionsFromBaseDM.IncludedElementId
        ).where(
            ExtInclusionsFromBaseDM.ElementType == "Entity",
            ExtInclusionsFromBaseDM.ExtDataModelId == data_model_id,
            ExtInclusionsFromBaseDM.ContributorOrganization != "LIF",
            ExtInclusionsFromBaseDM.ContributorOrganization != this_organization,
            ExtInclusionsFromBaseDM.Deleted == False,
        )
    elif (data_model_type == DataModelType.OrgLIF or data_model_type == DataModelType.PartnerLIF) and org_ext_only:
        total_query = total_query.join(
            ExtInclusionsFromBaseDM, EntityAssociation.ParentEntityId == ExtInclusionsFromBaseDM.IncludedElementId
        ).where(
            ExtInclusionsFromBaseDM.ElementType == "Entity",
            ExtInclusionsFromBaseDM.ExtDataModelId == data_model_id,
            ExtInclusionsFromBaseDM.ContributorOrganization == this_organization,
            ExtInclusionsFromBaseDM.Deleted == False,
        )
    elif (data_model_type == DataModelType.OrgLIF or data_model_type == DataModelType.PartnerLIF) and public_only:
        total_query = total_query.join(
            ExtInclusionsFromBaseDM, EntityAssociation.ParentEntityId == ExtInclusionsFromBaseDM.IncludedElementId
        ).where(
            ExtInclusionsFromBaseDM.ElementType == "Entity",
            ExtInclusionsFromBaseDM.ExtDataModelId == data_model_id,
            ExtInclusionsFromBaseDM.LevelOfAccess == "Public",
            ExtInclusionsFromBaseDM.Deleted == False,
        )
    elif data_model_type == DataModelType.OrgLIF or data_model_type == DataModelType.PartnerLIF:
        total_query = total_query.join(
            ExtInclusionsFromBaseDM, EntityAssociation.ParentEntityId == ExtInclusionsFromBaseDM.IncludedElementId
        ).where(
            ExtInclusionsFromBaseDM.ElementType == "Entity",
            ExtInclusionsFromBaseDM.ExtDataModelId == data_model_id,
            ExtInclusionsFromBaseDM.Deleted == False,
        )

    result = await session.execute(total_query)
    entity_associations = result.scalars().all()
    total_count = len(entity_associations)
    parent_entities: List[EntityDTO] = []
    for parent_id in entity_associations:
        parent_entity = await get_entity_by_id(session=session, id=parent_id)
        parent_entities.append(EntityDTO.from_orm(parent_entity))
    return parent_entities


async def get_entity_children(session: AsyncSession, entity_id: int):
    # Query to count total records
    total_query = (
        select(EntityAssociation.ChildEntityId)
        .distinct()
        .where(EntityAssociation.Deleted == False, EntityAssociation.ParentEntityId == entity_id)
        .order_by(EntityAssociation.ChildEntityId)
    )
    result = await session.execute(total_query)
    entity_associations = result.scalars().all()
    total_count = len(entity_associations)
    child_entities: List[EntityDTO] = []
    for child_id in entity_associations:
        child_entity = await get_entity_by_id(session=session, id=child_id)
        child_entities.append(EntityDTO.from_orm(child_entity))
    return child_entities


async def get_filtered_entity_children(
    session: AsyncSession,
    entity_id: int,
    data_model_id: int,
    data_model_type: str,
    partner_only: bool = False,
    org_ext_only: bool = False,
    public_only: bool = False,
    this_organization: str = "LIF",
):
    # if more than one of partner_only, org_ext_only, or public_only is true, throw exception
    if (partner_only and org_ext_only) or (partner_only and public_only) or (org_ext_only and public_only):
        raise HTTPException(status_code=400, detail="Using more than one filter at once is not supported at this time.")

    # Query to count total records
    if data_model_type == DataModelType.OrgLIF or data_model_type == DataModelType.PartnerLIF:
        total_query = (
            select(EntityAssociation)
            .distinct()
            .where(
                EntityAssociation.Deleted == False,
                EntityAssociation.ParentEntityId == entity_id,
                or_(
                    EntityAssociation.ExtendedByDataModelId == data_model_id,
                    EntityAssociation.ExtendedByDataModelId.is_(None),
                ),
            )
            .order_by(EntityAssociation.ChildEntityId)
        )
    else:
        total_query = (
            select(EntityAssociation)
            .distinct()
            .where(
                EntityAssociation.Deleted == False,
                EntityAssociation.ParentEntityId == entity_id,
                EntityAssociation.ExtendedByDataModelId.is_(None),
            )
            .order_by(EntityAssociation.ChildEntityId)
        )
    # We need to select only the items from the above query which match the filtering criteria
    if (data_model_type == DataModelType.OrgLIF or data_model_type == DataModelType.PartnerLIF) and partner_only:
        total_query = total_query.join(
            ExtInclusionsFromBaseDM, EntityAssociation.ChildEntityId == ExtInclusionsFromBaseDM.IncludedElementId
        ).where(
            ExtInclusionsFromBaseDM.ElementType == "Entity",
            ExtInclusionsFromBaseDM.ExtDataModelId == data_model_id,
            ExtInclusionsFromBaseDM.ContributorOrganization != "LIF",
            ExtInclusionsFromBaseDM.ContributorOrganization != this_organization,
            ExtInclusionsFromBaseDM.Deleted == False,
        )
    elif (data_model_type == DataModelType.OrgLIF or data_model_type == DataModelType.PartnerLIF) and org_ext_only:
        total_query = total_query.join(
            ExtInclusionsFromBaseDM, EntityAssociation.ChildEntityId == ExtInclusionsFromBaseDM.IncludedElementId
        ).where(
            ExtInclusionsFromBaseDM.ElementType == "Entity",
            ExtInclusionsFromBaseDM.ExtDataModelId == data_model_id,
            ExtInclusionsFromBaseDM.ContributorOrganization == this_organization,
            ExtInclusionsFromBaseDM.Deleted == False,
        )
    elif (data_model_type == DataModelType.OrgLIF or data_model_type == DataModelType.PartnerLIF) and public_only:
        total_query = total_query.join(
            ExtInclusionsFromBaseDM, EntityAssociation.ChildEntityId == ExtInclusionsFromBaseDM.IncludedElementId
        ).where(
            ExtInclusionsFromBaseDM.ElementType == "Entity",
            ExtInclusionsFromBaseDM.ExtDataModelId == data_model_id,
            ExtInclusionsFromBaseDM.LevelOfAccess == "Public",
            ExtInclusionsFromBaseDM.Deleted == False,
        )
    elif data_model_type == DataModelType.OrgLIF or data_model_type == DataModelType.PartnerLIF:
        total_query = total_query.join(
            ExtInclusionsFromBaseDM, EntityAssociation.ChildEntityId == ExtInclusionsFromBaseDM.IncludedElementId
        ).where(
            ExtInclusionsFromBaseDM.ElementType == "Entity",
            ExtInclusionsFromBaseDM.ExtDataModelId == data_model_id,
            ExtInclusionsFromBaseDM.Deleted == False,
        )

    result = await session.execute(total_query)
    entity_associations = result.scalars().all()
    print(f"entity_associations: {entity_associations}")
    total_count = len(entity_associations)
    child_entities: List[ChildEntityDTO] = []
    for association in entity_associations:
        child_entity = await get_entity_by_id(session=session, id=association.ChildEntityId)
        dto = ChildEntityDTO.model_validate(child_entity, from_attributes=True).model_copy(
            update={
                "ParentEntityId": entity_id,
                "Relationship": association.Relationship,
                "Placement": association.Placement,
            }
        )
        child_entities.append(dto)
    return child_entities


async def get_unique_entity(
    session: AsyncSession, unique_name: str, data_model_id: int, base_data_model_id: int, data_model_type: str
):
    base_conditions = [Entity.UniqueName == unique_name, Entity.Deleted == False]

    if data_model_type == DataModelType.OrgLIF or data_model_type == DataModelType.PartnerLIF:
        base_conditions.append(or_(Entity.DataModelId == base_data_model_id, Entity.DataModelId == data_model_id))
    else:
        base_conditions.append(Entity.DataModelId == data_model_id)
    query = select(Entity).where(*base_conditions)
    result = await session.execute(query)
    entity = result.scalars().first()
    return entity

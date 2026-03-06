from typing import List, Optional, Sequence

from fastapi import HTTPException
from lif.datatypes.mdr_sql_model import DataModel, DataModelType, Entity, EntityAssociation, ExtInclusionsFromBaseDM
from lif.mdr_dto.entity_association_dto import (
    CreateEntityAssociationDTO,
    EntityAssociationDTO,
    UpdateEntityAssociationDTO,
)
from lif.mdr_services.entity_service import get_entity_by_id
from lif.mdr_services.helper_service import check_datamodel_by_id, check_entity_by_id
from lif.mdr_utils.logger_config import get_logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from sqlmodel import or_, select

logger = get_logger(__name__)


async def resolve_entity_id(
    session: AsyncSession, entity_name: str, data_model_name: str, data_model_version: Optional[str] = None
) -> int:
    # Get DataModelId based on the name and optional version without importing datamodel_service
    query = select(DataModel.Id).where(DataModel.Name == data_model_name, DataModel.Deleted == False)
    if data_model_version:
        query = query.where(DataModel.DataModelVersion == data_model_version)
    dm_result = await session.execute(query)
    data_model_id = dm_result.scalar_one_or_none()
    if not data_model_id:
        raise HTTPException(status_code=404, detail=f"Data model '{data_model_name}' not found")

    # Get EntityId based on the name and DataModelId
    entity_query = select(Entity.Id).where(
        Entity.Name == entity_name, Entity.DataModelId == data_model_id, Entity.Deleted == False
    )
    entity_result = await session.execute(entity_query)
    entity_id = entity_result.scalar_one_or_none()

    if not entity_id:
        raise HTTPException(
            status_code=404, detail=f"Entity '{entity_name}' not found in data model '{data_model_name}'"
        )

    return entity_id


async def check_existing_association(
    session: AsyncSession, parent_entity_id: int, child_entity_id: int, extended_by_data_model_id: int
) -> bool:
    query = select(EntityAssociation).where(
        EntityAssociation.ParentEntityId == parent_entity_id,
        EntityAssociation.ChildEntityId == child_entity_id,
        EntityAssociation.Deleted == False,
        or_(
            EntityAssociation.ExtendedByDataModelId == None,
            EntityAssociation.ExtendedByDataModelId == extended_by_data_model_id,
        ),
    )
    result = await session.execute(query)
    return result.scalar_one_or_none() is not None


async def retrieve_all_entity_associations(
    session: AsyncSession, parent_entity_id: int, child_entity_id: int, extended_by_data_model_id: int
) -> Sequence[EntityAssociation]:
    query = select(EntityAssociation).where(
        EntityAssociation.ParentEntityId == parent_entity_id,
        EntityAssociation.ChildEntityId == child_entity_id,
        EntityAssociation.Deleted == False,
        or_(
            EntityAssociation.ExtendedByDataModelId == None,
            EntityAssociation.ExtendedByDataModelId == extended_by_data_model_id,
        ),
    )
    result = await session.execute(query)
    associations = result.scalars().all()
    if not associations or len(associations) == 0:
        raise HTTPException(
            status_code=404,
            detail=f"Child {child_entity_id} association with parent {parent_entity_id} not found in data model association",
        )
    return associations


async def create_entity_association(session: AsyncSession, data: CreateEntityAssociationDTO):
    # Resolve parent and child entity IDs

    parent_entity = await get_entity_by_id(session=session, id=data.ParentEntityId)
    child_entity = await get_entity_by_id(session=session, id=data.ChildEntityId)

    if parent_entity.Extension or child_entity.Extension:
        data.Extension = True
    else:
        data.Extension = False

    # Check if the association already exists
    if await check_existing_association(session, data.ParentEntityId, data.ChildEntityId, data.ExtendedByDataModelId):
        raise HTTPException(
            status_code=400,
            detail=f"Association already exists between the parent ({data.ParentEntityId}) and child ({data.ChildEntityId}) entities with ExtendedByDataModelId {data.ExtendedByDataModelId} or Base LIF",
        )

    # Create the new EntityAssociation
    entity_association = EntityAssociation(
        ParentEntityId=data.ParentEntityId,
        ChildEntityId=data.ChildEntityId,
        Relationship=data.Relationship,
        Placement=data.Placement,
        Notes=data.Notes,
        CreationDate=data.CreationDate,
        ActivationDate=data.ActivationDate,
        DeprecationDate=data.DeprecationDate,
        Contributor=data.Contributor,
        ContributorOrganization=data.ContributorOrganization,
        Extension=data.Extension,
        ExtendedByDataModelId=data.ExtendedByDataModelId,
    )
    session.add(entity_association)
    await session.commit()
    await session.refresh(entity_association)

    return EntityAssociationDTO.from_orm(entity_association)


async def get_entity_association_by_id(session: AsyncSession, association_id: int):
    association = await session.get(EntityAssociation, association_id)
    if not association:
        raise HTTPException(status_code=404, detail=f"EntityAssociation with ID {association_id} not found")
    if association.Deleted:
        raise HTTPException(status_code=404, detail=f"EntityAssociation with ID {association_id} is deleted")
    # association_dto =   EntityAssociationDTO.from_orm(association)
    return association


async def get_entity_association_by_parent_child_relationship(
    session, parent_entity_id, child_entity_id, relationship, extended_by_data_model_id
):
    query = select(EntityAssociation).where(
        EntityAssociation.ParentEntityId == parent_entity_id,
        EntityAssociation.ChildEntityId == child_entity_id,
        EntityAssociation.Relationship == relationship,
        or_(
            EntityAssociation.ExtendedByDataModelId == None,
            EntityAssociation.ExtendedByDataModelId == extended_by_data_model_id,
        ),
        EntityAssociation.Deleted == False,
    )
    result = await session.execute(query)
    return result.scalars().first()


async def update_entity_association(session: AsyncSession, association_id: int, dto: UpdateEntityAssociationDTO):
    # Get existing association
    entity_association = await get_entity_association_by_id(session, association_id)

    if dto.ParentEntityId:
        await check_entity_by_id(session, dto.ParentEntityId)
    if dto.ChildEntityId:
        await check_entity_by_id(session, dto.ChildEntityId)

    # Check if the association already exists with the new parent and child IDs
    if dto.ParentEntityId or dto.ChildEntityId:
        updated_parent_entity_id = dto.ParentEntityId if dto.ParentEntityId else entity_association.ParentEntityId
        updated_child_entity_id = dto.ChildEntityId if dto.ChildEntityId else entity_association.ChildEntityId
        updated_relationship = dto.Relationship if dto.Relationship else entity_association.Relationship
        updated_extended_by_data_model_id = (
            dto.ExtendedByDataModelId if dto.ExtendedByDataModelId else entity_association.ExtendedByDataModelId
        )
        existing_association = await get_entity_association_by_parent_child_relationship(
            session,
            updated_parent_entity_id,
            updated_child_entity_id,
            updated_relationship,
            updated_extended_by_data_model_id,
        )
        if existing_association and existing_association.Id != association_id:
            raise HTTPException(
                status_code=400,
                detail="EntityAssociation with the same ParentEntityId, ChildEntityId and Relationship already exists for base LIF or given data model.",
            )

    for key, value in dto.dict(exclude_unset=True).items():
        setattr(entity_association, key, value)

    session.add(entity_association)
    await session.commit()
    await session.refresh(entity_association)
    return EntityAssociationDTO.from_orm(entity_association)
    # return {"message": "Entity association updated successfully"}


async def delete_entity_association(session: AsyncSession, association_id: int) -> dict:
    entity_association = await get_entity_association_by_id(session, association_id)
    await session.delete(entity_association)
    await session.commit()
    return {"message": f"Entity association with ID {association_id} deleted successfully"}


async def soft_delete_entity_association(session: AsyncSession, association_id: int) -> dict:
    entity_association = await get_entity_association_by_id(session, association_id)
    entity_association.Deleted = True
    session.add(entity_association)
    await session.commit()
    return {"message": f"Entity association with ID {association_id} deleted successfully"}


async def get_entity_associations_by_data_model_id(session: AsyncSession, data_model_id: int):
    # Check for data model id and for extension
    data_model = await check_datamodel_by_id(session=session, id=data_model_id)

    entity_associations = []
    if data_model.Type == DataModelType.OrgLIF or data_model.Type == DataModelType.PartnerLIF:
        included_entities_query = select(ExtInclusionsFromBaseDM.IncludedElementId).where(
            ExtInclusionsFromBaseDM.ExtDataModelId == data_model_id,
            ExtInclusionsFromBaseDM.ElementType == "Entity",
            ExtInclusionsFromBaseDM.Deleted.is_(False),
        )
        included_entity_ids_result = await session.execute(included_entities_query)
        included_entity_ids = included_entity_ids_result.scalars().all()
        # select EntityAssociation where both ParentEntityId and ChildEntityId are in included_entity_ids
        query = select(EntityAssociation).where(
            EntityAssociation.ParentEntityId.in_(included_entity_ids),
            EntityAssociation.ChildEntityId.in_(included_entity_ids),
            EntityAssociation.Deleted.is_(False),
            or_(
                EntityAssociation.ExtendedByDataModelId == data_model_id,
                EntityAssociation.ExtendedByDataModelId.is_(None),
            ),
        )
        result = await session.execute(query)
        entity_associations = result.scalars().all()
    else:
        # Use aliased entities to avoid conflicts
        ParentEntity = aliased(Entity)
        ChildEntity = aliased(Entity)

        # Query for associations where the parent entity belongs to the given data model
        parent_query = (
            select(EntityAssociation)
            .join(ParentEntity, ParentEntity.Id == EntityAssociation.ParentEntityId)
            .where(
                ParentEntity.DataModelId == data_model_id,
                EntityAssociation.Deleted == False,
                EntityAssociation.ExtendedByDataModelId == None,
            )
        )

        # Query for associations where the child entity belongs to the given data model
        child_query = (
            select(EntityAssociation)
            .join(ChildEntity, ChildEntity.Id == EntityAssociation.ChildEntityId)
            .where(
                ChildEntity.DataModelId == data_model_id,
                EntityAssociation.Deleted == False,
                EntityAssociation.ExtendedByDataModelId == None,
            )
        )

        # Combine the two queries using a union
        query = parent_query.union(child_query)

        result = await session.execute(query)
        entity_associations = result.fetchall()

    # logger.info(f"entity_associations: {entity_associations}")
    # Fetch parent and child entity names and create DTOs
    association_dtos: List[EntityAssociationDTO] = []
    for association in entity_associations:
        # Create DTO using from_orm and add extra fields
        association_dto = EntityAssociationDTO.from_orm(association)
        association_dtos.append(association_dto)

    return association_dtos


async def get_entity_associations_by_parent_entity_id(
    session: AsyncSession, parent_entity_id: int, including_extended_by_data_model_id: int = None
) -> List[EntityAssociationDTO]:
    # Check if parent entity exists
    parent_entity = await check_entity_by_id(session=session, id=parent_entity_id)
    if not parent_entity:
        raise HTTPException(status_code=404, detail=f"Parent entity with ID {parent_entity_id} not found")

    if including_extended_by_data_model_id:
        query = select(EntityAssociation).where(
            EntityAssociation.ParentEntityId == parent_entity_id,
            EntityAssociation.Deleted.is_(False),
            or_(
                EntityAssociation.ExtendedByDataModelId == including_extended_by_data_model_id,
                EntityAssociation.ExtendedByDataModelId.is_(None),
            ),
        )
    else:
        query = select(EntityAssociation).where(
            EntityAssociation.ParentEntityId == parent_entity_id,
            EntityAssociation.Deleted.is_(False),
            EntityAssociation.ExtendedByDataModelId.is_(None),
        )
    result = await session.execute(query)
    entity_associations = result.scalars().all()

    # Fetch parent and child entity names and create DTOs
    association_dtos = []
    for association in entity_associations:
        # Create DTO using from_orm and add extra fields
        association_dto = EntityAssociationDTO.from_orm(association)
        association_dtos.append(association_dto)

    return association_dtos

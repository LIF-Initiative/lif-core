from typing import List, Optional, Sequence, Tuple

from fastapi import HTTPException
from lif.datatypes.mdr_sql_model import (
    Attribute,
    DataModelType,
    Entity,
    EntityAttributeAssociation,
    ExtInclusionsFromBaseDM,
)
from lif.mdr_dto.entity_attribute_association_dto import (
    CreateEntityAttributeAssociationDTO,
    EntityAttributeAssociationDTO,
    UpdateEntityAttributeAssociationDTO,
)
from lif.mdr_services.helper_service import check_attribute_by_id, check_datamodel_by_id, check_entity_by_id
from lif.mdr_utils.logger_config import get_logger
from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)


# helper for pagination
def _paginate(q: Select, offset: int, limit: int, enabled: bool) -> Select:
    return q.order_by(EntityAttributeAssociation.Id).offset(offset).limit(limit) if enabled else q


async def check_existing_association(
    session: AsyncSession, entity_id: int, attribute_id: int, extended_by_data_model_id: int
) -> bool:
    query = select(EntityAttributeAssociation).where(
        EntityAttributeAssociation.EntityId == entity_id,
        EntityAttributeAssociation.AttributeId == attribute_id,
        EntityAttributeAssociation.Deleted == False,
        or_(
            EntityAttributeAssociation.ExtendedByDataModelId == None,
            EntityAttributeAssociation.ExtendedByDataModelId == extended_by_data_model_id,
        ),
    )
    result = await session.execute(query)
    return result.scalar_one_or_none() is not None


async def retrieve_all_entity_attribute_associations(
    session: AsyncSession, entity_id: int, attribute_id: int, extended_by_data_model_id: int
) -> Sequence[EntityAttributeAssociation]:
    query = select(EntityAttributeAssociation).where(
        EntityAttributeAssociation.EntityId == entity_id,
        EntityAttributeAssociation.AttributeId == attribute_id,
        EntityAttributeAssociation.Deleted == False,
        or_(
            EntityAttributeAssociation.ExtendedByDataModelId == None,
            EntityAttributeAssociation.ExtendedByDataModelId == extended_by_data_model_id,
        ),
    )
    result = await session.execute(query)
    associations = result.scalars().all()
    if not associations or len(associations) == 0:
        raise HTTPException(
            status_code=404,
            detail=f"Attribute {attribute_id} association with entity {entity_id} not found in data model association",
        )
    return associations


async def create_entity_attribute_association(session: AsyncSession, data: CreateEntityAttributeAssociationDTO):
    # checking if provided entity id and attribute id exist or not
    entity = await check_entity_by_id(session=session, id=data.EntityId)
    attribute = await check_attribute_by_id(session=session, id=data.AttributeId)

    # Check if the association already exists
    if await check_existing_association(session, data.EntityId, data.AttributeId, data.ExtendedByDataModelId):
        raise HTTPException(status_code=400, detail="Association already exists between the entity and attribute")

    # Create the new EntityAssociation
    entity_attribute_association = EntityAttributeAssociation(**data.dict())
    session.add(entity_attribute_association)
    await session.commit()
    await session.refresh(entity_attribute_association)

    return EntityAttributeAssociationDTO.from_orm(entity_attribute_association)


async def get_entity_attribute_association_by_id(session: AsyncSession, association_id: int):
    association = await session.get(EntityAttributeAssociation, association_id)
    if not association:
        raise HTTPException(status_code=404, detail=f"EntityAttributeAssociation with ID {association_id} not found")
    if association.Deleted:
        raise HTTPException(status_code=404, detail=f"EntityAttributeAssociation with ID {association_id} is deleted")

    # return EntityAttributeAssociationDTO.from_orm(association)
    return association


async def get_entity_attribute_association_by_entity_attribute_id(
    session: AsyncSession, entity_id: int, attribute_id: int, extended_by_data_model_id: int
) -> Optional[EntityAttributeAssociation]:
    query = select(EntityAttributeAssociation).where(
        EntityAttributeAssociation.EntityId == entity_id,
        EntityAttributeAssociation.AttributeId == attribute_id,
        EntityAttributeAssociation.Deleted == False,
        or_(
            EntityAttributeAssociation.ExtendedByDataModelId == None,
            EntityAttributeAssociation.ExtendedByDataModelId == extended_by_data_model_id,
        ),
    )
    result = await session.execute(query)
    entity_attribute_association = result.scalars().first()
    return entity_attribute_association


async def update_entity_attribute_association(
    session: AsyncSession, association_id: int, data: UpdateEntityAttributeAssociationDTO
):
    # Get existing association
    entity_attribute_association = await get_entity_attribute_association_by_id(session, association_id)

    if data.EntityId:
        await check_entity_by_id(session=session, id=data.EntityId)
    if data.AttributeId:
        await check_attribute_by_id(session=session, id=data.AttributeId)

    # Checking if unique association already exists
    if data.EntityId or data.AttributeId:
        updated_entity_id = data.EntityId if data.EntityId else entity_attribute_association.EntityId
        updated_attribute_id = data.AttributeId if data.AttributeId else entity_attribute_association.AttributeId
        updated_extended_by_data_model_id = (
            data.ExtendedByDataModelId
            if data.ExtendedByDataModelId
            else entity_attribute_association.ExtendedByDataModelId
        )
        existing_association = await get_entity_attribute_association_by_entity_attribute_id(
            session, updated_entity_id, updated_attribute_id, updated_extended_by_data_model_id
        )
        if existing_association and existing_association.Id != association_id:
            raise HTTPException(
                status_code=400,
                detail="EntityAttributeAssociation with the same EntityId and AttributeId already exists.",
            )

    for key, value in data.dict(exclude_unset=True).items():
        setattr(entity_attribute_association, key, value)

    session.add(entity_attribute_association)
    await session.commit()
    await session.refresh(entity_attribute_association)
    return EntityAttributeAssociationDTO.from_orm(entity_attribute_association)


async def delete_entity_attribute_association(session: AsyncSession, association_id: int) -> dict:
    entity_association = await get_entity_attribute_association_by_id(session, association_id)
    await session.delete(entity_association)
    await session.commit()
    return {"message": f"Entity association with ID {association_id} deleted successfully"}


async def soft_delete_entity_attribute_association(session: AsyncSession, association_id: int) -> dict:
    entity_association = await get_entity_attribute_association_by_id(session, association_id)
    entity_association.Deleted = True
    session.add(entity_association)
    await session.commit()
    return {"message": f"Entity association with ID {association_id} deleted successfully"}


async def get_entity_attribute_associations_by_data_model_id(
    session: AsyncSession, data_model_id: int, offset: int = 0, limit: int = 10, pagination: bool = True
) -> Tuple[int, List[EntityAttributeAssociationDTO]]:
    # Validate/resolve the data model
    data_model = await check_datamodel_by_id(session=session, id=data_model_id)

    # --- Branch 1: Extension data models (OrgLIF/PartnerLIF) -------------------
    if data_model.Type in {DataModelType.OrgLIF, DataModelType.PartnerLIF}:
        included_ids_subq = (
            select(ExtInclusionsFromBaseDM.IncludedElementId)
            .where(
                ExtInclusionsFromBaseDM.ExtDataModelId == data_model_id,
                ExtInclusionsFromBaseDM.ElementType == "Attribute",
                ExtInclusionsFromBaseDM.Deleted.is_(False),
            )
            .subquery()
        )

        base_query = select(EntityAttributeAssociation).where(
            EntityAttributeAssociation.AttributeId.in_(select(included_ids_subq.c.IncludedElementId)),
            or_(
                EntityAttributeAssociation.ExtendedByDataModelId == data_model_id,
                EntityAttributeAssociation.ExtendedByDataModelId.is_(None),
            ),
            EntityAttributeAssociation.Deleted.is_(False),
        )

        # count efficiently
        count_query = select(func.count()).select_from(base_query.subquery())
        total_count = (await session.execute(count_query)).scalar_one()

        # fetch page (or all)
        rows = await session.execute(_paginate(base_query, offset, limit, pagination))
        associations = rows.scalars().all()

    # --- Branch 2: Base LIF or Source Schema data models ----------------------------------
    else:
        entity_side = (
            select(EntityAttributeAssociation)
            .join(Entity, Entity.Id == EntityAttributeAssociation.EntityId)
            .where(
                Entity.DataModelId == data_model_id,
                Entity.Deleted.is_(False),
                EntityAttributeAssociation.Deleted.is_(False),
                EntityAttributeAssociation.ExtendedByDataModelId.is_(None),
            )
        )

        attribute_side = (
            select(EntityAttributeAssociation)
            .join(Attribute, Attribute.Id == EntityAttributeAssociation.AttributeId)
            .where(
                Attribute.DataModelId == data_model_id,
                Attribute.Deleted.is_(False),
                EntityAttributeAssociation.Deleted.is_(False),
                EntityAttributeAssociation.ExtendedByDataModelId.is_(None),
            )
        )

        total_query = entity_side.union(attribute_side)
        count_query = select(func.count()).select_from(total_query.subquery())
        total_count = (await session.execute(count_query)).scalar_one()

        union_subq = entity_side.union(attribute_side).subquery()
        page_query = select(EntityAttributeAssociation).join(
            union_subq, EntityAttributeAssociation.Id == union_subq.c.Id
        )
        page_query = _paginate(page_query, offset, limit, pagination)

        rows = await session.execute(page_query)
        associations = rows.scalars().all()

    logger.info("entity_attribute_associations: %s", associations)

    # Map to DTOs
    dto_list: List[EntityAttributeAssociationDTO] = [EntityAttributeAssociationDTO.from_orm(a) for a in associations]
    return total_count, dto_list


async def get_entity_attribute_associations_by_entity_id(
    session: AsyncSession,
    entity_id: int,
    offset: int = 0,
    limit: int = 10,
    pagination: bool = True,
    including_extended_by_data_model_id: Optional[int] = None,
) -> Tuple[int, List[EntityAttributeAssociationDTO]]:
    # Common WHERE conditions
    conditions = [EntityAttributeAssociation.EntityId == entity_id, EntityAttributeAssociation.Deleted.is_(False)]

    # ExtendedByDataModelId filter
    if including_extended_by_data_model_id is not None:
        conditions.append(
            or_(
                EntityAttributeAssociation.ExtendedByDataModelId.is_(None),
                EntityAttributeAssociation.ExtendedByDataModelId == including_extended_by_data_model_id,
            )
        )
    else:
        conditions.append(EntityAttributeAssociation.ExtendedByDataModelId.is_(None))

    # Count (efficient; no row materialization)
    count_query = select(func.count()).select_from(EntityAttributeAssociation).where(*conditions)
    total_count = (await session.execute(count_query)).scalar_one()

    # Page (or full list, consistently ordered)
    entity_query = _paginate(select(EntityAttributeAssociation).where(*conditions), offset, limit, pagination)
    rows = await session.execute(entity_query)
    associations = rows.scalars().all()

    logger.info("entity_attribute_associations: %s", associations)

    dto_list: List[EntityAttributeAssociationDTO] = [EntityAttributeAssociationDTO.from_orm(a) for a in associations]
    return total_count, dto_list


async def get_entity_attribute_associations_by_attribute_id(
    session: AsyncSession,
    attribute_id: int,
    offset: int = 0,
    limit: int = 10,
    pagination: bool = True,
    including_extended_by_data_model_id: Optional[int] = None,
) -> Tuple[int, List[EntityAttributeAssociationDTO]]:
    # Common WHERE conditions
    conditions = [EntityAttributeAssociation.AttributeId == attribute_id, EntityAttributeAssociation.Deleted.is_(False)]

    # ExtendedByDataModelId filter
    if including_extended_by_data_model_id is not None:
        conditions.append(
            or_(
                EntityAttributeAssociation.ExtendedByDataModelId.is_(None),
                EntityAttributeAssociation.ExtendedByDataModelId == including_extended_by_data_model_id,
            )
        )
    else:
        conditions.append(EntityAttributeAssociation.ExtendedByDataModelId.is_(None))

    # Count efficiently (no row materialization)
    count_query = select(func.count()).select_from(EntityAttributeAssociation).where(*conditions)
    total_count = (await session.execute(count_query)).scalar_one()

    # Fetch page (or full list), consistently ordered
    entity_query = _paginate(select(EntityAttributeAssociation).where(*conditions), offset, limit, pagination)
    rows = await session.execute(entity_query)
    associations = rows.scalars().all()

    logger.info("entity_attribute_associations: %s", associations)

    # Map to DTOs
    dto_list: List[EntityAttributeAssociationDTO] = [EntityAttributeAssociationDTO.from_orm(a) for a in associations]

    return total_count, dto_list

from fastapi import HTTPException
from lif.datatypes.mdr_sql_model import (
    Attribute,
    DataModel,
    Entity,
    EntityAttributeAssociation,
    Transformation,
    TransformationGroup,
    ValueSet,
    ValueSetValue,
)
from lif.mdr_utils.logger_config import get_logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

logger = get_logger(__name__)


async def check_datamodel_by_id(session: AsyncSession, id: int):
    datamodel = await session.get(DataModel, id)
    if not datamodel:
        raise HTTPException(status_code=404, detail="DataModel not found")
    if datamodel.Deleted:
        raise HTTPException(status_code=404, detail=f"Data Model with ID {id} is deleted")
    return datamodel


async def check_entity_by_id(session: AsyncSession, id: int):
    entity = await session.get(Entity, id)
    if not entity:
        raise HTTPException(status_code=404, detail=f"Entity with id {id}  not found")
    if entity.Deleted:
        raise HTTPException(status_code=404, detail=f"Entity with ID {id} is deleted")
    return entity


async def check_attribute_by_id(session: AsyncSession, id: int):
    attribute = await session.get(Attribute, id)
    if not attribute:
        raise HTTPException(status_code=404, detail=f"Attribute with id {id}  not found")
    if attribute.Deleted:
        raise HTTPException(status_code=404, detail=f"Attribute with ID {id} is deleted")
    # return EntityDTO.from_orm(entity)
    return attribute


async def check_entity_attribute_association(session: AsyncSession, entity_id: int, attribute_id: int):
    query = select(EntityAttributeAssociation).where(
        EntityAttributeAssociation.EntityId == entity_id, EntityAttributeAssociation.AttributeId == attribute_id
    )
    result = await session.execute(query)
    associations = result.fetchall()
    if not associations:
        raise HTTPException(
            status_code=404,
            detail=f"EntityAttributeAssociation with EntityId {entity_id} and AttributeId {attribute_id} not found",
        )
    return associations


async def check_value_set_by_id(session: AsyncSession, id: int):
    value_set = await session.get(ValueSet, id)
    if not value_set:
        raise HTTPException(status_code=404, detail=f"Value set with id {id}  not found")
    if value_set.Deleted:
        raise HTTPException(status_code=404, detail=f"Value set with ID {id} is deleted")
    # return EntityDTO.from_orm(entity)
    return value_set


async def check_value_set_values_by_id(session: AsyncSession, id: int):
    value_set_value = await session.get(ValueSetValue, id)
    if not value_set_value:
        raise HTTPException(status_code=404, detail=f"Value set value with id {id}  not found")
    if value_set_value.Deleted:
        raise HTTPException(status_code=404, detail=f"Value set value with ID {id} is deleted")
    # return EntityDTO.from_orm(entity)
    return value_set_value


async def check_transformation_group_by_id(session: AsyncSession, id: int):
    group = await session.get(TransformationGroup, id)
    if not group:
        raise HTTPException(status_code=404, detail=f"Transformation group with id {id}  not found")
    if group.Deleted:
        raise HTTPException(status_code=404, detail=f"Transformation group with ID {id} is deleted")
    # return EntityDTO.from_orm(entity)
    return group


async def check_transformation_by_id(session: AsyncSession, id: int):
    transformation = await session.get(Transformation, id)
    if not transformation:
        raise HTTPException(status_code=404, detail=f"Transformation with id {id}  not found")
    if transformation.Deleted:
        raise HTTPException(status_code=404, detail=f"Transformation with ID {id} is deleted")
    # return EntityDTO.from_orm(entity)
    return transformation


async def get_entity_by_attribute_id(session: AsyncSession, attribute_id):
    query = select(EntityAttributeAssociation.EntityId).where(
        EntityAttributeAssociation.AttributeId == attribute_id, EntityAttributeAssociation.Deleted == False
    )
    result = await session.execute(query)
    entity_id = result.scalars().first()
    return entity_id


async def get_entity_attribute_association_dict(session: AsyncSession):
    query = select(EntityAttributeAssociation.EntityId, EntityAttributeAssociation.AttributeId).where(
        EntityAttributeAssociation.Deleted == False
    )
    result = await session.execute(query)
    associations = result.fetchall()
    association_dict = {association.AttributeId: association.EntityId for association in associations}

    return association_dict


async def get_attribute_by_name_and_entity_id(session: AsyncSession, name: str, entity_id: int):
    # Query to join EntityAttributeAssociation with Attribute and filter by attribute name and entity_id
    query = (
        select(Attribute)
        .join(EntityAttributeAssociation, EntityAttributeAssociation.AttributeId == Attribute.Id)
        .where(EntityAttributeAssociation.EntityId == entity_id)
        .where(Attribute.Name == name, Attribute.Deleted == False)
    )

    result = await session.execute(query)
    attribute = result.scalar_one_or_none()

    if not attribute:
        raise HTTPException(status_code=404, detail=f"Attribute '{name}' not found for entity ID {entity_id}")

    if attribute.Deleted:
        raise HTTPException(status_code=404, detail=f"Attribute with name '{name}' is already deleted")

    return attribute

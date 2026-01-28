from fastapi import HTTPException
from lif.datatypes.mdr_sql_model import DatamodelElementType, EntityAttributeAssociation, ExtInclusionsFromBaseDM
from lif.mdr_dto.inclusion_dto import CreateInclusionDTO, InclusionDTO, UpdateInclusionDTO
from lif.mdr_services.attribute_service import get_attribute_by_id
from lif.mdr_services.entity_service import get_entity_by_id
from lif.mdr_services.helper_service import check_datamodel_by_id
from lif.mdr_utils.logger_config import get_logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import func, select

logger = get_logger(__name__)


async def soft_delete_data_model_ext_inclusions(session: AsyncSession, data_model_id: int):
    query = select(ExtInclusionsFromBaseDM).where(
        ExtInclusionsFromBaseDM.ExtDataModelId == data_model_id, ExtInclusionsFromBaseDM.Deleted == False
    )
    result = await session.execute(query)
    ext_inclusions = result.scalars().all()
    for ext_inclusion in ext_inclusions:
        ext_inclusion.Deleted = True
        session.add(ext_inclusion)
    await session.commit()
    logger.info(f"Soft deleted ExtInclusionsFromBaseDM for DataModelId {data_model_id}")


async def get_inclusion_by_id(session: AsyncSession, inclusion_id: int):
    query = select(ExtInclusionsFromBaseDM).where(ExtInclusionsFromBaseDM.Id == inclusion_id)
    result = await session.execute(query)
    inclusion = result.scalars().first()
    if not inclusion:
        raise HTTPException(status_code=404, detail=f"Inclusion with ID {inclusion_id} not found")
    if inclusion.Deleted:
        raise HTTPException(status_code=404, detail=f"Inclusion with ID {inclusion_id} is deleted")
    return InclusionDTO.from_orm(inclusion)


async def check_inclusion_exists(
    session: AsyncSession, data_model_id: int, element_type: str, included_element_id: int
):
    query = select(ExtInclusionsFromBaseDM).where(
        ExtInclusionsFromBaseDM.ExtDataModelId == data_model_id,
        ExtInclusionsFromBaseDM.ElementType == element_type,
        ExtInclusionsFromBaseDM.IncludedElementId == included_element_id,
        ExtInclusionsFromBaseDM.Deleted == False,
    )
    result = await session.execute(query)
    existing_inclusion = result.scalars().first()
    return existing_inclusion


async def handle_queryable_modifiable_for_inclusion(
    session: AsyncSession, data, elementType: str, element_id: int, data_model_id: int
):
    if elementType == "Entity" and (data.Queryable is not None or data.Modifiable is not None):
        # Find any Attributes that belong to this entity that have already been included and mark them as Queryable/Modifiable == true as well
        attribute_query = (
            select(EntityAttributeAssociation.AttributeId)
            .where(EntityAttributeAssociation.EntityId == element_id)
            .where(EntityAttributeAssociation.Deleted == False)
            .where(
                EntityAttributeAssociation.AttributeId.in_(
                    select(ExtInclusionsFromBaseDM.IncludedElementId)
                    .where(ExtInclusionsFromBaseDM.ExtDataModelId == data_model_id)
                    .where(ExtInclusionsFromBaseDM.ElementType == "Attribute")
                    .where(ExtInclusionsFromBaseDM.IncludedElementId == EntityAttributeAssociation.AttributeId)
                    .where(ExtInclusionsFromBaseDM.Deleted == False)
                )
            )
        )
        results = await session.execute(attribute_query)
        attribute_ids = results.scalars().all()

        # Mark the found attributes as Queryable/Modifiable
        for attr_id in attribute_ids:
            existing_inclusion = await check_inclusion_exists(session, data_model_id, "Attribute", attr_id)
            if existing_inclusion:
                if data.Queryable is not None:
                    existing_inclusion.Queryable = data.Queryable
                if data.Modifiable is not None:
                    existing_inclusion.Modifiable = data.Modifiable
                session.add(existing_inclusion)
    return data


async def create_inclusion(session: AsyncSession, data: CreateInclusionDTO):
    # Check if data model exists
    await check_datamodel_by_id(session=session, id=data.ExtDataModelId)

    # Check if element exists
    if data.ElementType == "Entity" and await get_entity_by_id(session=session, id=data.IncludedElementId) == None:
        raise HTTPException(status_code=404, detail=f"Entity with ID {data.IncludedElementId} not found")
    if (
        data.ElementType == "Attribute"
        and await get_attribute_by_id(session=session, id=data.IncludedElementId) == None
    ):
        raise HTTPException(status_code=404, detail=f"Attribute with ID {data.IncludedElementId} not found")

    # Check if inclusion already exists
    if await check_inclusion_exists(session, data.ExtDataModelId, data.ElementType, data.IncludedElementId):
        raise HTTPException(status_code=400, detail="Inclusion already exists for the specified DataModel")

    data = await handle_queryable_modifiable_for_inclusion(
        session, data, data.ElementType, data.IncludedElementId, data.ExtDataModelId
    )

    new_inclusion = ExtInclusionsFromBaseDM(**data.dict())
    session.add(new_inclusion)
    await session.commit()
    await session.refresh(new_inclusion)
    return InclusionDTO.from_orm(new_inclusion)


async def update_inclusion(session: AsyncSession, inclusion_id: int, data: UpdateInclusionDTO):
    inclusion = await session.get(ExtInclusionsFromBaseDM, inclusion_id)
    if not inclusion:
        raise HTTPException(status_code=404, detail=f"Inclusion with ID {inclusion_id} not found")
    if inclusion.Deleted:
        raise HTTPException(status_code=404, detail=f"Inclusion with ID {inclusion_id} is deleted")

    data = await handle_queryable_modifiable_for_inclusion(
        session, data, inclusion.ElementType, inclusion.IncludedElementId, inclusion.ExtDataModelId
    )

    for key, value in data.dict(exclude_unset=True).items():
        setattr(inclusion, key, value)

    session.add(inclusion)
    await session.commit()
    await session.refresh(inclusion)
    return InclusionDTO.from_orm(inclusion)


async def soft_delete_inclusion(session: AsyncSession, inclusion_id: int):
    if not await get_inclusion_by_id(session, inclusion_id):
        raise HTTPException(status_code=404, detail="Inclusion not found")

    inclusion = await session.get(ExtInclusionsFromBaseDM, inclusion_id)
    if not inclusion:
        raise HTTPException(status_code=404, detail=f"Inclusion with ID {inclusion_id} not found in session")
    if inclusion.Deleted:
        raise HTTPException(status_code=404, detail=f"Inclusion with ID {inclusion_id} is already deleted")

    setattr(inclusion, "Deleted", True)
    session.add(inclusion)
    await session.commit()
    return {"ok": True}


async def get_list_of_inclusions_for_data_model(
    session: AsyncSession, data_model_id: int, offset: int, size: int, pagination: bool = True, check_base: bool = True
):
    query = select(ExtInclusionsFromBaseDM).where(
        ExtInclusionsFromBaseDM.ExtDataModelId == data_model_id, ExtInclusionsFromBaseDM.Deleted == False
    )
    if pagination:
        query = query.offset(offset).limit(size)
    result = await session.execute(query)
    inclusions = result.scalars().all()
    total_count = await session.scalar(select(func.count()).select_from(query.subquery()))

    # Convert to InclusionDTO list
    inclusion_dtos = [InclusionDTO.from_orm(inclusion) for inclusion in inclusions]

    return total_count, inclusion_dtos


async def get_entity_inclusions_by_data_model_id(session: AsyncSession, data_model_id: int):
    query = select(ExtInclusionsFromBaseDM).where(
        ExtInclusionsFromBaseDM.ExtDataModelId == data_model_id,
        ExtInclusionsFromBaseDM.Deleted == False,
        ExtInclusionsFromBaseDM.ElementType == "Entity",
    )
    result = await session.execute(query)
    inclusions = result.scalars().all()
    inclusion_dtos = [InclusionDTO.from_orm(inclusion) for inclusion in inclusions]
    return inclusion_dtos


async def get_attribute_inclusions_by_data_model_id(session: AsyncSession, data_model_id: int):
    query = select(ExtInclusionsFromBaseDM).where(
        ExtInclusionsFromBaseDM.ExtDataModelId == data_model_id,
        ExtInclusionsFromBaseDM.Deleted == False,
        ExtInclusionsFromBaseDM.ElementType == "Attribute",
    )
    result = await session.execute(query)
    inclusions = result.scalars().all()
    inclusion_dtos = [InclusionDTO.from_orm(inclusion) for inclusion in inclusions]
    return inclusion_dtos


async def get_attribute_inclusions_by_data_model_id_and_entity_id(
    session: AsyncSession, data_model_id: int, entity_id: int
):
    # Check if the entity is included in the data model
    query = select(ExtInclusionsFromBaseDM).where(
        ExtInclusionsFromBaseDM.ExtDataModelId == data_model_id,
        ExtInclusionsFromBaseDM.Deleted == False,
        ExtInclusionsFromBaseDM.ElementType == "Entity",
        ExtInclusionsFromBaseDM.IncludedElementId == entity_id,
    )
    result = await session.execute(query)
    entity_inclusion = result.scalars().first()
    if not entity_inclusion:
        raise HTTPException(
            status_code=404, detail=f"Entity with ID {entity_id} not included in data model {data_model_id}"
        )

    # Get the attribute ids associated with this entity
    entity_query = (
        select(EntityAttributeAssociation.AttributeId)
        .where(EntityAttributeAssociation.EntityId == entity_id, EntityAttributeAssociation.Deleted == False)
        .order_by(EntityAttributeAssociation.Id)
    )

    result = await session.execute(entity_query)
    attribute_ids = result.scalars().all()

    logger.info(f"Attribute IDs for Entity {entity_id} in DataModel {data_model_id}: {attribute_ids}")

    # Get the attribute inclusions for these attribute ids
    query = select(ExtInclusionsFromBaseDM).where(
        ExtInclusionsFromBaseDM.ExtDataModelId == data_model_id,
        ExtInclusionsFromBaseDM.Deleted == False,
        ExtInclusionsFromBaseDM.ElementType == "Attribute",
        ExtInclusionsFromBaseDM.IncludedElementId.in_(attribute_ids),
    )
    result = await session.execute(query)
    inclusions = result.scalars().all()
    inclusion_dtos = [InclusionDTO.from_orm(inclusion) for inclusion in inclusions]
    return inclusion_dtos


async def check_existing_inclusion(
    session: AsyncSession, type: DatamodelElementType, node_id: int, included_by_data_model_id: int
) -> None:
    query = select(ExtInclusionsFromBaseDM).where(
        ExtInclusionsFromBaseDM.ExtDataModelId == included_by_data_model_id,
        ExtInclusionsFromBaseDM.IncludedElementId == node_id,
        ExtInclusionsFromBaseDM.ElementType == type,
        ExtInclusionsFromBaseDM.Deleted == False,
    )
    result = await session.execute(query)
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=404, detail=f"Inclusion of {type} {node_id} not found in data model {included_by_data_model_id}"
        )

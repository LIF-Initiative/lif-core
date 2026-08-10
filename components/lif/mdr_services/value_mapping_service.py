from fastapi import HTTPException
from lif.datatypes.mdr_sql_model import ValueSetValueMapping
from lif.mdr_dto.value_mapping_dto import (
    CreateValueSetValueMappingDTO,
    UpdateValueSetValueMappingDTO,
    ValueSetValueMappingDTO,
)
from lif.mdr_services.transformation_service import get_transformation_group_by_id
from lif.mdr_services.value_set_values_service import get_value_set_value_by_id
from lif.mdr_services.valueset_service import get_value_set_by_id
from lif.mdr_utils.logger_config import get_logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, func

logger = get_logger(__name__)


async def create_value_set_value_mapping(
    session: AsyncSession, data: CreateValueSetValueMappingDTO
) -> ValueSetValueMappingDTO:
    # Check if transformation group exists
    await get_transformation_group_by_id(session=session, id=data.TransformationGroupId)

    # Check if the source ValueSetValueId exists
    source_value = await get_value_set_value_by_id(session=session, id=data.SourceValueId)

    # Check if the target ValueSetValueId exists
    target_value = await get_value_set_value_by_id(session=session, id=data.TargetValueId)

    query = select(ValueSetValueMapping).where(
        ValueSetValueMapping.SourceValueId == data.SourceValueId,
        ValueSetValueMapping.TargetValueId == data.TargetValueId,
        ValueSetValueMapping.Deleted == False,
    )
    result = await session.execute(query)
    valueset_values = result.scalars().all()
    if len(valueset_values) > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Mapping between source value id {data.SourceValueId} and target value id {data.TargetValueId} already exists.",
        )

    # Create the mapping between source and target value set values
    value_set_value_mapping = ValueSetValueMapping(**data.dict())
    session.add(value_set_value_mapping)
    await session.commit()
    await session.refresh(value_set_value_mapping)
    return ValueSetValueMappingDTO.from_orm(value_set_value_mapping)
    # return {
    #     "message": "Value set value mapping created successfully",
    #     "ValueSetValueMappingId": value_set_value_mapping.Id
    # }


async def get_paginated_value_mapping(session: AsyncSession, offset: int = 0, limit: int = 10, pagination: bool = True):
    # Query to count total records
    total_query = select(func.count(ValueSetValueMapping.Id)).where(ValueSetValueMapping.Deleted == False)
    total_result = await session.execute(total_query)
    total_count = total_result.scalar()
    # Query to fetch paginated results
    if pagination:
        query = select(ValueSetValueMapping).where(ValueSetValueMapping.Deleted == False).offset(offset).limit(limit)
    else:
        query = select(ValueSetValueMapping).where(ValueSetValueMapping.Deleted == False)
    result = await session.execute(query)
    mappings = result.scalars().all()
    # Convert the list of Attribute objects to AttributeDTO objects
    mapping_dtos = [ValueSetValueMappingDTO.from_orm(mapping) for mapping in mappings]
    return total_count, mapping_dtos


async def get_mapping_by_id(session: AsyncSession, id: int):
    mapping = await session.get(ValueSetValueMapping, id)
    if not mapping:
        raise HTTPException(status_code=404, detail=f"Value mapping with id {id}  not found")
    if mapping.Deleted:
        raise HTTPException(status_code=404, detail=f"Value mapping with ID {id} is deleted")
    # return EntityDTO.from_orm(entity)
    return mapping


async def get_value_mappings_by_transformation_group_id(session: AsyncSession, transformation_group_id: int):
    # Validate transformation group exists
    await get_transformation_group_by_id(session=session, id=transformation_group_id)

    query = select(ValueSetValueMapping).where(
        ValueSetValueMapping.TransformationGroupId == transformation_group_id, ValueSetValueMapping.Deleted == False
    )
    result = await session.execute(query)
    mappings = result.scalars().all()
    return [ValueSetValueMappingDTO.from_orm(mapping) for mapping in mappings]


async def get_value_mappings_by_value_ids(
    session: AsyncSession, source_value_id: int = None, target_value_id: int = None
):
    # Validate source and/or target value exists
    if source_value_id is not None:
        await get_value_set_value_by_id(session=session, id=source_value_id)
    if target_value_id is not None:
        await get_value_set_value_by_id(session=session, id=target_value_id)

    query = select(ValueSetValueMapping).where(ValueSetValueMapping.Deleted == False)
    if source_value_id is not None:
        query = query.where(ValueSetValueMapping.SourceValueId == source_value_id)
    if target_value_id is not None:
        query = query.where(ValueSetValueMapping.TargetValueId == target_value_id)

    result = await session.execute(query)
    mappings = result.scalars().all()
    return [ValueSetValueMappingDTO.from_orm(mapping) for mapping in mappings]


async def get_value_mappings_by_value_set_ids(
    session: AsyncSession, source_value_set_id: int = None, target_value_set_id: int = None
):
    # Validate source and/or target value sets exist
    if source_value_set_id is not None:
        await get_value_set_by_id(session=session, id=source_value_set_id)
    if target_value_set_id is not None:
        await get_value_set_by_id(session=session, id=target_value_set_id)

    query = select(ValueSetValueMapping).where(ValueSetValueMapping.Deleted == False)
    if source_value_set_id is not None:
        query = query.where(ValueSetValueMapping.SourceValueSetId == source_value_set_id)
    if target_value_set_id is not None:
        query = query.where(ValueSetValueMapping.TargetValueSetId == target_value_set_id)

    result = await session.execute(query)
    mappings = result.scalars().all()
    return [ValueSetValueMappingDTO.from_orm(mapping) for mapping in mappings]


async def soft_delete_mapping(session: AsyncSession, id: int):
    # Validate mapping exists
    await get_mapping_by_id(session=session, id=id)

    # Fetch and delete the value mapping by ID
    mapping = await get_mapping_by_id(session=session, id=id)
    mapping.Deleted = True
    session.add(mapping)
    await session.commit()
    return {"ok": True}


async def update_mapping(session: AsyncSession, id: int, data: UpdateValueSetValueMappingDTO) -> dict:
    mapping = await get_mapping_by_id(session=session, id=id)

    # Check if transformation group exists
    if data.TransformationGroupId:
        await get_transformation_group_by_id(session=session, id=data.TransformationGroupId)

    # Check if source value set exists
    if data.SourceValueSetId:
        await get_value_set_by_id(session=session, id=data.SourceValueSetId)

    # Check if target value set exists
    if data.TargetValueSetId:
        await get_value_set_by_id(session=session, id=data.TargetValueSetId)

    # Check if the source ValueSetValueId exists
    if data.SourceValueId:
        source_value_set_value = await get_value_set_value_by_id(session=session, id=data.SourceValueId)
        source_value_set_id = data.SourceValueSetId if data.SourceValueSetId else mapping.SourceValueSetId
        if source_value_set_id and source_value_set_value.ValueSetId != source_value_set_id:
            raise HTTPException(
                status_code=400,
                detail=f"Source ValueSetId {source_value_set_id} does not match the ValueSetId {source_value_set_value.ValueSetId} of the SourceValueId {data.SourceValueId}.",
            )

    # Check if the target ValueSetValueId exists
    if data.TargetValueId:
        target_value_set_value = await get_value_set_value_by_id(session=session, id=data.TargetValueId)
        target_value_set_id = data.TargetValueSetId if data.TargetValueSetId else mapping.TargetValueSetId
        if target_value_set_id and target_value_set_value.ValueSetId != target_value_set_id:
            raise HTTPException(
                status_code=400,
                detail=f"Target ValueSetId {target_value_set_id} does not match the ValueSetId {target_value_set_value.ValueSetId} of the TargetValueId {data.TargetValueId}.",
            )

    # Validate duplicate value mapping is not being created
    validation_query = None
    updated_transformation_group_id = (
        data.TransformationGroupId if data.TransformationGroupId else mapping.TransformationGroupId
    )
    updated_source_value_id = data.SourceValueId if data.SourceValueId else mapping.SourceValueId
    updated_target_value_id = data.TargetValueId if data.TargetValueId else mapping.TargetValueId

    if updated_transformation_group_id:
        validation_query = select(ValueSetValueMapping).where(
            ValueSetValueMapping.SourceValueId == updated_source_value_id,
            ValueSetValueMapping.TargetValueId == updated_target_value_id,
            ValueSetValueMapping.TransformationGroupId == updated_transformation_group_id,
            ValueSetValueMapping.Deleted == False,
        )
    elif data.SourceValueId or data.TargetValueId:
        validation_query = select(ValueSetValueMapping).where(
            ValueSetValueMapping.SourceValueId == updated_source_value_id,
            ValueSetValueMapping.TargetValueId == updated_target_value_id,
            ValueSetValueMapping.Deleted == False,
        )
        result = await session.execute(validation_query)
        valueset_values = result.scalars().all()
        if len(valueset_values) > 0:
            raise HTTPException(
                status_code=400,
                detail=f"Mapping between source value id {updated_source_value_id} and target value id {updated_target_value_id} already exists for transformation group id {updated_transformation_group_id}.",
            )

    # Create the mapping between source and target value set values
    for key, value in data.dict(exclude_unset=True).items():
        setattr(mapping, key, value)
    session.add(mapping)
    await session.commit()
    await session.refresh(mapping)
    return ValueSetValueMappingDTO.from_orm(mapping)

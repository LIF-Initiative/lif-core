from typing import List
from fastapi import HTTPException
from lif.datatypes.mdr_sql_model import ValueSet, ValueSetValue, ValueSetValueMapping
from lif.mdr_dto.value_set_values_dto import CreateValueSetValueDTO, UpdateValueSetValueDTO, ValueSetValueDTO
from lif.mdr_services.helper_service import check_datamodel_by_id
from lif.mdr_utils.logger_config import get_logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, func
from sqlalchemy import or_

logger = get_logger(__name__)


async def get_paginated_value_set_values(
    session: AsyncSession, offset: int = 0, limit: int = 10, pagination: bool = True
):
    total_query = select(func.count(ValueSetValue.Id)).where(ValueSetValue.Deleted == False)
    total_result = await session.execute(total_query)
    total_count = total_result.scalar()

    if pagination:
        query = select(ValueSetValue).where(ValueSetValue.Deleted == False).offset(offset).limit(limit)
    else:
        query = select(ValueSetValue).where(ValueSetValue.Deleted == False)
    result = await session.execute(query)
    value_set_values = result.scalars().all()

    value_set_value_dtos = [ValueSetValueDTO.from_orm(value) for value in value_set_values]

    return total_count, value_set_value_dtos


async def get_value_set_value_by_id(session: AsyncSession, id: int):
    value_set_value = await session.get(ValueSetValue, id)
    if not value_set_value:
        raise HTTPException(status_code=404, detail=f"ValueSetValue with ID {id} not found")
    if value_set_value.Deleted:
        raise HTTPException(status_code=404, detail=f"Value set value with ID {id} is deleted")

    return value_set_value


async def check_value_set_exists_by_id(session: AsyncSession, id: int) -> bool:
    query = select(ValueSet).where(ValueSet.Id == id)
    result = await session.execute(query)
    value_set = result.scalars().first()
    if not value_set:
        raise HTTPException(status_code=404, detail=f"ValueSet with ID {id} not found")
    if value_set.Deleted:
        raise HTTPException(status_code=404, detail=f"ValueSet with ID {id} is deleted")
    return value_set


async def create_value_set_values(session: AsyncSession, data: List[CreateValueSetValueDTO]) -> ValueSetValueDTO:
    value_set_values_dtos: list[ValueSetValueDTO] = []
    for value in data:
        # Check if data model exists
        await check_datamodel_by_id(session=session, id=value.DataModelId)

        # Check if value set exists
        value_set = await check_value_set_exists_by_id(session=session, id=value.ValueSetId)

        # If value set is an extension, then the values must also all be extensions
        if value_set.Extension:
            value.Extension = True

        # Check if value already exists in the value set
        check_value_query = select(ValueSetValue).where(
            ValueSetValue.ValueSetId == value.ValueSetId,
            ValueSetValue.DataModelId == value.DataModelId,
            ValueSetValue.Value == value.Value,
            ValueSetValue.ValueName == value.ValueName,
            ValueSetValue.Deleted == False,
        )
        result = await session.execute(check_value_query)
        values = result.scalars().all()
        if values:
            raise HTTPException(
                status_code=404,
                detail=f"ValueSetValue with value {value.Value} under value set id {value.ValueSetId} and data model id {value.DataModelId} already exists.",
            )

        # Create new ValueSetValue
        value_set_value = ValueSetValue(**value.dict())
        session.add(value_set_value)
        await session.commit()
        await session.refresh(value_set_value)
        value_set_values_dtos.append(ValueSetValueDTO.from_orm(value_set_value))

    return value_set_values_dtos


async def update_value_set_value(session: AsyncSession, id: int, data: UpdateValueSetValueDTO) -> ValueSetValueDTO:
    value_set_value = await get_value_set_value_by_id(session=session, id=id)

    # `is not None`, not truthiness: an id of 0 is a value the client supplied, and the
    # write below applies it (dict(exclude_unset=True)) — so it must be validated, not skipped.
    if data.DataModelId is not None:
        data_model = await check_datamodel_by_id(session=session, id=data.DataModelId)

    if data.DataModelId is not None or data.Value or data.ValueName:
        updated_data_model_id = data.DataModelId if data.DataModelId is not None else value_set_value.DataModelId
        updated_value = data.Value if data.Value else value_set_value.Value
        updated_value_name = data.ValueName if data.ValueName else value_set_value.ValueName
        existing_value_query = select(ValueSetValue).where(
            ValueSetValue.ValueSetId == value_set_value.ValueSetId,
            ValueSetValue.DataModelId == updated_data_model_id,
            ValueSetValue.Value == updated_value,
            ValueSetValue.ValueName == updated_value_name,
            ValueSetValue.Deleted == False,
        )
        result = await session.execute(existing_value_query)
        existing_value = result.scalars().first()
        if existing_value and existing_value.Id != id:
            raise HTTPException(status_code=400, detail=f"ValueSetValue with value {updated_value} already exists.")

    for key, value in data.dict(exclude_unset=True).items():
        setattr(value_set_value, key, value)

    session.add(value_set_value)
    await session.commit()
    await session.refresh(value_set_value)

    return ValueSetValueDTO.from_orm(value_set_value)


async def delete_value_set_value(session: AsyncSession, id: int):
    value_set_value = await get_value_set_value_by_id(session=session, id=id)

    await session.delete(value_set_value)
    await session.commit()

    return {"ok": True}


async def soft_delete_value_set_value(session: AsyncSession, id: int):
    value_set_value = await get_value_set_value_by_id(session=session, id=id)
    value_mapping_query = select(ValueSetValueMapping).where(
        or_(
            (ValueSetValueMapping.SourceValueId == value_set_value.Id),
            (ValueSetValueMapping.TargetValueId == value_set_value.Id),
        ),
        ValueSetValueMapping.Deleted == False,
    )
    result = await session.execute(value_mapping_query)
    mapped_values = result.scalars().all()
    for mapping in mapped_values:
        mapping.Deleted = True
        session.add(mapping)
    value_set_value.Deleted = True
    session.add(value_set_value)
    await session.commit()

    return {"ok": True}


async def get_list_of_values_for_value_set(
    session: AsyncSession, valueset_id: int, offset: int = 0, limit: int = 10, pagination: bool = True
):
    # Check if value set exists
    await check_value_set_exists_by_id(session=session, id=valueset_id)

    # Query to count total ValueSetValues for the given ValueSet
    total_query = select(func.count(ValueSetValue.Id)).where(
        ValueSetValue.ValueSetId == valueset_id, ValueSetValue.Deleted == False
    )
    total_result = await session.execute(total_query)
    total_count = total_result.scalar()

    # logger.info(f"total_count : {total_count}")

    # Query to fetch paginated ValueSetValues for the given ValueSet, ordered by Id
    if pagination:
        query = (
            select(ValueSetValue)
            .where(ValueSetValue.ValueSetId == valueset_id, ValueSetValue.Deleted == False)
            .order_by(ValueSetValue.Id)
            .offset(offset)
            .limit(limit)
        )
    else:
        query = (
            select(ValueSetValue)
            .where(ValueSetValue.ValueSetId == valueset_id, ValueSetValue.Deleted == False)
            .order_by(ValueSetValue.Id)
        )
    result = await session.execute(query)
    valueset_values = result.scalars().all()

    # logger.info(f"valueset_values : {valueset_values}")
    # Convert to ValueSetValueDTO list
    valueset_value_dtos = [ValueSetValueDTO.from_orm(value) for value in valueset_values]
    # logger.info(f"valueset_value_dtos : {valueset_value_dtos}")

    return total_count, valueset_value_dtos

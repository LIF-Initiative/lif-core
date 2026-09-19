from typing import List
from lif.mdr_dto.datamodel_dto import EntityAttributeExportDTO
from fastapi import HTTPException
from lif.datatypes.mdr_sql_model import (
    Attribute,
    DataModel,
    DataModelType,
    Entity,
    EntityAttributeAssociation,
    ValueSet,
    ValueSetValue,
    ValueSetValueMapping,
)
from lif.mdr_dto.valueset_dto import CreateValueSetDTO, CreateValueSetWithValuesDTO, UpdateValueSetDTO, ValueSetDTO
from lif.mdr_services.helper_service import check_datamodel_by_id
from lif.mdr_services.value_set_values_service import create_value_set_values
from lif.mdr_utils.logger_config import get_logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, func
from sqlalchemy import or_, and_

logger = get_logger(__name__)


async def get_paginated_value_sets(session: AsyncSession, offset: int = 0, limit: int = 10, pagination: bool = True):
    total_query = select(func.count(ValueSet.Id)).where(ValueSet.Deleted == False)
    total_result = await session.execute(total_query)
    total_count = total_result.scalar()

    if pagination:
        query = select(ValueSet).where(ValueSet.Deleted == False).offset(offset).limit(limit)
    else:
        query = select(ValueSet).where(ValueSet.Deleted == False)
    result = await session.execute(query)
    value_sets = result.scalars().all()
    # Convert the list of Attribute objects to AttributeDTO objects
    value_set_dtos = [ValueSetDTO.from_orm(value_set) for value_set in value_sets]

    return total_count, value_set_dtos


async def get_value_set_by_id(session: AsyncSession, id: int):
    value_set = await session.get(ValueSet, id)
    if not value_set:
        raise HTTPException(status_code=404, detail="ValueSet not found")
    if value_set.Deleted:
        raise HTTPException(status_code=404, detail=f"ValueSet with ID {id} is deleted")
    # return ValueSetDTO.from_orm(value_set)
    return value_set


async def create_value_set(session: AsyncSession, data: CreateValueSetDTO):
    # Check if a value set with the same name exists in the given data model
    data_model = await check_datamodel_by_id(session=session, id=data.DataModelId)

    if await check_value_set_exists(session, data.Name, data.DataModelId):
        raise HTTPException(
            status_code=400, detail=f"ValueSet with name '{data.Name}' already exists in the specified DataModel"
        )

    # if data_model.Extension and not data.Extension:
    #     data.Extension = True
    # if not data_model.Extension and data.Extension:
    #     logger.info("Data model is not extension so provided value set can not be an extension.")
    #     data.Extension = False

    value_set = ValueSet(**data.dict())
    session.add(value_set)
    await session.commit()
    await session.refresh(value_set)
    return ValueSetDTO.from_orm(value_set)


async def update_value_set(session: AsyncSession, id: int, data: UpdateValueSetDTO):
    value_set = await get_value_set_by_id(session=session, id=id)
    data_model_id = value_set.DataModelId
    # `is not None`, not truthiness: an id of 0 is a value the client supplied, and the
    # write below applies it (dict(exclude_unset=True)) — so it must be honored, not skipped.
    if data.DataModelId is not None:
        data_model_id = data.DataModelId

    if data.DataModelId is not None or data.Name:
        updated_data_model_id = data.DataModelId if data.DataModelId is not None else value_set.DataModelId
        updated_name = data.Name if data.Name else value_set.Name
        existing_value_set_query = select(ValueSet).where(
            ValueSet.Name == updated_name, ValueSet.DataModelId == updated_data_model_id, ValueSet.Deleted == False
        )
        result = await session.execute(existing_value_set_query)
        existing_value_set = result.scalars().first()
        if existing_value_set and existing_value_set.Id != id:
            raise HTTPException(
                status_code=400, detail=f"ValueSet with name '{updated_name}' already exists in the specified DataModel"
            )

    for key, value in data.dict(exclude_unset=True).items():
        setattr(value_set, key, value)

    session.add(value_set)
    await session.commit()
    await session.refresh(value_set)
    return ValueSetDTO.from_orm(value_set)


async def delete_value_set(session: AsyncSession, id: int):
    value_set = await get_value_set_by_id(session=session, id=id)

    await session.delete(value_set)
    await session.commit()
    return {"ok": True}


async def soft_delete_value_set(session: AsyncSession, id: int):
    value_set = await get_value_set_by_id(session=session, id=id)

    # Delete associations in the EntityAttributeAssociation table
    value_set_value_query = select(ValueSetValue).where(ValueSetValue.ValueSetId == id, ValueSetValue.Deleted == False)
    result = await session.execute(value_set_value_query)
    values = result.scalars().all()

    # Delete all associated values from ValueSetValues
    for value in values:
        value_mapping_query = select(ValueSetValueMapping).where(
            or_((ValueSetValueMapping.SourceValueId == value.Id), (ValueSetValueMapping.TargetValueId == value.Id)),
            ValueSetValueMapping.Deleted == False,
        )
        result = await session.execute(value_mapping_query)
        mapped_values = result.scalars().all()
        for mapping in mapped_values:
            mapping.Deleted = True
            session.add(mapping)
        value.Deleted = True
        session.add(value)

    # Now delete the value set itself
    value_set.Deleted = True
    session.add(value_set)

    await session.commit()
    return {"ok": True}


async def check_value_set_exists(session: AsyncSession, name: str, data_model_id: int) -> bool:
    # Query to check if a value set with the same name exists in the given data model
    query = select(ValueSet).where(
        ValueSet.Name == name, ValueSet.DataModelId == data_model_id, ValueSet.Deleted == False
    )
    result = await session.execute(query)
    existing_value_set = result.scalars().first()

    if existing_value_set:
        return True  # ValueSet with the same name exists

    return False  # No ValueSet with the same name exists


async def get_valuesets_by_ids(session: AsyncSession, ids: List[int]) -> List[ValueSetDTO]:
    # Query to get the value sets for the provided list of IDs
    query = select(ValueSet).where(ValueSet.Id.in_(ids), ValueSet.Deleted == False)
    result = await session.execute(query)
    valuesets = result.scalars().all()

    # Convert the list of ValueSet objects to ValueSetDTO objects
    valueset_dtos = [ValueSetDTO.from_orm(valueset) for valueset in valuesets]

    return valueset_dtos


# async def get_list_of_values(session: AsyncSession, id: int):
#     value_set = await get_value_set_by_id(session,id)
#     values = await get_list_of_values_for_value_set(session=session, value_set_id=id)
#     value_set_values = ValueSetAndValuesDTO(
#             ValueSet=value_set,
#             Values=values
#         )
#     return value_set_values


async def create_value_set_with_values(session: AsyncSession, data: CreateValueSetWithValuesDTO):
    # Check if a value set with the same name exists in the given data model
    value_set_data = data.ValueSet
    data_model = await check_datamodel_by_id(session=session, id=value_set_data.DataModelId)
    try:
        if await check_value_set_exists(session, value_set_data.Name, value_set_data.DataModelId):
            raise HTTPException(
                status_code=400,
                detail=f"ValueSet with name '{value_set_data.Name}' already exists in the specified DataModel",
            )

        value_set = ValueSet(**value_set_data.dict())
        session.add(value_set)
        await session.commit()
        await session.refresh(value_set)

        list_of_value_data = data.Values
        for value_data in list_of_value_data:
            value_data.ValueSetId = value_set.Id
            value_data.DataModelId = value_set.DataModelId
        await create_value_set_values(session, list_of_value_data)

        return ValueSetDTO.from_orm(value_set)
    except BaseException as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error while creating ValueSet with name '{value_set_data.Name}' with values. Error: {e}",
        )


async def get_paginated_value_sets_by_data_model_id(
    session: AsyncSession, data_model_id: int, offset: int = 0, limit: int = 1, pagination: bool = True
) -> dict:
    # Check for data model id and for extension
    data_model_id_list: List[int] = []
    data_model = await check_datamodel_by_id(session=session, id=data_model_id)
    data_model_id_list.append(data_model.Id)
    if data_model.Type == DataModelType.OrgLIF or data_model.Type == DataModelType.PartnerLIF:
        base_data_model = await check_datamodel_by_id(session=session, id=data_model.BaseDataModelId)
        data_model_id_list.append(base_data_model.Id)

    total_query = select(func.count(ValueSet.Id)).where(
        ValueSet.DataModelId.in_(data_model_id_list), ValueSet.Deleted == False
    )
    total_result = await session.execute(total_query)
    total_count = total_result.scalar()

    if pagination:
        query = (
            select(ValueSet)
            .where(ValueSet.DataModelId.in_(data_model_id_list), ValueSet.Deleted == False)
            .offset(offset)
            .limit(limit)
        )
    else:
        query = select(ValueSet).where(ValueSet.DataModelId.in_(data_model_id_list), ValueSet.Deleted == False)
    result = await session.execute(query)
    value_sets = result.scalars().all()
    # Convert the list of Attribute objects to AttributeDTO objects
    value_set_dtos = [ValueSetDTO.from_orm(value_set) for value_set in value_sets]

    return total_count, value_set_dtos


async def get_value_sets_by_data_model_id_and_attributes(
    session: AsyncSession, data_model_id: int, entity_attribute_export_list: List[EntityAttributeExportDTO]
):
    # Check for data model id and for extension
    data_model = await check_datamodel_by_id(session=session, id=data_model_id)
    data_model_id_list: List[int] = []
    data_model_id_list.append(data_model.Id)
    if data_model.Type == DataModelType.OrgLIF or data_model.Type == DataModelType.PartnerLIF:
        base_data_model = await check_datamodel_by_id(session=session, id=data_model.BaseDataModelId)
        data_model_id_list.append(base_data_model.Id)

    # For each item in entity_attribute_export_list, loop through each list of Attributes and collect all ValueSetIds
    value_set_ids = []
    for item in entity_attribute_export_list:
        for attribute in item.Attributes:
            if attribute.ValueSetId and attribute.ValueSetId not in value_set_ids:
                value_set_ids.append(attribute.ValueSetId)

    # Select all value sets where DataModelId is in data_model_id_list OR Id is in value_set_ids
    query = select(ValueSet).where(
        and_(
            or_(ValueSet.DataModelId.in_(data_model_id_list), ValueSet.Id.in_(value_set_ids)), ValueSet.Deleted == False
        )
    )

    result = await session.execute(query)
    value_sets = result.scalars().all()
    # Convert the list of Attribute objects to AttributeDTO objects
    value_set_dtos = [ValueSetDTO.from_orm(value_set) for value_set in value_sets]

    return value_set_dtos


async def get_attributes_by_value_set_id(session: AsyncSession, value_set_id: int):
    # Aliases for the models if necessary
    a = Attribute
    eaa = EntityAttributeAssociation
    dm = DataModel
    e = Entity

    value_set = await get_value_set_by_id(session=session, id=value_set_id)
    if not value_set:
        raise HTTPException(status_code=404, detail="ValueSet not found")
    if value_set.Deleted:
        raise HTTPException(status_code=404, detail=f"ValueSet with ID {value_set_id} is deleted")

    # Build the query
    query = (
        select(
            a.Id.label("attribute_id"),
            a.Name.label("attribute_name"),
            a.UniqueName.label("attribute_unique_name"),
            e.Id.label("entity_id"),
            e.Name.label("entity_name"),
            e.UniqueName.label("entity_unique_name"),
            dm.Id.label("data_model_id"),
            dm.Name.label("data_model_name"),
        )
        .join(eaa, a.Id == eaa.AttributeId)  # Join EntityAttributeAssociation on AttributeId
        .join(dm, a.DataModelId == dm.Id)  # Join DataModels on DataModelId
        .join(e, and_(e.Id == eaa.EntityId, e.DataModelId == a.DataModelId))  # Join Entities with condition
        .where(a.ValueSetId == value_set_id, a.Deleted == False)  # Where condition on ValueSetId and Deleted
    )

    # Execute the query
    result = await session.execute(query)

    # Fetch the result
    attribute_details = result.fetchall()

    # Convert each row to a dictionary if needed
    attributes = []
    for row in attribute_details:
        attributes.append(
            {
                "attribute_id": row.attribute_id,
                "attribute_name": row.attribute_name,
                "attribute_unique_name": row.attribute_unique_name,
                "entity_id": row.entity_id,
                "entity_name": row.entity_name,
                "entity_unique_name": row.entity_unique_name,
                "data_model_id": row.data_model_id,
                "data_model_name": row.data_model_name,
            }
        )

    return attributes


# async def check_datamodel_by_id(session: AsyncSession, id: int):
#     datamodel = await session.get(DataModel, id)
#     if not datamodel:
#         raise HTTPException(status_code=404, detail="DataModel not found")
#     if datamodel.Deleted:
#         raise HTTPException(status_code=404, detail=f"Data Model with ID {id} is deleted")
#     return datamodel

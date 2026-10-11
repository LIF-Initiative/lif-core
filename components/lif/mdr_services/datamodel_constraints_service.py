from fastapi import HTTPException
from lif.mdr_sql_model.core import DataModelConstraints, DatamodelElementType
from lif.mdr_dto.datamodel_constraints_dto import (
    CreateDataModelConstraintsDTO,
    DataModelConstraintsDTO,
    UpdateDataModelConstraintsDTO,
)
from lif.mdr_services.helper_service import (
    check_attribute_by_id,
    check_datamodel_by_id,
    check_entity_by_id,
    check_transformation_by_id,
    check_transformation_group_by_id,
    check_value_set_by_id,
    check_value_set_values_by_id,
)
from lif.mdr_utils.logger_config import get_logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, func


logger = get_logger(__name__)


async def create_data_model_constraint(session: AsyncSession, data: CreateDataModelConstraintsDTO):
    data_model = await check_datamodel_by_id(session=session, id=data.ForDataModelId)
    element = await check_element(session=session, element_id=data.ElementId, element_type=data.ElementType)

    constraint = DataModelConstraints(**data.dict())
    session.add(constraint)
    await session.commit()
    await session.refresh(constraint)
    return DataModelConstraintsDTO.from_orm(constraint)


async def get_data_model_constraint_by_id(session: AsyncSession, association_id: int):
    constraint = await session.get(DataModelConstraints, association_id)
    if not constraint:
        raise HTTPException(status_code=404, detail=f"DataModel constraint with ID {association_id} not found")
    if constraint.Deleted:
        raise HTTPException(status_code=404, detail=f"DataModel constraint with ID {association_id} is deleted")
    # association_dto =   EntityAssociationDTO.from_orm(association)
    return constraint


async def update_data_model_constraint(session: AsyncSession, constraint_id: int, data: UpdateDataModelConstraintsDTO):
    # Get existing association
    constraint = await get_data_model_constraint_by_id(session, constraint_id)

    for key, value in data.dict(exclude_unset=True).items():
        if key == "ParentEntityId" or key == "ChildEntityId":
            existing_entity = await check_entity_by_id(session, value)
        setattr(constraint, key, value)

    session.add(constraint)
    await session.commit()
    await session.refresh(constraint)
    return DataModelConstraintsDTO.from_orm(constraint)
    # return {"message": "Entity association updated successfully"}


async def delete_data_model_constraint(session: AsyncSession, constraint_id: int) -> dict:
    constraint = await get_data_model_constraint_by_id(session, constraint_id)
    await session.delete(constraint)
    await session.commit()
    return {"message": f"DataModel constraint with ID {constraint_id} deleted successfully"}


async def soft_delete_data_model_constraint(session: AsyncSession, constraint_id: int) -> dict:
    constraint = await get_data_model_constraint_by_id(session, constraint_id)
    constraint.Deleted = True
    session.add(constraint)
    await session.commit()
    return {"message": f"DataModel constraint with ID {constraint_id} deleted successfully"}


async def get_paginated_data_model_constraints(
    session: AsyncSession, offset: int = 0, limit: int = 10, pagination: bool = True
):
    # Step 1: Query to count total non-deleted records
    total_query = select(func.count(DataModelConstraints.Id)).where(DataModelConstraints.Deleted == False)
    total_result = await session.execute(total_query)
    total_count = total_result.scalar()

    # Step 2: Query to fetch paginated results (non-deleted records only)
    if pagination:
        query = (
            select(DataModelConstraints)
            .where(DataModelConstraints.Deleted == False)
            .order_by(DataModelConstraints.Id)
            .offset(offset)
            .limit(limit)
        )
    else:
        query = (
            select(DataModelConstraints).where(DataModelConstraints.Deleted == False).order_by(DataModelConstraints.Id)
        )
    result = await session.execute(query)
    constraints = result.scalars().all()

    # Fetch parent and child entity names and create DTOs
    constraint_dtos = []
    for constraint in constraints:
        # Create DTO using from_orm and add extra fields
        constraint_dto = DataModelConstraintsDTO.from_orm(constraint)
        element_details = await check_element(
            session=session, element_id=constraint.ElementId, element_type=constraint.ElementType
        )
        if "Name" in element_details.dict():
            constraint_dto.ElementName = element_details.Name
        constraint_dtos.append(constraint_dto)

    return total_count, constraint_dtos


async def get_data_model_constraints_by_data_model_id(
    session: AsyncSession, data_model_id: int, offset: int = 0, limit: int = 10, pagination: bool = True
):
    # Check for data model id and for extension
    data_model = await check_datamodel_by_id(session=session, id=data_model_id)
    # Step 1: Query to count total non-deleted records
    total_query = select(func.count(DataModelConstraints.Id)).where(
        DataModelConstraints.Deleted == False, DataModelConstraints.ForDataModelId == data_model_id
    )
    total_result = await session.execute(total_query)
    total_count = total_result.scalar()

    # Step 2: Query to fetch paginated results (non-deleted records only)
    if pagination:
        query = (
            select(DataModelConstraints)
            .where(DataModelConstraints.Deleted == False, DataModelConstraints.ForDataModelId == data_model_id)
            .order_by(DataModelConstraints.Id)
            .offset(offset)
            .limit(limit)
        )
    else:
        query = (
            select(DataModelConstraints)
            .where(DataModelConstraints.Deleted == False, DataModelConstraints.ForDataModelId == data_model_id)
            .order_by(DataModelConstraints.Id)
        )
    result = await session.execute(query)
    constraints = result.scalars().all()

    # Fetch parent and child entity names and create DTOs
    constraint_dtos = []
    for constraint in constraints:
        # Create DTO using from_orm and add extra fields
        constraint_dto = DataModelConstraintsDTO.from_orm(constraint)
        element_details = await check_element(
            session=session, element_id=constraint.ElementId, element_type=constraint.ElementType
        )
        if "Name" in element_details.dict():
            constraint_dto.ElementName = element_details.Name
        constraint_dtos.append(constraint_dto)

    return total_count, constraint_dtos


async def check_element(session: AsyncSession, element_id: int, element_type: DatamodelElementType):
    if element_type == DatamodelElementType.Attribute:
        return await check_attribute_by_id(session=session, id=element_id)
    if element_type == DatamodelElementType.Entity:
        return await check_entity_by_id(session=session, id=element_id)
    if element_type == DatamodelElementType.ValueSet:
        return await check_value_set_by_id(session=session, id=element_id)
    if element_type == DatamodelElementType.ValueSetValues:
        return await check_value_set_values_by_id(session=session, id=element_id)
    if element_type == DatamodelElementType.TransformationsGroup:
        return await check_transformation_group_by_id(session=session, id=element_id)
    if element_type == DatamodelElementType.Transformations:
        return await check_transformation_by_id(session=session, id=element_id)

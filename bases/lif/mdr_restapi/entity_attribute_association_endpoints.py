from typing import Any, Dict

from fastapi import APIRouter, Depends, Query, Request, Response, status
from lif.mdr_dto.entity_attribute_association_dto import (
    CreateEntityAttributeAssociationDTO,
    EntityAttributeAssociationDTO,
    UpdateEntityAttributeAssociationDTO,
)
from lif.mdr_services import entity_attribute_association_service
from lif.mdr_utils.database_setup import get_session
from lif.mdr_utils.logger_config import get_logger
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()
logger = get_logger(__name__)


# Create an entity association
@router.post("/", response_model=EntityAttributeAssociationDTO, status_code=status.HTTP_201_CREATED)
async def create_entity_attribute_association(
    data: CreateEntityAttributeAssociationDTO, response: Response, session: AsyncSession = Depends(get_session)
):
    # Call the service to create the entity association
    entity_association = await entity_attribute_association_service.create_entity_attribute_association(session, data)

    # Set the Location header with the new entity association ID
    response.headers["Location"] = f"/entity_attribute_associations/{entity_association.Id}"

    return entity_association


# Get an entity association by ID
@router.get("/{association_id}", response_model=EntityAttributeAssociationDTO)
async def get_entity_attribute_association(association_id: int, session: AsyncSession = Depends(get_session)):
    return await entity_attribute_association_service.get_entity_attribute_association_by_id(session, association_id)


# Update an entity association by ID
@router.put("/{association_id}")
async def update_entity_attribute_association(
    association_id: int, data: UpdateEntityAttributeAssociationDTO, session: AsyncSession = Depends(get_session)
):
    return await entity_attribute_association_service.update_entity_attribute_association(session, association_id, data)


# Delete an entity association by ID
@router.delete("/{association_id}")
async def delete_entity_attribute_association(association_id: int, session: AsyncSession = Depends(get_session)):
    return await entity_attribute_association_service.soft_delete_entity_attribute_association(session, association_id)


@router.get("/by_data_model_id/{data_model_id}", response_model=Dict[str, Any])
async def get_entity_associations(
    data_model_id: int,
    request: Request,
    session: AsyncSession = Depends(get_session),
    page: int = Query(1, ge=1),  # Page number, default is 1
    size: int = Query(10, ge=1),  # Page size, default is 10
    pagination: bool = True,
    check_base: bool = True,
):
    # Calculate offset
    offset = (page - 1) * size

    (
        total_count,
        entity_attribute_associations,
    ) = await entity_attribute_association_service.get_entity_attribute_associations_by_data_model_id(
        session=session, data_model_id=data_model_id, offset=offset, limit=size, pagination=pagination
    )
    if pagination:
        total_pages = (total_count + size - 1) // size
        base_url = str(request.url).split("?")[0]
        next_url = f"{base_url}?page={page + 1}&size={size}" if page < total_pages else None
        previous_url = f"{base_url}?page={page - 1}&size={size}" if page > 1 else None

        return {
            "total": total_count,
            "page": page,
            "size": size,
            "total_pages": total_pages,
            "next": next_url,
            "previous": previous_url,
            "data": entity_attribute_associations,
        }

    return {"total": total_count, "data": entity_attribute_associations}


@router.get("/by_entity_id/{entity_id}", response_model=Dict[str, Any])
async def get_entity_associations(
    entity_id: int,
    request: Request,
    session: AsyncSession = Depends(get_session),
    including_extended_by_data_model_id: int | None = None,
    page: int = Query(1, ge=1),  # Page number, default is 1
    size: int = Query(10, ge=1),  # Page size, default is 10
    pagination: bool = True,
):
    # Calculate offset
    offset = (page - 1) * size

    (
        total_count,
        entity_attribute_associations,
    ) = await entity_attribute_association_service.get_entity_attribute_associations_by_entity_id(
        session=session,
        entity_id=entity_id,
        offset=offset,
        limit=size,
        including_extended_by_data_model_id=including_extended_by_data_model_id,
        pagination=pagination,
    )
    if pagination:
        total_pages = (total_count + size - 1) // size
        base_url = str(request.url).split("?")[0]
        next_url = f"{base_url}?page={page + 1}&size={size}" if page < total_pages else None
        previous_url = f"{base_url}?page={page - 1}&size={size}" if page > 1 else None

        return {
            "total": total_count,
            "page": page,
            "size": size,
            "total_pages": total_pages,
            "next": next_url,
            "previous": previous_url,
            "data": entity_attribute_associations,
        }

    return {"total": total_count, "data": entity_attribute_associations}


@router.get("/by_attribute_id/{attribute_id}", response_model=Dict[str, Any])
async def get_entity_associations(
    attribute_id: int,
    request: Request,
    session: AsyncSession = Depends(get_session),
    including_extended_by_data_model_id: int | None = None,
    page: int = Query(1, ge=1),  # Page number, default is 1
    size: int = Query(10, ge=1),  # Page size, default is 10
    pagination: bool = True,
):
    # Calculate offset
    offset = (page - 1) * size

    (
        total_count,
        entity_attribute_associations,
    ) = await entity_attribute_association_service.get_entity_attribute_associations_by_attribute_id(
        session=session,
        attribute_id=attribute_id,
        offset=offset,
        limit=size,
        including_extended_by_data_model_id=including_extended_by_data_model_id,
        pagination=pagination,
    )
    if pagination:
        total_pages = (total_count + size - 1) // size
        base_url = str(request.url).split("?")[0]
        next_url = f"{base_url}?page={page + 1}&size={size}" if page < total_pages else None
        previous_url = f"{base_url}?page={page - 1}&size={size}" if page > 1 else None

        return {
            "total": total_count,
            "page": page,
            "size": size,
            "total_pages": total_pages,
            "next": next_url,
            "previous": previous_url,
            "data": entity_attribute_associations,
        }

    return {"total": total_count, "data": entity_attribute_associations}

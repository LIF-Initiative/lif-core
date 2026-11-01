from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from lif.mdr_dto.value_mapping_dto import (
    CreateValueSetValueMappingDTO,
    UpdateValueSetValueMappingDTO,
    ValueSetValueMappingDTO,
)
from lif.mdr_services import value_mapping_service
from lif.mdr_utils.database_setup import get_session
from lif.mdr_utils.logger_config import get_logger
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()
logger = get_logger(__name__)


@router.post("/", response_model=ValueSetValueMappingDTO, status_code=status.HTTP_201_CREATED)
async def create_value_set_value_mapping_api(
    data: CreateValueSetValueMappingDTO, response: Response, session: AsyncSession = Depends(get_session)
):
    mapping = await value_mapping_service.create_value_set_value_mapping(session, data)
    # Set the Location header with the new entity association ID
    response.headers["Location"] = f"/value_mappings/{mapping.Id}"
    return mapping


@router.get("/", response_model=Dict[str, Any])
async def get_value_mappings(
    request: Request,
    session: AsyncSession = Depends(get_session),
    page: int = Query(1, ge=1),  # Default to page 1
    size: int = Query(10, ge=1),  # Default to 10 items per page
    pagination: bool = True,
):
    # Calculate offset
    offset = (page - 1) * size

    # Call the service function to get total count and paginated results
    total_count, mappings = await value_mapping_service.get_paginated_value_mapping(session, offset, size, pagination)

    if pagination:
        # Calculate total pages
        total_pages = (total_count + size - 1) // size

        # Generate next and previous links
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
            "data": mappings,
        }

    return {"total": total_count, "data": mappings}


@router.get(
    "/by_transformation_group/{transformation_group_id}",
    response_model=List[ValueSetValueMappingDTO],
    deprecated=True,  # Value mappings are not grouped; a crosswalk is identified by its value sets (#1440)
)
async def get_value_mappings_by_transformation_group_id(
    transformation_group_id: int, session: AsyncSession = Depends(get_session)
):
    return await value_mapping_service.get_value_mappings_by_transformation_group_id(session, transformation_group_id)


@router.get("/by_value_ids/", response_model=List[ValueSetValueMappingDTO])
async def get_value_mappings_by_value_ids(
    source_value_id: int = Query(None), target_value_id: int = Query(None), session: AsyncSession = Depends(get_session)
):
    if source_value_id or target_value_id:
        return await value_mapping_service.get_value_mappings_by_value_ids(session, source_value_id, target_value_id)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one of source_value_id or target_value_id must be provided.",
        )


@router.get("/by_value_set_ids/", response_model=List[ValueSetValueMappingDTO])
async def get_value_mappings_by_value_set_ids(
    source_value_set_id: int = Query(None),
    target_value_set_id: int = Query(None),
    session: AsyncSession = Depends(get_session),
):
    if source_value_set_id or target_value_set_id:
        return await value_mapping_service.get_value_mappings_by_value_set_ids(
            session, source_value_set_id, target_value_set_id
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one of source_value_set_id or target_value_set_id must be provided.",
        )


@router.get("/{mapping_id}")
async def get_entity(mapping_id: int, session: AsyncSession = Depends(get_session)):
    entity = await value_mapping_service.get_mapping_by_id(session, mapping_id)
    return entity


@router.delete("/{mapping_id}")
async def delete_entity(mapping_id: int, session: AsyncSession = Depends(get_session)):
    return await value_mapping_service.soft_delete_mapping(session, mapping_id)


@router.put("/{mapping_id}", response_model=ValueSetValueMappingDTO)
async def update_entity(
    mapping_id: int, data: UpdateValueSetValueMappingDTO, session: AsyncSession = Depends(get_session)
):
    entity = await value_mapping_service.update_mapping(session, mapping_id, data)
    return entity

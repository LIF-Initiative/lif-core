from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query, Request, Response, status
from lif.mdr_dto.transformation_dto import (
    CreateTransformationDTO,
    CreateTransformationGroupDTO,
    CreateTransformationWithTransformationGroupDTO,
    TransformationDTO,
    TransformationGroupDTO,
    TransformationListDTO,
    UpdateTransformationDTO,
    UpdateTransformationGroupDTO,
)
from lif.mdr_services import tag_service, transformation_service
from lif.mdr_utils.database_setup import get_session
from lif.mdr_utils.logger_config import get_logger
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()
logger = get_logger(__name__)


@router.post("/transformations/", response_model=TransformationDTO, status_code=status.HTTP_201_CREATED)
async def create_transformation(
    data: CreateTransformationDTO, response: Response, session: AsyncSession = Depends(get_session)
):
    transformation = await transformation_service.create_transformation(session, data)
    # Set the Location header with the new entity association ID
    response.headers["Location"] = f"/transformation_groups/transformations/{transformation.Id}"
    return transformation


# @router.get("/", response_model=TransformationDTO)
# async def get_all_transformation(data: CreateTransformationDTO, session: AsyncSession = Depends(get_session)):
#     return await transformation_service.create_transformation(session, data)


@router.get("/transformations/", response_model=Dict[str, Any])
async def get_all_transformations(
    request: Request,
    source_data_model_id: Optional[int] = None,
    target_data_model_id: Optional[int] = None,
    page: int = Query(1, ge=1),  # Default to page 1
    size: int = Query(10, ge=1),  # Default to size 10
    session: AsyncSession = Depends(get_session),
    pagination: bool = True,
):
    # Calculate offset for pagination
    offset = (page - 1) * size

    (total_count, transformations) = await transformation_service.get_paginated_all_transformations(
        session=session,
        offset=offset,
        limit=size,
        source_data_model_id=source_data_model_id,
        target_data_model_id=target_data_model_id,
        pagination=pagination,
    )

    if pagination:
        # Calculate total pages
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
            "data": transformations,
        }

    return {"total": total_count, "data": transformations}


@router.get("/data_models/", response_model=List[Dict[str, Any]])
async def get_data_models_in_transformations(session: AsyncSession = Depends(get_session)):
    return await transformation_service.get_distinct_data_models_in_transformations(session)


@router.get("/exists/by-triplet", response_model=Dict[str, Any])
async def check_transformation_group_exists(
    sourceId: int = Query(..., alias="sourceId"),
    targetId: int = Query(..., alias="targetId"),
    version: str = Query(..., alias="version"),
    include_deleted: bool = Query(True, alias="include_deleted"),
    session: AsyncSession = Depends(get_session),
):
    """
    Returns { exists: bool, id?: number, deleted?: bool } indicating whether a group
    with the given (sourceId, targetId, version) exists. If include_deleted is true,
    soft-deleted groups are considered as existing and returned with deleted=true.
    """
    grp = await transformation_service.find_transformation_group_by_triplet(
        session=session, source_id=sourceId, target_id=targetId, group_version=version, include_deleted=include_deleted
    )
    if grp is None:
        return {"exists": False}
    return {"exists": True, "id": grp.Id, "deleted": bool(getattr(grp, "Deleted", False))}


@router.get("/source_and_target/", response_model=List[TransformationGroupDTO])
async def get_source_and_target_data_models(
    source_data_model_id: int, target_data_model_id: int, session: AsyncSession = Depends(get_session)
):
    return await transformation_service.get_transformation_group_for_source_and_target(
        session, source_data_model_id, target_data_model_id
    )


@router.get("/transformations_for_data_models/", response_model=Dict[str, Any])
async def get_paginated_transformations_for_given_source_and_target(
    request: Request,
    source_data_model_id: int,
    target_data_model_id: int,
    page: int = Query(1, ge=1),  # Default to page 1
    size: int = Query(10, ge=1),  # Default to size 10
    session: AsyncSession = Depends(get_session),
):
    # Calculate offset for pagination
    offset = (page - 1) * size

    (total_count, transformations) = await transformation_service.get_paginated_all_transformations(
        session=session,
        offset=offset,
        limit=size,
        source_data_model_id=source_data_model_id,
        target_data_model_id=target_data_model_id,
    )

    # Calculate total pages
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
        "data": transformations,
    }


@router.get("/transformations_by_path_ids/", response_model=List[TransformationDTO])
async def get_transformations_by_path_ids(
    entity_id_path: str, attribute_id: int = None, session: AsyncSession = Depends(get_session)
):
    return await transformation_service.get_transformations_by_path_ids(session, entity_id_path, attribute_id)


# @router.post("/{transformation_id}/add_transformation_attributes", response_model=Dict[str, any])
# async def add_transformation_attributes(transformation_id: int, data: List[TransformationAttributeDTO], session: AsyncSession = Depends(get_session)):
#     return await transformation_service.add_transformation_attribute(session=session,transformation_id=transformation_id,data=data)


@router.get("/transformations/{transformation_id}", response_model=TransformationDTO)
async def get_transformation_details_by_id(transformation_id: int, session: AsyncSession = Depends(get_session)):
    return await transformation_service.get_transformation_by_id(session, transformation_id)


@router.put("/transformations/{transformation_id}", response_model=TransformationDTO)
async def update_transformation(
    transformation_id: int, data: UpdateTransformationDTO, session: AsyncSession = Depends(get_session)
):
    return await transformation_service.update_transformation(session, transformation_id, data)


@router.delete("/transformations/{transformation_id}")
async def delete_transformation(transformation_id: int, session: AsyncSession = Depends(get_session)):
    return await transformation_service.soft_delete_transformation_by_id(session, transformation_id)


@router.get("/data-model/{data_model_id}", response_model=TransformationListDTO)
async def get_transformations_by_data_model_id(data_model_id: int, session: AsyncSession = Depends(get_session)):
    return await transformation_service.get_transformations_by_data_model_id(session, data_model_id)


@router.get("/", response_model=Dict[str, Any])
async def get_all_transformation_groups(
    request: Request,
    source_data_model_id: Optional[int] = None,
    target_data_model_id: Optional[int] = None,
    page: int = Query(1, ge=1),  # Default to page 1
    size: int = Query(10, ge=1),  # Default to size 10
    session: AsyncSession = Depends(get_session),
    pagination: bool = True,
):
    # Calculate offset for pagination
    offset = (page - 1) * size

    (total_count, transformations) = await transformation_service.get_paginated_transformations_groups(
        session=session,
        offset=offset,
        limit=size,
        source_data_model_id=source_data_model_id,
        target_data_model_id=target_data_model_id,
        pagination=pagination,
    )

    if pagination:
        # Calculate total pages
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
            "data": transformations,
        }

    return {"total": total_count, "data": transformations}


@router.get("/{transformation_group_id}", response_model=Dict[str, Any])
async def get_all_transformations_for_a_group(
    request: Request,
    transformation_group_id: int,
    page: int = Query(1, ge=1),  # Default to page 1
    size: int = Query(10, ge=1),  # Default to size 10
    session: AsyncSession = Depends(get_session),
    pagination: bool = True,
):
    # Calculate offset for pagination
    offset = (page - 1) * size

    (total_count, transformations) = await transformation_service.get_paginated_transformations_for_a_group(
        session=session, group_id=transformation_group_id, offset=offset, limit=size, pagination=pagination
    )

    if pagination:
        # Calculate total pages
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
            "data": transformations,
        }

    return {"total": total_count, "data": transformations}


@router.get("/transformations_by_attribute_id/{attribute_id}", response_model=Dict[str, Any])
async def get_all_transformations_for_an_attribute(
    request: Request,
    attribute_id: int,
    attribute_as_source: bool,
    source_data_model_id: int = None,
    target_data_model_id: int = None,
    page: int = Query(1, ge=1),  # Default to page 1
    size: int = Query(10, ge=1),  # Default to size 10
    session: AsyncSession = Depends(get_session),
    pagination: bool = True,
):
    # Calculate offset for pagination
    offset = (page - 1) * size

    (total_count, transformations) = await transformation_service.get_paginated_all_transformations_for_an_attribute(
        session=session,
        attribute_id=attribute_id,
        attribute_as_source=attribute_as_source,
        offset=offset,
        limit=size,
        source_data_model_id=source_data_model_id,
        target_data_model_id=target_data_model_id,
        pagination=pagination,
    )

    if pagination:
        # Calculate total pages
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
            "data": transformations,
        }

    return {"total": total_count, "data": transformations}


@router.post("/", response_model=TransformationGroupDTO, status_code=status.HTTP_201_CREATED)
async def create_transformation_group_with_transformations(
    data: CreateTransformationGroupDTO, response: Response, session: AsyncSession = Depends(get_session)
):
    transformation_group = await transformation_service.create_transformation_group(session, data)
    # Set the Location header with the new entity association ID
    response.headers["Location"] = f"/transformation_groups/{transformation_group.Id}"
    return transformation_group


@router.post(
    "/add_transformation/{transformation_group_id}",
    response_model=TransformationGroupDTO,
    status_code=status.HTTP_201_CREATED,
)
async def create_transformation_group_with_transformations(
    data: List[CreateTransformationWithTransformationGroupDTO],
    response: Response,
    transformation_group_id: int,
    session: AsyncSession = Depends(get_session),
):
    transformation_group = await transformation_service.create_multiple_transformations_for_a_group(
        session, transformation_group_id, data
    )
    return transformation_group


@router.put("/{transformation_group_id}", response_model=TransformationGroupDTO)
async def update_transformation(
    transformation_group_id: int, data: UpdateTransformationGroupDTO, session: AsyncSession = Depends(get_session)
):
    return await transformation_service.update_transformation_group(session, transformation_group_id, data)


@router.delete("/{transformation_group_id}")
async def delete_transformation(transformation_group_id: int, session: AsyncSession = Depends(get_session)):
    return await transformation_service.soft_delete_transformation_group(session, transformation_group_id)


@router.post("/tags/{transformation_group_id}", status_code=status.HTTP_201_CREATED)
async def add_tags_for_transformation_group(
    transformation_group_id: int, tags: List[str] = Query(...), session: AsyncSession = Depends(get_session)
):
    return await tag_service.add_tags(
        session=session,
        id=transformation_group_id,
        tags=tags,
        element_type=tag_service.TagElementType.TransformationGroup,
    )


@router.delete("/tags/{transformation_group_id}")
async def delete_tags_for_transformation_group(
    transformation_group_id: int, tags: List[str] = Query(...), session: AsyncSession = Depends(get_session)
):
    return await tag_service.delete_tags(
        session=session,
        id=transformation_group_id,
        tags=tags,
        element_type=tag_service.TagElementType.TransformationGroup,
    )


@router.get("/tags/{transformation_group_id}")
async def get_tags_for_transformation_group(transformation_group_id: int, session: AsyncSession = Depends(get_session)):
    return await tag_service.get_tags(
        session=session, id=transformation_group_id, element_type=tag_service.TagElementType.TransformationGroup
    )

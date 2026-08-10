from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from lif.mdr_dto.entity_association_dto import (
    CreateEntityAssociationDTO,
    EntityAssociationDTO,
    UpdateEntityAssociationDTO,
)
from lif.mdr_services import entity_association_service
from lif.mdr_utils.database_setup import get_session
from lif.mdr_utils.logger_config import get_logger
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()
logger = get_logger(__name__)


# Create an entity association
@router.post("/", response_model=EntityAssociationDTO, status_code=status.HTTP_201_CREATED)
async def create_association(
    dto: CreateEntityAssociationDTO, response: Response, session: AsyncSession = Depends(get_session)
):
    # Call the service to create the entity association
    entity_association = await entity_association_service.create_entity_association(session, dto)

    # Set the Location header with the new entity association ID
    response.headers["Location"] = f"/entity_associations/{entity_association.Id}"

    return entity_association


# Get an entity association by ID
@router.get("/{association_id}", response_model=EntityAssociationDTO)
async def get_association(association_id: int, session: AsyncSession = Depends(get_session)):
    return await entity_association_service.get_entity_association_by_id(session, association_id)


# Update an entity association by ID
@router.put("/{association_id}")
async def update_association(
    association_id: int, dto: UpdateEntityAssociationDTO, session: AsyncSession = Depends(get_session)
):
    return await entity_association_service.update_entity_association(session, association_id, dto)


# Delete an entity association by ID
@router.delete("/{association_id}")
async def delete_association(association_id: int, session: AsyncSession = Depends(get_session)):
    return await entity_association_service.soft_delete_entity_association(session, association_id)


@router.get("/by_data_model_id/{data_model_id}", response_model=List[EntityAssociationDTO])
async def get_entity_associations(
    data_model_id: int,
    session: AsyncSession = Depends(get_session),
    allow_empty: bool = Query(False, description="Return an empty list instead of 404 when no associations are found."),
):
    entity_associations = await entity_association_service.get_entity_associations_by_data_model_id(
        session, data_model_id
    )

    if not entity_associations and not allow_empty:
        raise HTTPException(status_code=404, detail=f"No entity associations found for data model ID {data_model_id}")

    return entity_associations


@router.get("/by_parent_entity_id/{parent_entity_id}", response_model=List[EntityAssociationDTO])
async def get_entity_associations_by_parent(
    parent_entity_id: int,
    session: AsyncSession = Depends(get_session),
    including_extended_by_data_model_id: int | None = None,
    allow_empty: bool = Query(False, description="Return an empty list instead of 404 when no associations are found."),
):
    entity_associations = await entity_association_service.get_entity_associations_by_parent_entity_id(
        session, parent_entity_id, including_extended_by_data_model_id
    )

    if not entity_associations and not allow_empty:
        raise HTTPException(
            status_code=404, detail=f"No entity associations found for parent entity ID {parent_entity_id}"
        )

    return entity_associations

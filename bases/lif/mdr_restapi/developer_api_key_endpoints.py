"""Developer API key endpoints (#1033).

Cognito-authed CRUD for a user's personal API keys (used by downstream apps against the LDE
/exports API). Keys are scoped to the caller's Cognito `sub` (ownership) and their selected
workspace (the tenant schema is already set on the request via search_path by the auth
middleware / get_session, so no explicit tenant handling is needed here).
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request, status
from lif.mdr_dto.developer_api_key_dto import CreatedDeveloperApiKeyDTO, CreateDeveloperApiKeyDTO, DeveloperApiKeyDTO
from lif.mdr_services import developer_api_key_service
from lif.mdr_utils.database_setup import get_session
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


def _require_owner_sub(request: Request) -> str:
    """Return the caller's Cognito `sub` (the key owner).

    Rejects service-principal (API-key) callers — they have no Cognito identity, so they can't
    own personal keys.
    """
    sub = getattr(request.state, "cognito_sub", None)
    if not sub:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Requires a signed-in Cognito user")
    return sub


@router.post("/", response_model=CreatedDeveloperApiKeyDTO, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    data: CreateDeveloperApiKeyDTO, request: Request, session: AsyncSession = Depends(get_session)
):
    owner_sub = _require_owner_sub(request)
    return await developer_api_key_service.create_developer_api_key(session, owner_sub, data)


@router.get("/", response_model=List[DeveloperApiKeyDTO])
async def list_api_keys(request: Request, session: AsyncSession = Depends(get_session)):
    owner_sub = _require_owner_sub(request)
    return await developer_api_key_service.list_developer_api_keys(session, owner_sub)


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(key_id: int, request: Request, session: AsyncSession = Depends(get_session)):
    owner_sub = _require_owner_sub(request)
    await developer_api_key_service.revoke_developer_api_key(session, owner_sub, key_id)

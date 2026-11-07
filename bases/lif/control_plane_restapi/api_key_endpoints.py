"""Developer API key endpoints of the control plane (#1182, ADR 0008).

Cognito users issue, list and revoke their own keys. The owner is the token's `sub`. The workspace
is named in the request (``?workspace=``), because the control plane can't read MDR's signed
workspace cookie, and is checked against the token's ``cognito:groups`` with the same rule MDR uses.
Listing is per workspace, and revoking needs ownership only (ADR 0008 decision 5).
"""

from typing import AsyncIterator, List

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from lif import developer_keys
from lif.developer_keys import CreatedDeveloperApiKeyDTO, CreateDeveloperApiKeyDTO, DeveloperApiKeyDTO
from lif.tenant_routing import tenant_schema_for_group

router = APIRouter(prefix="/api-keys")


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.sessions() as session:
        yield session


def _require_owner_sub(request: Request) -> str:
    """The caller's Cognito `sub`. Only signed-in Cognito users own keys (ADR 0008 decision 1)."""
    if getattr(request.state, "auth_method", None) != "cognito":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Requires a signed-in Cognito user")
    return request.state.principal


def _require_member(request: Request, workspace: str) -> None:
    """403 unless one of the caller's groups maps to ``workspace`` (ADR 0008 decision 4)."""
    groups = request.state.claims.get("cognito:groups") or []
    if not any(tenant_schema_for_group(group) == workspace for group in groups):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a member of this workspace")


@router.post("/", response_model=CreatedDeveloperApiKeyDTO, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    data: CreateDeveloperApiKeyDTO,
    request: Request,
    workspace: str = Query(min_length=1),
    session: AsyncSession = Depends(get_session),
):
    owner_sub = _require_owner_sub(request)
    _require_member(request, workspace)
    return await developer_keys.create_workspace_developer_api_key(session, workspace, owner_sub, data)


@router.get("/", response_model=List[DeveloperApiKeyDTO])
async def list_api_keys(
    request: Request, workspace: str = Query(min_length=1), session: AsyncSession = Depends(get_session)
):
    owner_sub = _require_owner_sub(request)
    _require_member(request, workspace)
    return await developer_keys.list_workspace_developer_api_keys(session, workspace, owner_sub)


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(key_id: int, request: Request, session: AsyncSession = Depends(get_session)):
    owner_sub = _require_owner_sub(request)
    await developer_keys.revoke_workspace_developer_api_key(session, owner_sub, key_id)

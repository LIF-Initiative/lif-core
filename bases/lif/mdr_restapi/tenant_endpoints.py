"""Tenant lifecycle endpoints for MDR self-serve (issues #883, #884).

- POST /tenants/provision (#883 PR 4a): creates a new tenant schema for a
  Cognito group. Called by the post-confirmation Lambda; service-key auth.
- GET  /tenants/mine     (#884 Phase 3 PR 1): lists workspaces accessible
  to the calling user. User-auth only.
- POST /tenants/select   (#884 Phase 3 PR 1): records the user's chosen
  workspace via signed cookie so subsequent requests route to that tenant.
  User-auth only.

Other lifecycle operations (reset, delete, invite/accept) live in later
PRs of the #884 split.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from lif.mdr_auth.workspace_cookie import COOKIE_NAME, DEFAULT_MAX_AGE_SECONDS, encode_workspace_cookie
from lif.mdr_services.tenant_service import InvalidGroupNameError, TenantAlreadyExistsError, provision_tenant
from lif.mdr_services.workspace_service import (
    WorkspaceItem,
    find_workspace,
    list_workspaces_for_groups,
    to_workspace_item,
)
from lif.mdr_utils.config import get_settings
from lif.mdr_utils.database_setup import get_session
from lif.mdr_utils.logger_config import get_logger
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()
logger = get_logger(__name__)
settings = get_settings()


# --- Request/response models ---


class ProvisionTenantRequest(BaseModel):
    # 128 matches Cognito's own GroupName limit — anything longer than that
    # couldn't have come from a real cognito:groups claim, so reject early.
    group_name: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="Cognito group name (server sanitizes it into a tenant schema identifier)",
    )


class ProvisionTenantResponse(BaseModel):
    tenant_schema: str
    created: bool


# ``WorkspaceItem`` (the per-workspace payload) lives in the workspace_service
# component since it's a domain DTO; the envelopes below are endpoint-layer
# wrappers.
class ListMyWorkspacesResponse(BaseModel):
    workspaces: list[WorkspaceItem]


class SelectWorkspaceRequest(BaseModel):
    group: str = Field(..., min_length=1, max_length=128, description="Cognito group name to switch to")


class SelectWorkspaceResponse(BaseModel):
    group: str
    tenant_schema: str


# --- Auth dependencies ---


async def require_service_principal(request: Request) -> str:
    """Dependency: 403 unless the request authenticated via an X-API-Key service credential.

    Tenant lifecycle is a privileged operation — only internal services (the
    post-confirmation Lambda, ops scripts) should call it. End users with a
    Cognito JWT are rejected even if they're authenticated.
    """
    principal = getattr(request.state, "principal", None)
    if not (isinstance(principal, str) and principal.startswith("service:")):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Service principal required")
    return principal


async def require_user_principal(request: Request) -> str:
    """Dependency: 403 unless the request authenticated as a user (not a service).

    Workspace listing/selection is a per-user concept; service principals
    have no per-user workspace — they always route to the configured
    service schema. Reject them rather than returning a confusing empty
    response.
    """
    principal = getattr(request.state, "principal", None)
    if not isinstance(principal, str):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    if principal.startswith("service:"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User principal required")
    return principal


# --- Endpoints ---


@router.post(
    "/provision",
    response_model=ProvisionTenantResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        200: {"model": ProvisionTenantResponse, "description": "Schema already existed (idempotent)"},
        400: {"description": "Group name is invalid or sanitizes to empty"},
        403: {"description": "Not authenticated as a service"},
    },
)
async def provision_tenant_endpoint(
    body: ProvisionTenantRequest,
    response: Response,
    _principal: str = Depends(require_service_principal),
    session: AsyncSession = Depends(get_session),
) -> ProvisionTenantResponse:
    """Provision a tenant schema for a Cognito group.

    Clones DDL + data + FKs + sequences from public into
    tenant_{sanitized-group} via the Flyway-installed clone_lif_schema
    function. Idempotent on re-invocation: returns 200 (not 409) when the
    schema already exists so the post-confirmation Lambda can safely retry
    without tripping Cognito error handling.
    """
    try:
        tenant_schema = await provision_tenant(session, body.group_name)
    except InvalidGroupNameError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except TenantAlreadyExistsError as e:
        logger.info("Tenant schema %s already exists; returning 200 for idempotency", e.tenant_schema)
        response.status_code = status.HTTP_200_OK
        return ProvisionTenantResponse(tenant_schema=e.tenant_schema, created=False)

    logger.info("Provisioned tenant schema %s for group %r", tenant_schema, body.group_name)
    return ProvisionTenantResponse(tenant_schema=tenant_schema, created=True)


@router.get(
    "/mine",
    response_model=ListMyWorkspacesResponse,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Service principals have no per-user workspaces"},
    },
)
async def list_my_workspaces(
    request: Request, _principal: str = Depends(require_user_principal)
) -> ListMyWorkspacesResponse:
    """List the workspaces the calling user can access.

    Sourced from the JWT ``cognito:groups`` claim that the auth middleware
    already extracted onto ``request.state``. Cognito users with no group
    receive an empty list (frontend should show a "no workspaces yet"
    state); HS256 callers (legacy local JWT path, no group concept) also
    receive an empty list.
    """
    cognito_groups: list[str] = getattr(request.state, "cognito_groups", [])
    workspaces = list_workspaces_for_groups(cognito_groups)
    return ListMyWorkspacesResponse(workspaces=[to_workspace_item(w) for w in workspaces])


@router.post(
    "/select",
    response_model=SelectWorkspaceResponse,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Service principals can't select a workspace"},
        404: {"description": "Group is not in the user's Cognito groups"},
    },
)
async def select_workspace(
    body: SelectWorkspaceRequest,
    request: Request,
    response: Response,
    _principal: str = Depends(require_user_principal),
) -> SelectWorkspaceResponse:
    """Record the caller's chosen workspace via signed cookie.

    The middleware reads this cookie on subsequent requests to set the
    tenant schema. The cookie is HMAC-signed and re-validated against the
    user's ``cognito:groups`` on every request, so a stolen or stale
    cookie can't grant access to a workspace the user no longer belongs
    to. Returns 404 (not 403) when the group isn't in the user's groups —
    the user's groups are the ground truth, and a non-member's perspective
    is "that workspace doesn't exist for me."
    """
    cognito_groups: list[str] = getattr(request.state, "cognito_groups", [])
    workspace = find_workspace(cognito_groups, body.group)
    if workspace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Group {body.group!r} is not one of your workspaces"
        )

    cookie_value = encode_workspace_cookie(workspace.group, secret=settings.mdr__auth__jwt_secret_key)
    # SameSite=Lax (not Strict): the future invite-email flow needs the cookie
    # to survive a top-level cross-site navigation when a recipient clicks an
    # emailed invite URL. Strict would drop the cookie on that first GET and
    # send the user back to the workspace re-select screen. Lax still blocks
    # the cookie on cross-site POSTs and iframes, which is the threat that
    # matters; CSRF on /tenants/select itself is mitigated separately by the
    # Authorization Bearer JWT (cookies can't supply that).
    response.set_cookie(
        key=COOKIE_NAME,
        value=cookie_value,
        max_age=DEFAULT_MAX_AGE_SECONDS,
        httponly=True,
        secure=settings.mdr__cookie__secure,
        samesite="lax",
        path="/",
    )
    logger.info("User %r selected workspace %r → %s", request.state.principal, workspace.group, workspace.tenant_schema)
    return SelectWorkspaceResponse(group=workspace.group, tenant_schema=workspace.tenant_schema)

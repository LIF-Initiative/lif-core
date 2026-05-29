"""Tenant lifecycle endpoints for MDR self-serve (issues #883, #884).

- POST /tenants/provision     (#883 PR 4a):       creates a new tenant schema for a
  Cognito group. Called by the post-confirmation Lambda; service-key auth.
- GET  /tenants/mine          (#884 Phase 3 PR 1): lists workspaces accessible
  to the calling user. User-auth only.
- POST /tenants/select        (#884 Phase 3 PR 1): records the user's chosen
  workspace via signed cookie so subsequent requests route to that tenant.
  User-auth only.
- POST /tenants/invite        (#884 Phase 3 PR 2): generates a signed invite
  token for a group the caller belongs to. User-auth only.
- POST /tenants/invite/accept (#884 Phase 3 PR 2): adds the caller to the
  group named in a valid invite token via Cognito Admin API. User-auth only.
- POST /tenants/reset         (#884 Phase 3 PR 3): drops + re-clones the
  caller's tenant schema back to seed state ("Start Over"). User-auth only.

Admin endpoints live in later PRs of the #884 split.
"""

import time

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from lif.mdr_auth.cognito_admin import (
    CognitoAdminConfig,
    CognitoAdminError,
    GroupNotFoundError,
    UserNotFoundError,
    add_user_to_group,
)
from lif.mdr_auth.invite_token import decode_invite_token, encode_invite_token
from lif.mdr_auth.workspace_cookie import COOKIE_NAME, DEFAULT_MAX_AGE_SECONDS, encode_workspace_cookie
from lif.mdr_services.tenant_service import (
    InvalidGroupNameError,
    TenantAlreadyExistsError,
    provision_tenant,
    reset_tenant,
)
from lif.mdr_services.workspace_service import (
    WorkspaceItem,
    find_workspace,
    list_workspaces_for_groups,
    to_workspace_item,
)
from lif.tenant_routing import tenant_schema_for_group
from lif.mdr_utils.config import get_settings
from lif.mdr_utils.database_setup import get_session
from lif.mdr_utils.logger_config import get_logger
from pydantic import BaseModel, Field
from sqlalchemy.exc import DBAPIError
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
    # display_name mirrors the friendly label from /tenants/mine so the
    # frontend can update its workspace indicator immediately on select
    # without a follow-up listing round-trip (issue #943).
    display_name: str


class CreateInviteRequest(BaseModel):
    group: str = Field(..., min_length=1, max_length=128, description="Group to invite the recipient into")


class CreateInviteResponse(BaseModel):
    token: str
    group: str
    expires_at: int


class AcceptInviteRequest(BaseModel):
    # Real tokens are well under 2 KB (base64url payload + signature); 4096
    # leaves headroom while rejecting clearly-bogus inputs before they reach
    # HMAC verification (called up to twice on the expired-token branch).
    token: str = Field(..., min_length=1, max_length=4096, description="Invite token from POST /tenants/invite")


class AcceptInviteResponse(BaseModel):
    group: str
    tenant_schema: str
    inviter_sub: str


class ResetWorkspaceRequest(BaseModel):
    group: str = Field(..., min_length=1, max_length=128, description="Cognito group whose workspace to reset")


class ResetWorkspaceResponse(BaseModel):
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


def _require_cognito_sub(request: Request) -> str:
    """Pull the inviter's Cognito ``sub`` off ``request.state``.

    The auth middleware stamps the decoded payload's ``sub`` (or email)
    into ``request.state.principal``; for Cognito callers the sub is also
    set on ``request.state.cognito_sub`` in PR 2 (this PR). Endpoints that
    need the stable user identifier should call this helper rather than
    parsing ``principal``, which may be an email string.
    """
    sub = getattr(request.state, "cognito_sub", None)
    if not isinstance(sub, str) or not sub:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invite operations require a Cognito-issued JWT (no Cognito sub on request)",
        )
    return sub


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
    cognito_sub: str | None = getattr(request.state, "cognito_sub", None)
    principal: str | None = getattr(request.state, "principal", None)
    workspaces = list_workspaces_for_groups(cognito_groups)
    return ListMyWorkspacesResponse(
        workspaces=[to_workspace_item(w, cognito_sub=cognito_sub, principal=principal) for w in workspaces]
    )


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
    cognito_sub: str | None = getattr(request.state, "cognito_sub", None)
    principal: str | None = getattr(request.state, "principal", None)
    item = to_workspace_item(workspace, cognito_sub=cognito_sub, principal=principal)
    return SelectWorkspaceResponse(group=item.group, tenant_schema=item.tenant_schema, display_name=item.display_name)


@router.post(
    "/invite",
    response_model=CreateInviteResponse,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Service principals can't create invites"},
        404: {"description": "Group is not in the user's Cognito groups"},
    },
)
async def create_invite(
    body: CreateInviteRequest, request: Request, _principal: str = Depends(require_user_principal)
) -> CreateInviteResponse:
    """Generate a signed invite token for a group the caller belongs to.

    The token is opaque, time-limited, and contains the target group and
    inviter sub. There is no server-side store of issued tokens: the
    inviter shares the resulting token (typically embedded in a URL),
    and any registered Cognito user who presents it within the expiry
    window can join the group. Single-use enforcement is deferred to a
    later PR if reuse abuse appears in practice.
    """
    cognito_groups: list[str] = getattr(request.state, "cognito_groups", [])
    # `find_workspace` (not raw `in cognito_groups`) so we also reject groups
    # whose names sanitize to no tenant schema (e.g. "---", "123") — those
    # would mint a token guaranteed to fail at /invite/accept time.
    if find_workspace(cognito_groups, body.group) is None:
        # Can't invite to a group you don't belong to. 404 (not 403) for
        # the same reason as /tenants/select: from the caller's perspective
        # this group isn't theirs to operate on.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Group {body.group!r} is not one of your workspaces"
        )

    inviter_sub = _require_cognito_sub(request)
    # Compute expires_at locally — same formula encode_invite_token uses
    # internally, so we don't have to decode the just-produced token just to
    # surface the timestamp. Avoids using `assert` as a runtime guard (which
    # would be stripped under `python -O`) and drops a redundant HMAC round-trip.
    expires_at = int(time.time()) + settings.mdr__invite__token_max_age_seconds
    token = encode_invite_token(
        body.group,
        inviter_sub,
        secret=settings.mdr__auth__jwt_secret_key,
        max_age_seconds=settings.mdr__invite__token_max_age_seconds,
    )
    logger.info("User %r created invite for group %r (expires %d)", inviter_sub, body.group, expires_at)
    return CreateInviteResponse(token=token, group=body.group, expires_at=expires_at)


@router.post(
    "/invite/accept",
    response_model=AcceptInviteResponse,
    responses={
        400: {"description": "Token is malformed or signature is invalid"},
        401: {"description": "Not authenticated"},
        403: {"description": "Service principals can't accept invites"},
        410: {"description": "Token has expired"},
        500: {"description": "Cognito AdminAddUserToGroup failed"},
    },
)
async def accept_invite(
    body: AcceptInviteRequest, request: Request, _principal: str = Depends(require_user_principal)
) -> AcceptInviteResponse:
    """Add the calling user to the group named in a valid invite token.

    On success, the user's *next* Cognito JWT will include the new group;
    the current JWT is not retroactively updated. Frontends should
    prompt a token refresh (or full logout/login) before expecting the
    new workspace to appear in GET /tenants/mine.

    Returns 400 for malformed/forged tokens and 410 (Gone) specifically
    for expired tokens so the frontend can show a "ask for a fresh invite"
    message rather than a generic error.
    """
    # Decode once with now=0 to bypass the expiry check; we want to know
    # whether the token is *structurally* valid + correctly signed first,
    # then branch on expiry separately. Two reasons to keep the 400 vs 410
    # distinction: (a) the frontend can show "ask for a fresh invite" on
    # 410 instead of a generic "invalid" error, (b) it's cheap and the
    # extra decode-with-real-now would log a duplicate warning at the
    # decoder layer.
    decoded = decode_invite_token(body.token, secret=settings.mdr__auth__jwt_secret_key, now=0)
    if decoded is None:
        # Truly invalid: malformed, bad signature, or non-conforming payload.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invite token is invalid")
    if decoded.expires_at <= int(time.time()):
        # Was a real token, but past its TTL.
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Invite token has expired")

    target_schema = tenant_schema_for_group(decoded.group)
    if target_schema is None:
        # The inviter's group sanitizes to empty — would have been rejected
        # by /tenants/invite, so this is either a forged token or a Cognito
        # group rename. Treat as invalid.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invite group is not provisionable")

    acceptor_sub = _require_cognito_sub(request)
    config = CognitoAdminConfig(
        user_pool_id=settings.mdr__auth__cognito_user_pool_id, region=settings.mdr__auth__cognito_region
    )
    try:
        add_user_to_group(config, username=acceptor_sub, group_name=decoded.group)
    except (UserNotFoundError, GroupNotFoundError) as e:
        # If our own ``sub`` isn't in the pool (UserNotFound), something's
        # deeply wrong — surface as 500. If the *group* isn't in the pool
        # (GroupNotFound), the inviter's group was deleted after the invite
        # was issued; same story for the recipient. Both are 500-class.
        # Log full detail server-side (includes pool ID and sub); return a
        # generic message so we don't leak that detail to the client.
        logger.exception("Invite accept failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Invite accept failed; contact support if this persists",
        ) from e
    except CognitoAdminError as e:
        # Wraps boto3 ClientError + BotoCoreError. The exception message can
        # carry transport-layer detail (region, IAM error codes, internal IDs)
        # we don't want in client-visible responses. Log server-side; return
        # generic.
        logger.exception("Invite accept failed: cognito admin error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Invite accept failed; please retry or contact support if this persists",
        ) from e

    logger.info(
        "User %r accepted invite from %r to group %r (schema %s)",
        acceptor_sub,
        decoded.inviter_sub,
        decoded.group,
        target_schema,
    )
    return AcceptInviteResponse(group=decoded.group, tenant_schema=target_schema, inviter_sub=decoded.inviter_sub)


@router.post(
    "/reset",
    response_model=ResetWorkspaceResponse,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "User principal required"},
        404: {"description": "Group is not in the user's Cognito groups"},
        500: {"description": "Database error during DROP or clone; transaction rolled back"},
    },
)
async def reset_workspace(
    body: ResetWorkspaceRequest,
    request: Request,
    _principal: str = Depends(require_user_principal),
    session: AsyncSession = Depends(get_session),
) -> ResetWorkspaceResponse:
    """Reset the caller's tenant schema back to seed state ("Start Over").

    Drops every table in ``tenant_{group}`` and re-clones from public. All
    data the user added (or other group members added) is irrecoverably
    gone — the frontend is responsible for the "are you sure?" confirm.
    Auth model mirrors /tenants/select: the request body names the group
    and we re-check against the JWT's ``cognito:groups``; a 404 (not 403)
    signals that, from the caller's perspective, the group isn't theirs
    to operate on.

    Idempotent on the missing-schema branch — if the user's schema was
    never provisioned (or was already dropped) the helper just clones
    fresh and returns success. Same outcome a fresh registration would
    produce.
    """
    cognito_groups: list[str] = getattr(request.state, "cognito_groups", [])
    workspace = find_workspace(cognito_groups, body.group)
    if workspace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Group {body.group!r} is not one of your workspaces"
        )

    try:
        tenant_schema = await reset_tenant(session, workspace.group)
    except InvalidGroupNameError:
        # Shouldn't reach here — find_workspace already filtered groups whose
        # names don't sanitize to a tenant schema. Belt-and-suspenders so a
        # future regression in find_workspace doesn't 500 the user. Don't echo
        # the exception message — it carries the raw group string we sanitized.
        logger.exception("Unexpected InvalidGroupNameError on reset for group=%r", workspace.group)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not reset workspace")
    except DBAPIError:
        # DROP or clone failed at the DB layer (transient PG outage, clone
        # function bug, etc.). The surrounding transaction is rolled back by
        # SQLAlchemy / asyncpg so prior tenant data is preserved; the user
        # just sees a generic 500. Log full SQLSTATE detail server-side via
        # logger.exception — don't echo the SDK exception to the client.
        logger.exception("Database error while resetting workspace %r", workspace.group)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not reset workspace; please retry or contact support if this persists",
        )

    logger.info("User %r reset workspace %r -> %s", request.state.principal, workspace.group, tenant_schema)
    return ResetWorkspaceResponse(group=workspace.group, tenant_schema=tenant_schema)

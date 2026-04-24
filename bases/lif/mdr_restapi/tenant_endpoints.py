"""Tenant lifecycle endpoints for MDR self-serve (issue #883).

Currently exposes POST /tenants/provision, called by the Cognito
post-confirmation Lambda (PR 4b) after a new user registers. Other
lifecycle operations (reset, delete, status) live in the proposal's
Phase 3 scope and are not yet implemented.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from lif.mdr_services.tenant_service import InvalidGroupNameError, TenantAlreadyExistsError, provision_tenant
from lif.mdr_utils.database_setup import get_session
from lif.mdr_utils.logger_config import get_logger
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()
logger = get_logger(__name__)


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

"""Operational read-only endpoints for detecting schema drift (#1226).

Separate from the domain routers because this reports on the *database's* state
rather than on metadata, and because it is service-principal only: it exposes
schema shape, which end users have no reason to see.
"""

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, Request, status
from fastapi.exceptions import HTTPException
from lif.mdr_services import schema_drift_service
from lif.mdr_utils.database_setup import get_session
from lif.mdr_utils.logger_config import get_logger
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()
logger = get_logger(__name__)


class AppliedMigration(BaseModel):
    version: str
    description: str | None = None
    success: bool
    installed_on: str | None = None


class SchemaDrift(BaseModel):
    schema_name: str
    missing: List[str]


class SchemaStateResponse(BaseModel):
    """What the database actually has. The caller decides whether that is wrong."""

    applied_migrations: List[AppliedMigration]
    latest_version: str | None
    schemas: List[SchemaDrift]
    drifted_schema_count: int


def _highest_successful(applied: List[Dict[str, Any]]) -> str | None:
    """The highest version recorded as successfully applied.

    Not simply the newest row: `flyway_schema_history` is ordered by attempt, so a
    failed migration is the most recent entry. Reporting that as `latest_version`
    would have the script print it in its reassuring branch -- "all N repo migrations
    recorded applied (latest X)" -- naming the version that did not apply.
    """
    successful = [row["version"] for row in applied if row["success"]]
    if not successful:
        return None
    return max(successful, key=lambda v: [int(part) for part in v.split(".")])


async def require_service_principal(request: Request) -> str:
    """403 unless the caller authenticated with an X-API-Key service credential.

    Mirrors the dependency in ``tenant_endpoints``. Schema shape is operational
    detail, not tenant data, so a Cognito user is rejected even when authenticated.
    """
    principal = getattr(request.state, "principal", None)
    if not (isinstance(principal, str) and principal.startswith("service:")):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Service principal required")
    return principal


@router.get("/schema-state", response_model=SchemaStateResponse)
async def get_schema_state(
    _principal: str = Depends(require_service_principal), session: AsyncSession = Depends(get_session)
) -> SchemaStateResponse:
    """Report applied migrations and per-schema column drift against ``public``.

    Deliberately reports raw state and makes no judgement. Whether a migration is
    *missing* depends on which ``V*.sql`` files the repo carries, which the database
    does not know -- that comparison lives in ``scripts/check-migration-drift.py``.

    Both halves are needed. ``flyway_schema_history`` alone said version 1.6 /
    Success on 2026-09-17 while all 19 tenant schemas across dev and demo were
    missing the column that migration added (#1265).
    """
    applied: List[Dict[str, Any]] = await schema_drift_service.applied_migrations(session)
    schemas: List[Dict[str, Any]] = await schema_drift_service.tenant_schema_drift(session)

    drifted = [s for s in schemas if s["missing"]]
    if drifted:
        logger.warning(
            "Schema drift: %d of %d non-public schemas are missing columns public has", len(drifted), len(schemas)
        )

    return SchemaStateResponse(
        applied_migrations=[AppliedMigration(**row) for row in applied],
        latest_version=_highest_successful(applied),
        schemas=[SchemaDrift(schema_name=s["schema"], missing=s["missing"]) for s in schemas],
        drifted_schema_count=len(drifted),
    )

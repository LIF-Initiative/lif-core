"""Tenant lifecycle operations for MDR self-serve (issue #883).

Thin wrapper over the ``public.clone_lif_schema`` PL/pgSQL function
installed by Flyway V1.2. The endpoint layer calls into here; the real
work happens in the database.
"""

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from lif.mdr_auth.tenant import tenant_schema_for_group
from lif.mdr_utils.logger_config import get_logger

logger = get_logger(__name__)

# SQLSTATE raised by the clone_lif_schema function when the target schema
# exists. Also raised natively by PG on CREATE SCHEMA of a duplicate.
DUPLICATE_SCHEMA_SQLSTATE = "42P06"


class InvalidGroupNameError(ValueError):
    """Raised when a group name cannot be sanitized into a valid schema identifier."""


class TenantAlreadyExistsError(Exception):
    """Raised when the target tenant schema already exists."""

    def __init__(self, tenant_schema: str) -> None:
        self.tenant_schema = tenant_schema
        super().__init__(f"Tenant schema {tenant_schema!r} already exists")


async def provision_tenant(session: AsyncSession, group_name: str) -> str:
    """Clone the LIF schema into a fresh tenant schema for a Cognito group.

    Returns the resulting tenant schema name. Raises:
      - InvalidGroupNameError if the group sanitizes to empty
      - TenantAlreadyExistsError if the target schema already exists
    """
    target = tenant_schema_for_group(group_name)
    if target is None:
        raise InvalidGroupNameError(f"Group name {group_name!r} does not produce a valid tenant schema")

    try:
        await session.execute(text("SELECT public.clone_lif_schema(:target)"), {"target": target})
        await session.commit()
    except DBAPIError as e:
        sqlstate = getattr(getattr(e, "orig", None), "sqlstate", None) or getattr(
            getattr(e, "orig", None), "pgcode", None
        )
        if sqlstate == DUPLICATE_SCHEMA_SQLSTATE:
            raise TenantAlreadyExistsError(target) from e
        raise

    return target

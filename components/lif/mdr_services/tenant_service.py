"""Tenant lifecycle operations for MDR self-serve (issue #883).

Thin wrapper over the ``public.clone_lif_schema`` PL/pgSQL function
installed by Flyway V1.2. The endpoint layer calls into here; the real
work happens in the database.
"""

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from lif.tenant_routing import tenant_schema_for_group
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
        # SQLAlchemy wraps the driver-level exception in DBAPIError. The
        # original driver exception (asyncpg or psycopg) is on `.orig` and
        # exposes the PG SQLSTATE as either `.sqlstate` or `.pgcode`
        # depending on the driver. We check both so this works against
        # either backend.
        orig = getattr(e, "orig", None)
        sqlstate = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
        if sqlstate == DUPLICATE_SCHEMA_SQLSTATE:
            raise TenantAlreadyExistsError(target) from e
        raise

    return target


async def reset_tenant(session: AsyncSession, group_name: str) -> str:
    """Reset a tenant schema back to the LIF seed state.

    Drops the existing schema (CASCADE — all tables, data, FKs go) and
    re-clones from public in the same transaction. Idempotent: if the
    schema doesn't exist, the DROP IF EXISTS is a no-op and the clone
    just provisions it fresh.

    The endpoint layer is responsible for authorizing the caller — this
    helper assumes the caller has already been verified as a member of
    the target group. By design this is irrecoverable; there is no
    snapshot of the prior tenant state.

    Returns the resulting tenant schema name.

    Raises:
      - InvalidGroupNameError if the group sanitizes to empty.
      - sqlalchemy.exc.DBAPIError if the DROP or clone fails — the surrounding
        transaction is rolled back, so the prior tenant data is preserved.
    """
    target = tenant_schema_for_group(group_name)
    if target is None:
        # Friendly message: this exception is wrapped into the endpoint's
        # generic 400 today, but a future caller (CLI, other endpoint) may
        # surface the message directly. Match the tone the endpoint uses
        # for the same situation.
        raise InvalidGroupNameError(f"Group {group_name!r} is not a valid workspace")

    # CASCADE removes everything that depends on the schema (tables,
    # constraints, sequences, FKs into the schema). Anything outside this
    # schema is untouched. clone_lif_schema then rebuilds DDL + data from
    # public. Both run in the session's open transaction; if the clone
    # raises, the drop is rolled back and the tenant data is preserved.
    # (Verified: both psycopg and asyncpg execute DDL inside the explicit
    # transaction — no implicit commit between the two statements.)
    #
    # Identifiers can't be bound as parameters, so we interpolate `target`
    # directly. Safety: `tenant_schema_for_group` enforces the
    # `tenant_[a-z][a-z0-9_]*` shape, so there's no injection surface.
    logger.info("Resetting tenant schema %s", target)
    await session.execute(text(f'DROP SCHEMA IF EXISTS "{target}" CASCADE'))
    await session.execute(text("SELECT public.clone_lif_schema(:target)"), {"target": target})
    await session.commit()
    logger.info("Reset of tenant schema %s complete", target)
    return target

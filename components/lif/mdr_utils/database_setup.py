import psycopg2
from psycopg2 import Error
import mysql.connector
import os
import re
from typing import AsyncGenerator
from urllib.parse import urlparse, urlunparse

from fastapi import HTTPException, Request, status
from lif.mdr_utils.logger_config import get_logger

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

logger = get_logger(__name__)


def _redact_url(url: str) -> str:
    """Mask the password in a SQLAlchemy connection URL for safe logging.

    Returns the URL with the password replaced by ``***`` while preserving
    scheme, username, host, port, and database. URLs without a password
    are returned unchanged. Issue #938: the previous startup log emitted
    the full URL including the credential, exposing the dev/demo DB
    password to anyone with read access on the shared CloudWatch log
    group.

    Best-effort: this is only called for logging, so we never want it to
    raise and take down MDR startup. Any parsing surprise (urlparse on
    a malformed URL, ``parts.port`` raising on a non-integer port — which
    happens when an env var was unset and the URL contains the literal
    string ``None``) returns a sentinel so the log line still emits
    something operator-readable.
    """
    try:
        parts = urlparse(url)
        if not parts.password:
            return url
        user = parts.username or ""
        host = parts.hostname or ""
        netloc = f"{user}:***@{host}"
        if parts.port:
            netloc += f":{parts.port}"
        return urlunparse(parts._replace(netloc=netloc))
    except ValueError:
        return "<unparseable-url>"


DATABASE_URL = f"postgresql+asyncpg://{os.getenv('POSTGRESQL_USER')}:{os.getenv('POSTGRESQL_PASSWORD')}@{os.getenv('POSTGRESQL_HOST')}:{os.getenv('POSTGRESQL_PORT')}/{os.getenv('POSTGRESQL_DB')}"
logger.info("DATABASE_URL : %s", _redact_url(DATABASE_URL))
# Create an async engine
engine = create_async_engine(DATABASE_URL, echo=True)

# Create an async sessionmaker
async_session = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

# Tenant schema names reach SET search_path via string interpolation (PG does
# not accept bind parameters for SET), so they must match a strict identifier
# pattern before touching the cursor. resolve_tenant_schema produces names in
# this shape, but we re-validate here as defense in depth.
_TENANT_SCHEMA_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")


async def get_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """Yield an AsyncSession, optionally scoped to a tenant schema.

    ``request`` is auto-injected by FastAPI whenever this runs as a Depends.
    When the auth middleware has set ``request.state.tenant_schema`` (i.e.
    the tenant-routing feature flag is on and a tenant could be resolved),
    this issues ``SET search_path`` so every query in the session resolves
    against that schema. When unset — flag off or a public endpoint that
    bypassed auth — the session uses PG's default search_path and behaves
    exactly as it did before #883.

    If ``tenant_schema`` is set but does not match the identifier pattern,
    the request is failed with 500 rather than silently falling back to
    the default schema. An invalid name here means the middleware produced
    something the sanitizer never emits — treating that as "route to public"
    would either leak data across tenants or mask a resolver bug.
    """
    tenant_schema = getattr(request.state, "tenant_schema", None)
    async with async_session() as session:
        # `SET search_path` persists on the underlying pooled connection
        # for its entire lifetime. We MUST issue an explicit SET on every
        # request — including the no-tenant branch below — or a connection
        # that was checked out for tenant A and returned to the pool would
        # still have its search_path pointing at tenant A's schema when
        # the next request (which might bypass tenant routing entirely)
        # checks it back out. That's a cross-tenant data-leak risk, not
        # just a correctness annoyance.
        if tenant_schema and _TENANT_SCHEMA_RE.match(tenant_schema):
            # Fail closed if the resolved tenant schema doesn't exist (#961).
            # PG does NOT error on a missing schema in `SET search_path` — it
            # silently skips it and resolves everything against the `public`
            # fallback below, which would serve wrong/empty data instead of
            # surfacing a provisioning failure (cf. the 2026-05-26 silent
            # provision-failure). Verify existence first and deny otherwise.
            # Parameterized — never interpolate the schema into this query.
            schema_exists = await session.execute(
                text("SELECT 1 FROM information_schema.schemata WHERE schema_name = :schema"), {"schema": tenant_schema}
            )
            if schema_exists.first() is None:
                logger.error("Resolved tenant schema %r is not provisioned; denying request", tenant_schema)
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Tenant schema not provisioned"
                )
            # Include `public` as a fallback in the search_path so PG-level
            # user-defined types (e.g. `elementtype`, `datamodelelementtype`
            # enums defined in V1.1) resolve correctly. `clone_lif_schema`
            # copies tables but NOT custom types, so a tenant-scoped query
            # that casts a value to one of those enums (SQLAlchemy generates
            # `'Entity'::elementtype` etc.) would otherwise fail with
            # `UndefinedObjectError: type "elementtype" does not exist`.
            # Tables are still resolved tenant-first; public fall-through
            # only fires for objects the tenant schema doesn't contain.
            # NOTE: this means a tenant schema that EXISTS but is missing a
            # given table still falls through to public for that table — the
            # clean fix (copy PG types into tenant schemas, then drop the
            # `public` fallback) is tracked as a follow-up under #949/#961.
            await session.execute(text(f'SET search_path TO "{tenant_schema}", public'))
        elif tenant_schema:
            logger.error("Refusing to SET search_path to invalid tenant_schema %r", tenant_schema)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal tenant routing error"
            )
        else:
            # No tenant routing for this request, but still neutralize any
            # leftover search_path the pooled connection carried over from
            # a prior tenant-scoped request. Reset to PG's default so this
            # branch behaves as if it had a fresh connection.
            await session.execute(text("SET search_path TO public"))
        yield session


async def get_db_connection(db_type: str):
    # We can use
    try:
        match db_type:
            case "POSTGRESQL":
                # Connect to your PostgreSQL database
                logger.info("DB type is POSTGRESQL")
                connection = psycopg2.connect(
                    user=os.environ["POSTGRESQL_USER"],
                    password=os.environ["POSTGRESQL_PASSWORD"],
                    host=os.environ["POSTGRESQL_HOST"],
                    port=os.environ["POSTGRESQL_PORT"],
                    database=os.environ["POSTGRESQL_DB"],
                )
                logger.info("Connection Done")

            case "MYSQL":
                logger.info("DB type is MYSQL")
                connection = mysql.connector.connect(
                    host=os.environ["MYSQL_HOST"],
                    port=os.environ["MYSQL_PORT"],
                    user=os.environ["MYSQL_USER"],
                    password=os.environ["MYSQL_PASSWORD"],
                    database=os.environ["MYSQL_DB"],
                )
                logger.info("Connection Done")
            case _:
                logger.info("Specified database type is not configured : %s", db_type)
                raise Exception

        return connection
    except (Exception, Error) as error:
        logger.error("Error while connecting DB doe the DB type: %s.  Error : %s", db_type, error)
        raise

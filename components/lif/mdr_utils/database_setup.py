import psycopg2
from psycopg2 import Error
import mysql.connector
import os
import re
from typing import AsyncGenerator

from fastapi import HTTPException, Request, status
from lif.mdr_utils.logger_config import get_logger

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

logger = get_logger(__name__)


DATABASE_URL = f"postgresql+asyncpg://{os.getenv('POSTGRESQL_USER')}:{os.getenv('POSTGRESQL_PASSWORD')}@{os.getenv('POSTGRESQL_HOST')}:{os.getenv('POSTGRESQL_PORT')}/{os.getenv('POSTGRESQL_DB')}"
logger.info(f"DATABASE_URL : {DATABASE_URL}")
# Create an async engine
engine = create_async_engine(DATABASE_URL, echo=True)

# Create an async sessionmaker
async_session = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

# Tenant schema names reach SET search_path via string interpolation (PG does
# not accept bind parameters for SET), so they must match a strict identifier
# pattern before touching the cursor. resolve_tenant_schema produces names in
# this shape, but we re-validate here as defense in depth.
_TENANT_SCHEMA_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")


async def get_session(request: Request | None = None) -> AsyncGenerator[AsyncSession, None]:
    """Yield an AsyncSession, optionally scoped to a tenant schema.

    When the auth middleware has set ``request.state.tenant_schema`` (i.e.
    the tenant-routing feature flag is on and a tenant could be resolved),
    this issues ``SET search_path`` so every query in the session resolves
    against that schema. When unset — flag off, public endpoint, or no
    request bound (background jobs, some tests) — the session uses PG's
    default search_path and behaves exactly as it did before #883.

    If ``tenant_schema`` is set but does not match the identifier pattern,
    the request is failed with 500 rather than silently falling back to
    the default schema. An invalid name here means the middleware produced
    something the sanitizer never emits — treating that as "route to public"
    would either leak data across tenants or mask a resolver bug.
    """
    tenant_schema = getattr(request.state, "tenant_schema", None) if request is not None else None
    async with async_session() as session:
        if tenant_schema and _TENANT_SCHEMA_RE.match(tenant_schema):
            await session.execute(text(f'SET search_path TO "{tenant_schema}"'))
        elif tenant_schema:
            logger.error("Refusing to SET search_path to invalid tenant_schema %r", tenant_schema)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal tenant routing error"
            )
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

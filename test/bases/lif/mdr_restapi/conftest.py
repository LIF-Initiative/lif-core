import os
import subprocess
from pathlib import Path
from urllib.parse import urlparse

import pytest
import testing.postgresql
from httpx import ASGITransport, AsyncClient
from lif.translator_restapi import core as translator_core
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

#
# Setup to test the end-to-end API with a real postgreSQL database
#


@pytest.fixture
def mdr_api_headers():
    """Standard headers for MDR API requests."""
    return {"X-API-Key": "changeme1"}


@pytest.fixture(scope="session")
def postgres_server():
    """Start a PostgreSQL server for testing (no Docker required).

    Requires PostgreSQL to be installed locally (e.g., `brew install postgresql` on macOS).
    """

    # Get the absolute path to the SQL file that is used to initialize the database
    backup_sql_path = Path(__file__).parent.parent.parent.parent.parent / "projects/lif_mdr_database/backup.sql"

    try:
        postgresql = testing.postgresql.Postgresql()
    except RuntimeError as e:
        pytest.skip(f"PostgreSQL not available locally: {e}")

    with postgresql:
        # Initialize database with backup.sql using psql command
        # (psycopg2 can't handle COPY ... FROM stdin with inline data)
        parsed = urlparse(postgresql.url())
        env = os.environ.copy()
        env["PGPASSWORD"] = parsed.password or ""

        result = subprocess.run(
            [
                "psql",
                "-h",
                parsed.hostname,
                "-p",
                str(parsed.port),
                "-U",
                parsed.username,
                "-d",
                parsed.path.lstrip("/"),
                "-f",
                str(backup_sql_path),
            ],
            env=env,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            pytest.fail(f"Failed to load backup.sql: {result.stderr}")

        # Set environment variables for MDR
        os.environ["POSTGRESQL_USER"] = parsed.username or "postgres"
        os.environ["POSTGRESQL_PASSWORD"] = parsed.password or ""
        os.environ["POSTGRESQL_HOST"] = parsed.hostname or "localhost"
        os.environ["POSTGRESQL_PORT"] = str(parsed.port)
        os.environ["POSTGRESQL_DB"] = parsed.path.lstrip("/")

        yield postgresql


@pytest.fixture(scope="function")
async def test_db_session(postgres_server):
    """Create a new database session for each test."""
    # Convert psycopg2 URL to asyncpg URL format
    parsed = urlparse(postgres_server.url())
    DATABASE_URL = (
        f"postgresql+asyncpg://{parsed.username}:{parsed.password or ''}@{parsed.hostname}:{parsed.port}{parsed.path}"
    )

    engine = create_async_engine(DATABASE_URL, echo=True)
    async_session_maker = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session_maker() as session:
        yield session

    await engine.dispose()


@pytest.fixture(scope="function")
async def async_client_mdr(test_db_session):
    """Create async HTTP client for testing MDR."""

    # Leave imports here to force database setup with
    # the test container environment variables
    from lif.mdr_restapi import core
    from lif.mdr_utils.database_setup import get_session

    # Override MDR's get_session dependency to use the test database session
    # so the event loop is the same as the test, otherwise, errors such as "got
    # Future <Future pending cb=[BaseProtocol._on_waiter_completed()]> attached
    # to a different loop" get thrown.
    async def override_get_session():
        yield test_db_session

    core.app.dependency_overrides[get_session] = override_get_session

    async with AsyncClient(transport=ASGITransport(app=core.app), base_url="http://test") as client:
        yield client

    # Clean up
    core.app.dependency_overrides.clear()


@pytest.fixture(scope="function")
async def async_client_translator(async_client_mdr):
    """Create async HTTP client for testing the Translator."""
    from lif.mdr_client import core as mdr_client_core

    # Store original function for cleanup
    original_get_mdr_client = mdr_client_core._get_mdr_client
    original_get_mdr_api_url = mdr_client_core._get_mdr_api_url
    original_get_mdr_api_auth_token = mdr_client_core._get_mdr_api_auth_token

    # Override mdr_client's _get_mdr_client to use the test MDR app
    async def override_get_mdr_client():
        yield async_client_mdr

    mdr_client_core._get_mdr_client = override_get_mdr_client
    mdr_client_core._get_mdr_api_url = lambda: "http://test"
    mdr_client_core._get_mdr_api_auth_token = lambda: "changeme1"

    # Create the translator client
    async with AsyncClient(transport=ASGITransport(app=translator_core.app), base_url="http://test") as client:
        yield client

    # Clean up - restore original function
    mdr_client_core._get_mdr_client = original_get_mdr_client
    mdr_client_core._get_mdr_api_url = original_get_mdr_api_url
    mdr_client_core._get_mdr_api_auth_token = original_get_mdr_api_auth_token

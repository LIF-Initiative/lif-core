import json
import os
from pathlib import Path

import pytest
import testcontainers.postgres
from deepdiff import DeepDiff
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

HEADER_MDR_API_KEY_GRAPHQL = {"X-API-Key": "changeme1"}

#
# Setup to test the end-to-end API with a real postgreSQL database
#


@pytest.fixture(scope="session")
def postgres_container():
    """Start a PostgreSQL container for testing."""

    # Get the absolute path to the SQL file that is used to
    # initialize the database when docker compose starts up
    backup_sql_path = str(Path(__file__).parent.parent.parent.parent.parent / "projects/lif_mdr_database/backup.sql")

    # Create a postgreSQL container with volume mapping for the init SQL script
    postgres = testcontainers.postgres.PostgresContainer(
        "postgres:17", username="postgres", password="postgres", dbname="LIF"
    ).with_volume_mapping(backup_sql_path, "/docker-entrypoint-initdb.d/01-backup.sql", mode="ro")

    try:
        with postgres as pg:
            # Set environment variables for MDR
            os.environ["POSTGRESQL_USER"] = pg.username
            os.environ["POSTGRESQL_PASSWORD"] = pg.password
            os.environ["POSTGRESQL_HOST"] = pg.get_container_host_ip()
            os.environ["POSTGRESQL_PORT"] = str(pg.get_exposed_port(5432))
            os.environ["POSTGRESQL_DB"] = pg.dbname

            yield pg
    except Exception:
        # Print container logs if startup fails
        logs = postgres.get_wrapped_container().logs().decode("utf-8")
        print(f"Container logs:\n{logs}")
        raise


@pytest.fixture(scope="function")
async def test_db_session(postgres_container):
    """Create a new database session for each test."""
    DATABASE_URL = f"postgresql+asyncpg://{postgres_container.username}:{postgres_container.password}@{postgres_container.get_container_host_ip()}:{str(postgres_container.get_exposed_port(5432))}/{postgres_container.dbname}"
    engine = create_async_engine(DATABASE_URL, echo=True)
    async_session_maker = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session_maker() as session:
        yield session

    await engine.dispose()


@pytest.fixture(scope="function")
async def async_client(test_db_session):
    """Create async HTTP client for testing."""

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


#
# Test cases
#


@pytest.mark.asyncio
async def test_test_auth_info_graphql_api_key(async_client):
    response = await async_client.get("/test/auth-info", headers=HEADER_MDR_API_KEY_GRAPHQL)
    assert response.status_code == 200, str(response.content)
    assert response.json() == {
        "auth_type": "API key",
        "authenticated_as": "microservice",
        "service_name": "graphql-service",
    }


@pytest.mark.asyncio
async def test_create_source_schema_datamodel_without_upload_success(async_client):
    # Create data model without OpenAPI schema upload

    response = await async_client.post(
        "/datamodels/",
        headers=HEADER_MDR_API_KEY_GRAPHQL,
        json={
            "DataModelVersion": "1.0",
            "State": "Draft",
            "CreationDate": "2025-12-02T21:01:00Z",
            "ActivationDate": "2025-12-02T21:01:00Z",
            "Name": "Test Source Schema Data Model",
            "Type": "SourceSchema",
            "BaseDataModelId": None,
            "Description": "Test Source Schema Data Model description",
            "Notes": "For testing",
            "UseConsiderations": "Public use",
            "Tags": "test1",
            "Contributor": "JSmith",
            "ContributorOrganization": "Acme",
            "DeprecationDate": "2040-12-12T01:02:00Z",
        },
    )
    assert response.status_code == 201, str(response.content) + str(response.text) + str(response.headers)

    # Extract ID from location header

    location = response.headers.get("location")
    datamodel_id = int(location.split("/")[-1])

    # Confirm creation response

    assert response.json() == {
        "ActivationDate": "2025-12-02T21:01:00Z",
        "BaseDataModelId": None,
        "Contributor": "JSmith",
        "ContributorOrganization": "Acme",
        "CreationDate": "2025-12-02T21:01:00Z",
        "DataModelVersion": "1.0",
        "Deleted": False,
        "DeprecationDate": "2040-12-12T01:02:00Z",
        "Description": "Test Source Schema Data Model description",
        "Id": datamodel_id,
        "Name": "Test Source Schema Data Model",
        "Notes": "For testing",
        "State": "Draft",
        "Tags": "test1",
        "Type": "SourceSchema",
        "UseConsiderations": "Public use",
    }

    # Download full OpenAPI schema with metadata to verify creation

    retrieve_response = await async_client.get(
        f"/datamodels/open_api_schema/{datamodel_id}?download=true&include_entity_md=true&include_attr_md=true&full_export=true",
        headers=HEADER_MDR_API_KEY_GRAPHQL,
    )
    assert retrieve_response.status_code == 200, str(retrieve_response.text)

    retrieved_schema = retrieve_response.json()
    assert retrieved_schema == {
        "components": {"schemas": {}},
        "info": {
            "description": "OpenAPI Spec",
            "title": "Machine-Readable Schema for Test Source Schema Data Model",
            "version": "1.0",
        },
        "openapi": "3.0.0",
        "paths": {},
    }, "Retrieved schema does not match empty schema"


@pytest.mark.asyncio
async def test_create_source_schema_datamodel_with_duplicate_valuesets(async_client):
    """
    Create data model with OpenAPI schema upload that contains duplicate valuesets.

    Should fail the creation call.
    """

    schema_path = Path(__file__).parent / "data_model_test_duplicate_valuesets.json"
    create_response = await async_client.post(
        "/datamodels/open_api_schema/upload",
        headers=HEADER_MDR_API_KEY_GRAPHQL,
        files={"file": ("filename.json", open(schema_path, "rb"), "application/json")},
        data={
            "data_model_version": "1.0",
            "state": "Draft",
            "activation_date": "2025-12-02T21:01:00Z",
            "data_model_name": "Test Source Schema Data Model with Duplicate ValueSets",
            "data_model_type": "SourceSchema",
        },
    )

    # Confirm creation response

    assert create_response.status_code == 500, str(create_response.text) + str(create_response.headers)
    assert "IntegrityError" in create_response.json()["detail"], str(create_response.text) + str(
        create_response.headers
    )


@pytest.mark.asyncio
async def test_create_source_schema_datamodel_with_duplicate_valuesetvalues(async_client):
    """
    Create data model with OpenAPI schema upload that contains duplicate valueset values.

    Should fail the creation call.
    """

    schema_path = Path(__file__).parent / "data_model_test_duplicate_valuesetvalues.json"
    create_response = await async_client.post(
        "/datamodels/open_api_schema/upload",
        headers=HEADER_MDR_API_KEY_GRAPHQL,
        files={"file": ("filename.json", open(schema_path, "rb"), "application/json")},
        data={
            "data_model_version": "1.0",
            "state": "Draft",
            "activation_date": "2025-12-02T21:01:00Z",
            "data_model_name": "Test Source Schema Data Model with Duplicate ValueSetValues",
            "data_model_type": "SourceSchema",
        },
    )

    # Confirm creation response

    assert create_response.status_code == 500, str(create_response.text) + str(create_response.headers)
    assert "IntegrityError" in create_response.json()["detail"], str(create_response.text) + str(
        create_response.headers
    )


@pytest.mark.asyncio
async def test_create_source_schema_datamodel_with_upload_success(async_client):
    # Create data model with OpenAPI schema upload

    schema_path = Path(__file__).parent / "data_model_example_datasource_full_openapi_schema.json"
    create_response = await async_client.post(
        "/datamodels/open_api_schema/upload",
        headers=HEADER_MDR_API_KEY_GRAPHQL,
        files={"file": ("filename.json", open(schema_path, "rb"), "application/json")},
        data={
            "data_model_version": "1.0",
            "state": "Draft",
            "activation_date": "2025-12-02T21:01:00Z",
            "data_model_name": "Test Source Schema Data Model with Upload",
            "data_model_type": "SourceSchema",
        },
    )

    # Confirm creation response

    assert create_response.status_code == 201, str(create_response.text) + str(create_response.headers)
    # Location header is not populated for this endpoint, so extract ID from response body
    data_model_id = create_response.json()["Id"]
    assert data_model_id is not None
    assert isinstance(data_model_id, int)

    assert create_response.json() == {
        "ActivationDate": "2025-12-02T21:01:00Z",
        "BaseDataModelId": None,
        "Contributor": None,
        "ContributorOrganization": None,
        "CreationDate": None,
        "DataModelVersion": "1.0",
        "Deleted": False,
        "DeprecationDate": None,
        "Description": None,
        "Id": data_model_id,
        "Name": "Test Source Schema Data Model with Upload",
        "Notes": None,
        "State": "Draft",
        "Tags": None,
        "Type": "SourceSchema",
        "UseConsiderations": None,
    }

    # Download full OpenAPI schema with metadata to verify upload

    retrieve_response = await async_client.get(
        f"/datamodels/open_api_schema/{data_model_id}?download=true&include_entity_md=true&include_attr_md=true&full_export=true",
        headers=HEADER_MDR_API_KEY_GRAPHQL,
    )
    assert retrieve_response.status_code == 200, str(retrieve_response.text)

    retrieved_schema = retrieve_response.json()
    with open(schema_path, "r") as f:
        original_schema = json.load(f)
        original_schema["info"]["title"] = "Machine-Readable Schema for Test Source Schema Data Model with Upload"

        diff = DeepDiff(
            original_schema,
            retrieved_schema,
            ignore_order=True,
            exclude_paths=[
                "root['components']['schemas']['person']['Id']",
                "root['components']['schemas']['person']['DataModelId']",
                "root['components']['schemas']['person']['properties']['id']['Id']",
                "root['components']['schemas']['person']['properties']['id']['DataModelId']",
                "root['components']['schemas']['person']['properties']['id']['EntityAttributeAssociationId']",
                "root['components']['schemas']['person']['properties']['id']['EntityId']",
                "root['components']['schemas']['person']['properties']['employment']['DataModelId']",
                "root['components']['schemas']['person']['properties']['employment']['Id']",
                "root['components']['schemas']['person']['properties']['employment']['EntityAssociationId']",
                "root['components']['schemas']['person']['properties']['employment']['EntityAssociationParentEntityId']",
                "root['components']['schemas']['person']['properties']['employment']['properties']['preferences']['DataModelId']",
                "root['components']['schemas']['person']['properties']['employment']['properties']['preferences']['Id']",
                "root['components']['schemas']['person']['properties']['employment']['properties']['preferences']['EntityAssociationId']",
                "root['components']['schemas']['person']['properties']['employment']['properties']['preferences']['EntityAssociationParentEntityId']",
                "root['components']['schemas']['person']['properties']['employment']['properties']['preferences']['properties']['preferred_org_types']['Id']",
                "root['components']['schemas']['person']['properties']['employment']['properties']['preferences']['properties']['preferred_org_types']['DataModelId']",
                "root['components']['schemas']['person']['properties']['employment']['properties']['preferences']['properties']['preferred_org_types']['EntityAttributeAssociationId']",
                "root['components']['schemas']['person']['properties']['employment']['properties']['preferences']['properties']['preferred_org_types']['EntityId']",
            ],
        )
        assert not diff, f"Retrieved schema does not match original: {diff}"

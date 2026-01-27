import inspect
import json
import os
import subprocess
from pathlib import Path
from urllib.parse import urlparse

import pytest
import testing.postgresql
from deepdiff import DeepDiff
from httpx import ASGITransport, AsyncClient
from lif.translator_restapi import core as translator_core
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from test.utils.lif.datasets.transform_deep_literal_attribute.loader import DatasetTransformDeepLiteralAttribute
from test.utils.lif.datasets.transform_with_embeddings.loader import DatasetTransformWithEmbeddings
from test.utils.lif.mdr.api import convert_unique_names_to_id_path, create_transformation
from test.utils.lif.translator.api import create_translation

HEADER_MDR_API_KEY_GRAPHQL = {"X-API-Key": "changeme1"}


#
# Setup to test the end-to-end API with a real postgreSQL database
#


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
                "-h", parsed.hostname,
                "-p", str(parsed.port),
                "-U", parsed.username,
                "-d", parsed.path.lstrip("/"),
                "-f", str(backup_sql_path),
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
    DATABASE_URL = f"postgresql+asyncpg://{parsed.username}:{parsed.password or ''}@{parsed.hostname}:{parsed.port}{parsed.path}"

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


#
# Test cases
#


@pytest.mark.asyncio
async def test_test_auth_info_graphql_api_key(async_client_mdr):
    response = await async_client_mdr.get("/test/auth-info", headers=HEADER_MDR_API_KEY_GRAPHQL)
    assert response.status_code == 200, str(response.content)
    assert response.json() == {
        "auth_type": "API key",
        "authenticated_as": "microservice",
        "service_name": "graphql-service",
    }


@pytest.mark.asyncio
async def test_create_source_schema_datamodel_without_upload_success(async_client_mdr):
    # Create data model without OpenAPI schema upload

    response = await async_client_mdr.post(
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

    retrieve_response = await async_client_mdr.get(
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
async def test_create_source_schema_datamodel_with_duplicate_valuesets(async_client_mdr):
    """
    Create data model with OpenAPI schema upload that contains duplicate valuesets.

    Should fail the creation call.
    """

    schema_path = Path(__file__).parent / "data_model_test_duplicate_valuesets.json"
    create_response = await async_client_mdr.post(
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
async def test_create_source_schema_datamodel_with_duplicate_valuesetvalues(async_client_mdr):
    """
    Create data model with OpenAPI schema upload that contains duplicate valueset values.

    Should fail the creation call.
    """

    schema_path = Path(__file__).parent / "data_model_test_duplicate_valuesetvalues.json"
    create_response = await async_client_mdr.post(
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


# Old tests use the name.dot.name format for entityIdPath and once that API logic is
# removed, can be deleted.
@pytest.mark.asyncio
async def test_transforms_deep_literal_attribute_old_api_format(async_client_mdr, async_client_translator):
    """
    Transform a 'deep' literal attribute to another deep literal attribute using the old API format for entityIdPath.

    Source and Target are source schemas.

    """

    test_case_name = inspect.currentframe().f_code.co_name

    # General setup for dataset deep_literal_attribute

    dataset_transform_deep_literal_attribute = await DatasetTransformDeepLiteralAttribute.prepare(
        async_client_mdr=async_client_mdr,
        source_data_model_name=f"{test_case_name}_source",
        target_data_model_name=f"{test_case_name}_target",
        transformation_group_name=f"{test_case_name}_transform_group",
    )

    # Create transform - Old API format for entityIdPath

    _ = await create_transformation(
        async_client_mdr=async_client_mdr,
        transformation_group_id=dataset_transform_deep_literal_attribute.transformation_group_id,
        source_parent_entity_id=dataset_transform_deep_literal_attribute.source_parent_entity_id,
        source_attribute_id=dataset_transform_deep_literal_attribute.source_attribute_id,
        source_entity_path="Person.Courses",
        target_parent_entity_id=dataset_transform_deep_literal_attribute.target_parent_entity_id,
        target_attribute_id=dataset_transform_deep_literal_attribute.target_attribute_id,
        target_entity_path="User.Skills",
        mapping_expression='{ "User": { "Skills": { "Genre": Person.Courses.Grade } } }',
        transformation_name="User.Skills.Genre",
    )

    # Use the transform via the Translator endpoint

    translated_json = await create_translation(
        async_client_translator=async_client_translator,
        source_data_model_id=dataset_transform_deep_literal_attribute.source_data_model_id,
        target_data_model_id=dataset_transform_deep_literal_attribute.target_data_model_id,
        json_to_translate={"Person": {"Courses": {"Grade": "A", "Style": "Lecture"}}},
        headers=HEADER_MDR_API_KEY_GRAPHQL,
    )
    assert translated_json == {"User": {"Skills": {"Genre": "A"}}}


@pytest.mark.asyncio
async def test_transforms_deep_literal_attribute(async_client_mdr, async_client_translator):
    """
    Transform a 'deep' literal attribute to another deep literal attribute.

    Source and Target are source schemas.

    """

    test_case_name = inspect.currentframe().f_code.co_name

    # General setup for dataset deep_literal_attribute

    dataset_transform_deep_literal_attribute = await DatasetTransformDeepLiteralAttribute.prepare(
        async_client_mdr=async_client_mdr,
        source_data_model_name=f"{test_case_name}_source",
        target_data_model_name=f"{test_case_name}_target",
        transformation_group_name=f"{test_case_name}_transform_group",
    )

    # Create transform

    _ = await create_transformation(
        async_client_mdr=async_client_mdr,
        transformation_group_id=dataset_transform_deep_literal_attribute.transformation_group_id,
        source_parent_entity_id=None,
        source_attribute_id=dataset_transform_deep_literal_attribute.source_attribute_id,
        source_entity_path=convert_unique_names_to_id_path(
            dataset_transform_deep_literal_attribute.source_schema, ["person", "person.courses", "person.courses.grade"]
        ),
        target_parent_entity_id=None,
        target_attribute_id=dataset_transform_deep_literal_attribute.target_attribute_id,
        target_entity_path=convert_unique_names_to_id_path(
            dataset_transform_deep_literal_attribute.target_schema, ["user", "user.skills", "user.skills.genre"]
        ),
        mapping_expression='{ "User": { "Skills": { "Genre": Person.Courses.Grade } } }',
        transformation_name="User.Skills.Genre",
    )

    # Use the transform via the Translator endpoint

    translated_json = await create_translation(
        async_client_translator=async_client_translator,
        source_data_model_id=dataset_transform_deep_literal_attribute.source_data_model_id,
        target_data_model_id=dataset_transform_deep_literal_attribute.target_data_model_id,
        json_to_translate={"Person": {"Courses": {"Grade": "A", "Style": "Lecture"}}},
        headers=HEADER_MDR_API_KEY_GRAPHQL,
    )
    assert translated_json == {"User": {"Skills": {"Genre": "A"}}}


@pytest.mark.asyncio
async def test_create_transform_fail_single_id_in_source_attribute_path(async_client_mdr, async_client_translator):
    """
    Confirms a single ID in the source attribute path is rejected.

    Source and Target are source schemas.

    """

    test_case_name = inspect.currentframe().f_code.co_name

    # General setup for dataset deep_literal_attribute

    dataset_transform_deep_literal_attribute = await DatasetTransformDeepLiteralAttribute.prepare(
        async_client_mdr=async_client_mdr,
        source_data_model_name=f"{test_case_name}_source",
        target_data_model_name=f"{test_case_name}_target",
        transformation_group_name=f"{test_case_name}_transform_group",
    )

    # Create transform

    _ = await create_transformation(
        async_client_mdr=async_client_mdr,
        transformation_group_id=dataset_transform_deep_literal_attribute.transformation_group_id,
        source_parent_entity_id=dataset_transform_deep_literal_attribute.source_parent_entity_id,
        source_attribute_id=dataset_transform_deep_literal_attribute.source_attribute_id,
        source_entity_path=f"{dataset_transform_deep_literal_attribute.source_parent_entity_id}",  # This is the point of the test!
        target_parent_entity_id=dataset_transform_deep_literal_attribute.target_parent_entity_id,
        target_attribute_id=dataset_transform_deep_literal_attribute.target_attribute_id,
        target_entity_path="0,0",  # Doesn't matter for this test
        mapping_expression='{ "User": { "Skills": { "Genre": Person.Courses.Grade } } }',
        transformation_name="User.Skills.Genre",
        expected_status_code=400,
        expected_response={"detail": "Invalid EntityIdPath format. The path must contain at least two IDs."},
    )


@pytest.mark.asyncio
async def test_create_transform_fail_non_numeric_source_attribute_path_entry(async_client_mdr, async_client_translator):
    """
    Confirms only numeric IDs in the source attribute path are allowed.

    Source and Target are source schemas.

    """

    test_case_name = inspect.currentframe().f_code.co_name

    # General setup for dataset deep_literal_attribute (source sourceSchema, target sourceSchema, transform group, and relevant IDs)

    dataset_transform_deep_literal_attribute = await DatasetTransformDeepLiteralAttribute.prepare(
        async_client_mdr=async_client_mdr,
        source_data_model_name=f"{test_case_name}_source",
        target_data_model_name=f"{test_case_name}_target",
        transformation_group_name=f"{test_case_name}_transform_group",
    )

    # Create transform

    _ = await create_transformation(
        async_client_mdr=async_client_mdr,
        transformation_group_id=dataset_transform_deep_literal_attribute.transformation_group_id,
        source_parent_entity_id=dataset_transform_deep_literal_attribute.source_parent_entity_id,
        source_attribute_id=dataset_transform_deep_literal_attribute.source_attribute_id,
        source_entity_path="a,b",  # This is the point of the test!
        target_parent_entity_id=dataset_transform_deep_literal_attribute.target_parent_entity_id,
        target_attribute_id=dataset_transform_deep_literal_attribute.target_attribute_id,
        target_entity_path="0,0",  # Doesn't matter for this test
        mapping_expression='{ "User": { "Skills": { "Genre": Person.Courses.Grade } } }',
        transformation_name="User.Skills.Genre",
        expected_status_code=400,
        expected_response={
            "detail": "Invalid EntityIdPath format. IDs must be in the format 'id1,id2,...,idN' and all IDs must be integers."
        },
    )


# Old tests use the name.dot.name format for entityIdPath and once that API logic is
# removed, can be deleted.
@pytest.mark.asyncio
async def test_transforms_with_embeddings_old_api_format(async_client_mdr, async_client_translator):
    """
    Transform source and target attributes both from their original location and their entity embedded location.

    Source and Target are source schemas.

    """

    test_case_name = inspect.currentframe().f_code.co_name

    dataset_transform_with_embeddings = await DatasetTransformWithEmbeddings.prepare(
        async_client_mdr=async_client_mdr,
        source_data_model_name=f"{test_case_name}_source",
        target_data_model_name=f"{test_case_name}_target",
        transformation_group_name=f"{test_case_name}_transform_group",
    )

    # Create transformations

    _ = await create_transformation(
        async_client_mdr=async_client_mdr,
        transformation_group_id=dataset_transform_with_embeddings.transformation_group_id,
        source_parent_entity_id=dataset_transform_with_embeddings.flow1_source_parent_entity_id,
        source_attribute_id=dataset_transform_with_embeddings.flow1_source_attribute_id,
        source_entity_path="Person.Employment.SkillsGainedFromCourses",
        target_parent_entity_id=dataset_transform_with_embeddings.flow1_target_parent_entity_id,
        target_attribute_id=dataset_transform_with_embeddings.flow1_target_attribute_id,
        target_entity_path="User.Workplace.Abilities.Skills",
        mapping_expression='{ "User": { "Workplace": { "Abilities": { "Skills": { "LevelOfSkillAbility": Person.Employment.SkillsGainedFromCourses.SkillLevel } } } } }',
        transformation_name="User.Workplace.Abilities.Skills.LevelOfSkillAbility",
    )

    _ = await create_transformation(
        async_client_mdr=async_client_mdr,
        transformation_group_id=dataset_transform_with_embeddings.transformation_group_id,
        source_parent_entity_id=dataset_transform_with_embeddings.flow2_source_parent_entity_id,
        source_attribute_id=dataset_transform_with_embeddings.flow2_source_attribute_id,
        source_entity_path="Person.Employment.Profession",
        target_parent_entity_id=dataset_transform_with_embeddings.flow2_target_parent_entity_id,
        target_attribute_id=dataset_transform_with_embeddings.flow2_target_attribute_id,
        target_entity_path="User.Abilities.Skills",
        mapping_expression='{ "User": { "Abilities": { "Skills": { "LevelOfSkillAbility": Person.Employment.Profession.DurationAtProfession } } } }',
        transformation_name="User.Abilities.Skills.LevelOfSkillAbility",
    )

    _ = await create_transformation(
        async_client_mdr=async_client_mdr,
        transformation_group_id=dataset_transform_with_embeddings.transformation_group_id,
        source_parent_entity_id=dataset_transform_with_embeddings.flow3_source_parent_entity_id,
        source_attribute_id=dataset_transform_with_embeddings.flow3_source_attribute_id,
        source_entity_path="Person.Courses.SkillsGainedFromCourses",
        target_parent_entity_id=dataset_transform_with_embeddings.flow3_target_parent_entity_id,
        target_attribute_id=dataset_transform_with_embeddings.flow3_target_attribute_id,
        target_entity_path="User.Preferences",
        mapping_expression='{ "User": { "Preferences": { "WorkPreference": Person.Courses.SkillsGainedFromCourses.SkillLevel } } }',
        transformation_name="User.Preferences.WorkPreference",
    )

    # Use the transformations via the Translator endpoint

    translated_json = await create_translation(
        async_client_translator=async_client_translator,
        source_data_model_id=dataset_transform_with_embeddings.source_data_model_id,
        target_data_model_id=dataset_transform_with_embeddings.target_data_model_id,
        json_to_translate={
            "Person": {
                "Employment": {
                    "SkillsGainedFromCourses": {"SkillLevel": "Mastery"},
                    "Profession": {"DurationAtProfession": "10 Years"},
                },
                "Courses": {"SkillsGainedFromCourses": {"SkillLevel": "Advanced"}},
            }
        },
        headers=HEADER_MDR_API_KEY_GRAPHQL,
    )
    assert translated_json == {
        "User": {
            "Workplace": {"Abilities": {"Skills": {"LevelOfSkillAbility": "Mastery"}}},
            "Abilities": {"Skills": {"LevelOfSkillAbility": "10 Years"}},
            "Preferences": {"WorkPreference": "Advanced"},
        }
    }


@pytest.mark.asyncio
async def test_transforms_with_embeddings(async_client_mdr, async_client_translator):
    """
    Transform source and target attributes both from their original location and their entity embedded location.

    Source and Target are source schemas.

    """

    test_case_name = inspect.currentframe().f_code.co_name

    dataset_transform_with_embeddings = await DatasetTransformWithEmbeddings.prepare(
        async_client_mdr=async_client_mdr,
        source_data_model_name=f"{test_case_name}_source",
        target_data_model_name=f"{test_case_name}_target",
        transformation_group_name=f"{test_case_name}_transform_group",
    )

    # Create transformations

    _ = await create_transformation(
        async_client_mdr=async_client_mdr,
        transformation_group_id=dataset_transform_with_embeddings.transformation_group_id,
        source_parent_entity_id=None,
        source_attribute_id=dataset_transform_with_embeddings.flow1_source_attribute_id,
        source_entity_path=dataset_transform_with_embeddings.flow1_source_entity_id_path,
        target_parent_entity_id=None,
        target_attribute_id=dataset_transform_with_embeddings.flow1_target_attribute_id,
        target_entity_path=dataset_transform_with_embeddings.flow1_target_entity_id_path,
        mapping_expression='{ "User": { "Workplace": { "Abilities": { "Skills": { "LevelOfSkillAbility": Person.Employment.SkillsGainedFromCourses.SkillLevel } } } } }',
        transformation_name="User.Workplace.Abilities.Skills.LevelOfSkillAbility",
    )

    _ = await create_transformation(
        async_client_mdr=async_client_mdr,
        transformation_group_id=dataset_transform_with_embeddings.transformation_group_id,
        source_parent_entity_id=None,
        source_attribute_id=dataset_transform_with_embeddings.flow2_source_attribute_id,
        source_entity_path=dataset_transform_with_embeddings.flow2_source_entity_id_path,
        target_parent_entity_id=None,
        target_attribute_id=dataset_transform_with_embeddings.flow2_target_attribute_id,
        target_entity_path=dataset_transform_with_embeddings.flow2_target_entity_id_path,
        mapping_expression='{ "User": { "Abilities": { "Skills": { "LevelOfSkillAbility": Person.Employment.Profession.DurationAtProfession } } } }',
        transformation_name="User.Abilities.Skills.LevelOfSkillAbility",
    )

    _ = await create_transformation(
        async_client_mdr=async_client_mdr,
        transformation_group_id=dataset_transform_with_embeddings.transformation_group_id,
        source_parent_entity_id=None,
        source_attribute_id=dataset_transform_with_embeddings.flow3_source_attribute_id,
        source_entity_path=dataset_transform_with_embeddings.flow3_source_entity_id_path,
        target_parent_entity_id=None,
        target_attribute_id=dataset_transform_with_embeddings.flow3_target_attribute_id,
        target_entity_path=dataset_transform_with_embeddings.flow3_target_entity_id_path,
        mapping_expression='{ "User": { "Preferences": { "WorkPreference": Person.Courses.SkillsGainedFromCourses.SkillLevel } } }',
        transformation_name="User.Preferences.WorkPreference",
    )

    # Use the transformations via the Translator endpoint

    translated_json = await create_translation(
        async_client_translator=async_client_translator,
        source_data_model_id=dataset_transform_with_embeddings.source_data_model_id,
        target_data_model_id=dataset_transform_with_embeddings.target_data_model_id,
        json_to_translate={
            "Person": {
                "Employment": {
                    "SkillsGainedFromCourses": {"SkillLevel": "Mastery"},
                    "Profession": {"DurationAtProfession": "10 Years"},
                },
                "Courses": {"SkillsGainedFromCourses": {"SkillLevel": "Advanced"}},
            }
        },
        headers=HEADER_MDR_API_KEY_GRAPHQL,
    )
    assert translated_json == {
        "User": {
            "Workplace": {"Abilities": {"Skills": {"LevelOfSkillAbility": "Mastery"}}},
            "Abilities": {"Skills": {"LevelOfSkillAbility": "10 Years"}},
            "Preferences": {"WorkPreference": "Advanced"},
        }
    }


@pytest.mark.asyncio
async def test_create_source_schema_datamodel_with_upload_success(async_client_mdr):
    # Create data model with OpenAPI schema upload

    schema_path = Path(__file__).parent / "data_model_example_datasource_full_openapi_schema.json"
    create_response = await async_client_mdr.post(
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

    retrieve_response = await async_client_mdr.get(
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

import json
from pathlib import Path

import pytest
from deepdiff import DeepDiff


@pytest.mark.asyncio
async def test_create_source_schema_datamodel_without_upload_success(async_client_mdr, mdr_api_headers):
    # Create data model without OpenAPI schema upload

    response = await async_client_mdr.post(
        "/datamodels/",
        headers=mdr_api_headers,
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
        headers=mdr_api_headers,
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
async def test_create_source_schema_datamodel_with_duplicate_valuesets(async_client_mdr, mdr_api_headers):
    """
    Create data model with OpenAPI schema upload that contains duplicate valuesets.

    Should fail the creation call.
    """

    schema_path = Path(__file__).parent / "data_model_test_duplicate_valuesets.json"
    create_response = await async_client_mdr.post(
        "/datamodels/open_api_schema/upload",
        headers=mdr_api_headers,
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
async def test_create_source_schema_datamodel_with_duplicate_valuesetvalues(async_client_mdr, mdr_api_headers):
    """
    Create data model with OpenAPI schema upload that contains duplicate valueset values.

    Should fail the creation call.
    """

    schema_path = Path(__file__).parent / "data_model_test_duplicate_valuesetvalues.json"
    create_response = await async_client_mdr.post(
        "/datamodels/open_api_schema/upload",
        headers=mdr_api_headers,
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
async def test_create_source_schema_datamodel_with_upload_success(async_client_mdr, mdr_api_headers):
    # Create data model with OpenAPI schema upload

    schema_path = Path(__file__).parent / "data_model_example_datasource_full_openapi_schema.json"
    create_response = await async_client_mdr.post(
        "/datamodels/open_api_schema/upload",
        headers=mdr_api_headers,
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
        headers=mdr_api_headers,
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

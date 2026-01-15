from pathlib import Path
from typing import Tuple

from httpx import AsyncClient

HEADER_MDR_API_KEY_GRAPHQL = {"X-API-Key": "changeme1"}


async def create_data_model_by_upload(
    *,
    async_client_mdr: AsyncClient,
    schema_path: Path,
    data_model_name: str,
    data_model_type: str,
    headers: dict = HEADER_MDR_API_KEY_GRAPHQL,
) -> Tuple[str, dict]:
    """
    Helper function to create a data model by uploading an OpenAPI schema file.

    Args:
        async_client_mdr: An instance of AsyncClient to make HTTP requests to the MDR API
        schema_filename: The filename of the schema to upload (relative to the test file)
        data_model_name: The name to assign to the created data model
        data_model_type: The type of the data model (e.g., "OpenAPI")
        headers: Optional headers to include in the request (default is HEADER_MDR_API_KEY_GRAPHQL)

    Returns:
        The JSON representation of the created data model schema
    """

    # Create the data model by uploading the schema file

    schema_path = schema_path
    create_response = await async_client_mdr.post(
        "/datamodels/open_api_schema/upload",
        headers=headers,
        files={"file": ("filename.json", open(schema_path, "rb"), "application/json")},
        data={
            "data_model_version": "1.0",
            "state": "Draft",
            "activation_date": "2025-12-02T21:01:00Z",
            "data_model_name": data_model_name,
            "data_model_type": data_model_type,
        },
    )

    # Confirm creation response and gather ID

    assert create_response.status_code == 201, str(create_response.text) + str(create_response.headers)
    data_model_id = create_response.json()["Id"]

    # Gather data model to determine entity and attribute IDs for transform creation

    retrieve_data_model_response = await async_client_mdr.get(
        f"/datamodels/open_api_schema/{data_model_id}?download=true&include_entity_md=true&include_attr_md=true&full_export=true",
        headers=HEADER_MDR_API_KEY_GRAPHQL,
    )
    assert retrieve_data_model_response.status_code == 200, str(retrieve_data_model_response.text)
    return (data_model_id, retrieve_data_model_response.json())


async def create_transformation_groups(
    *,
    async_client_mdr: AsyncClient,
    source_data_model_id: str,
    target_data_model_id: str,
    group_name: str,
    headers: dict = HEADER_MDR_API_KEY_GRAPHQL,
) -> str:
    """
    Helper function to create a transformation group between a source and target data model.

    Args:
        async_client_mdr: An instance of AsyncClient to make HTTP requests to the MDR API
        source_data_model_id: The ID of the source data model
        target_data_model_id: The ID of the target data model
        group_name: The name to assign to the transformation group
        headers: Optional headers to include in the request (default is HEADER_MDR_API_KEY_GRAPHQL)

    Returns:
        The ID of the created transformation group
    """

    # Create transformation group between source and target

    response = await async_client_mdr.post(
        "/transformation_groups/",
        headers=headers,
        json={
            "SourceDataModelId": source_data_model_id,
            "TargetDataModelId": target_data_model_id,
            "Name": group_name,
            "GroupVersion": "1.0",
        },
    )

    # Confirm transformation group response and gather ID

    assert response.status_code == 201, str(response.text) + str(response.headers)
    group_id = response.json()["Id"]
    assert response.json() == {
        "Id": group_id,
        "SourceDataModelId": source_data_model_id,
        "TargetDataModelId": target_data_model_id,
        "SourceDataModelName": None,
        "TargetDataModelName": None,
        "Name": group_name,
        "GroupVersion": "1.0",
        "Description": None,
        "Notes": None,
        "CreationDate": None,
        "ActivationDate": None,
        "DeprecationDate": None,
        "Contributor": None,
        "ContributorOrganization": None,
        "Tags": None,
    }

    return group_id


async def create_transformation(
    *,
    async_client_mdr: AsyncClient,
    transformation_group_id: str,
    source_parent_entity_id: str,
    source_attribute_id: str,
    source_entity_path: str,  # "Person.Courses"
    target_parent_entity_id: str,
    target_attribute_id: str,
    target_entity_path: str,  # "User.Skills"
    mapping_expression: str,  # '{ "User": { "Skills": { "Genre": Person.Courses.Grade } } }'
    transformation_name: str,  # "User.Skills.Genre",
    headers: dict = HEADER_MDR_API_KEY_GRAPHQL,
) -> str:
    """
    Helper function to create a transform between a single source attribute and a target attribute

    Args:
        async_client_mdr: An instance of AsyncClient to make HTTP requests to the MDR API
        transformation_group_id: The ID of the transformation group to which this transform belongs
        source_parent_entity_id: The ID of the parent entity for the source attribute
        source_attribute_id: The ID of the source attribute
        source_entity_path: The path to the source attribute within the source data model (e.g., "Person.Courses")
        target_parent_entity_id: The ID of the parent entity for the target attribute
        target_attribute_id: The ID of the target attribute
        target_entity_path: The path to the target attribute within the target data model (e.g., "User.Skills")
        mapping_expression: The JSONata expression that defines the transformation logic (e.g., '{ "User": { "Skills": { "Genre": Person.Courses.Grade } } }')
        transformation_name: The name to assign to the transformation
        headers: Optional headers to include in the request (default is HEADER_MDR_API_KEY_GRAPHQL)

    Returns:
        The ID of the created transformation
    """
    response = await async_client_mdr.post(
        "/transformation_groups/transformations/",
        headers=headers,
        json={
            "ExpressionLanguage": "JSONata",
            "TransformationGroupId": transformation_group_id,
            "Expression": mapping_expression,
            "Name": transformation_name,
            "SourceAttributes": [
                {
                    "AttributeId": source_attribute_id,
                    "AttributeType": "Source",
                    "EntityIdPath": source_entity_path,
                    "EntityId": source_parent_entity_id,
                }
            ],
            "TargetAttribute": {
                "AttributeId": target_attribute_id,
                "AttributeType": "Target",
                "EntityIdPath": target_entity_path,
                "EntityId": target_parent_entity_id,
            },
        },
    )

    # Confirm transform response and gather ID

    assert response.status_code == 201, str(response.text) + str(response.headers)
    transformation_id = response.json()["Id"]
    assert response.json() == {
        "Id": transformation_id,
        "TransformationGroupId": transformation_group_id,
        "Name": transformation_name,
        "Expression": mapping_expression,
        "ExpressionLanguage": "JSONata",
        "Notes": None,
        "Alignment": None,
        "CreationDate": None,
        "ActivationDate": None,
        "DeprecationDate": None,
        "Contributor": None,
        "ContributorOrganization": None,
        "SourceAttributes": [
            {
                "AttributeId": source_attribute_id,
                "EntityId": source_parent_entity_id,
                "AttributeName": None,
                "AttributeType": "Source",
                "Notes": None,
                "CreationDate": None,
                "ActivationDate": None,
                "DeprecationDate": None,
                "Contributor": None,
                "ContributorOrganization": None,
                "EntityIdPath": source_entity_path,
            }
        ],
        "TargetAttribute": {
            "AttributeId": target_attribute_id,
            "EntityId": target_parent_entity_id,
            "AttributeName": None,
            "AttributeType": "Target",
            "Notes": None,
            "CreationDate": None,
            "ActivationDate": None,
            "DeprecationDate": None,
            "Contributor": None,
            "ContributorOrganization": None,
            "EntityIdPath": target_entity_path,
        },
    }

    return transformation_id

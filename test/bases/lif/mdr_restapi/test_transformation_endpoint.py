import copy
import inspect
import re

import pytest
from deepdiff import DeepDiff
from lif.datatypes.mdr_sql_model import Attribute, DataModel, DataModelType, Entity
from lif.mdr_services.attribute_service import get_unique_attribute
from lif.mdr_services.entity_service import get_unique_entity
from sqlalchemy import text

from test.utils.lif.datasets.transform_deep_literal_attribute.loader import DatasetTransformDeepLiteralAttribute
from test.utils.lif.datasets.transform_with_embeddings.loader import DatasetTransformWithEmbeddings
from test.utils.lif.mdr.api import (
    convert_unique_names_to_id_path,
    create_transformation,
    delete_transformation,
    delete_transformation_group,
    export_transformation_group,
    import_transformation_group,
    update_transformation,
)
from test.utils.lif.translator.api import create_translation


def _clean_jsonata_expression(expression: str) -> str:
    """
    Helper function to clean JSONata expressions for comparison, by removing extra whitespace.

    Args:
        expression (str): The JSONata expression to clean.

    Returns:
        str: The cleaned JSONata expression with extra whitespace removed.
    """
    return re.sub(r"\s+", " ", expression).strip()


@pytest.mark.asyncio
async def test_transforms_deep_literal_attribute(async_client_mdr, async_client_translator, mdr_api_headers):
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
            dataset_transform_deep_literal_attribute.source_schema,
            ["person", "person.courses", "person.courses.grade"],
            True,
        ),
        target_parent_entity_id=None,
        target_attribute_id=dataset_transform_deep_literal_attribute.target_attribute_id,
        target_entity_path=convert_unique_names_to_id_path(
            dataset_transform_deep_literal_attribute.target_schema, ["user", "user.skills", "user.skills.genre"], True
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
        headers=mdr_api_headers,
    )
    assert translated_json == {"User": {"Skills": {"Genre": "A"}}}


@pytest.mark.asyncio
async def test_transforms_into_target_entity(async_client_mdr, async_client_translator, mdr_api_headers):
    """
    Transform a 'deep' literal attribute into a target entity.

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
            dataset_transform_deep_literal_attribute.source_schema,
            ["person", "person.courses", "person.courses.grade"],
            True,
        ),
        target_parent_entity_id=None,
        target_attribute_id=dataset_transform_deep_literal_attribute.target_attribute_id,
        target_entity_path=convert_unique_names_to_id_path(
            dataset_transform_deep_literal_attribute.target_schema, ["user"], False
        ),
        mapping_expression='{ "User": Person.Courses.Grade }',
        transformation_name="User.Skills.Genre",
    )

    # Use the transform via the Translator endpoint

    translated_json = await create_translation(
        async_client_translator=async_client_translator,
        source_data_model_id=dataset_transform_deep_literal_attribute.source_data_model_id,
        target_data_model_id=dataset_transform_deep_literal_attribute.target_data_model_id,
        json_to_translate={"Person": {"Courses": {"Grade": "A", "Style": "Lecture"}}},
        headers=mdr_api_headers,
    )
    assert translated_json == {"User": "A"}


@pytest.mark.asyncio
async def test_create_transform_fail_empty_source_attribute_path(async_client_mdr, async_client_translator):
    """
    Confirms an empty source attribute path is rejected.

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
        source_entity_path="",  # This is the point of the test!
        target_parent_entity_id=dataset_transform_deep_literal_attribute.target_parent_entity_id,
        target_attribute_id=dataset_transform_deep_literal_attribute.target_attribute_id,
        target_entity_path="0,0",  # Doesn't matter for this test
        mapping_expression='{ "User": { "Skills": { "Genre": Person.Courses.Grade } } }',
        transformation_name="User.Skills.Genre",
        expected_status_code=400,
        expected_response={"detail": "Invalid EntityIdPath format. The path must not be empty."},
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


@pytest.mark.asyncio
async def test_transforms_with_embeddings(async_client_mdr, async_client_translator, mdr_api_headers):
    """
    Transform source and target attributes both from their original location and their entity embedded location.

    Source and Target are source schemas.

    """

    test_case_name = inspect.currentframe().f_code.co_name
    group_contributor = f"{test_case_name}_contributor"
    group_contributor_organization = f"{test_case_name}_contributor_org"
    group_description = "group description"
    group_notes = "group notes"
    # Not precisely like the UX, that only sends the YYYY-MM-DD,
    # but using the full format to avoid timezone issues with testing
    group_creation_date = "2026-03-01T00:00:00Z"
    group_activation_date = "2026-03-02T00:00:00Z"
    group_deprecation_date = "2026-03-03T00:00:00Z"

    dataset_transform_with_embeddings = await DatasetTransformWithEmbeddings.prepare(
        async_client_mdr=async_client_mdr,
        source_data_model_name=test_case_name,
        target_data_model_name=test_case_name,
        transformation_group_name=test_case_name,
        transformation_group_contributor=group_contributor,
        transformation_group_contributor_organization=group_contributor_organization,
        transformation_group_description=group_description,
        transformation_group_notes=group_notes,
        transformation_group_creation_date=group_creation_date,
        transformation_group_activation_date=group_activation_date,
        transformation_group_deprecation_date=group_deprecation_date,
    )

    # Create transformations
    transformation1__contributor = f"{test_case_name}_transformation1_contributor"
    transformation1__contributor_organization = f"{test_case_name}_contributor_org"
    transformation1__description = "transformation1 description"
    transformation1__notes = "transformation1 notes"
    # Not precisely like the UX, that only sends the YYYY-MM-DD,
    # but using the full format to avoid timezone issues with testing
    transformation1__creation_date = "2021-03-01T00:00:00Z"
    transformation1__activation_date = "2021-03-02T00:00:00Z"
    transformation1__deprecation_date = "2021-03-03T00:00:00Z"
    transformation1_data = await create_transformation(
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

    transformation2_data = await create_transformation(
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

    transformation3_data = await create_transformation(
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

    transformation_data_to_be_deleted = await create_transformation(
        async_client_mdr=async_client_mdr,
        transformation_group_id=dataset_transform_with_embeddings.transformation_group_id,
        source_parent_entity_id=None,
        source_attribute_id=dataset_transform_with_embeddings.flow3_source_attribute_id,
        source_entity_path=dataset_transform_with_embeddings.flow3_source_entity_id_path,
        target_parent_entity_id=None,
        target_attribute_id=dataset_transform_with_embeddings.flow3_target_attribute_id,
        target_entity_path=dataset_transform_with_embeddings.flow3_target_entity_id_path,
        mapping_expression="{ }",
        transformation_name="Transformation To Be Deleted",
    )

    await delete_transformation(
        async_client_mdr=async_client_mdr, transformation_id=transformation_data_to_be_deleted["Id"]
    )

    # Add a non-JSONata transformation to confirm it is ignored in the export
    await create_transformation(
        async_client_mdr=async_client_mdr,
        transformation_group_id=dataset_transform_with_embeddings.transformation_group_id,
        source_parent_entity_id=None,
        source_attribute_id=dataset_transform_with_embeddings.flow2_source_attribute_id,
        source_entity_path=dataset_transform_with_embeddings.flow2_source_entity_id_path,
        target_parent_entity_id=None,
        target_attribute_id=dataset_transform_with_embeddings.flow2_target_attribute_id,
        target_entity_path=dataset_transform_with_embeddings.flow2_target_entity_id_path,
        expression_language="LIF_Pseudo_Code",
        mapping_expression="foo(bar())",
        transformation_name="Non-JSONata expression!",
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
        headers=mdr_api_headers,
    )
    assert translated_json == {
        "User": {
            "Workplace": {"Abilities": {"Skills": {"LevelOfSkillAbility": "Mastery"}}},
            "Abilities": {"Skills": {"LevelOfSkillAbility": "10 Years"}},
            "Preferences": {"WorkPreference": "Advanced"},
        }
    }

    # Check the export

    export_data = await export_transformation_group(
        async_client_mdr=async_client_mdr,
        transformation_group_id=dataset_transform_with_embeddings.transformation_group_id,
        headers=mdr_api_headers,
        expected_status_code=200,
    )
    source_data_model_id = dataset_transform_with_embeddings.source_data_model_id
    target_data_model_id = dataset_transform_with_embeddings.target_data_model_id
    expected_data = {
        "Id": dataset_transform_with_embeddings.transformation_group_id,
        "SourceDataModelId": source_data_model_id,
        "TargetDataModelId": target_data_model_id,
        "SourceDataModelName": f"{test_case_name}_source",
        "TargetDataModelName": f"{test_case_name}_target",
        "SourceDataModel": None,
        "TargetDataModel": None,
        "Name": f"{test_case_name}_transform_group",
        "GroupVersion": "1.0",
        "Description": group_description,
        "Notes": group_notes,
        "CreationDate": group_creation_date,
        "ActivationDate": group_activation_date,
        "DeprecationDate": group_deprecation_date,
        "Contributor": group_contributor,
        "ContributorOrganization": group_contributor_organization,
        "Transformations": [
            {
                "Id": transformation1_data["Id"],
                "TransformationGroupId": dataset_transform_with_embeddings.transformation_group_id,
                "Name": "User.Workplace.Abilities.Skills.LevelOfSkillAbility",
                "Expression": "",  # Check later on
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
                        "AttributeId": dataset_transform_with_embeddings.flow1_source_attribute_id,
                        "EntityId": dataset_transform_with_embeddings.flow1_source_parent_entity_id,
                        "AttributeName": "SkillLevel",
                        "AttributeType": "Source",
                        "Notes": None,
                        "CreationDate": None,
                        "ActivationDate": None,
                        "DeprecationDate": None,
                        "Contributor": None,
                        "ContributorOrganization": None,
                        "EntityIdPath": f"{source_data_model_id}:person,{source_data_model_id}:person.courses,{source_data_model_id}:person.courses.skillsgainedfromcourses,{source_data_model_id}:~person.courses.skillsgainedfromcourses.skilllevel",
                    }
                ],
                "TargetAttribute": {
                    "AttributeId": dataset_transform_with_embeddings.flow1_target_attribute_id,
                    "EntityId": dataset_transform_with_embeddings.flow1_target_parent_entity_id,
                    "AttributeName": "LevelOfSkillAbility",
                    "AttributeType": "Target",
                    "Notes": None,
                    "CreationDate": None,
                    "ActivationDate": None,
                    "DeprecationDate": None,
                    "Contributor": None,
                    "ContributorOrganization": None,
                    "EntityIdPath": f"{target_data_model_id}:user,{target_data_model_id}:user.abilities,{target_data_model_id}:user.abilities.skills,{target_data_model_id}:~user.abilities.skills.levelofskillability",
                },
            },
            {
                "Id": transformation2_data["Id"],
                "TransformationGroupId": dataset_transform_with_embeddings.transformation_group_id,
                "Name": "User.Abilities.Skills.LevelOfSkillAbility",
                "Expression": "",  # Check later on
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
                        "AttributeId": dataset_transform_with_embeddings.flow2_source_attribute_id,
                        "EntityId": dataset_transform_with_embeddings.flow2_source_parent_entity_id,
                        "AttributeName": "DurationAtProfession",
                        "AttributeType": "Source",
                        "Notes": None,
                        "CreationDate": None,
                        "ActivationDate": None,
                        "DeprecationDate": None,
                        "Contributor": None,
                        "ContributorOrganization": None,
                        "EntityIdPath": f"{source_data_model_id}:person,{source_data_model_id}:person.employment,{source_data_model_id}:person.employment.profession,{source_data_model_id}:~person.employment.profession.durationatprofession",
                    }
                ],
                "TargetAttribute": {
                    "AttributeId": dataset_transform_with_embeddings.flow2_target_attribute_id,
                    "EntityId": dataset_transform_with_embeddings.flow2_target_parent_entity_id,
                    "AttributeName": "LevelOfSkillAbility",
                    "AttributeType": "Target",
                    "Notes": None,
                    "CreationDate": None,
                    "ActivationDate": None,
                    "DeprecationDate": None,
                    "Contributor": None,
                    "ContributorOrganization": None,
                    "EntityIdPath": f"{target_data_model_id}:user,{target_data_model_id}:user.abilities,{target_data_model_id}:user.abilities.skills,{target_data_model_id}:~user.abilities.skills.levelofskillability",
                },
            },
            {
                "Id": transformation3_data["Id"],
                "TransformationGroupId": dataset_transform_with_embeddings.transformation_group_id,
                "Name": "User.Preferences.WorkPreference",
                "Expression": "",  # Check later on
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
                        "AttributeId": dataset_transform_with_embeddings.flow3_source_attribute_id,
                        "EntityId": dataset_transform_with_embeddings.flow3_source_parent_entity_id,
                        "AttributeName": "SkillLevel",
                        "AttributeType": "Source",
                        "Notes": None,
                        "CreationDate": None,
                        "ActivationDate": None,
                        "DeprecationDate": None,
                        "Contributor": None,
                        "ContributorOrganization": None,
                        "EntityIdPath": f"{source_data_model_id}:person,{source_data_model_id}:person.courses,{source_data_model_id}:person.courses.skillsgainedfromcourses,{source_data_model_id}:~person.courses.skillsgainedfromcourses.skilllevel",
                    }
                ],
                "TargetAttribute": {
                    "AttributeId": dataset_transform_with_embeddings.flow3_target_attribute_id,
                    "EntityId": dataset_transform_with_embeddings.flow3_target_parent_entity_id,
                    "AttributeName": "WorkPreference",
                    "AttributeType": "Target",
                    "Notes": None,
                    "CreationDate": None,
                    "ActivationDate": None,
                    "DeprecationDate": None,
                    "Contributor": None,
                    "ContributorOrganization": None,
                    "EntityIdPath": f"{target_data_model_id}:user,{target_data_model_id}:user.preferences,{target_data_model_id}:~user.preferences.workpreference",
                },
            },
        ],
        "Tags": None,
    }
    diff = DeepDiff(
        export_data, expected_data, exclude_regex_paths=[r"root\['Transformations'\]\[\d+\]\['Expression'\]"]
    )
    assert diff == {}, diff

    # Check expressions
    cleaned_expression0_actual = _clean_jsonata_expression(export_data["Transformations"][0]["Expression"])
    cleaned_expression0_expected = _clean_jsonata_expression(
        '{ "User": { "Workplace": { "Abilities": { "Skills": { "LevelOfSkillAbility": Person.Employment.SkillsGainedFromCourses.SkillLevel } } } } }'
    )
    assert cleaned_expression0_actual == cleaned_expression0_expected
    cleaned_expression1_actual = _clean_jsonata_expression(export_data["Transformations"][1]["Expression"])
    cleaned_expression1_expected = _clean_jsonata_expression(
        '{ "User": { "Abilities": { "Skills": { "LevelOfSkillAbility": Person.Employment.Profession.DurationAtProfession } } } }'
    )
    assert cleaned_expression1_actual == cleaned_expression1_expected
    cleaned_expression2_actual = _clean_jsonata_expression(export_data["Transformations"][2]["Expression"])
    cleaned_expression2_expected = _clean_jsonata_expression(
        '{ "User": { "Preferences": { "WorkPreference": Person.Courses.SkillsGainedFromCourses.SkillLevel } } }'
    )
    assert cleaned_expression2_actual == cleaned_expression2_expected


@pytest.mark.asyncio
async def test_transforms_export_fail_with_no_transforms(async_client_mdr, mdr_api_headers):
    """
    Confirms the export will fail nicely if there are no transformations in the group.

    """

    test_case_name = inspect.currentframe().f_code.co_name
    group_contributor = f"{test_case_name}_contributor"
    group_contributor_organization = f"{test_case_name}_contributor_org"
    group_description = "group description"
    group_notes = "group notes"
    # Not precisely like the UX, that only sends the YYYY-MM-DD,
    # but using the full format to avoid timezone issues with testing
    group_creation_date = "2026-03-01T00:00:00Z"
    group_activation_date = "2026-03-02T00:00:00Z"
    group_deprecation_date = "2026-03-03T00:00:00Z"

    dataset_transform_with_embeddings = await DatasetTransformWithEmbeddings.prepare(
        async_client_mdr=async_client_mdr,
        source_data_model_name=test_case_name,
        target_data_model_name=test_case_name,
        transformation_group_name=test_case_name,
        transformation_group_contributor=group_contributor,
        transformation_group_contributor_organization=group_contributor_organization,
        transformation_group_description=group_description,
        transformation_group_notes=group_notes,
        transformation_group_creation_date=group_creation_date,
        transformation_group_activation_date=group_activation_date,
        transformation_group_deprecation_date=group_deprecation_date,
    )

    await export_transformation_group(
        async_client_mdr=async_client_mdr,
        transformation_group_id=dataset_transform_with_embeddings.transformation_group_id,
        headers=mdr_api_headers,
        expected_status_code=400,
        expected_response_data={
            "detail": (
                "There are no valid transformations to export for this group / version. "
                "Please add a transformation to this group's version and retry the export."
            )
        },
    )


@pytest.mark.asyncio
async def test_transforms_export_fail_with_only_non_jsonata_transform(async_client_mdr, mdr_api_headers):
    """
    Confirms the export will fail nicely if there are no JSONata transformations in the group.

    """

    test_case_name = inspect.currentframe().f_code.co_name
    group_contributor = f"{test_case_name}_contributor"
    group_contributor_organization = f"{test_case_name}_contributor_org"
    group_description = "group description"
    group_notes = "group notes"
    # Not precisely like the UX, that only sends the YYYY-MM-DD,
    # but using the full format to avoid timezone issues with testing
    group_creation_date = "2026-03-01T00:00:00Z"
    group_activation_date = "2026-03-02T00:00:00Z"
    group_deprecation_date = "2026-03-03T00:00:00Z"

    dataset_transform_with_embeddings = await DatasetTransformWithEmbeddings.prepare(
        async_client_mdr=async_client_mdr,
        source_data_model_name=test_case_name,
        target_data_model_name=test_case_name,
        transformation_group_name=test_case_name,
        transformation_group_contributor=group_contributor,
        transformation_group_contributor_organization=group_contributor_organization,
        transformation_group_description=group_description,
        transformation_group_notes=group_notes,
        transformation_group_creation_date=group_creation_date,
        transformation_group_activation_date=group_activation_date,
        transformation_group_deprecation_date=group_deprecation_date,
    )

    await create_transformation(
        async_client_mdr=async_client_mdr,
        transformation_group_id=dataset_transform_with_embeddings.transformation_group_id,
        source_parent_entity_id=None,
        source_attribute_id=dataset_transform_with_embeddings.flow2_source_attribute_id,
        source_entity_path=dataset_transform_with_embeddings.flow2_source_entity_id_path,
        target_parent_entity_id=None,
        target_attribute_id=dataset_transform_with_embeddings.flow2_target_attribute_id,
        target_entity_path=dataset_transform_with_embeddings.flow2_target_entity_id_path,
        expression_language="LIF_Pseudo_Code",
        mapping_expression="foo(bar())",
        transformation_name="Non-JSONata expression!",
    )

    await export_transformation_group(
        async_client_mdr=async_client_mdr,
        transformation_group_id=dataset_transform_with_embeddings.transformation_group_id,
        headers=mdr_api_headers,
        expected_status_code=400,
        expected_response_data={
            "detail": (
                "There are no valid transformations to export for this group / version. "
                "Please add a transformation to this group's version and retry the export."
            )
        },
    )


@pytest.mark.asyncio
async def test_transforms_export_fail_with_only_deleted_jsonata_transform(async_client_mdr, mdr_api_headers):
    """
    Confirms the export will fail nicely if there are no active JSONata transformations in the group.

    """

    test_case_name = inspect.currentframe().f_code.co_name
    group_contributor = f"{test_case_name}_contributor"
    group_contributor_organization = f"{test_case_name}_contributor_org"
    group_description = "group description"
    group_notes = "group notes"
    # Not precisely like the UX, that only sends the YYYY-MM-DD,
    # but using the full format to avoid timezone issues with testing
    group_creation_date = "2026-03-01T00:00:00Z"
    group_activation_date = "2026-03-02T00:00:00Z"
    group_deprecation_date = "2026-03-03T00:00:00Z"

    dataset_transform_with_embeddings = await DatasetTransformWithEmbeddings.prepare(
        async_client_mdr=async_client_mdr,
        source_data_model_name=test_case_name,
        target_data_model_name=test_case_name,
        transformation_group_name=test_case_name,
        transformation_group_contributor=group_contributor,
        transformation_group_contributor_organization=group_contributor_organization,
        transformation_group_description=group_description,
        transformation_group_notes=group_notes,
        transformation_group_creation_date=group_creation_date,
        transformation_group_activation_date=group_activation_date,
        transformation_group_deprecation_date=group_deprecation_date,
    )

    transform_data = await create_transformation(
        async_client_mdr=async_client_mdr,
        transformation_group_id=dataset_transform_with_embeddings.transformation_group_id,
        source_parent_entity_id=None,
        source_attribute_id=dataset_transform_with_embeddings.flow2_source_attribute_id,
        source_entity_path=dataset_transform_with_embeddings.flow2_source_entity_id_path,
        target_parent_entity_id=None,
        target_attribute_id=dataset_transform_with_embeddings.flow2_target_attribute_id,
        target_entity_path=dataset_transform_with_embeddings.flow2_target_entity_id_path,
        mapping_expression="{}",
        transformation_name="Will be deleted!",
    )

    await delete_transformation(async_client_mdr=async_client_mdr, transformation_id=transform_data["Id"])

    await export_transformation_group(
        async_client_mdr=async_client_mdr,
        transformation_group_id=dataset_transform_with_embeddings.transformation_group_id,
        headers=mdr_api_headers,
        expected_status_code=400,
        expected_response_data={
            "detail": (
                "There are no valid transformations to export for this group / version. "
                "Please add a transformation to this group's version and retry the export."
            )
        },
    )


@pytest.mark.asyncio
async def test_update_transform_only_expression(async_client_mdr, async_client_translator, mdr_api_headers):
    """
    Confirms a transformation update can occur for just the expression.

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

    transformation = await create_transformation(
        async_client_mdr=async_client_mdr,
        transformation_group_id=dataset_transform_deep_literal_attribute.transformation_group_id,
        source_parent_entity_id=dataset_transform_deep_literal_attribute.source_parent_entity_id,
        source_attribute_id=dataset_transform_deep_literal_attribute.source_attribute_id,
        source_entity_path=dataset_transform_deep_literal_attribute.source_entity_id_path,
        target_parent_entity_id=dataset_transform_deep_literal_attribute.target_parent_entity_id,
        target_attribute_id=dataset_transform_deep_literal_attribute.target_attribute_id,
        target_entity_path=dataset_transform_deep_literal_attribute.target_entity_id_path,
        mapping_expression='{ "User": { "Skills": { "Genre": Person.Courses.Grade } } }',
        transformation_name="User.Skills.Genre",
    )

    # Use the transform via the Translator endpoint to prove original translation

    json_to_translate = {"Person": {"Courses": {"Grade": "K"}}}
    translated_json = await create_translation(
        async_client_translator=async_client_translator,
        source_data_model_id=dataset_transform_deep_literal_attribute.source_data_model_id,
        target_data_model_id=dataset_transform_deep_literal_attribute.target_data_model_id,
        json_to_translate=json_to_translate,
        headers=mdr_api_headers,
    )
    assert translated_json == {"User": {"Skills": {"Genre": "K"}}}

    _ = await update_transformation(
        async_client_mdr=async_client_mdr,
        original_transformation=transformation,
        expression='{ "User": { "Skills": { "Genre": Person.Courses } } }',
    )

    # Use the transform via the Translator endpoint to prove the updated expression

    translated_json = await create_translation(
        async_client_translator=async_client_translator,
        source_data_model_id=dataset_transform_deep_literal_attribute.source_data_model_id,
        target_data_model_id=dataset_transform_deep_literal_attribute.target_data_model_id,
        json_to_translate=json_to_translate,
        headers=mdr_api_headers,
    )
    assert translated_json == {"User": {"Skills": {"Genre": {"Grade": "K"}}}}


@pytest.mark.asyncio
async def test_get_transformation_groups_exportable(async_client_mdr, mdr_api_headers):
    """
    The transformation-groups listing carries portable (name, version, org) refs for
    source/target only when exportable=true; otherwise those fields stay null.
    """

    test_case_name = inspect.currentframe().f_code.co_name

    dataset = await DatasetTransformDeepLiteralAttribute.prepare(
        async_client_mdr=async_client_mdr,
        source_data_model_name=f"{test_case_name}_source",
        target_data_model_name=f"{test_case_name}_target",
        transformation_group_name=f"{test_case_name}_transform_group",
    )

    # exportable=true -> each group includes the portable source/target refs.
    response = await async_client_mdr.get(
        "/transformation_groups/",
        headers=mdr_api_headers,
        params={"source_data_model_id": dataset.source_data_model_id, "exportable": "true", "pagination": "false"},
    )
    assert response.status_code == 200, response.text
    groups = response.json()["data"]
    group = next(g for g in groups if g["Id"] == dataset.transformation_group_id)

    # Data models created via upload use version "1.0" with no contributor organization.
    assert group["SourceDataModel"] == {
        "name": f"{test_case_name}_source",
        "version": "1.0",
        "contributorOrganization": None,
    }
    assert group["TargetDataModel"] == {
        "name": f"{test_case_name}_target",
        "version": "1.0",
        "contributorOrganization": None,
    }

    # Default (exportable not set) -> portable refs are null.
    response = await async_client_mdr.get(
        "/transformation_groups/",
        headers=mdr_api_headers,
        params={"source_data_model_id": dataset.source_data_model_id, "pagination": "false"},
    )
    assert response.status_code == 200, response.text
    group = next(g for g in response.json()["data"] if g["Id"] == dataset.transformation_group_id)
    assert group["SourceDataModel"] is None
    assert group["TargetDataModel"] is None


# --- Import transformation group (#772) -------------------------------------------------------


def _transform_signature(transformation: dict) -> tuple:
    """Comparable identity of an exported transformation, independent of DB IDs — its name,
    (whitespace-normalized) expression, and portable source/target attribute paths."""
    return (
        transformation["Name"],
        _clean_jsonata_expression(transformation["Expression"] or ""),
        tuple(sorted(sa["EntityIdPath"] for sa in (transformation["SourceAttributes"] or []))),
        (transformation["TargetAttribute"] or {}).get("EntityIdPath"),
    )


async def _prepare_group_with_two_jsonata_transforms(async_client_mdr, test_case_name: str):
    """Create a source/target/group dataset with two JSONata transformations, then export it.

    Returns (dataset, exported_group_json) — the exported JSON is a valid import body.
    """
    dataset = await DatasetTransformWithEmbeddings.prepare(
        async_client_mdr=async_client_mdr,
        source_data_model_name=test_case_name,
        target_data_model_name=test_case_name,
        transformation_group_name=test_case_name,
    )
    await create_transformation(
        async_client_mdr=async_client_mdr,
        transformation_group_id=dataset.transformation_group_id,
        source_parent_entity_id=None,
        source_attribute_id=dataset.flow1_source_attribute_id,
        source_entity_path=dataset.flow1_source_entity_id_path,
        target_parent_entity_id=None,
        target_attribute_id=dataset.flow1_target_attribute_id,
        target_entity_path=dataset.flow1_target_entity_id_path,
        mapping_expression=(
            '{ "User": { "Workplace": { "Abilities": { "Skills": '
            '{ "LevelOfSkillAbility": Person.Employment.SkillsGainedFromCourses.SkillLevel } } } } }'
        ),
        transformation_name="User.Workplace.Abilities.Skills.LevelOfSkillAbility",
    )
    await create_transformation(
        async_client_mdr=async_client_mdr,
        transformation_group_id=dataset.transformation_group_id,
        source_parent_entity_id=None,
        source_attribute_id=dataset.flow2_source_attribute_id,
        source_entity_path=dataset.flow2_source_entity_id_path,
        target_parent_entity_id=None,
        target_attribute_id=dataset.flow2_target_attribute_id,
        target_entity_path=dataset.flow2_target_entity_id_path,
        mapping_expression=(
            '{ "User": { "Abilities": { "Skills": '
            '{ "LevelOfSkillAbility": Person.Employment.Profession.DurationAtProfession } } } }'
        ),
        transformation_name="User.Abilities.Skills.LevelOfSkillAbility",
    )
    exported = await export_transformation_group(
        async_client_mdr=async_client_mdr, transformation_group_id=dataset.transformation_group_id
    )
    return dataset, exported


@pytest.mark.asyncio
async def test_import_transformation_group_round_trip_clone(async_client_mdr, mdr_api_headers):
    """Export a group, import it back with a blank version, and confirm it clones into the next
    major version with byte-for-byte identical portable transformation paths (same-DB round trip)."""
    test_case_name = inspect.currentframe().f_code.co_name
    dataset, exported = await _prepare_group_with_two_jsonata_transforms(async_client_mdr, test_case_name)

    result = await import_transformation_group(
        async_client_mdr=async_client_mdr,
        transformation_group_id=dataset.transformation_group_id,
        body=exported,
        version=None,  # blank -> clone into the next major version
        headers=mdr_api_headers,
    )

    assert result["Success"] is True
    assert result["SkippedTransformations"] == []
    assert result["ImportedTransformationCount"] == 2
    new_group_id = result["TransformationGroupId"]
    assert new_group_id is not None
    assert new_group_id != dataset.transformation_group_id

    new_export = await export_transformation_group(
        async_client_mdr=async_client_mdr, transformation_group_id=new_group_id, headers=mdr_api_headers
    )
    assert new_export["GroupVersion"] == "2.0"
    assert sorted(_transform_signature(t) for t in new_export["Transformations"]) == sorted(
        _transform_signature(t) for t in exported["Transformations"]
    )


@pytest.mark.asyncio
async def test_import_missing_paths_aborts_without_allow(async_client_mdr, mdr_api_headers):
    """A path whose UniqueName does not resolve is a non-match; without allowMissingPaths the whole
    import fails, lists the skipped transformation with the reason, and makes no changes (no new
    group)."""
    test_case_name = inspect.currentframe().f_code.co_name
    dataset, exported = await _prepare_group_with_two_jsonata_transforms(async_client_mdr, test_case_name)

    body = copy.deepcopy(exported)
    # Corrupt the first transformation's target path to reference a non-existent attribute. The
    # numeric prefix is ignored on import, so only the bogus UniqueName drives the miss.
    body["Transformations"][0]["TargetAttribute"]["EntityIdPath"] = "999:~totally.bogus.attribute"

    result = await import_transformation_group(
        async_client_mdr=async_client_mdr,
        transformation_group_id=dataset.transformation_group_id,
        body=body,
        version=None,
        allow_missing_paths=False,
        headers=mdr_api_headers,
    )

    # The corrupted transformation is the sole skip; its reason weaves in the target path and the
    # unresolved UniqueName. The second (untouched) transformation is not reported — it resolved
    # fine and was simply rolled back with everything else.
    assert result == {
        "Success": False,
        "TransformationGroupId": None,
        "ImportedTransformationCount": 0,
        "SkippedTransformationCount": 1,
        "SkippedTransformations": [
            {
                "TransformationName": exported["Transformations"][0]["Name"],
                "Reason": (
                    "no attribute uniquely named 'totally.bogus.attribute' found in the target path "
                    f"999:~totally.bogus.attribute in data model {test_case_name}_target "
                    f"({dataset.target_data_model_id}) (or its base model)"
                ),
            }
        ],
    }

    # No new (2.0) group should have been created — the transaction was rolled back.
    response = await async_client_mdr.get(
        "/transformation_groups/",
        headers=mdr_api_headers,
        params={
            "source_data_model_id": dataset.source_data_model_id,
            "target_data_model_id": dataset.target_data_model_id,
            "pagination": "false",
        },
    )
    assert response.status_code == 200, response.text
    assert "2.0" not in {g["GroupVersion"] for g in response.json()["data"]}


@pytest.mark.asyncio
async def test_import_lone_attribute_path_is_a_non_match(async_client_mdr, mdr_api_headers):
    """A single-segment path (attribute with no owning-entity segment) resolves by name but has no
    entity to satisfy the NOT NULL TransformationAttributes.EntityId. It must surface as a normal
    non-match rather than blowing up as an opaque IntegrityError."""
    test_case_name = inspect.currentframe().f_code.co_name
    dataset, exported = await _prepare_group_with_two_jsonata_transforms(async_client_mdr, test_case_name)

    body = copy.deepcopy(exported)
    # Reduce the target path to just its terminal attribute segment — a valid attribute UniqueName,
    # but with the owning entity stripped off.
    full_target_path = body["Transformations"][0]["TargetAttribute"]["EntityIdPath"]
    lone_attribute_path = full_target_path.split(",")[-1]
    body["Transformations"][0]["TargetAttribute"]["EntityIdPath"] = lone_attribute_path

    result = await import_transformation_group(
        async_client_mdr=async_client_mdr,
        transformation_group_id=dataset.transformation_group_id,
        body=body,
        version=None,
        allow_missing_paths=False,
        headers=mdr_api_headers,
    )

    assert result == {
        "Success": False,
        "TransformationGroupId": None,
        "ImportedTransformationCount": 0,
        "SkippedTransformationCount": 1,
        "SkippedTransformations": [
            {
                "TransformationName": exported["Transformations"][0]["Name"],
                "Reason": f"the target path {lone_attribute_path} must include the attribute's owning entity",
            }
        ],
    }


@pytest.mark.asyncio
async def test_import_missing_paths_skipped_with_allow(async_client_mdr, mdr_api_headers):
    """With allowMissingPaths, a transformation with an unmatched path is skipped whole while the
    rest import; the response lists the skipped transformation."""
    test_case_name = inspect.currentframe().f_code.co_name
    dataset, exported = await _prepare_group_with_two_jsonata_transforms(async_client_mdr, test_case_name)

    body = copy.deepcopy(exported)
    body["Transformations"][0]["TargetAttribute"]["EntityIdPath"] = "999:~totally.bogus.attribute"

    result = await import_transformation_group(
        async_client_mdr=async_client_mdr,
        transformation_group_id=dataset.transformation_group_id,
        body=body,
        version=None,
        allow_missing_paths=True,
        headers=mdr_api_headers,
    )

    imported_group_id = result["TransformationGroupId"]
    assert imported_group_id is not None
    assert result == {
        "Success": True,
        "TransformationGroupId": imported_group_id,
        "ImportedTransformationCount": 1,  # only the untouched (second) transformation
        "SkippedTransformationCount": 1,
        "SkippedTransformations": [
            {
                "TransformationName": exported["Transformations"][0]["Name"],
                "Reason": (
                    "no attribute uniquely named 'totally.bogus.attribute' found in the target path "
                    f"999:~totally.bogus.attribute in data model {test_case_name}_target "
                    f"({dataset.target_data_model_id}) (or its base model)"
                ),
            }
        ],
    }

    new_export = await export_transformation_group(
        async_client_mdr=async_client_mdr,
        transformation_group_id=result["TransformationGroupId"],
        headers=mdr_api_headers,
    )
    assert len(new_export["Transformations"]) == 1
    assert new_export["Transformations"][0]["Name"] == exported["Transformations"][1]["Name"]


@pytest.mark.asyncio
async def test_import_empty_transformations_fails(async_client_mdr, mdr_api_headers):
    """A group with no importable transformations imports nothing: a 200 result with Success=false
    and no new group (no empty groups), rather than an HTTP error — clients handle every non-success
    through the one result shape."""
    test_case_name = inspect.currentframe().f_code.co_name
    dataset, exported = await _prepare_group_with_two_jsonata_transforms(async_client_mdr, test_case_name)

    body = copy.deepcopy(exported)
    body["Transformations"] = []

    result = await import_transformation_group(
        async_client_mdr=async_client_mdr,
        transformation_group_id=dataset.transformation_group_id,
        body=body,
        version=None,
        headers=mdr_api_headers,
    )
    assert result == {
        "Success": False,
        "TransformationGroupId": None,
        "ImportedTransformationCount": 0,
        "SkippedTransformationCount": 0,
        "SkippedTransformations": [],
    }


@pytest.mark.asyncio
async def test_import_non_jsonata_transformations_are_reported_as_skipped(async_client_mdr, mdr_api_headers):
    """Non-JSONata transformations are out of scope for portable import. They must be surfaced in the
    response (SkippedTransformations + SkippedTransformationCount), not dropped with the only trace in
    the server log. A file of only non-JSONata transforms imports nothing (Success=false) but explains
    why."""
    test_case_name = inspect.currentframe().f_code.co_name
    dataset, exported = await _prepare_group_with_two_jsonata_transforms(async_client_mdr, test_case_name)

    body = copy.deepcopy(exported)
    for transformation in body["Transformations"]:
        transformation["ExpressionLanguage"] = "LIF_Pseudo_Code"

    result = await import_transformation_group(
        async_client_mdr=async_client_mdr,
        transformation_group_id=dataset.transformation_group_id,
        body=body,
        version=None,
        headers=mdr_api_headers,
    )
    out_of_scope_reason = "non-JSONata expression language 'LIF_Pseudo_Code' is out of scope for portable import"
    assert result == {
        "Success": False,
        "TransformationGroupId": None,
        "ImportedTransformationCount": 0,
        "SkippedTransformationCount": 2,
        "SkippedTransformations": [
            {"TransformationName": body["Transformations"][0]["Name"], "Reason": out_of_scope_reason},
            {"TransformationName": body["Transformations"][1]["Name"], "Reason": out_of_scope_reason},
        ],
    }


@pytest.mark.asyncio
async def test_import_known_version_edit_not_yet_supported(async_client_mdr, mdr_api_headers):
    """Layer 1 boundary: importing into an already-existing version (edit mode) is not yet
    implemented and returns 409 Conflict (with a detail message) rather than silently cloning or
    corrupting the existing group."""
    test_case_name = inspect.currentframe().f_code.co_name
    dataset, exported = await _prepare_group_with_two_jsonata_transforms(async_client_mdr, test_case_name)

    result = await import_transformation_group(
        async_client_mdr=async_client_mdr,
        transformation_group_id=dataset.transformation_group_id,
        body=exported,
        version="1.0",  # already exists for this (source, target)
        headers=mdr_api_headers,
        expected_status_code=409,
    )
    assert "not yet supported" in result["detail"].lower()


@pytest.mark.asyncio
async def test_import_treats_null_deleted_group_as_active(async_client_mdr, test_db_session, mdr_api_headers):
    """A legacy group row with Deleted = NULL still occupies its version in the partial unique index
    (WHERE "Deleted" IS NOT TRUE). The import's next-major computation must count it — matching the
    index — so the clone lands on a free version instead of colliding into an opaque 409. Regression
    for the `== False` vs `IS NOT TRUE` discrepancy."""
    test_case_name = inspect.currentframe().f_code.co_name
    dataset, exported = await _prepare_group_with_two_jsonata_transforms(async_client_mdr, test_case_name)

    # Simulate legacy data: force the v1.0 group's Deleted to NULL — invisible to `== False` but
    # still active per the index. Expire the identity map so later ORM reads see the DB value.
    await test_db_session.execute(
        text('UPDATE "TransformationsGroup" SET "Deleted" = NULL WHERE "Id" = :id'),
        {"id": dataset.transformation_group_id},
    )
    await test_db_session.commit()
    test_db_session.expire_all()

    # Pre-fix this raised a 409 (next-major skipped the NULL-deleted 1.0, then the index rejected the
    # re-created 1.0). Post-fix it correctly skips to 2.0.
    result = await import_transformation_group(
        async_client_mdr=async_client_mdr,
        transformation_group_id=dataset.transformation_group_id,
        body=exported,
        version=None,
        headers=mdr_api_headers,
    )
    assert result["Success"] is True
    new_export = await export_transformation_group(
        async_client_mdr=async_client_mdr,
        transformation_group_id=result["TransformationGroupId"],
        headers=mdr_api_headers,
    )
    assert new_export["GroupVersion"] == "2.0"


def _hand_written_attribute(entity_id_path: str) -> dict:
    """A minimal TransformationAttribute as it appears in a hand-authored import file: only the
    portable named path is needed — no database IDs (AttributeId/EntityId) are required or used."""
    return {"EntityIdPath": entity_id_path}


@pytest.mark.asyncio
async def test_import_hand_edited_group_then_translate_reflects_all_changes(
    async_client_mdr, async_client_translator, mdr_api_headers
):
    """End-to-end: export a group, hand-edit the file (materially change flow1's mapping +
    expression, keep flow2, add a new valid flow3, add a flow4 whose source path is broken, add a
    non-JSONata flow5 that would overwrite flow3's output if applied), import with allowMissingPaths,
    delete the original group, then confirm the Translator output reflects exactly the edits that
    landed — and that flow5's out-of-scope overwrite did NOT.

    Hand-written EntityIdPaths use a dummy "0:" originating-model prefix to prove the prefix is
    ignored on import and paths resolve portably by UniqueName.
    """
    test_case_name = inspect.currentframe().f_code.co_name
    dataset, exported = await _prepare_group_with_two_jsonata_transforms(async_client_mdr, test_case_name)

    transformations = exported["Transformations"]

    # (1) Materially change flow1: remap its output from Employment.SkillsGainedFromCourses.SkillLevel
    #     to Employment.Profession.DurationAtProfession — both the JSONata expression and the source
    #     path change, so the same target now yields "10 Years" instead of "Mastery".
    flow1 = transformations[0]
    flow1["Name"] = "User.Workplace.Abilities.Skills.LevelOfSkillAbility (edited)"
    flow1["Expression"] = (
        '{ "User": { "Workplace": { "Abilities": { "Skills": '
        '{ "LevelOfSkillAbility": Person.Employment.Profession.DurationAtProfession } } } } }'
    )
    flow1["SourceAttributes"] = [
        _hand_written_attribute(
            "0:person,0:person.employment,0:person.employment.profession,"
            "0:~person.employment.profession.durationatprofession"
        )
    ]

    # (2) flow2 (User.Abilities.Skills.LevelOfSkillAbility) is left unchanged.

    # (3) Add a new, valid flow3 by hand: Person.Courses.SkillsGainedFromCourses.SkillLevel
    #     -> User.Preferences.WorkPreference.
    transformations.append(
        {
            "Name": "User.Preferences.WorkPreference",
            "Expression": (
                '{ "User": { "Preferences": { "WorkPreference": Person.Courses.SkillsGainedFromCourses.SkillLevel } } }'
            ),
            "ExpressionLanguage": "JSONata",
            "Notes": None,
            "Alignment": None,
            "CreationDate": None,
            "ActivationDate": None,
            "DeprecationDate": None,
            "Contributor": None,
            "ContributorOrganization": None,
            "SourceAttributes": [
                _hand_written_attribute(
                    "0:person,0:person.courses,0:person.courses.skillsgainedfromcourses,"
                    "0:~person.courses.skillsgainedfromcourses.skilllevel"
                )
            ],
            "TargetAttribute": _hand_written_attribute("0:user,0:user.preferences,0:~user.preferences.workpreference"),
        }
    )

    # (4) Add a flow4 whose SOURCE path is broken (no such attribute) — a non-match that must be
    #     skipped under allowMissingPaths while everything else imports.
    transformations.append(
        {
            "Name": "Broken Source Transform",
            "Expression": '{ "User": { "Preferences": { "SomethingElse": Person.Courses.SkillsGainedFromCourses.SkillLevel } } }',
            "ExpressionLanguage": "JSONata",
            "Notes": None,
            "Alignment": None,
            "CreationDate": None,
            "ActivationDate": None,
            "DeprecationDate": None,
            "Contributor": None,
            "ContributorOrganization": None,
            "SourceAttributes": [_hand_written_attribute("0:~totally.bogus.attribute")],
            "TargetAttribute": _hand_written_attribute("0:user,0:user.preferences,0:~user.preferences.workpreference"),
        }
    )

    # (5) Add a flow5 that is NON-JSONata but otherwise fully valid — every path resolves, and its
    #     expression, IF it were treated as JSONata, would overwrite flow3's WorkPreference ("Advanced")
    #     with "Mastery". It must be dropped at import (out of scope) so the translated shape below is
    #     unaffected — proving the skip happens before anything lands in the DB, not just in the logs.
    transformations.append(
        {
            "Name": "Non-JSONata WorkPreference Overwrite",
            "Expression": (
                '{ "User": { "Preferences": '
                '{ "WorkPreference": Person.Employment.SkillsGainedFromCourses.SkillLevel } } }'
            ),
            "ExpressionLanguage": "LIF_Pseudo_Code",
            "Notes": None,
            "Alignment": None,
            "CreationDate": None,
            "ActivationDate": None,
            "DeprecationDate": None,
            "Contributor": None,
            "ContributorOrganization": None,
            "SourceAttributes": [
                _hand_written_attribute(
                    "0:person,0:person.employment,0:person.employment.skillsgainedfromcourses,"
                    "0:~person.employment.skillsgainedfromcourses.skilllevel"
                )
            ],
            "TargetAttribute": _hand_written_attribute("0:user,0:user.preferences,0:~user.preferences.workpreference"),
        }
    )

    # Import with allowMissingPaths: flow1 (edited) + flow2 + flow3 import; flow4 is skipped for its
    # broken source path and flow5 is skipped as non-JSONata — both reported in SkippedTransformations.
    result = await import_transformation_group(
        async_client_mdr=async_client_mdr,
        transformation_group_id=dataset.transformation_group_id,
        body=exported,
        version=None,
        allow_missing_paths=True,
        headers=mdr_api_headers,
    )
    imported_group_id = result["TransformationGroupId"]
    assert imported_group_id is not None and imported_group_id != dataset.transformation_group_id
    assert result == {
        "Success": True,
        "TransformationGroupId": imported_group_id,
        "ImportedTransformationCount": 3,  # edited flow1 + flow2 + new flow3
        "SkippedTransformationCount": 2,  # flow4 (broken source) + flow5 (non-JSONata)
        "SkippedTransformations": [
            {
                "TransformationName": "Broken Source Transform",
                "Reason": (
                    "no attribute uniquely named 'totally.bogus.attribute' found in the source path "
                    f"0:~totally.bogus.attribute in data model {test_case_name}_source "
                    f"({dataset.source_data_model_id}) (or its base model)"
                ),
            },
            {
                "TransformationName": "Non-JSONata WorkPreference Overwrite",
                "Reason": "non-JSONata expression language 'LIF_Pseudo_Code' is out of scope for portable import",
            },
        ],
    }

    # Delete the ORIGINAL group so only the imported (v2.0) group serves this source/target pair.
    await delete_transformation_group(
        async_client_mdr=async_client_mdr, transformation_group_id=dataset.transformation_group_id
    )

    translated_json = await create_translation(
        async_client_translator=async_client_translator,
        source_data_model_id=dataset.source_data_model_id,
        target_data_model_id=dataset.target_data_model_id,
        json_to_translate={
            "Person": {
                "Employment": {
                    "SkillsGainedFromCourses": {"SkillLevel": "Mastery"},
                    "Profession": {"DurationAtProfession": "10 Years"},
                },
                "Courses": {"SkillsGainedFromCourses": {"SkillLevel": "Advanced"}},
            }
        },
        headers=mdr_api_headers,
    )
    assert translated_json == {
        "User": {
            # flow1 (edited) now maps DurationAtProfession -> "10 Years" (was "Mastery").
            "Workplace": {"Abilities": {"Skills": {"LevelOfSkillAbility": "10 Years"}}},
            # flow2 (unchanged) still supplies this.
            "Abilities": {"Skills": {"LevelOfSkillAbility": "10 Years"}},
            # flow3 (hand-added) supplies WorkPreference = "Advanced". It is NOT "Mastery": flow5's
            # non-JSONata overwrite was dropped at import, never reaching the DB. No "SomethingElse"
            # either: flow4 was skipped for its broken source path.
            "Preferences": {"WorkPreference": "Advanced"},
        }
    }


async def _make_data_model(session, name: str, model_type: DataModelType, base_data_model_id: int | None) -> int:
    dm = DataModel(
        Name=name,
        Description=None,
        UseConsiderations=None,
        Type=model_type,
        BaseDataModelId=base_data_model_id,
        Notes=None,
        DataModelVersion="1.0",
        ContributorOrganization="test",
        Deleted=False,
    )
    session.add(dm)
    await session.flush()
    return dm.Id


@pytest.mark.asyncio
async def test_get_unique_attribute_prefers_org_override_over_base(test_db_session):
    """For an Org/Partner LIF anchor, when the same UniqueName exists in both the base model and the
    anchor, the anchor's own (override) attribute must win. The base row is inserted first so that a
    bare `.first()` (no ORDER BY) would return the base — this locks in the anchor-preferring order."""
    base_id = await _make_data_model(test_db_session, "unique_attr_base", DataModelType.BaseLIF, None)
    org_id = await _make_data_model(test_db_session, "unique_attr_org", DataModelType.OrgLIF, base_id)

    # Insert the BASE row first, the ORG override second — physical order favours base for an
    # unordered scan, so returning the org row proves the ordering is doing the work.
    base_attr = Attribute(Name="Skill Level", UniqueName="shared.attr", DataModelId=base_id, DataType="string")
    org_attr = Attribute(Name="Skill Level", UniqueName="shared.attr", DataModelId=org_id, DataType="string")
    test_db_session.add(base_attr)
    await test_db_session.flush()
    test_db_session.add(org_attr)
    await test_db_session.flush()

    resolved = await get_unique_attribute(
        session=test_db_session,
        unique_name="shared.attr",
        data_model_id=org_id,
        base_data_model_id=base_id,
        data_model_type=DataModelType.OrgLIF,
    )
    assert resolved is not None
    assert resolved.Id == org_attr.Id
    assert resolved.DataModelId == org_id


@pytest.mark.asyncio
async def test_get_unique_entity_prefers_org_override_over_base(test_db_session):
    """Entity-side mirror of the attribute preference: an org override entity must win over the
    inherited base entity of the same UniqueName."""
    base_id = await _make_data_model(test_db_session, "unique_entity_base", DataModelType.BaseLIF, None)
    org_id = await _make_data_model(test_db_session, "unique_entity_org", DataModelType.OrgLIF, base_id)

    base_entity = Entity(Name="Person", UniqueName="shared.entity", DataModelId=base_id, Deleted=False)
    org_entity = Entity(Name="Person", UniqueName="shared.entity", DataModelId=org_id, Deleted=False)
    test_db_session.add(base_entity)
    await test_db_session.flush()
    test_db_session.add(org_entity)
    await test_db_session.flush()

    resolved = await get_unique_entity(
        session=test_db_session,
        unique_name="shared.entity",
        data_model_id=org_id,
        base_data_model_id=base_id,
        data_model_type=DataModelType.OrgLIF,
    )
    assert resolved is not None
    assert resolved.Id == org_entity.Id
    assert resolved.DataModelId == org_id

import inspect
import re

import pytest
from deepdiff import DeepDiff

from test.utils.lif.datasets.transform_deep_literal_attribute.loader import DatasetTransformDeepLiteralAttribute
from test.utils.lif.datasets.transform_with_embeddings.loader import DatasetTransformWithEmbeddings
from test.utils.lif.mdr.api import (
    convert_unique_names_to_id_path,
    create_transformation,
    export_transformation_group,
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

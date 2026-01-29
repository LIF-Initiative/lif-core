import inspect

import pytest

from test.utils.lif.datasets.transform_deep_literal_attribute.loader import DatasetTransformDeepLiteralAttribute
from test.utils.lif.datasets.transform_with_embeddings.loader import DatasetTransformWithEmbeddings
from test.utils.lif.mdr.api import convert_unique_names_to_id_path, create_transformation, update_transformation
from test.utils.lif.translator.api import create_translation


# Old tests use the name.dot.name format for entityIdPath and once that API logic is
# removed, can be deleted.
@pytest.mark.asyncio
async def test_transforms_deep_literal_attribute_old_api_format(
    async_client_mdr, async_client_translator, mdr_api_headers
):
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
        headers=mdr_api_headers,
    )
    assert translated_json == {"User": {"Skills": {"Genre": "A"}}}


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


# Old tests use the name.dot.name format for entityIdPath and once that API logic is
# removed, can be deleted.
@pytest.mark.asyncio
async def test_transforms_with_embeddings_old_api_format(async_client_mdr, async_client_translator, mdr_api_headers):
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
        headers=mdr_api_headers,
    )
    assert translated_json == {
        "User": {
            "Workplace": {"Abilities": {"Skills": {"LevelOfSkillAbility": "Mastery"}}},
            "Abilities": {"Skills": {"LevelOfSkillAbility": "10 Years"}},
            "Preferences": {"WorkPreference": "Advanced"},
        }
    }


@pytest.mark.asyncio
async def test_transforms_with_embeddings(async_client_mdr, async_client_translator, mdr_api_headers):
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
        headers=mdr_api_headers,
    )
    assert translated_json == {
        "User": {
            "Workplace": {"Abilities": {"Skills": {"LevelOfSkillAbility": "Mastery"}}},
            "Abilities": {"Skills": {"LevelOfSkillAbility": "10 Years"}},
            "Preferences": {"WorkPreference": "Advanced"},
        }
    }


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

from dataclasses import dataclass
from pathlib import Path

from httpx import AsyncClient

from test.utils.lif.mdr.api import (
    convert_unique_names_to_id_path,
    create_data_model_by_upload,
    create_transformation_groups,
    find_object_property_by_unique_name,
)


@dataclass
class DatasetTransformWithEmbeddings:
    source_data_model_id: str
    source_schema: dict
    flow1_source_parent_entity_id: str
    flow1_source_attribute_id: str
    flow1_source_entity_id_path: str
    flow2_source_parent_entity_id: str
    flow2_source_attribute_id: str
    flow2_source_entity_id_path: str
    flow3_source_parent_entity_id: str
    flow3_source_attribute_id: str
    flow3_source_entity_id_path: str
    target_data_model_id: str
    target_schema: dict
    flow1_target_parent_entity_id: str
    flow1_target_attribute_id: str
    flow1_target_entity_id_path: str
    flow2_target_parent_entity_id: str
    flow2_target_attribute_id: str
    flow2_target_entity_id_path: str
    flow3_target_parent_entity_id: str
    flow3_target_attribute_id: str
    flow3_target_entity_id_path: str
    transformation_group_id: str

    @classmethod
    async def prepare(
        cls,
        async_client_mdr: AsyncClient,
        source_data_model_name: str,
        target_data_model_name: str,
        transformation_group_name: str,
    ) -> "DatasetTransformWithEmbeddings":
        """Prepare the dataset by creating source/target data models and transformation group."""

        # Create Source Data Model and extract IDs for the entity and attribute

        (source_data_model_id, source_schema) = await create_data_model_by_upload(
            async_client_mdr=async_client_mdr,
            schema_path=Path(__file__).parent / "transform_with_embeddings_source.json",
            data_model_name=f"{source_data_model_name}_source",
            data_model_type="SourceSchema",
        )

        flow1_source_parent_entity_id = find_object_property_by_unique_name(
            source_schema, "person.courses.skillsgainedfromcourses", "Id"
        )
        assert flow1_source_parent_entity_id is not None, (
            "Could not find source parent entity ID of person.courses.skillsgainedfromcourses... " + str(source_schema)
        )
        flow1_source_attribute_id = find_object_property_by_unique_name(
            source_schema, "person.courses.skillsgainedfromcourses.skilllevel", "Id"
        )
        assert flow1_source_attribute_id is not None, (
            "Could not find source attribute ID of person.courses.skillsgainedfromcourses.skilllevel... "
            + str(source_schema)
        )
        flow1_source_entity_id_path = convert_unique_names_to_id_path(
            source_schema,
            [
                "person",
                "person.courses",
                "person.courses.skillsgainedfromcourses",
                "person.courses.skillsgainedfromcourses.skilllevel",
            ],
            True,
        )

        flow2_source_parent_entity_id = find_object_property_by_unique_name(
            source_schema, "person.employment.profession", "Id"
        )
        assert flow2_source_parent_entity_id is not None, (
            "Could not find source parent entity ID of person.employment.profession... " + str(source_schema)
        )
        flow2_source_attribute_id = find_object_property_by_unique_name(
            source_schema, "person.employment.profession.durationatprofession", "Id"
        )
        assert flow2_source_attribute_id is not None, (
            "Could not find source attribute ID of person.employment.profession.durationatprofession... "
            + str(source_schema)
        )
        flow2_source_entity_id_path = convert_unique_names_to_id_path(
            source_schema,
            [
                "person",
                "person.employment",
                "person.employment.profession",
                "person.employment.profession.durationatprofession",
            ],
            True,
        )

        flow3_source_parent_entity_id = find_object_property_by_unique_name(
            source_schema, "person.courses.skillsgainedfromcourses", "Id"
        )
        assert flow3_source_parent_entity_id is not None, (
            "Could not find source parent entity ID of person.courses.skillsgainedfromcourses... " + str(source_schema)
        )
        flow3_source_attribute_id = find_object_property_by_unique_name(
            source_schema, "person.courses.skillsgainedfromcourses.skilllevel", "Id"
        )
        assert flow3_source_attribute_id is not None, (
            "Could not find source attribute ID of person.courses.skillsgainedfromcourses.skilllevel... "
            + str(source_schema)
        )
        flow3_source_entity_id_path = convert_unique_names_to_id_path(
            source_schema,
            [
                "person",
                "person.courses",
                "person.courses.skillsgainedfromcourses",
                "person.courses.skillsgainedfromcourses.skilllevel",
            ],
            True,
        )

        # Create Target Data Model and extract IDs for the entity and attribute

        (target_data_model_id, target_schema) = await create_data_model_by_upload(
            async_client_mdr=async_client_mdr,
            schema_path=Path(__file__).parent / "transform_with_embeddings_target.json",
            data_model_name=f"{source_data_model_name}_target",
            data_model_type="SourceSchema",
        )
        flow1_target_parent_entity_id = find_object_property_by_unique_name(
            target_schema, "user.abilities.skills", "Id"
        )
        assert flow1_target_parent_entity_id is not None, (
            "Could not find target parent entity ID of user.abilities.skills... " + str(target_schema)
        )
        flow1_target_attribute_id = find_object_property_by_unique_name(
            target_schema, "user.abilities.skills.levelofskillability", "Id"
        )
        assert flow1_target_attribute_id is not None, (
            "Could not find target attribute ID of user.abilities.skills.levelofskillability... " + str(target_schema)
        )
        flow1_target_entity_id_path = convert_unique_names_to_id_path(
            target_schema,
            ["user", "user.abilities", "user.abilities.skills", "user.abilities.skills.levelofskillability"],
            True,
        )

        flow2_target_parent_entity_id = find_object_property_by_unique_name(
            target_schema, "user.abilities.skills", "Id"
        )
        assert flow2_target_parent_entity_id is not None, (
            "Could not find target parent entity ID of user.abilities.skills... " + str(target_schema)
        )
        flow2_target_attribute_id = find_object_property_by_unique_name(
            target_schema, "user.abilities.skills.levelofskillability", "Id"
        )
        assert flow2_target_attribute_id is not None, (
            "Could not find target attribute ID of user.abilities.skills.levelofskillability..." + str(target_schema)
        )
        flow2_target_entity_id_path = convert_unique_names_to_id_path(
            target_schema,
            ["user", "user.abilities", "user.abilities.skills", "user.abilities.skills.levelofskillability"],
            True,
        )

        flow3_target_parent_entity_id = find_object_property_by_unique_name(target_schema, "user.preferences", "Id")
        assert flow3_target_parent_entity_id is not None, (
            "Could not find target parent entity ID of user.preferences... " + str(target_schema)
        )
        flow3_target_attribute_id = find_object_property_by_unique_name(
            target_schema, "user.preferences.workpreference", "Id"
        )
        assert flow3_target_attribute_id is not None, (
            "Could not find target attribute ID of user.preferences.workpreference..." + str(target_schema)
        )
        flow3_target_entity_id_path = convert_unique_names_to_id_path(
            target_schema, ["user", "user.preferences", "user.preferences.workpreference"], True
        )

        # Create transform group between source and target

        transformation_group_id = await create_transformation_groups(
            async_client_mdr=async_client_mdr,
            source_data_model_id=source_data_model_id,
            target_data_model_id=target_data_model_id,
            group_name=f"{transformation_group_name}_transform_group",
        )

        return cls(
            source_data_model_id=source_data_model_id,
            source_schema=source_schema,
            flow1_source_parent_entity_id=flow1_source_parent_entity_id,
            flow1_source_attribute_id=flow1_source_attribute_id,
            flow1_source_entity_id_path=flow1_source_entity_id_path,
            flow2_source_parent_entity_id=flow2_source_parent_entity_id,
            flow2_source_attribute_id=flow2_source_attribute_id,
            flow2_source_entity_id_path=flow2_source_entity_id_path,
            flow3_source_parent_entity_id=flow3_source_parent_entity_id,
            flow3_source_attribute_id=flow3_source_attribute_id,
            flow3_source_entity_id_path=flow3_source_entity_id_path,
            target_data_model_id=target_data_model_id,
            flow1_target_parent_entity_id=flow1_target_parent_entity_id,
            flow1_target_attribute_id=flow1_target_attribute_id,
            flow1_target_entity_id_path=flow1_target_entity_id_path,
            flow2_target_parent_entity_id=flow2_target_parent_entity_id,
            flow2_target_attribute_id=flow2_target_attribute_id,
            flow2_target_entity_id_path=flow2_target_entity_id_path,
            flow3_target_parent_entity_id=flow3_target_parent_entity_id,
            flow3_target_attribute_id=flow3_target_attribute_id,
            flow3_target_entity_id_path=flow3_target_entity_id_path,
            transformation_group_id=transformation_group_id,
            target_schema=target_schema,
        )

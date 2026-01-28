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
class DatasetTransformDeepLiteralAttribute:
    source_data_model_id: str
    source_parent_entity_id: str
    source_attribute_id: str
    source_entity_id_path: str
    source_schema: dict
    target_data_model_id: str
    target_parent_entity_id: str
    target_attribute_id: str
    target_entity_id_path: str
    target_schema: dict
    transformation_group_id: str

    @classmethod
    async def prepare(
        cls,
        async_client_mdr: AsyncClient,
        source_data_model_name: str,
        target_data_model_name: str,
        transformation_group_name: str,
    ) -> "DatasetTransformDeepLiteralAttribute":
        """Prepare the dataset by creating source/target data models and transformation group."""

        # Create Source Data Model and extract IDs for the entity and attribute

        (source_data_model_id, source_schema) = await create_data_model_by_upload(
            async_client_mdr=async_client_mdr,
            schema_path=Path(__file__).parent / "transform_deep_literal_attribute_source.json",
            data_model_name=source_data_model_name,
            data_model_type="SourceSchema",
        )
        source_parent_entity_id = find_object_property_by_unique_name(source_schema, "person.courses", "Id")
        assert source_parent_entity_id is not None, (
            "Could not find source parent entity ID for person.courses... " + str(source_schema)
        )
        source_attribute_id = find_object_property_by_unique_name(source_schema, "person.courses.grade", "Id")
        assert source_attribute_id is not None, "Could not find source attribute ID for person.courses.grade... " + str(
            source_schema
        )
        source_entity_id_path = convert_unique_names_to_id_path(
            source_schema, ["person", "person.courses", "person.courses.grade"], True
        )

        # Create Target Data Model and extract IDs for the entity and attribute

        (target_data_model_id, target_schema) = await create_data_model_by_upload(
            async_client_mdr=async_client_mdr,
            schema_path=Path(__file__).parent / "transform_deep_literal_attribute_target.json",
            data_model_name=target_data_model_name,
            data_model_type="SourceSchema",
        )
        target_parent_entity_id = find_object_property_by_unique_name(target_schema, "user.skills", "Id")
        assert target_parent_entity_id is not None, "Could not find target parent entity ID for user.skills... " + str(
            target_schema
        )
        target_attribute_id = find_object_property_by_unique_name(target_schema, "user.skills.genre", "Id")
        assert target_attribute_id is not None, "Could not find target attribute ID for user.skills.genre... " + str(
            target_schema
        )
        target_entity_id_path = convert_unique_names_to_id_path(
            target_schema, ["user", "user.skills", "user.skills.genre"], True
        )

        # Create transform group between source and target

        transformation_group_id = await create_transformation_groups(
            async_client_mdr=async_client_mdr,
            source_data_model_id=source_data_model_id,
            target_data_model_id=target_data_model_id,
            group_name=transformation_group_name,
        )
        return cls(
            source_data_model_id=source_data_model_id,
            source_parent_entity_id=source_parent_entity_id,
            source_attribute_id=source_attribute_id,
            source_entity_id_path=source_entity_id_path,
            source_schema=source_schema,
            target_data_model_id=target_data_model_id,
            target_parent_entity_id=target_parent_entity_id,
            target_attribute_id=target_attribute_id,
            target_entity_id_path=target_entity_id_path,
            target_schema=target_schema,
            transformation_group_id=transformation_group_id,
        )

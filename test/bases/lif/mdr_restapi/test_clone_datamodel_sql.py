"""A cloned model generates the same schema as its source (Issue #1404).

clone_datamodel used to drop fields that change what the model means: Relationship and Placement on
entity associations, Required and Array on elements, TargetEntityId on attributes. Before that it
failed outright on Postgres, because the new DataModel's Deleted was inserted as NULL. These tests
run the clone against the seed and compare the generated schemas, which covers every dropped field
at once.
"""

import pytest
from fastapi.encoders import jsonable_encoder

from lif.mdr_dto.import_export_dto import CreateCloneDTO
from lif.mdr_services.import_export_service import clone_datamodel
from lif.mdr_services.schema_generation_service import generate_openapi_schema
from lif.mdr_sql_model.core import DataModel, DataModelType

CASE = 14
OPEN_BADGES_V3 = 29

# The metadata flags and full_export emit row Ids (value sets' too) and dates, which differ between a
# source and its clone by design.
FLAG_MATRIX = [
    {"include_attr_md": False, "include_entity_md": False, "public_only": public_only, "full_export": False}
    for public_only in (False, True)
]


def _without_required_order(node):
    # The generator reads attributes and associations without an ORDER BY, so a `required` list comes
    # out in the rows' physical order, which a clone's new rows need not share. JSON Schema treats
    # `required` as a set, so it is compared as one. Property order is already ignored by dict equality.
    if isinstance(node, dict):
        return {
            key: sorted(value) if key == "required" and isinstance(value, list) else _without_required_order(value)
            for key, value in node.items()
        }
    if isinstance(node, list):
        return [_without_required_order(item) for item in node]
    return node


async def _generate(session, data_model_id: int, flags: dict) -> dict:
    session.expunge_all()
    schema = jsonable_encoder(await generate_openapi_schema(session, data_model_id, **flags))
    schema["info"].pop("title")
    return _without_required_order(schema)


@pytest.mark.parametrize("source_id", [CASE, OPEN_BADGES_V3], ids=["CASE", "Open Badges v3"])
async def test_a_clone_generates_the_same_schema_as_its_source(test_db_session, source_id):
    session = test_db_session
    source = await session.get(DataModel, source_id)
    clone = await clone_datamodel(
        session,
        CreateCloneDTO(
            source_data_model_id=source_id,
            data_model_name=f"Clone of {source.Name} (#1404)",
            data_model_type=DataModelType.SourceSchema,
            data_model_version=source.DataModelVersion,
        ),
    )
    await session.commit()

    for flags in FLAG_MATRIX:
        assert await _generate(session, clone.Id, flags) == await _generate(session, source_id, flags), flags

"""Postgres-backed check that exported enums follow ValueSetValue Id order (issue #1437).

Without an ORDER BY the values come back in heap order, which differs across Postgres versions.
An UPDATE writes a new tuple version at the end of the heap, so updating the lowest-Id value
reorders a sequential scan on any engine. Model 26 has no enums of its own; the test gives
person.id (root entity) and preferred_org_types (nested entity) one value set, then rolls back.
"""

import pytest
from sqlalchemy import text

from lif.mdr_services.schema_generation_service import generate_openapi_schema

MODEL_ID = 26
PERSON_ID_ATTRIBUTE, PREFERRED_ORG_TYPES_ATTRIBUTE = 1894, 1895


@pytest.fixture
async def session(test_db_session):
    try:
        yield test_db_session
    finally:
        await test_db_session.rollback()


async def _insert(session, statement: str) -> int:
    return (await session.execute(text(statement + ' RETURNING "Id"'))).scalar_one()


async def test_enum_values_follow_id_order(session):
    value_set = await _insert(
        session, f'INSERT INTO "ValueSets" ("Name", "DataModelId") VALUES (\'OrderTest\', {MODEL_ID})'
    )
    value_ids = [
        await _insert(
            session,
            f'INSERT INTO "ValueSetValues" ("ValueSetId", "Value", "DataModelId") '
            f"VALUES ({value_set}, '{value}', {MODEL_ID})",
        )
        for value in "abc"
    ]
    await session.execute(text(f'UPDATE "ValueSetValues" SET "Description" = \'moved\' WHERE "Id" = {value_ids[0]}'))
    await session.execute(
        text(
            f'UPDATE "Attributes" SET "ValueSetId" = {value_set} '
            f'WHERE "Id" IN ({PERSON_ID_ATTRIBUTE}, {PREFERRED_ORG_TYPES_ATTRIBUTE})'
        )
    )

    schema = await generate_openapi_schema(
        session, MODEL_ID, include_attr_md=True, include_entity_md=False, full_export=True
    )

    person = schema["components"]["schemas"]["person"]
    preferences = person["properties"]["employment"]["properties"]["preferences"]
    for attribute in (person["properties"]["id"], preferences["properties"]["preferred_org_types"]):
        assert attribute["enum"] == ["a", "b", "c"]
        assert [value.Id for value in attribute["ValueSet"]["Values"]] == value_ids

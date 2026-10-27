"""Postgres-backed checks that the generator reads element flags and association Names (issue #1395).

Model 26 (R1 Demo Source Data Model) is small and self-contained: person -> employment -> preferences,
all Embedded, with attributes person.id and preferences.preferred_org_types. Each test edits seed rows
in its own session without committing and rolls back, so the shared database is left as loaded.
"""

import pytest
from sqlalchemy import text

from lif.mdr_services.schema_generation_service import generate_openapi_schema, is_overlay_model

MODEL_ID = 26
PERSON, EMPLOYMENT, PREFERENCES = 375, 376, 377
PERSON_TO_EMPLOYMENT, EMPLOYMENT_TO_PREFERENCES = 181, 182
PERSON_ID_ATTRIBUTE, PERSON_ID_ASSOCIATION = 1894, 1865


@pytest.fixture
async def session(test_db_session):
    try:
        yield test_db_session
    finally:
        await test_db_session.rollback()


async def _execute(session, *statements):
    for statement in statements:
        await session.execute(text(statement))


async def test_flags_come_from_the_element_rows(session):
    await _execute(
        session,
        f'UPDATE "Entities" SET "Queryable" = true, "Modifiable" = true WHERE "Id" = {EMPLOYMENT}',
        f'UPDATE "Attributes" SET "Queryable" = true WHERE "Id" = {PERSON_ID_ATTRIBUTE}',
    )

    schema = await generate_openapi_schema(session, MODEL_ID, include_attr_md=True, include_entity_md=False)

    person = schema["components"]["schemas"]["person"]
    assert (person["x-mutable"], person["x-queryable"]) == (False, False)
    employment = person["properties"]["employment"]
    assert (employment["x-mutable"], employment["x-queryable"]) == (True, True)
    person_id = person["properties"]["id"]
    assert (person_id["x-mutable"], person_id["x-queryable"]) == (False, True)


async def test_attribute_flags_follow_include_attr_md_as_on_overlays(session):
    # Overlays emit attribute flags only with attribute metadata on; self-contained models match.
    schema = await generate_openapi_schema(session, MODEL_ID, include_attr_md=False, include_entity_md=False)

    person = schema["components"]["schemas"]["person"]
    assert "x-queryable" in person
    assert "x-queryable" not in person["properties"]["id"]


async def test_child_keys_come_from_the_association_name(session):
    # Names the has*/relevant* rule would never produce, as an import or #1388 may set them.
    await _execute(
        session,
        f'UPDATE "EntityAssociation" SET "Name" = \'currentEmployment\' WHERE "Id" = {PERSON_TO_EMPLOYMENT}',
        f'UPDATE "EntityAttributeAssociation" SET "Name" = \'personId\' WHERE "Id" = {PERSON_ID_ASSOCIATION}',
        f'UPDATE "Attributes" SET "Required" = \'Yes\' WHERE "Id" = {PERSON_ID_ATTRIBUTE}',
    )

    schema = await generate_openapi_schema(session, MODEL_ID, include_attr_md=False, include_entity_md=False)

    person = schema["components"]["schemas"]["person"]
    assert set(person["properties"]) == {"currentEmployment", "personId"}
    assert set(person["required"]) == {"currentEmployment", "personId"}  # employment is Required in the seed
    assert "preferences" in person["properties"]["currentEmployment"]["properties"]


async def test_reference_key_comes_from_the_association_name(session):
    # employment -> preferences becomes a Reference; preferences is then a root of its own.
    await _execute(
        session,
        f'UPDATE "EntityAssociation" SET "Placement" = \'Reference\', "Name" = \'preferredSettings\' '
        f'WHERE "Id" = {EMPLOYMENT_TO_PREFERENCES}',
    )

    schema = await generate_openapi_schema(session, MODEL_ID, include_attr_md=False, include_entity_md=False)

    employment = schema["components"]["schemas"]["person"]["properties"]["employment"]
    assert "preferredSettings" in employment["properties"]
    assert "RefPreferences" not in employment["properties"]
    assert "preferences" in schema["components"]["schemas"]


async def test_public_only_reads_the_element_level_of_access(session):
    await _execute(
        session,
        f'UPDATE "Entities" SET "LevelOfAccess" = \'Private\' WHERE "Id" = {EMPLOYMENT}',
        f'UPDATE "Attributes" SET "LevelOfAccess" = \'Restricted\' WHERE "Id" = {PERSON_ID_ATTRIBUTE}',
    )

    everything = await generate_openapi_schema(session, MODEL_ID, include_attr_md=False, include_entity_md=False)
    public = await generate_openapi_schema(
        session, MODEL_ID, include_attr_md=False, include_entity_md=False, public_only=True
    )

    assert {"employment", "id"} <= set(everything["components"]["schemas"]["person"]["properties"])
    assert public["components"]["schemas"]["person"]["properties"] == {}
    assert "employment" not in public["components"]["schemas"]


async def test_type_name_does_not_select_the_overlay_path(session):
    # #1388 converts models 17 and 18 in place: what makes a model an overlay is its inclusion rows.
    assert await is_overlay_model(session, 17)
    assert not await is_overlay_model(session, MODEL_ID)

    before = await generate_openapi_schema(session, MODEL_ID, include_attr_md=True, include_entity_md=False)
    await _execute(session, f'UPDATE "DataModels" SET "Type" = \'OrgLIF\' WHERE "Id" = {MODEL_ID}')
    after = await generate_openapi_schema(session, MODEL_ID, include_attr_md=True, include_entity_md=False)

    assert after == before

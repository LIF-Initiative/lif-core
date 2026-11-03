"""Postgres-backed check that an embedded-association cycle is refused, not recursed into.

find_children descends the embedded tree and find_ancestors climbs it; neither noticed an entity
that leads back to itself, so a cycle in one model's data ran until Python's recursion limit. That
error was unhandled, so the API answered a bare 500 without CORS headers and the MDR frontend showed
only "Network Error" for that one model. Model 29 (Open Badges v3) ships Profile and
EndorsementCredential pointing at each other as two References; the tests make them Embedded, or
build an isolated cycle that a Reference points at, then roll back.
"""

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from lif.mdr_services.schema_generation_service import generate_openapi_schema

MODEL_ID = 29


@pytest.fixture
async def session(test_db_session):
    try:
        yield test_db_session
    finally:
        await test_db_session.rollback()


async def _entity_id(session, name: str) -> int:
    return (
        await session.execute(
            text(
                f'SELECT "Id" FROM "Entities" WHERE "DataModelId" = {MODEL_ID} AND "Name" = \'{name}\' '
                'AND "Deleted" IS NOT TRUE'
            )
        )
    ).scalar_one()


async def _insert_entity(session, name: str) -> int:
    return (
        await session.execute(
            text(
                f'INSERT INTO "Entities" ("Name", "UniqueName", "DataModelId", "Deleted") '
                f"VALUES ('{name}', '{name}', {MODEL_ID}, false) RETURNING \"Id\""
            )
        )
    ).scalar_one()


async def _insert_association(session, parent: int, child: int, placement: str | None, name: str) -> None:
    placement_sql = "NULL" if placement is None else f"'{placement}'"
    await session.execute(
        text(
            f'INSERT INTO "EntityAssociation" ("ParentEntityId", "ChildEntityId", "Placement", "Name", "Deleted") '
            f"VALUES ({parent}, {child}, {placement_sql}, '{name}', false)"
        )
    )


async def _generate(session):
    return await generate_openapi_schema(
        session, MODEL_ID, include_attr_md=False, include_entity_md=False, full_export=False
    )


async def test_an_embedded_cycle_under_a_root_is_refused(session):
    profile = await _entity_id(session, "Profile")
    endorsement = await _entity_id(session, "EndorsementCredential")
    await session.execute(
        text(
            f'UPDATE "EntityAssociation" SET "Placement" = NULL WHERE "Deleted" IS NOT TRUE AND '
            f'("ParentEntityId", "ChildEntityId") IN (({profile}, {endorsement}), ({endorsement}, {profile}))'
        )
    )

    with pytest.raises(HTTPException) as info:
        await _generate(session)

    assert info.value.status_code == 400
    assert info.value.detail.startswith("Embedded associations form a cycle: ")
    assert "Profile -> EndorsementCredential" in info.value.detail
    assert "EndorsementCredential -> Profile" in info.value.detail


async def test_an_embedded_cycle_only_a_reference_reaches_is_refused(session):
    # Neither entity is a root (both are children), so find_children never visits them; the
    # Reference's ancestor walk is what climbs into the cycle.
    root = await _entity_id(session, "OpenBadgeCredential")
    loop_a = await _insert_entity(session, "LoopA")
    loop_b = await _insert_entity(session, "LoopB")
    await _insert_association(session, loop_a, loop_b, None, "LoopB")
    await _insert_association(session, loop_b, loop_a, None, "LoopA")
    await _insert_association(session, root, loop_a, "Reference", "RefLoopA")

    with pytest.raises(HTTPException) as info:
        await _generate(session)

    assert info.value.status_code == 400
    assert "LoopA -> LoopB -> LoopA" in info.value.detail


async def test_the_seed_model_still_generates(session):
    schema = await _generate(session)
    assert "OpenBadgeCredential" in schema["components"]["schemas"]

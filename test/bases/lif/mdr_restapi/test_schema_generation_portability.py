"""Postgres-backed check that schema generation refuses a model the portability rules refuse (#1468).

Generation exports the model first, so it refuses with the same {code, element, reason} that export
does (Portability Spec §10), and the endpoint answers 422 as /portable does. A model export refuses only
as not yet migrated, or for an incomplete identity, is still generated until #1513 clears those.

Each test imports a small model that exports, then breaks one rule by inserting rows directly. No
supported write path saves a model that breaks a rule, so the rows stand in for data saved before the
rules were enforced. Everything rolls back.
"""

import json

import pytest
from sqlalchemy import text

from lif.mdr_portability import PortabilityErrorGroup, list_refusals, parse_model_file
from lif.mdr_services.model_converter import import_model
from lif.mdr_services.overlay_converter import FLAG_MATRIX, generate_matrix
from lif.mdr_services.schema_generation_service import generate_openapi_schema

# Closing Person -> Contact -> Address with Address -> Person. Export walks the model's entities in
# canonical order (Spec §8, §9), so from Address it closes the cycle at Contact -> Address.
CYCLE_REFUSAL = {
    "code": "ASSOCIATION_CYCLE",
    "element": "Associations[Contact, Address]",
    "reason": "a cycle of containing associations: 'Address', 'Person', 'Contact', 'Address'",
}


@pytest.fixture
async def session(test_db_session):
    try:
        yield test_db_session
    finally:
        await test_db_session.rollback()


def _entity(name: str) -> dict:
    return {"UniqueName": name, "Name": name, "LevelOfAccess": "Public", "Queryable": False, "Modifiable": False}


async def _import_person_model(session, tag: str) -> int:
    """Person contains Contact, which contains Address; Person has a name. It exports."""
    content = {
        "Format": {"Type": "lif-mdr-model", "Version": 1},
        "Details": {"Name": f"GenerationPortability_{tag}", "Version": "1.0", "ContributorOrganization": "LIF"},
        "ValueSets": [],
        "Entities": [_entity("Address"), _entity("Contact"), _entity("Person")],
        "Attributes": [
            {
                "UniqueName": "Person.name",
                "Name": "name",
                "DataType": "string",
                "LevelOfAccess": "Public",
                "Queryable": False,
                "Modifiable": False,
            }
        ],
        "Associations": [
            {"Parent": {"Entity": "Contact"}, "Child": {"Entity": "Address"}, "Name": "Address"},
            {"Parent": {"Entity": "Person"}, "Child": {"Entity": "Contact"}, "Name": "Contact"},
            {"Parent": {"Entity": "Person"}, "Child": {"Attribute": "Person.name"}, "Name": "name"},
        ],
    }
    return await import_model(session, parse_model_file(json.dumps(content).encode()))


async def _entity_id(session, data_model_id: int, name: str) -> int:
    return (
        await session.execute(
            text('SELECT "Id" FROM "Entities" WHERE "DataModelId" = :model AND "UniqueName" = :name'),
            {"model": data_model_id, "name": name},
        )
    ).scalar_one()


async def _contain(session, data_model_id: int, parent: str, child: str, name: str) -> None:
    await session.execute(
        text(
            'INSERT INTO "EntityAssociation" ("ParentEntityId", "ChildEntityId", "Placement", "Name", "Array", "Deleted") '
            "VALUES (:parent, :child, 'Embedded', :name, false, false)"
        ),
        {
            "parent": await _entity_id(session, data_model_id, parent),
            "child": await _entity_id(session, data_model_id, child),
            "name": name,
        },
    )


async def _generate(session, data_model_id: int):
    return await generate_openapi_schema(session, data_model_id, include_attr_md=False, include_entity_md=False)


async def test_a_model_that_exports_still_generates(session):
    data_model_id = await _import_person_model(session, "exports")

    schema = await _generate(session, data_model_id)

    person = schema["components"]["schemas"]["Person"]
    assert set(person["properties"]) == {"name", "Contact"}


async def test_a_containment_cycle_is_refused_as_export_refuses_it(session):
    data_model_id = await _import_person_model(session, "cycle")
    await _contain(session, data_model_id, "Address", "Person", "Person")

    with pytest.raises(PortabilityErrorGroup) as info:
        await _generate(session, data_model_id)

    assert list_refusals(info.value) == [CYCLE_REFUSAL]


async def test_two_children_under_one_name_are_refused(session):
    # Since #1508 an association's Name can be set directly, and no index stops two children of one
    # parent sharing it. The generator would write both under one key and keep only the last.
    data_model_id = await _import_person_model(session, "name_taken")
    await _contain(session, data_model_id, "Person", "Address", "Contact")

    with pytest.raises(PortabilityErrorGroup) as info:
        await _generate(session, data_model_id)

    assert list_refusals(info.value) == [
        {
            "code": "ASSOCIATION_NAME_TAKEN",
            "element": "Associations[Person, Contact]",
            "reason": "2 associations have this parent and Name",
        }
    ]


async def test_a_model_refused_only_for_its_identity_still_generates(session):
    # POST /datamodels/ saves a model with no ContributorOrganization.
    data_model_id = await _import_person_model(session, "identity")
    await session.execute(
        text('UPDATE "DataModels" SET "ContributorOrganization" = NULL WHERE "Id" = :model'), {"model": data_model_id}
    )

    schema = await _generate(session, data_model_id)

    assert "Person" in schema["components"]["schemas"]


async def test_the_overlay_conversion_records_a_refusal_as_the_endpoint_does(session):
    # convert_overlays compares these matrices and reports a failed combination; a refusal must be one.
    data_model_id = await _import_person_model(session, "matrix")
    await _contain(session, data_model_id, "Address", "Person", "Person")

    schemas = await generate_matrix(session, data_model_id)

    assert len(schemas) == len(FLAG_MATRIX)
    assert all(
        schema == {"x-http-error": {"status_code": 422, "detail": [CYCLE_REFUSAL]}} for schema in schemas.values()
    )


@pytest.mark.parametrize("query", ["", "?download=true&include_entity_md=true&include_attr_md=true&full_export=true"])
async def test_the_endpoint_lists_every_refusal(session, async_client_mdr, mdr_api_headers, query):
    data_model_id = await _import_person_model(session, f"endpoint_{bool(query)}")
    await _contain(session, data_model_id, "Address", "Person", "Person")

    response = await async_client_mdr.get(
        f"/datamodels/open_api_schema/{data_model_id}{query}", headers=mdr_api_headers
    )

    assert response.status_code == 422
    assert response.json() == {"detail": [CYCLE_REFUSAL]}

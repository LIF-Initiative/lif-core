"""API tests of the portable export and import endpoints (issue #1408).

The converters are tested in test_model_converter.py, test_mapping_group_converter.py and
test_crosswalk_converter.py; these cover what the endpoints add: the raw body and canonical bytes, the
status codes, the transaction, and the lock on a crosswalk's pair.

Install 1 is the shared test database and install 2 a separate seeded server, so a round trip crosses
two databases. Model names carry the test name, since install 1 is shared across the session.
"""

import asyncio
import json
from pathlib import Path
from unittest import mock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from sqlmodel import select

from lif.mdr_portability import dump_canonical, parse_crosswalk_file, parse_mapping_group_file, parse_model_file
from lif.mdr_sql_model.core import ValueSet

FIXTURES = Path(__file__).parents[3] / "components/lif/mdr_portability/fixtures"


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / f"test_reference_{name}_file.json").read_text())


def _reference_files(tag: str) -> dict[str, bytes]:
    """The reference source model, target model, mapping group and crosswalk, renamed for the test, in
    canonical form.

    The group leaves out its two mappings through roles (Course,AccreditedBy and Course,ApprovedBy), which
    import refuses until two roles can be stored apart (#1434).
    """
    source, target, group = _load_fixture("source_model"), _load_fixture("target_model"), _load_fixture("mapping_group")
    crosswalk = _load_fixture("crosswalk")
    for model in (source, target):
        model["Details"]["Name"] = f"{model['Details']['Name']} {tag}"
    for side, model in (("Source", source), ("Target", target)):
        group["Details"][side]["Name"] = model["Details"]["Name"]
        crosswalk["Details"][side]["Model"]["Name"] = model["Details"]["Name"]
    role_paths = {"Course,AccreditedBy,name", "Course,ApprovedBy,name"}
    group["Mappings"] = [mapping for mapping in group["Mappings"] if mapping["Target"]["Path"] not in role_paths]
    return {
        "source": dump_canonical(parse_model_file(json.dumps(source).encode())),
        "target": dump_canonical(parse_model_file(json.dumps(target).encode())),
        "group": dump_canonical(parse_mapping_group_file(json.dumps(group).encode())),
        "crosswalk": dump_canonical(parse_crosswalk_file(json.dumps(crosswalk).encode())),
    }


@pytest.fixture
async def client(test_db_session, seed_db_session, mdr_api_headers):
    """An MDR client, use_database(install) to point it at install 1 or install 2, and each install's session."""
    from lif.mdr_restapi import core
    from lif.mdr_utils.database_setup import get_session

    sessions = {1: test_db_session, 2: seed_db_session}

    def use_database(install: int):
        async def override_get_session():
            yield sessions[install]

        core.app.dependency_overrides[get_session] = override_get_session

    use_database(1)
    async with AsyncClient(
        transport=ASGITransport(app=core.app), base_url="http://test", headers=mdr_api_headers
    ) as http_client:
        yield http_client, use_database, sessions
    core.app.dependency_overrides.clear()


def _count_models(pg_conn, name: str) -> int:
    # A separate connection, so it sees only what was committed.
    with pg_conn.cursor() as cursor:
        cursor.execute('SELECT count(*) FROM "DataModels" WHERE "Name" = %s AND "Deleted" IS NOT TRUE', (name,))
        return cursor.fetchone()[0]


async def _crosswalk_route(session, model_ids: dict[str, int]) -> str:
    """The export route for the reference crosswalk, from its two value sets' Ids in this install."""
    details = _load_fixture("crosswalk")["Details"]
    value_set_ids = {}
    for side, kind in (("Source", "source"), ("Target", "target")):
        query = select(ValueSet.Id).where(
            ValueSet.DataModelId == model_ids[kind], ValueSet.Name == details[side]["ValueSet"]
        )
        value_set_ids[side] = (await session.execute(query)).scalar_one()
    return (
        f"/portable/crosswalks?source_value_set_id={value_set_ids['Source']}"
        f"&target_value_set_id={value_set_ids['Target']}"
    )


async def _import_reference_files(http_client, files, order=("source", "target", "group", "crosswalk")):
    """Import the reference files in order, and return the Id of each model and group."""
    routes = {"source": "models", "target": "models", "group": "mapping_groups", "crosswalk": "crosswalks"}
    ids = {}
    for kind in order:
        response = await http_client.post(f"/portable/{routes[kind]}", content=files[kind])
        assert response.status_code == 201, response.text
        ids[kind] = response.json().get("Id")
    return ids


async def _export_reference_files(http_client, session, ids) -> dict[str, bytes]:
    exported = {}
    for kind, route in (("source", "models"), ("target", "models"), ("group", "mapping_groups")):
        response = await http_client.get(f"/portable/{route}/{ids[kind]}")
        assert response.status_code == 200, response.text
        exported[kind] = response.content
    response = await http_client.get(await _crosswalk_route(session, ids))
    assert response.status_code == 200, response.text
    exported["crosswalk"] = response.content
    return exported


def _codes(response) -> list[tuple[str, str]]:
    return sorted((error["code"], error["element"]) for error in response.json()["detail"])


async def test_every_file_kind_round_trips_between_installs_byte_for_byte(client):
    http_client, use_database, sessions = client
    files = _reference_files("roundtrip")

    use_database(1)
    ids_1 = await _import_reference_files(http_client, files)
    exported_b = await _export_reference_files(http_client, sessions[1], ids_1)
    assert exported_b == files

    # Install 2 imports the target model first, so the two models' row IDs differ from install 1's.
    use_database(2)
    ids_2 = await _import_reference_files(http_client, exported_b, order=("target", "source", "group", "crosswalk"))
    exported_c = await _export_reference_files(http_client, sessions[2], ids_2)
    assert exported_c == files
    assert (ids_2["source"], ids_2["target"]) != (ids_1["source"], ids_1["target"])


async def test_a_crosswalk_import_returns_how_many_value_mappings_it_created(client):
    http_client, _, _ = client
    files = _reference_files("created")
    await _import_reference_files(http_client, files, order=("source", "target"))

    response = await http_client.post("/portable/crosswalks", content=files["crosswalk"])

    assert response.status_code == 201
    assert response.json() == {"Created": len(json.loads(files["crosswalk"])["Entries"])}


async def test_an_import_is_committed(client, pg_conn):
    http_client, _, _ = client
    files = _reference_files("committed")
    name = json.loads(files["source"])["Details"]["Name"]

    response = await http_client.post("/portable/models", content=files["source"])

    assert response.status_code == 201
    assert _count_models(pg_conn, name) == 1


async def test_a_refused_import_returns_every_refusal_and_writes_nothing(client, pg_conn):
    http_client, _, _ = client
    content = json.loads(_reference_files("refused")["source"])
    content["Entities"][0]["Id"] = 7
    content["Details"]["Version"] = " "

    response = await http_client.post("/portable/models", content=json.dumps(content).encode())

    assert response.status_code == 422
    assert {code for code, _ in _codes(response)} == {"ROW_ID_PRESENT", "MODEL_IDENTITY_INCOMPLETE"}
    assert _count_models(pg_conn, content["Details"]["Name"]) == 0


async def test_a_group_whose_models_are_not_installed_is_refused(client):
    http_client, _, _ = client

    response = await http_client.post("/portable/mapping_groups", content=_reference_files("no-models")["group"])

    assert response.status_code == 422
    assert _codes(response) == [("MODEL_MISSING", "Details.Source"), ("MODEL_MISSING", "Details.Target")]


@pytest.mark.parametrize(
    "content, code",
    [
        (b'{"Format": {"Type": "lif-mdr-model", "Version": 1}, "Format": {}}', "FIELD_INVALID"),
        ('{"Format": 1}'.encode("utf-16"), "FORMAT_UNKNOWN"),
        (b"not json", "FORMAT_UNKNOWN"),
    ],
)
async def test_the_body_is_read_as_sent(client, content, code):
    http_client, _, _ = client

    response = await http_client.post("/portable/models", content=content)

    assert response.status_code == 422
    assert {found for found, _ in _codes(response)} == {code}


async def test_a_leading_byte_order_mark_is_accepted(client):
    http_client, _, _ = client

    response = await http_client.post("/portable/models", content=b"\xef\xbb\xbf" + _reference_files("bom")["source"])

    assert response.status_code == 201, response.text


async def test_importing_installed_content_again_is_a_conflict(client):
    http_client, _, _ = client
    files = _reference_files("again")
    await _import_reference_files(http_client, files)

    model = await http_client.post("/portable/models", content=files["source"])
    group = await http_client.post("/portable/mapping_groups", content=files["group"])
    crosswalk = await http_client.post("/portable/crosswalks", content=files["crosswalk"])

    assert model.status_code == 409
    assert _codes(model) == [("MODEL_EXISTS", "Details")]
    assert group.status_code == 409
    assert {code for code, _ in _codes(group)} == {"GROUP_EXISTS"}
    assert crosswalk.status_code == 409
    assert _codes(crosswalk) == [("CROSSWALK_EXISTS", "Details")]


async def test_a_conflict_alongside_another_refusal_is_a_422(client):
    http_client, _, _ = client
    files = _reference_files("mixed")
    assert (await http_client.post("/portable/models", content=files["source"])).status_code == 201
    content = json.loads(files["source"])
    content["Entities"].append(content["Entities"][0])

    response = await http_client.post("/portable/models", content=json.dumps(content).encode())

    assert response.status_code == 422
    assert {code for code, _ in _codes(response)} == {"MODEL_EXISTS", "DUPLICATE_KEY"}


async def test_a_concurrent_duplicate_caught_by_the_database_is_a_conflict(client):
    http_client, _, _ = client
    from lif.mdr_services import portability_converter

    with mock.patch.object(
        portability_converter, "import_model", mock.AsyncMock(side_effect=IntegrityError("INSERT", {}, Exception()))
    ):
        response = await http_client.post("/portable/models", content=_reference_files("race")["source"])

    assert response.status_code == 409
    assert isinstance(response.json()["detail"], str)


async def test_exporting_a_missing_model_group_or_value_set_is_a_404(client):
    http_client, _, _ = client

    assert (await http_client.get("/portable/models/999999")).status_code == 404
    assert (await http_client.get("/portable/mapping_groups/999999")).status_code == 404
    missing_value_set = "/portable/crosswalks?source_value_set_id=999999&target_value_set_id=999998"
    assert (await http_client.get(missing_value_set)).status_code == 404


async def test_a_crosswalk_import_waits_for_another_import_of_the_same_pair(client):
    from lif.mdr_restapi.portable_endpoints import lock_crosswalk_pair

    http_client, _, sessions = client
    files = _reference_files("lock")
    await _import_reference_files(http_client, files, order=("source", "target"))
    async with AsyncSession(sessions[1].bind) as other_import:
        await lock_crosswalk_pair(other_import, parse_crosswalk_file(files["crosswalk"]))

        waiting = asyncio.create_task(http_client.post("/portable/crosswalks", content=files["crosswalk"]))
        await asyncio.sleep(0.2)
        assert not waiting.done()

        await other_import.rollback()
        response = await asyncio.wait_for(waiting, timeout=5)
    assert response.status_code == 201, response.text


async def test_a_crosswalk_import_does_not_wait_for_an_import_into_another_tenant(client, pg_conn):
    from lif.mdr_restapi.portable_endpoints import lock_crosswalk_pair

    http_client, _, sessions = client
    files = _reference_files("tenant-lock")
    await _import_reference_files(http_client, files, order=("source", "target"))
    with pg_conn.cursor() as cursor:
        cursor.execute("CREATE SCHEMA IF NOT EXISTS portable_lock_other_tenant")
    async with AsyncSession(sessions[1].bind) as other_tenant:
        # SET LOCAL ends with the transaction, so the pooled connection keeps its own search_path.
        await other_tenant.execute(text("SET LOCAL search_path TO portable_lock_other_tenant"))
        await lock_crosswalk_pair(other_tenant, parse_crosswalk_file(files["crosswalk"]))

        response = await asyncio.wait_for(
            http_client.post("/portable/crosswalks", content=files["crosswalk"]), timeout=5
        )
        await other_tenant.rollback()
    assert response.status_code == 201, response.text


async def test_exporting_a_model_that_is_not_migrated_returns_the_refusals(client):
    http_client, _, _ = client

    # Seed model 1 (LIF) still uses deprecated constructs.
    response = await http_client.get("/portable/models/1")

    assert response.status_code == 422
    assert {code for code, _ in _codes(response)} == {"NOT_MIGRATED"}


async def test_the_openapi_spec_documents_each_file_kind_by_its_schema(client):
    from lif.mdr_restapi import core

    spec = core.app.openapi()
    components = spec["components"]["schemas"]
    for route, file_model in (
        ("/portable/models", "ModelFile"),
        ("/portable/mapping_groups", "MappingGroupFile"),
        ("/portable/crosswalks", "CrosswalkFile"),
    ):
        # The import's $ref names the schema its export registers, which FastAPI renames on a name clash.
        body = spec["paths"][route]["post"]["requestBody"]["content"]["application/json"]["schema"]
        assert body == {"$ref": f"#/components/schemas/{file_model}"}
        assert file_model in components

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, event
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from unittest.mock import AsyncMock, MagicMock, patch

from lif.exceptions.core import DataNotFoundException, DataStoreException
from lif.identity_mapper_restapi import core
from lif.identity_mapper_service.core import IdentityMapperService
from lif.identity_mapper_storage.core import DeleteOutcome
from lif.identity_mapper_storage_sql import core as storage_core
from lif.identity_mapper_storage_sql.core import IdentityMapperSqlStorage
from lif.identity_mapper_storage_sql.db import Base


@pytest_asyncio.fixture
async def mock_initialize():
    core.service = MagicMock(name="mock_service", spec=IdentityMapperService)


@pytest_asyncio.fixture
async def mock_shutdown():
    # no-op for shutdown in tests
    pass


def get_client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=core.app), base_url="http://test")


class _UnhealthySession:
    """Async session whose execute() fails the way an unreachable database does."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False

    async def execute(self, *args, **kwargs):
        raise OperationalError("SELECT 1", {}, Exception("database is down"))


@pytest_asyncio.fixture
async def db_session_factory():
    """An async factory -- the type get_db_session_factory() actually returns (#1199).

    The sync sessionmaker this fixture used to yield could not catch the /health
    breakage, because the service never receives a sync factory in production.
    """
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    yield async_sessionmaker(expire_on_commit=False, autoflush=False, bind=engine)
    await engine.dispose()


@pytest.fixture()
def unhealthy_session_factory():
    return lambda: _UnhealthySession()


@pytest.mark.asyncio
@patch("lif.identity_mapper_restapi.core.initialize", mock_initialize)
@patch("lif.identity_mapper_restapi.core.shutdown", mock_shutdown)
async def test_health_returns_200_and_ran_a_real_query_when_database_reachable(
    mock_initialize, mock_shutdown, db_session_factory
):
    executed_statements: list[str] = []

    def record_statement(conn, cursor, statement, parameters, context, executemany):
        executed_statements.append(statement)

    sync_engine = db_session_factory.kw["bind"].sync_engine
    event.listen(sync_engine, "before_cursor_execute", record_statement)
    try:
        async with get_client() as client:
            with patch.object(core, "get_db_session_factory", return_value=db_session_factory):
                response = await client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        assert any("SELECT 1" in statement for statement in executed_statements)
    finally:
        event.remove(sync_engine, "before_cursor_execute", record_statement)


@pytest.mark.asyncio
@patch("lif.identity_mapper_restapi.core.initialize", mock_initialize)
@patch("lif.identity_mapper_restapi.core.shutdown", mock_shutdown)
async def test_health_returns_503_when_session_factory_raises(
    mock_initialize, mock_shutdown, unhealthy_session_factory
):
    async with get_client() as client:
        with patch.object(core, "get_db_session_factory", return_value=unhealthy_session_factory):
            response = await client.get("/health")
        assert response.status_code == 503
        assert response.json() == {"status": "unhealthy"}


@pytest.mark.asyncio
@patch("lif.identity_mapper_restapi.core.initialize", mock_initialize)
@patch("lif.identity_mapper_restapi.core.shutdown", mock_shutdown)
async def test_health_does_not_report_a_wiring_mistake_as_unhealthy(mock_initialize, mock_shutdown):
    """A sync factory is a wiring bug, not an unreachable database (#1199).

    /health caught bare Exception, so handing it the sync sessionmaker from #1234 turned a
    TypeError into a permanent 503 "unhealthy" -- the task never reached steady state and
    the log blamed the database. Only SQLAlchemyError is a 503 now, so this surfaces loudly.
    """
    sync_factory = sessionmaker(bind=create_engine("sqlite://", poolclass=StaticPool))
    async with get_client() as client:
        with patch.object(core, "get_db_session_factory", return_value=sync_factory):
            with pytest.raises(TypeError, match="does not support the asynchronous context manager protocol"):
                await client.get("/health")


@pytest.mark.asyncio
@patch("lif.identity_mapper_restapi.core.initialize", mock_initialize)
@patch("lif.identity_mapper_restapi.core.shutdown", mock_shutdown)
async def test_do_delete_mapping_not_found(mock_initialize, mock_shutdown):
    org_id = "org1"
    person_id = "person1"
    mapping_id = "nonexistent-mapping-id"
    async with get_client() as client:
        with patch.object(core.service, "delete_mapping", new_callable=AsyncMock) as mock_delete_mapping:
            mock_delete_mapping.side_effect = DataNotFoundException("Mapping not found")
            response = await client.delete(f"/organizations/{org_id}/persons/{person_id}/mappings/{mapping_id}")
            assert response.status_code == 404
            response_json = response.json()
            assert response_json["status_code"] == "404"
            assert response_json["path"] == f"/organizations/{org_id}/persons/{person_id}/mappings/{mapping_id}"
            assert response_json["message"] == "Mapping not found"
            mock_delete_mapping.assert_awaited_once_with(org_id, person_id, mapping_id)


@pytest.mark.asyncio
@patch("lif.identity_mapper_restapi.core.initialize", mock_initialize)
@patch("lif.identity_mapper_restapi.core.shutdown", mock_shutdown)
async def test_do_delete_mapping_not_owned_is_indistinguishable_from_not_found(mock_initialize, mock_shutdown):
    """A mapping owned by another organization answers byte-for-byte like a missing one (#1177).

    Asserted on status *and* body rather than "both non-2xx": a differing status code or
    message is enough to tell a caller that a probed mapping ID is real. Driven through the
    real service so the exception-to-response mapping is exercised, not mocked past.
    """
    org_id = "org-a"
    person_id = "person-1"
    mapping_id = "3f0c9c1e-0000-4000-8000-000000000001"

    async def delete_refused_with(outcome: DeleteOutcome):
        storage = MagicMock()
        storage.delete_mapping_for_owner = AsyncMock(return_value=outcome)
        core.service = IdentityMapperService(storage=storage)
        async with get_client() as client:
            return await client.delete(f"/organizations/{org_id}/persons/{person_id}/mappings/{mapping_id}")

    not_found = await delete_refused_with(DeleteOutcome.NOT_FOUND)
    not_owned = await delete_refused_with(DeleteOutcome.NOT_OWNED)

    assert not_found.status_code == 404
    assert not_owned.status_code == not_found.status_code
    assert not_owned.text == not_found.text


@pytest.mark.asyncio
@patch("lif.identity_mapper_restapi.core.initialize", mock_initialize)
@patch("lif.identity_mapper_restapi.core.shutdown", mock_shutdown)
async def test_do_delete_mappings_datastore_exception(mock_initialize, mock_shutdown):
    org_id = "org1"
    person_id = "person1"
    mapping_id = "mapping1"
    async with get_client() as client:
        with patch.object(core.service, "delete_mapping", new_callable=AsyncMock) as mock_delete_mappings:
            mock_delete_mappings.side_effect = DataStoreException("Failed to delete mapping")
            response = await client.delete(f"/organizations/{org_id}/persons/{person_id}/mappings/{mapping_id}")
            assert response.status_code == 500
            response_json = response.json()
            assert response_json["status_code"] == "500"
            assert response_json["path"] == f"/organizations/{org_id}/persons/{person_id}/mappings/{mapping_id}"
            assert response_json["message"] == "Internal server error. Please try again later."
            assert "code" in response_json
            mock_delete_mappings.assert_awaited_once_with(org_id, person_id, mapping_id)


@pytest.mark.asyncio
@patch("lif.identity_mapper_restapi.core.initialize", mock_initialize)
@patch("lif.identity_mapper_restapi.core.shutdown", mock_shutdown)
async def test_do_delete_mappings_service_exception(mock_initialize, mock_shutdown):
    org_id = "org1"
    person_id = "person1"
    mapping_id = "mapping1"
    async with get_client() as client:
        with patch.object(core.service, "delete_mapping", new_callable=AsyncMock) as mock_delete_mappings:
            mock_delete_mappings.side_effect = Exception("Service error")
            try:
                await client.delete(f"/organizations/{org_id}/persons/{person_id}/mappings/{mapping_id}")
            except Exception as e:
                assert str(e) == "Service error"
                mock_delete_mappings.assert_awaited_once_with(org_id, person_id, mapping_id)


@pytest.mark.asyncio
@patch("lif.identity_mapper_restapi.core.initialize", mock_initialize)
@patch("lif.identity_mapper_restapi.core.shutdown", mock_shutdown)
async def test_do_delete_mapping_success(mock_initialize, mock_shutdown):
    org_id = "org1"
    person_id = "person1"
    mapping_id = "mapping1"
    async with get_client() as client:
        with patch.object(core.service, "delete_mapping", new_callable=AsyncMock) as mock_delete_mapping:
            mock_delete_mapping.return_value = None  # Successful deletion returns None
            response = await client.delete(f"/organizations/{org_id}/persons/{person_id}/mappings/{mapping_id}")
            assert response.status_code == 204
            mock_delete_mapping.assert_awaited_once_with(org_id, person_id, mapping_id)


@pytest.mark.asyncio
@patch("lif.identity_mapper_restapi.core.initialize", mock_initialize)
@patch("lif.identity_mapper_restapi.core.shutdown", mock_shutdown)
async def test_do_get_mappings_with_missing_org_id(mock_initialize, mock_shutdown):
    org_id = ""
    person_id = "person1"
    async with get_client() as client:
        response = await client.get(f"/organizations/{org_id}/persons/{person_id}/mappings")
        assert response.status_code == 404
        assert response.json() == {"detail": "Not Found"}


@pytest.mark.asyncio
@patch("lif.identity_mapper_restapi.core.initialize", mock_initialize)
@patch("lif.identity_mapper_restapi.core.shutdown", mock_shutdown)
async def test_do_get_mappings_with_missing_person_id(mock_initialize, mock_shutdown):
    org_id = "org1"
    person_id = ""
    async with get_client() as client:
        response = await client.get(f"/organizations/{org_id}/persons/{person_id}/mappings")
        assert response.status_code == 404
        assert response.json() == {"detail": "Not Found"}


@pytest.mark.asyncio
@patch("lif.identity_mapper_restapi.core.initialize", mock_initialize)
@patch("lif.identity_mapper_restapi.core.shutdown", mock_shutdown)
async def test_do_get_mappings_success(mock_initialize, mock_shutdown):
    org_id = "org1"
    person_id = "person1"
    mock_mappings = [
        core.IdentityMapping(
            mapping_id="mapping1",
            lif_organization_id=org_id,
            lif_organization_person_id=person_id,
            target_system_id="ext_org1",
            target_system_person_id_type="School-assigned number",
            target_system_person_id="ext_person1",
        ),
        core.IdentityMapping(
            mapping_id="mapping2",
            lif_organization_id=org_id,
            lif_organization_person_id=person_id,
            target_system_id="ext_org2",
            target_system_person_id_type="School-assigned number",
            target_system_person_id="ext_person2",
        ),
    ]
    async with get_client() as client:
        with patch.object(core.service, "get_mappings", new_callable=AsyncMock) as mock_get_mappings:
            mock_get_mappings.return_value = mock_mappings
            response = await client.get(f"/organizations/{org_id}/persons/{person_id}/mappings")
            assert response.status_code == 200
            assert response.json() == [mapping.model_dump() for mapping in mock_mappings]
            mock_get_mappings.assert_awaited_once_with(org_id, person_id)


@pytest.mark.asyncio
@patch("lif.identity_mapper_restapi.core.initialize", mock_initialize)
@patch("lif.identity_mapper_restapi.core.shutdown", mock_shutdown)
async def test_do_get_mappings_not_found(mock_initialize, mock_shutdown):
    org_id = "org1"
    person_id = "person1"
    async with get_client() as client:
        with patch.object(core.service, "get_mappings", new_callable=AsyncMock) as mock_get_mappings:
            mock_get_mappings.return_value = []
            response = await client.get(f"/organizations/{org_id}/persons/{person_id}/mappings")
            assert response.status_code == 200
            assert response.json() == []
            mock_get_mappings.assert_awaited_once_with(org_id, person_id)


@pytest.mark.asyncio
@patch("lif.identity_mapper_restapi.core.initialize", mock_initialize)
@patch("lif.identity_mapper_restapi.core.shutdown", mock_shutdown)
async def test_do_get_mappings_datastore_exception(mock_initialize, mock_shutdown):
    org_id = "org1"
    person_id = "person1"
    async with get_client() as client:
        with patch.object(core.service, "get_mappings", new_callable=AsyncMock) as mock_get_mappings:
            mock_get_mappings.side_effect = DataStoreException("Failed to retrieve mappings")
            response = await client.get(f"/organizations/{org_id}/persons/{person_id}/mappings")
            assert response.status_code == 500
            response_json = response.json()
            assert response_json["status_code"] == "500"
            assert response_json["path"] == f"/organizations/{org_id}/persons/{person_id}/mappings"
            assert response_json["message"] == "Internal server error. Please try again later."
            assert "code" in response_json
            mock_get_mappings.assert_awaited_once_with(org_id, person_id)


@pytest.mark.asyncio
@patch("lif.identity_mapper_restapi.core.initialize", mock_initialize)
@patch("lif.identity_mapper_restapi.core.shutdown", mock_shutdown)
async def test_do_get_mappings_service_exception(mock_initialize, mock_shutdown):
    org_id = "org1"
    person_id = "person1"
    async with get_client() as client:
        with patch.object(core.service, "get_mappings", new_callable=AsyncMock) as mock_get_mappings:
            mock_get_mappings.side_effect = Exception("Service error")
            try:
                await client.get(f"/organizations/{org_id}/persons/{person_id}/mappings")
            except Exception as e:
                assert str(e) == "Service error"
                mock_get_mappings.assert_awaited_once_with(org_id, person_id)


@pytest.mark.asyncio
@patch("lif.identity_mapper_restapi.core.initialize", mock_initialize)
@patch("lif.identity_mapper_restapi.core.shutdown", mock_shutdown)
async def test_do_save_mappings_datastore_exception(mock_initialize, mock_shutdown):
    org_id = "org1"
    person_id = "person1"
    new_mappings = [
        {
            "mapping_id": None,
            "lif_organization_id": org_id,
            "lif_organization_person_id": person_id,
            "target_system_id": "ext_org1",
            "target_system_person_id_type": "School-assigned number",
            "target_system_person_id": "ext_person1",
        }
    ]
    async with get_client() as client:
        with patch.object(core.service, "save_mappings", new_callable=AsyncMock) as mock_save_mappings:
            mock_save_mappings.side_effect = DataStoreException("Failed to save mappings")
            response = await client.post(f"/organizations/{org_id}/persons/{person_id}/mappings", json=new_mappings)
            assert response.status_code == 500
            response_json = response.json()
            assert response_json["status_code"] == "500"
            assert response_json["path"] == f"/organizations/{org_id}/persons/{person_id}/mappings"
            assert response_json["message"] == "Internal server error. Please try again later."
            assert "code" in response_json
            mock_save_mappings.assert_awaited_once_with(
                org_id, person_id, [core.IdentityMapping(**m) for m in new_mappings]
            )


# The column widths from projects/lif_identity_mapper_mariadb/02-ddl.sql after #1258. Pinned here
# as literals so a change to a column width shows up as a deliberate test change (#1300).
FIELD_WIDTHS = [
    ("lif_organization_id", 191),
    ("lif_organization_person_id", 191),
    ("target_system_id", 191),
    ("target_system_person_id_type", 100),
    ("target_system_person_id", 255),
]


def _mapping_with(field: str, value: str) -> dict:
    mapping = {
        "mapping_id": None,
        "lif_organization_id": "org1",
        "lif_organization_person_id": "person1",
        "target_system_id": "ext_org1",
        "target_system_person_id_type": "School-assigned number",
        "target_system_person_id": "ext_person1",
    }
    mapping[field] = value
    return mapping


@pytest.mark.asyncio
@pytest.mark.parametrize("field,width", FIELD_WIDTHS)
@patch("lif.identity_mapper_restapi.core.initialize", mock_initialize)
@patch("lif.identity_mapper_restapi.core.shutdown", mock_shutdown)
async def test_do_save_mappings_rejects_a_value_wider_than_its_column(field, width):
    """One character over the column width is a 422 naming the field, not a 500 from the database (#1300)."""
    async with get_client() as client:
        with patch.object(core.service, "save_mappings", new_callable=AsyncMock) as mock_save_mappings:
            response = await client.post(
                "/organizations/org1/persons/person1/mappings", json=[_mapping_with(field, "x" * (width + 1))]
            )

    assert response.status_code == 422
    assert [error["loc"] for error in response.json()["detail"]] == [["body", 0, field]]
    mock_save_mappings.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("field,width", FIELD_WIDTHS)
@patch("lif.identity_mapper_restapi.core.initialize", mock_initialize)
@patch("lif.identity_mapper_restapi.core.shutdown", mock_shutdown)
async def test_do_save_mappings_accepts_a_value_exactly_as_wide_as_its_column(field, width):
    """The service receives the plain IdentityMapping DTO; the request model only validates."""
    mapping = _mapping_with(field, "x" * width)
    async with get_client() as client:
        with patch.object(core.service, "save_mappings", new_callable=AsyncMock) as mock_save_mappings:
            mock_save_mappings.return_value = []
            response = await client.post("/organizations/org1/persons/person1/mappings", json=[mapping])

    assert response.status_code == 200
    mock_save_mappings.assert_awaited_once_with("org1", "person1", [core.IdentityMapping(**mapping)])


@pytest.mark.asyncio
@patch("lif.identity_mapper_restapi.core.initialize", mock_initialize)
@patch("lif.identity_mapper_restapi.core.shutdown", mock_shutdown)
async def test_do_save_mappings_persistent_collision_returns_409(mock_initialize, mock_shutdown, db_session_factory):
    """
    A natural-key collision that survives the storage retry answers 409, not the generic 500 (#1261).

    Runs through the real service and SQL storage rather than a mocked service, because the
    ways this breaks sit between the layers: the storage brick's broad `except` swallowing the
    conflict into a DataStoreException, or the exception reaching the LIFException handler's
    500 instead of its own. A test that stops at the exception type passes in both cases.
    """
    org_id = "org1"
    person_id = "person1"
    mapping = {
        "mapping_id": None,
        "lif_organization_id": org_id,
        "lif_organization_person_id": person_id,
        "target_system_id": "ext_org1",
        "target_system_person_id_type": "School-assigned number",
        "target_system_person_id": "ext_person1",
    }
    async with db_session_factory.kw["bind"].begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    storage = IdentityMapperSqlStorage(db_session_factory)
    await storage.save_mappings([core.IdentityMapping(**{**mapping, "target_system_person_id": "ext_racer"})])

    # Every pre-read misses the committed row, so both attempts insert into the existing key.
    reads: list[int] = []

    async def stale_read(*args, **kwargs):
        reads.append(1)
        return []

    with (
        patch.object(core, "service", IdentityMapperService(storage=storage)),
        patch.object(storage_core, "read_by_lif_org_and_person", side_effect=stale_read),
    ):
        async with get_client() as client:
            response = await client.post(f"/organizations/{org_id}/persons/{person_id}/mappings", json=[mapping])

    assert response.status_code == 409
    response_json = response.json()
    assert response_json["status_code"] == "409"
    assert response_json["path"] == f"/organizations/{org_id}/persons/{person_id}/mappings"
    assert "retried" in response_json["message"]
    # An expected, self-describing outcome: no correlation UUID for an operator to chase.
    assert "code" not in response_json
    # Still exactly one retry before the 409 (#1260's bound).
    assert len(reads) == 2


@pytest.mark.asyncio
@patch("lif.identity_mapper_restapi.core.initialize", mock_initialize)
@patch("lif.identity_mapper_restapi.core.shutdown", mock_shutdown)
async def test_do_save_mappings_success(mock_initialize, mock_shutdown):
    org_id = "org1"
    person_id = "person1"
    new_mappings = [
        {
            "mapping_id": None,
            "lif_organization_id": org_id,
            "lif_organization_person_id": person_id,
            "target_system_id": "ext_org1",
            "target_system_person_id_type": "School-assigned number",
            "target_system_person_id": "ext_person1",
        }
    ]
    saved_mappings = [
        core.IdentityMapping(
            mapping_id="mapping1",
            lif_organization_id=org_id,
            lif_organization_person_id=person_id,
            target_system_id="ext_org1",
            target_system_person_id_type="School-assigned number",
            target_system_person_id="ext_person1",
        )
    ]
    async with get_client() as client:
        with patch.object(core.service, "save_mappings", new_callable=AsyncMock) as mock_save_mappings:
            mock_save_mappings.return_value = saved_mappings
            response = await client.post(f"/organizations/{org_id}/persons/{person_id}/mappings", json=new_mappings)
            assert response.status_code == 200
            assert response.json() == [mapping.model_dump() for mapping in saved_mappings]
            mock_save_mappings.assert_awaited_once_with(
                org_id, person_id, [core.IdentityMapping(**m) for m in new_mappings]
            )


@pytest.mark.asyncio
@patch("lif.identity_mapper_restapi.core.initialize", mock_initialize)
@patch("lif.identity_mapper_restapi.core.shutdown", mock_shutdown)
async def test_do_save_mappings_service_exception(mock_initialize, mock_shutdown):
    org_id = "org1"
    person_id = "person1"
    new_mappings = [
        {
            "mapping_id": None,
            "lif_organization_id": org_id,
            "lif_organization_person_id": person_id,
            "target_system_id": "ext_org1",
            "target_system_person_id_type": "School-assigned number",
            "target_system_person_id": "ext_person1",
        }
    ]
    async with get_client() as client:
        with patch.object(core.service, "save_mappings", new_callable=AsyncMock) as mock_save_mappings:
            mock_save_mappings.side_effect = Exception("Service error")
            try:
                await client.post(f"/organizations/{org_id}/persons/{person_id}/mappings", json=new_mappings)
            except Exception as e:
                assert str(e) == "Service error"
                mock_save_mappings.assert_awaited_once_with(
                    org_id, person_id, [core.IdentityMapping(**m) for m in new_mappings]
                )

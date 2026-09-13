import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, event
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from unittest.mock import AsyncMock, MagicMock, patch

from lif.exceptions.core import DataNotFoundException, DataStoreException
from lif.identity_mapper_restapi import core
from lif.identity_mapper_service.core import IdentityMapperService


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
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False

    def execute(self, *args, **kwargs):
        raise OperationalError("SELECT 1", {}, Exception("database is down"))


@pytest.fixture()
def db_session_factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    yield sessionmaker(autocommit=False, autoflush=False, bind=engine)
    engine.dispose()


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

    event.listen(db_session_factory.kw["bind"], "before_cursor_execute", record_statement)
    try:
        async with get_client() as client:
            with patch.object(core, "get_db_session_factory", return_value=db_session_factory):
                response = await client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        assert any("SELECT 1" in statement for statement in executed_statements)
    finally:
        event.remove(db_session_factory.kw["bind"], "before_cursor_execute", record_statement)


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

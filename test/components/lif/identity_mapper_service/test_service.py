from unittest.mock import AsyncMock, Mock
import pytest

from lif.datatypes import IdentityMapping
from lif.exceptions.core import DataNotFoundException, DataStoreException
from lif.identity_mapper_service.core import IdentityMapperService
from lif.identity_mapper_storage.core import DeleteOutcome, IdentityMapperStorage


def _mapping(mapping_id=None, org="org-1", person="person-1", target_system="ext-org-1", person_id="ext-person-1"):
    return IdentityMapping(
        mapping_id=mapping_id,
        lif_organization_id=org,
        lif_organization_person_id=person,
        target_system_id=target_system,
        target_system_person_id_type="School-assigned number",
        target_system_person_id=person_id,
    )


def test_service_initialization():
    storage: IdentityMapperStorage = AsyncMock()
    service = IdentityMapperService(storage=storage)
    assert service.storage == storage


@pytest.mark.asyncio
async def test_get_mappings_with_no_mappings():
    storage: IdentityMapperStorage = Mock()
    storage.get_mappings = AsyncMock(return_value=[])
    service = IdentityMapperService(storage=storage)
    result = await service.get_mappings("org-1", "person-1")
    assert result == []
    storage.get_mappings.assert_called_once_with("org-1", "person-1")


@pytest.mark.asyncio
async def test_get_mappings_with_mappings():
    mappings = [
        _mapping(mapping_id="test-id-1", target_system="ext-org-1", person_id="ext-person-1"),
        _mapping(mapping_id="test-id-2", target_system="ext-org-2", person_id="ext-person-2"),
    ]
    storage: IdentityMapperStorage = Mock()
    storage.get_mappings = AsyncMock(return_value=mappings)
    service = IdentityMapperService(storage=storage)
    result = await service.get_mappings("org-1", "person-1")
    assert result == mappings
    storage.get_mappings.assert_called_once_with("org-1", "person-1")


@pytest.mark.asyncio
async def test_get_mappings_when_storage_raises_exception():
    storage: IdentityMapperStorage = Mock()
    storage.get_mappings = AsyncMock(side_effect=Exception("Database error"))
    service = IdentityMapperService(storage=storage)
    with pytest.raises(Exception) as err:
        await service.get_mappings("org-1", "person-1")
    assert str(err.value) == "Database error"
    storage.get_mappings.assert_called_once_with("org-1", "person-1")


@pytest.mark.asyncio
async def test_save_mappings_success():
    mappings = [_mapping(target_system="ext-org-1"), _mapping(target_system="ext-org-2")]
    saved_mappings = [
        _mapping(mapping_id="saved-id-1", target_system="ext-org-1"),
        _mapping(mapping_id="saved-id-2", target_system="ext-org-2"),
    ]
    storage: IdentityMapperStorage = Mock()
    storage.save_mappings = AsyncMock(return_value=saved_mappings)
    service = IdentityMapperService(storage=storage)
    result = await service.save_mappings("org-1", "person-1", mappings)
    assert result == saved_mappings
    storage.save_mappings.assert_called_once_with(mappings)


@pytest.mark.asyncio
async def test_save_mappings_raises_when_storage_returns_nothing():
    storage: IdentityMapperStorage = Mock()
    storage.save_mappings = AsyncMock(return_value=[])
    service = IdentityMapperService(storage=storage)
    with pytest.raises(DataStoreException):
        await service.save_mappings("org-1", "person-1", [_mapping()])


@pytest.mark.asyncio
async def test_save_mappings_when_storage_raises_exception():
    storage: IdentityMapperStorage = Mock()
    storage.save_mappings = AsyncMock(side_effect=Exception("Database error"))
    service = IdentityMapperService(storage=storage)
    with pytest.raises(Exception) as err:
        await service.save_mappings("org-1", "person-1", [_mapping()])
    assert str(err.value) == "Database error"


@pytest.mark.asyncio
async def test_save_mappings_with_org_mismatch():
    storage: IdentityMapperStorage = Mock()
    storage.save_mappings = AsyncMock()
    service = IdentityMapperService(storage=storage)
    with pytest.raises(ValueError):
        await service.save_mappings("org-1", "person-1", [_mapping(org="org-2")])
    storage.save_mappings.assert_not_called()


@pytest.mark.asyncio
async def test_save_mappings_with_person_mismatch():
    storage: IdentityMapperStorage = Mock()
    storage.save_mappings = AsyncMock()
    service = IdentityMapperService(storage=storage)
    with pytest.raises(ValueError):
        await service.save_mappings("org-1", "person-1", [_mapping(person="person-2")])
    storage.save_mappings.assert_not_called()


@pytest.mark.asyncio
async def test_delete_mapping_success():
    storage: IdentityMapperStorage = Mock()
    storage.delete_mapping_for_owner = AsyncMock(return_value=DeleteOutcome.DELETED)
    service = IdentityMapperService(storage=storage)
    result = await service.delete_mapping("org-1", "person-1", "mapping-id-1")
    assert result is None
    # The caller's org and person must reach storage, which is where ownership is
    # enforced -- the service no longer checks it afterwards (#1150).
    storage.delete_mapping_for_owner.assert_called_once_with("mapping-id-1", "org-1", "person-1")
    storage.get_mapping_by_id.assert_not_called()


@pytest.mark.asyncio
async def test_delete_mapping_when_mapping_not_found():
    storage: IdentityMapperStorage = Mock()
    storage.delete_mapping_for_owner = AsyncMock(return_value=DeleteOutcome.NOT_FOUND)
    service = IdentityMapperService(storage=storage)
    with pytest.raises(DataNotFoundException) as err:
        await service.delete_mapping("org-1", "person-1", "non-existent-id")
    assert str(err.value) == "Mapping not found for ID: non-existent-id"


@pytest.mark.asyncio
async def test_delete_mapping_not_owned_raises_value_error():
    """A mapping owned by someone else is a 400, distinct from the 404 above."""
    storage: IdentityMapperStorage = Mock()
    storage.delete_mapping_for_owner = AsyncMock(return_value=DeleteOutcome.NOT_OWNED)
    service = IdentityMapperService(storage=storage)
    with pytest.raises(ValueError):
        await service.delete_mapping("org-1", "person-1", "mapping-id-1")


@pytest.mark.asyncio
async def test_delete_mapping_when_storage_raises_exception():
    storage: IdentityMapperStorage = Mock()
    storage.delete_mapping_for_owner = AsyncMock(side_effect=DataStoreException("Database error."))
    service = IdentityMapperService(storage=storage)
    with pytest.raises(DataStoreException) as err:
        await service.delete_mapping("org-1", "person-1", "mapping-id-1")
    assert str(err.value) == "Database error."
    storage.delete_mapping_for_owner.assert_called_once_with("mapping-id-1", "org-1", "person-1")

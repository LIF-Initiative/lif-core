from unittest.mock import patch

import pytest

from lif.datatypes import IdentityMapping
from lif.exceptions.core import DataStoreException
from lif.identity_mapper_storage_sql.core import IdentityMapperSqlStorage


def _mapping(
    org: str = "org-1",
    person: str = "person-1",
    target_system: str = "sys-1",
    id_type: str = "School-assigned number",
    person_id: str = "ext-1",
    mapping_id: str | None = None,
) -> IdentityMapping:
    return IdentityMapping(
        mapping_id=mapping_id,
        lif_organization_id=org,
        lif_organization_person_id=person,
        target_system_id=target_system,
        target_system_person_id_type=id_type,
        target_system_person_id=person_id,
    )


@pytest.mark.asyncio
async def test_save_mappings_creates_new_rows(storage: IdentityMapperSqlStorage):
    mappings = [_mapping(target_system="sys-1", person_id="ext-1"), _mapping(target_system="sys-2", person_id="ext-2")]
    saved = await storage.save_mappings(mappings)
    assert len(saved) == 2
    assert all(m.mapping_id for m in saved)
    fetched = await storage.get_mappings("org-1", "person-1")
    assert len(fetched) == 2


@pytest.mark.asyncio
async def test_save_mappings_updates_existing_row(storage: IdentityMapperSqlStorage):
    saved = await storage.save_mappings([_mapping(target_system="sys-1", person_id="ext-1")])
    saved_id = saved[0].mapping_id
    updated = await storage.save_mappings([_mapping(target_system="sys-1", person_id="ext-2")])
    assert len(updated) == 1
    assert updated[0].mapping_id == saved_id
    assert updated[0].target_system_person_id == "ext-2"
    fetched = await storage.get_mappings("org-1", "person-1")
    assert len(fetched) == 1
    assert fetched[0].target_system_person_id == "ext-2"


@pytest.mark.asyncio
async def test_save_mappings_is_noop_for_unchanged_row(storage: IdentityMapperSqlStorage):
    saved = await storage.save_mappings([_mapping(target_system="sys-1", person_id="ext-1")])
    saved_id = saved[0].mapping_id
    saved_again = await storage.save_mappings([_mapping(target_system="sys-1", person_id="ext-1")])
    assert len(saved_again) == 1
    assert saved_again[0].mapping_id == saved_id
    fetched = await storage.get_mappings("org-1", "person-1")
    assert len(fetched) == 1


@pytest.mark.asyncio
async def test_save_mappings_duplicate_keys_in_batch_last_wins(storage: IdentityMapperSqlStorage):
    saved = await storage.save_mappings(
        [_mapping(target_system="sys-1", person_id="ext-1"), _mapping(target_system="sys-1", person_id="ext-2")]
    )
    assert len(saved) == 2
    fetched = await storage.get_mappings("org-1", "person-1")
    assert len(fetched) == 1
    assert fetched[0].target_system_person_id == "ext-2"


@pytest.mark.asyncio
async def test_save_mappings_rolls_back_whole_batch_on_failure(storage: IdentityMapperSqlStorage):
    mappings = [_mapping(target_system="sys-1", person_id="ext-1"), _mapping(target_system="sys-2", person_id="ext-2")]
    with patch("lif.identity_mapper_storage_sql.core.create", side_effect=[mappings[0], Exception("boom")]):
        with pytest.raises(DataStoreException):
            await storage.save_mappings(mappings)
    fetched = await storage.get_mappings("org-1", "person-1")
    assert fetched == []


@pytest.mark.asyncio
async def test_save_mapping_single_path(storage: IdentityMapperSqlStorage):
    mapping = _mapping(target_system="sys-1", person_id="ext-1")
    saved = await storage.save_mapping(mapping)
    assert saved.mapping_id
    fetched = await storage.get_mappings("org-1", "person-1")
    assert len(fetched) == 1


@pytest.mark.asyncio
async def test_get_mapping_by_id_returns_mapping(storage: IdentityMapperSqlStorage):
    saved = await storage.save_mappings([_mapping(target_system="sys-1", person_id="ext-1")])
    fetched = await storage.get_mapping_by_id(saved[0].mapping_id)
    assert fetched is not None
    assert fetched.target_system_person_id == "ext-1"


@pytest.mark.asyncio
async def test_get_mapping_by_id_returns_none_for_missing(storage: IdentityMapperSqlStorage):
    assert await storage.get_mapping_by_id("does-not-exist") is None


@pytest.mark.asyncio
async def test_get_mappings_returns_empty_list_when_none(storage: IdentityMapperSqlStorage):
    assert await storage.get_mappings("org-1", "person-1") == []


@pytest.mark.asyncio
async def test_delete_mapping_by_id_deletes_and_returns_mapping(storage: IdentityMapperSqlStorage):
    saved = await storage.save_mappings([_mapping(target_system="sys-1", person_id="ext-1")])
    deleted = await storage.delete_mapping_by_id(saved[0].mapping_id)
    assert deleted is not None
    assert deleted.mapping_id == saved[0].mapping_id
    assert await storage.get_mappings("org-1", "person-1") == []


@pytest.mark.asyncio
async def test_delete_mapping_by_id_returns_none_for_missing(storage: IdentityMapperSqlStorage):
    assert await storage.delete_mapping_by_id("does-not-exist") is None

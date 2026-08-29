from unittest.mock import patch

import pytest

from lif.datatypes import IdentityMapping
from lif.exceptions.core import DataStoreException
from lif.identity_mapper_storage.core import DeleteOutcome
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
async def test_delete_mapping_for_owner_deletes_own_mapping(storage: IdentityMapperSqlStorage):
    saved = await storage.save_mappings([_mapping(target_system="sys-1", person_id="ext-1")])
    outcome = await storage.delete_mapping_for_owner(saved[0].mapping_id, "org-1", "person-1")
    assert outcome is DeleteOutcome.DELETED
    assert await storage.get_mappings("org-1", "person-1") == []


@pytest.mark.asyncio
async def test_delete_mapping_for_owner_returns_not_found_for_missing(storage: IdentityMapperSqlStorage):
    assert await storage.delete_mapping_for_owner("does-not-exist", "org-1", "person-1") is DeleteOutcome.NOT_FOUND


@pytest.mark.asyncio
async def test_delete_mapping_for_owner_does_not_delete_another_orgs_mapping(storage: IdentityMapperSqlStorage):
    """#1150: a foreign mapping_id must survive the attempt.

    The regression this guards is ordering, not signalling: the old code deleted and
    committed first and compared organizations afterwards, so the caller got an error
    *and* the other organization lost its row. Asserting the outcome alone would still
    pass against that bug -- the surviving row is the assertion that matters.
    """
    saved = await storage.save_mappings([_mapping(org="org-2", person="person-2", target_system="sys-1")])
    victim_id = saved[0].mapping_id

    outcome = await storage.delete_mapping_for_owner(victim_id, "org-1", "person-1")

    assert outcome is DeleteOutcome.NOT_OWNED
    survivors = await storage.get_mappings("org-2", "person-2")
    assert [m.mapping_id for m in survivors] == [victim_id]


@pytest.mark.asyncio
async def test_delete_mapping_for_owner_does_not_delete_another_persons_mapping(storage: IdentityMapperSqlStorage):
    """#1150: same organization, different person -- the row must also survive."""
    saved = await storage.save_mappings([_mapping(org="org-1", person="person-2", target_system="sys-1")])
    victim_id = saved[0].mapping_id

    outcome = await storage.delete_mapping_for_owner(victim_id, "org-1", "person-1")

    assert outcome is DeleteOutcome.NOT_OWNED
    survivors = await storage.get_mappings("org-1", "person-2")
    assert [m.mapping_id for m in survivors] == [victim_id]

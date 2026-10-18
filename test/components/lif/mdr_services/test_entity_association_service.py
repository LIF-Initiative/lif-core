import types
import pytest
from unittest.mock import AsyncMock, MagicMock

pytestmark = pytest.mark.asyncio

svc = pytest.importorskip("lif.mdr_services.entity_association_service")

from lif.mdr_dto.entity_association_dto import UpdateEntityAssociationDTO  # noqa: E402


@pytest.fixture
def fake_session():
    s = MagicMock()
    s.execute = AsyncMock()
    s.get = AsyncMock(return_value=types.SimpleNamespace(Name="Course", Array="Yes"))  # the child entity
    s.add = MagicMock()
    s.commit = AsyncMock()
    s.refresh = AsyncMock()
    return s


@pytest.fixture(autouse=True)
def stub_dto(monkeypatch):
    monkeypatch.setattr(svc, "EntityAssociationDTO", types.SimpleNamespace(from_orm=lambda o: o))


@pytest.fixture
def existing_association():
    return types.SimpleNamespace(
        Id=9,
        Deleted=False,
        ParentEntityId=4,
        ChildEntityId=5,
        Relationship="parentOf",
        Placement=None,
        ExtendedByDataModelId=None,
        Name=None,  # not computed yet, as on a row an older MDR image created
        Array=None,
    )


async def test_update_validates_a_zero_child_entity_id(fake_session, monkeypatch, existing_association):
    """ChildEntityId=0 must reach check_entity_by_id — the write applies it either way."""
    monkeypatch.setattr(svc, "get_entity_association_by_id", AsyncMock(return_value=existing_association))
    check_entity = AsyncMock()
    monkeypatch.setattr(svc, "check_entity_by_id", check_entity)
    lookup = AsyncMock(return_value=None)
    monkeypatch.setattr(svc, "get_entity_association_by_parent_child_relationship", lookup)

    await svc.update_entity_association(fake_session, 9, UpdateEntityAssociationDTO(ChildEntityId=0))

    check_entity.assert_awaited_once_with(fake_session, 0)
    # The duplicate check must compare against the supplied 0, not fall back to the existing 5.
    assert lookup.await_args.args[2] == 0
    assert existing_association.ChildEntityId == 0


async def test_update_ignores_ids_the_client_did_not_send(fake_session, monkeypatch, existing_association):
    monkeypatch.setattr(svc, "get_entity_association_by_id", AsyncMock(return_value=existing_association))
    check_entity = AsyncMock()
    monkeypatch.setattr(svc, "check_entity_by_id", check_entity)
    monkeypatch.setattr(svc, "get_entity_association_by_parent_child_relationship", AsyncMock(return_value=None))

    await svc.update_entity_association(fake_session, 9, UpdateEntityAssociationDTO(Notes="just a note"))

    check_entity.assert_not_awaited()
    assert existing_association.ParentEntityId == 4
    assert existing_association.ChildEntityId == 5


async def test_update_recomputes_name_and_array_from_the_child(fake_session, monkeypatch, existing_association):
    """#1386: a Placement edit changes the key the child is stored under, so Name follows it."""
    monkeypatch.setattr(svc, "get_entity_association_by_id", AsyncMock(return_value=existing_association))

    await svc.update_entity_association(fake_session, 9, UpdateEntityAssociationDTO(Placement="Reference"))

    fake_session.get.assert_awaited_with(svc.Entity, 5)
    assert (existing_association.Name, existing_association.Array) == ("parentOfRefCourse", True)


async def test_update_leaves_a_name_and_array_that_did_not_come_from_the_rule(
    fake_session, monkeypatch, existing_association
):
    """#1386: a Name/Array set some other way (a model import, #1388's collision fixes) is not overwritten."""
    existing_association.Name, existing_association.Array = (
        "accreditedBy",
        False,
    )  # the rule would give parentOfCourse/True
    monkeypatch.setattr(svc, "get_entity_association_by_id", AsyncMock(return_value=existing_association))

    await svc.update_entity_association(fake_session, 9, UpdateEntityAssociationDTO(Placement="Reference"))

    assert (existing_association.Name, existing_association.Array) == ("accreditedBy", False)

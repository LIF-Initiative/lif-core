import types
import pytest
from unittest.mock import AsyncMock, MagicMock

pytestmark = pytest.mark.asyncio

svc = pytest.importorskip("lif.mdr_services.value_mapping_service")

from lif.mdr_dto.value_mapping_dto import UpdateValueSetValueMappingDTO  # noqa: E402


class _ScalarListResult:
    def __init__(self, items):
        self._items = items

    def scalars(self):
        return self

    def all(self):
        return list(self._items)


@pytest.fixture
def fake_session():
    s = MagicMock()
    s.execute = AsyncMock(return_value=_ScalarListResult([]))
    s.get = AsyncMock()
    s.add = MagicMock()
    s.commit = AsyncMock()
    s.refresh = AsyncMock()
    return s


@pytest.fixture(autouse=True)
def stub_dto(monkeypatch):
    monkeypatch.setattr(svc, "ValueSetValueMappingDTO", types.SimpleNamespace(from_orm=lambda o: o))


@pytest.fixture
def existing_mapping():
    return types.SimpleNamespace(
        Id=7,
        Deleted=False,
        TransformationGroupId=3,
        SourceValueSetId=11,
        TargetValueSetId=12,
        SourceValueId=21,
        TargetValueId=22,
    )


async def test_update_mapping_validates_a_zero_id_instead_of_skipping(fake_session, monkeypatch, existing_mapping):
    """A client-supplied id of 0 must be validated, not read as "field not provided".

    The write path applies whatever the client set (dict(exclude_unset=True)), so a guard
    that skips validation for 0 lets an invalid FK through to the database.
    """
    monkeypatch.setattr(svc, "get_mapping_by_id", AsyncMock(return_value=existing_mapping))
    get_group = AsyncMock()
    monkeypatch.setattr(svc, "get_transformation_group_by_id", get_group)
    monkeypatch.setattr(svc, "get_value_set_by_id", AsyncMock())
    monkeypatch.setattr(svc, "get_value_set_value_by_id", AsyncMock(return_value=types.SimpleNamespace(ValueSetId=11)))

    await svc.update_mapping(fake_session, 7, UpdateValueSetValueMappingDTO(TransformationGroupId=0))

    get_group.assert_awaited_once_with(session=fake_session, id=0)
    assert existing_mapping.TransformationGroupId == 0


async def test_update_mapping_zero_source_value_set_id_is_used_for_the_match_check(
    fake_session, monkeypatch, existing_mapping
):
    """A supplied SourceValueSetId of 0 must be compared against, not replaced by the existing one."""
    monkeypatch.setattr(svc, "get_mapping_by_id", AsyncMock(return_value=existing_mapping))
    monkeypatch.setattr(svc, "get_transformation_group_by_id", AsyncMock())
    monkeypatch.setattr(svc, "get_value_set_by_id", AsyncMock())
    # The value belongs to value set 11 (the mapping's existing one), not to the supplied 0.
    monkeypatch.setattr(svc, "get_value_set_value_by_id", AsyncMock(return_value=types.SimpleNamespace(ValueSetId=11)))

    dto = UpdateValueSetValueMappingDTO(SourceValueId=21, SourceValueSetId=0)
    with pytest.raises(svc.HTTPException) as exc:
        await svc.update_mapping(fake_session, 7, dto)

    assert exc.value.status_code == 400
    assert "Source ValueSetId 0" in exc.value.detail


async def test_update_mapping_leaves_unset_ids_alone(fake_session, monkeypatch, existing_mapping):
    """Fields the client did not send stay untouched — the partial-update contract is exclude_unset."""
    monkeypatch.setattr(svc, "get_mapping_by_id", AsyncMock(return_value=existing_mapping))
    get_group = AsyncMock()
    monkeypatch.setattr(svc, "get_transformation_group_by_id", get_group)
    monkeypatch.setattr(svc, "get_value_set_by_id", AsyncMock())
    monkeypatch.setattr(svc, "get_value_set_value_by_id", AsyncMock())

    await svc.update_mapping(fake_session, 7, UpdateValueSetValueMappingDTO(Notes="untouched"))

    get_group.assert_not_awaited()
    assert existing_mapping.TransformationGroupId == 3
    assert existing_mapping.Notes == "untouched"

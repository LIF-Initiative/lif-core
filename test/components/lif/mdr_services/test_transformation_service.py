import types
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

pytestmark = pytest.mark.asyncio

svc = pytest.importorskip("lif.mdr_services.transformation_service")


@pytest.fixture
def fake_session():
    s = MagicMock()
    s.get = AsyncMock()
    return s


def _record(unique_name: str, data_model_id: int = 7, deleted: bool = False):
    return types.SimpleNamespace(UniqueName=unique_name, DataModelId=data_model_id, Deleted=deleted)


async def test_resolve_entity_id_path_to_named_path_ok_and_cached(fake_session):
    fake_session.get.side_effect = [_record("Person"), _record("Person.firstName")]
    cache: dict[tuple[str, int], str] = {}

    named = await svc._resolve_entity_id_path_to_named_path(session=fake_session, id_path="5,-12", cache=cache)
    assert named == "7:Person,7:~Person.firstName"

    # A second resolution of the same path is served from the cache.
    again = await svc._resolve_entity_id_path_to_named_path(session=fake_session, id_path="5,-12", cache=cache)
    assert again == named
    assert fake_session.get.await_count == 2


async def test_resolve_entity_id_path_negative_non_terminal_raises_domain_error(fake_session):
    with pytest.raises(svc.ExportPathError) as exc_info:
        await svc._resolve_entity_id_path_to_named_path(session=fake_session, id_path="-5,-12", cache={})

    assert not isinstance(exc_info.value, HTTPException)
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == ("Unable to export - invalid path '-5,-12': non-terminal ID '-5' must be positive")
    fake_session.get.assert_not_awaited()


@pytest.mark.parametrize(
    ("record", "expected_detail"),
    [
        (None, "Unable to export - Attribute ID 12 in path '5,-12' not found"),
        (_record("Person.firstName", deleted=True), "Unable to export - Attribute ID 12 in path '5,-12' is deleted"),
    ],
)
async def test_resolve_entity_id_path_missing_or_deleted_raises_domain_error(fake_session, record, expected_detail):
    fake_session.get.side_effect = [_record("Person"), record]

    with pytest.raises(svc.ExportPathError) as exc_info:
        await svc._resolve_entity_id_path_to_named_path(session=fake_session, id_path="5,-12", cache={})

    assert not isinstance(exc_info.value, HTTPException)
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == expected_detail

import pytest
from unittest.mock import AsyncMock, MagicMock

pytestmark = pytest.mark.asyncio

svc = pytest.importorskip("lif.mdr_services.jinja_translation_service")


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar(self):
        return self._value


@pytest.fixture
def fake_session():
    s = MagicMock()
    s.execute = AsyncMock()
    return s


async def test_get_base_model_ids_walks_through_a_zero_base_model_id(fake_session):
    """A BaseDataModelId of 0 is a real ancestor; treating it as "no base" truncates the walk."""
    # 7 -> 0 -> 2 -> (no base)
    fake_session.execute.side_effect = [_ScalarResult(0), _ScalarResult(2), _ScalarResult(None)]

    assert await svc.get_base_model_ids(session=fake_session, data_model_id=7) == [7, 0, 2]


async def test_get_base_model_ids_stops_at_a_model_with_no_base(fake_session):
    fake_session.execute.side_effect = [_ScalarResult(None)]

    assert await svc.get_base_model_ids(session=fake_session, data_model_id=7) == [7]

import types
from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.asyncio

svc = pytest.importorskip("lif.mdr_services.entity_service")


class _ScalarListResult:
    def __init__(self, items):
        self._items = list(items)

    def scalars(self):
        return self

    def all(self):
        return list(self._items)

    def first(self):
        return self._items[0] if self._items else None


class _CountResult:
    def __init__(self, n: int):
        self._n = n

    def scalar(self):
        return int(self._n)


@pytest.fixture
def fake_session():
    s = MagicMock()
    s.execute = AsyncMock()
    s.get = AsyncMock()
    s.add = MagicMock()
    s.commit = AsyncMock()
    s.refresh = AsyncMock()
    s.delete = AsyncMock()
    s.rollback = AsyncMock()
    return s


@pytest.fixture(autouse=True)
def stub_entity_dtos(monkeypatch):
    if hasattr(svc, "EntityDTO"):
        monkeypatch.setattr(
            svc.EntityDTO,
            "from_orm",
            staticmethod(lambda o: {"Id": getattr(o, "Id", None), "Name": getattr(o, "Name", None)}),
            raising=False,
        )

    if hasattr(svc, "ChildEntityDTO"):

        class _ChildDTOShim:
            def __init__(self, base):
                self.base = {"Id": getattr(base, "Id", None), "Name": getattr(base, "Name", None)}

            def model_copy(self, update=None):
                d = dict(self.base)
                if update:
                    d.update(update)
                return d

        monkeypatch.setattr(
            svc.ChildEntityDTO,
            "model_validate",
            staticmethod(lambda obj, from_attributes=True: _ChildDTOShim(obj)),
            raising=False,
        )


async def test_get_all_entities_returns_list(fake_session):
    rows = [types.SimpleNamespace(Id=1, Name="A"), types.SimpleNamespace(Id=2, Name="B")]
    fake_session.execute.return_value = _ScalarListResult(rows)
    out = await svc.get_all_entities(fake_session)
    assert [e.Id for e in out] == [1, 2]
    fake_session.execute.assert_awaited_once()


async def test_get_paginated_entities_no_pagination(fake_session):
    fake_session.execute.side_effect = [
        _CountResult(2),
        _ScalarListResult([types.SimpleNamespace(Id=10, Name="X"), types.SimpleNamespace(Id=11, Name="Y")]),
    ]
    total, items = await svc.get_paginated_entities(fake_session, pagination=False)
    assert total == 2
    assert items == [{"Id": 10, "Name": "X"}, {"Id": 11, "Name": "Y"}]


async def test_get_entity_by_id_ok(fake_session):
    ent = types.SimpleNamespace(Id=7, Deleted=False)
    fake_session.get.return_value = ent
    out = await svc.get_entity_by_id(fake_session, 7)
    assert out is ent


async def test_get_entity_by_id_404_missing(fake_session):
    fake_session.get.return_value = None
    with pytest.raises(svc.HTTPException) as exc:
        await svc.get_entity_by_id(fake_session, 1)
    assert exc.value.status_code == 404


async def test_get_entity_by_id_404_deleted(fake_session):
    fake_session.get.return_value = types.SimpleNamespace(Deleted=True)
    with pytest.raises(svc.HTTPException):
        await svc.get_entity_by_id(fake_session, 1)


async def test_get_entity_by_attribute_id_fetches_via_association(fake_session, monkeypatch):
    assoc = types.SimpleNamespace(EntityId=77, Deleted=False)
    fake_session.execute.return_value = _ScalarListResult([assoc])
    ent = types.SimpleNamespace(Id=77, Name="Learner", Deleted=False)
    monkeypatch.setattr(svc, "get_entity_by_id", AsyncMock(return_value=ent))
    out = await svc.get_entity_by_attribute_id(fake_session, attribute_id=5)
    assert out == {"Id": 77, "Name": "Learner"}
    svc.get_entity_by_id.assert_awaited_once()


async def test_create_entity_sets_extension_flags_and_saves(fake_session, monkeypatch):
    dm_type = getattr(svc, "DataModelType")
    dm = types.SimpleNamespace(Id=100, BaseDataModelId=1, Type=dm_type.OrgLIF)
    monkeypatch.setattr(svc, "check_datamodel_by_id", AsyncMock(return_value=dm))
    monkeypatch.setattr(svc, "check_entity_exists", AsyncMock(return_value=None))

    class _CreateDTO:
        def __init__(self):
            self.Name = "Learner"
            self.UniqueName = "dm.learner"
            self.DataModelId = 100
            self.Extension = False

        def dict(self):
            return {
                "Name": self.Name,
                "UniqueName": self.UniqueName,
                "DataModelId": self.DataModelId,
                "Extension": self.Extension,
            }

    if not hasattr(svc, "Entity"):
        monkeypatch.setattr(svc, "Entity", lambda **kw: types.SimpleNamespace(**kw))

    out = await svc.create_entity(fake_session, _CreateDTO())
    fake_session.commit.assert_awaited()
    fake_session.refresh.assert_awaited()
    assert out["Name"] == "Learner"


async def test_create_entity_raises_400_on_duplicate(fake_session, monkeypatch):
    monkeypatch.setattr(
        svc, "check_datamodel_by_id", AsyncMock(return_value=types.SimpleNamespace(Id=1, BaseDataModelId=None))
    )
    monkeypatch.setattr(svc, "check_entity_exists", AsyncMock(return_value=True))

    class _Create:
        DataModelId = 1
        Name = "Dup"
        UniqueName = "dm.dup"
        Extension = False

        def dict(self):
            return {"Name": self.Name, "UniqueName": self.UniqueName, "DataModelId": self.DataModelId}

    with pytest.raises(svc.HTTPException) as exc:
        await svc.create_entity(fake_session, _Create())
    assert exc.value.status_code == 400


async def test_update_entity_happy_path_updates_fields(fake_session, monkeypatch):
    monkeypatch.setattr(svc, "check_datamodel_by_id", AsyncMock())
    current = types.SimpleNamespace(Id=9, Deleted=False, UniqueName="entity.old", DataModelId=1)
    monkeypatch.setattr(svc, "get_entity_by_id", AsyncMock(return_value=current))
    monkeypatch.setattr(svc, "check_entity_exists", AsyncMock(return_value=None))

    class _UpdateDTO:
        def __init__(self):
            self.UniqueName = "entity.new"
            self.DataModelId = 1

        def dict(self, exclude_unset=False):
            return {"UniqueName": "entity.new"}

    out = await svc.update_entity(fake_session, 9, _UpdateDTO())
    assert out["Id"] == 9
    fake_session.commit.assert_awaited()


async def test_update_entity_raises_400_on_conflict(fake_session, monkeypatch):
    monkeypatch.setattr(svc, "check_datamodel_by_id", AsyncMock())
    cur = types.SimpleNamespace(Id=5, Deleted=False, UniqueName="x", DataModelId=1)
    monkeypatch.setattr(svc, "get_entity_by_id", AsyncMock(return_value=cur))
    monkeypatch.setattr(svc, "check_entity_exists", AsyncMock(return_value=types.SimpleNamespace(Id=99)))

    class _Upd:
        UniqueName = "x"
        DataModelId = 1

        def dict(self, exclude_unset=False):
            return {}

    with pytest.raises(svc.HTTPException) as exc:
        await svc.update_entity(fake_session, 5, _Upd())
    assert exc.value.status_code == 400


async def test_delete_entity_deletes_graph_and_commits(fake_session, monkeypatch):
    monkeypatch.setattr(svc, "get_entity_by_id", AsyncMock(return_value=types.SimpleNamespace(Id=3, Deleted=False)))
    fake_session.execute.side_effect = [
        _ScalarListResult([types.SimpleNamespace(AttributeId=101), types.SimpleNamespace(AttributeId=102)]),
        _ScalarListResult([types.SimpleNamespace(Id=101), types.SimpleNamespace(Id=102)]),
        _ScalarListResult([types.SimpleNamespace(Id=999)]),
    ]

    out = await svc.delete_entity(fake_session, 3)
    assert out == {"ok": True}
    assert fake_session.delete.await_count >= 1
    fake_session.commit.assert_awaited_once()


async def test_delete_entity_rolls_back_on_exception(fake_session, monkeypatch):
    monkeypatch.setattr(svc, "get_entity_by_id", AsyncMock(return_value=types.SimpleNamespace(Id=3, Deleted=False)))

    async def _boom(*a, **k):
        raise RuntimeError("kaboom")

    fake_session.execute.side_effect = _boom
    with pytest.raises(svc.HTTPException) as exc:
        await svc.delete_entity(fake_session, 3)
    assert exc.value.status_code == 500
    fake_session.rollback.assert_awaited_once()


async def test_soft_delete_entity_marks_related_and_calls_soft_delete_attribute(fake_session, monkeypatch):
    monkeypatch.setattr(svc, "get_entity_by_id", AsyncMock(return_value=types.SimpleNamespace(Id=4, Deleted=False)))
    fake_session.execute.side_effect = [
        _ScalarListResult(
            [
                types.SimpleNamespace(AttributeId=201, Deleted=False),
                types.SimpleNamespace(AttributeId=202, Deleted=False),
            ]
        ),
        _ScalarListResult([types.SimpleNamespace(ParentEntityId=4, ChildEntityId=9, Deleted=False)]),
        _ScalarListResult([types.SimpleNamespace(Id=333, Deleted=False)]),
    ]
    monkeypatch.setattr(svc, "soft_delete_attribute", AsyncMock())

    out = await svc.soft_delete_entity(fake_session, 4)
    assert out == {"ok": True}
    assert svc.soft_delete_attribute.await_count == 2
    fake_session.commit.assert_awaited()


async def test_check_entity_exists_returns_entity_when_found(fake_session):
    e = types.SimpleNamespace(Id=1)
    fake_session.execute.return_value = _ScalarListResult([e])
    out = await svc.check_entity_exists(fake_session, "Learner", 10)
    assert out is e


async def test_check_entity_exists_returns_none_when_absent(fake_session):
    fake_session.execute.return_value = _ScalarListResult([])
    out = await svc.check_entity_exists(fake_session, "X", 1)
    assert out is None


async def test_get_entities_by_ids_maps_to_dtos(fake_session):
    fake_session.execute.return_value = _ScalarListResult(
        [types.SimpleNamespace(Id=1, Name="A"), types.SimpleNamespace(Id=2, Name="B")]
    )
    out = await svc.get_entities_by_ids(fake_session, [1, 2])
    assert out == [{"Id": 1, "Name": "A"}, {"Id": 2, "Name": "B"}]


async def test_get_list_of_entities_for_data_model_orglif_branch(fake_session, monkeypatch):
    dm_type = getattr(svc, "DataModelType")
    dm = types.SimpleNamespace(Id=100, Type=dm_type.OrgLIF, BaseDataModelId=1)
    monkeypatch.setattr(svc, "check_datamodel_by_id", AsyncMock(return_value=dm))

    fake_session.execute.side_effect = [
        _ScalarListResult([10, 11]),
        _ScalarListResult([types.SimpleNamespace(Id=10, Name="P"), types.SimpleNamespace(Id=11, Name="Q")]),
    ]

    total, items = await svc.get_list_of_entities_for_data_model(
        fake_session,
        data_model_id=100,
        pagination=False,
        partner_only=False,
        org_ext_only=False,
        this_organization="LIF",
    )
    assert total == 2
    assert items == [{"Id": 10, "Name": "P"}, {"Id": 11, "Name": "Q"}]


async def test_get_list_of_entities_for_data_model_baselif_branch(fake_session, monkeypatch):
    dm_type = getattr(svc, "DataModelType")
    dm = types.SimpleNamespace(Id=200, Type=dm_type.BaseLIF, BaseDataModelId=None)
    monkeypatch.setattr(svc, "check_datamodel_by_id", AsyncMock(return_value=dm))

    fake_session.execute.side_effect = [
        _CountResult(1),  # count
        _ScalarListResult([types.SimpleNamespace(Id=33, Name="R")]),
    ]
    total, items = await svc.get_list_of_entities_for_data_model(fake_session, data_model_id=200, pagination=True)
    assert total == 1
    assert items == [{"Id": 33, "Name": "R"}]


async def test_get_entity_by_name_ok(fake_session):
    row = types.SimpleNamespace(Id=7, Name="Learner", Deleted=False)
    fake_session.execute.return_value = _ScalarListResult([row])
    out = await svc.get_entity_by_name(fake_session, entity_name="Learner", data_model_id=1)
    assert out == {"Id": 7, "Name": "Learner"}


async def test_get_entity_by_name_404_missing_or_deleted(fake_session):
    fake_session.execute.return_value = _ScalarListResult([])
    with pytest.raises(svc.HTTPException) as exc:
        await svc.get_entity_by_name(fake_session, "X", 1)
    assert exc.value.status_code == 404

    fake_session.execute.return_value = _ScalarListResult([types.SimpleNamespace(Deleted=True)])
    with pytest.raises(svc.HTTPException):
        await svc.get_entity_by_name(fake_session, "X", 1)


async def test_get_entity_parents_maps_to_dto(fake_session, monkeypatch):
    fake_session.execute.return_value = _ScalarListResult([2, 3])
    monkeypatch.setattr(
        svc,
        "get_entity_by_id",
        AsyncMock(
            side_effect=[
                types.SimpleNamespace(Id=2, Name="ParentA", Deleted=False),
                types.SimpleNamespace(Id=3, Name="ParentB", Deleted=False),
            ]
        ),
    )
    out = await svc.get_entity_parents(fake_session, entity_id=1)
    assert out == [{"Id": 2, "Name": "ParentA"}, {"Id": 3, "Name": "ParentB"}]


async def test_get_filtered_entity_parents_raises_on_multiple_flags(fake_session):
    dm_type = getattr(svc, "DataModelType")
    with pytest.raises(svc.HTTPException) as exc:
        await svc.get_filtered_entity_parents(
            fake_session, 1, data_model_id=1, data_model_type=dm_type.OrgLIF, partner_only=True, org_ext_only=True
        )
    assert exc.value.status_code == 400


async def test_get_filtered_entity_parents_basic_path(fake_session, monkeypatch):
    dm_type = getattr(svc, "DataModelType")
    fake_session.execute.return_value = _ScalarListResult([2])
    monkeypatch.setattr(
        svc, "get_entity_by_id", AsyncMock(return_value=types.SimpleNamespace(Id=2, Name="P", Deleted=False))
    )
    out = await svc.get_filtered_entity_parents(fake_session, 1, data_model_id=1, data_model_type=dm_type.BaseLIF)
    assert out == [{"Id": 2, "Name": "P"}]


async def test_get_entity_children_maps_to_dto(fake_session, monkeypatch):
    fake_session.execute.return_value = _ScalarListResult([4, 5])
    monkeypatch.setattr(
        svc,
        "get_entity_by_id",
        AsyncMock(
            side_effect=[
                types.SimpleNamespace(Id=4, Name="C1", Deleted=False),
                types.SimpleNamespace(Id=5, Name="C2", Deleted=False),
            ]
        ),
    )
    out = await svc.get_entity_children(fake_session, entity_id=2)
    assert out == [{"Id": 4, "Name": "C1"}, {"Id": 5, "Name": "C2"}]


async def test_get_filtered_entity_children_builds_child_dtos(fake_session, monkeypatch):
    dm_type = getattr(svc, "DataModelType")
    assoc = types.SimpleNamespace(ChildEntityId=10, Relationship="rel", Placement="pl", Deleted=False)
    fake_session.execute.return_value = _ScalarListResult([assoc])
    monkeypatch.setattr(
        svc, "get_entity_by_id", AsyncMock(return_value=types.SimpleNamespace(Id=10, Name="Kid", Deleted=False))
    )
    out = await svc.get_filtered_entity_children(
        fake_session, entity_id=2, data_model_id=1, data_model_type=dm_type.BaseLIF
    )
    assert out and isinstance(out[0], dict)
    assert out[0]["ParentEntityId"] == 2
    assert out[0]["Relationship"] == "rel"
    assert out[0]["Placement"] == "pl"

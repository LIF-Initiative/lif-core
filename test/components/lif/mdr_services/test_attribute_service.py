import types
import pytest
from unittest.mock import AsyncMock, MagicMock

pytestmark = pytest.mark.asyncio

svc = pytest.importorskip("lif.mdr_services.attribute_service")


class _ScalarListResult:
    """Supports .scalars().all()/first() and .scalar() when we feed a single value."""

    def __init__(self, items):
        self._items = items

    def scalars(self):
        return self

    def all(self):
        if isinstance(self._items, list):
            return list(self._items)
        return []

    def first(self):
        if isinstance(self._items, list) and self._items:
            return self._items[0]
        return None

    def scalar(self):
        if isinstance(self._items, list):
            return len(self._items)
        return self._items


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
def stub_attribute_dto(monkeypatch):
    """Make AttributeDTO.from_orm return a simple dict so we don't depend on Pydantic config."""
    if hasattr(svc, "AttributeDTO"):

        class _AttrDTO(types.SimpleNamespace):
            pass

        def _base_from_orm(o):
            return _AttrDTO(
                Id=getattr(o, "Id", None),
                UniqueName=getattr(o, "UniqueName", None),
                DataModelId=getattr(o, "DataModelId", None),
                Deleted=getattr(o, "Deleted", False),
                Name=getattr(o, "Name", None),
                DataType=getattr(o, "DataType", None),
                Extension=getattr(o, "Extension", False),
            )

        monkeypatch.setattr(svc.AttributeDTO, "from_orm", staticmethod(_base_from_orm), raising=False)
        # Also stub AttributeWithAssociationMetadataDTO so we can set extra attributes later
        if hasattr(svc, "AttributeWithAssociationMetadataDTO"):
            monkeypatch.setattr(
                svc.AttributeWithAssociationMetadataDTO, "from_orm", staticmethod(_base_from_orm), raising=False
            )


async def test_get_paginated_attributes_no_pagination(fake_session):
    fake_session.execute.side_effect = [
        _CountResult(2),  # total count
        _ScalarListResult(
            [
                types.SimpleNamespace(Id=1, UniqueName="dm.attr1", DataModelId=10, Deleted=False, Name="A"),
                types.SimpleNamespace(Id=2, UniqueName="dm.attr2", DataModelId=10, Deleted=False, Name="B"),
            ]
        ),
    ]
    total, items = await svc.get_paginated_attributes(fake_session, pagination=False)
    assert total == 2
    assert [i.Id for i in items] == [1, 2]


async def test_get_attribute_dto_by_id_ok(fake_session):
    row = types.SimpleNamespace(Id=7, UniqueName="dm.x", DataModelId=1, Deleted=False)
    fake_session.get.return_value = row
    out = await svc.get_attribute_dto_by_id(fake_session, 7)
    assert out.Id == 7


async def test_get_attribute_dto_by_id_404(fake_session):
    fake_session.get.return_value = None
    with pytest.raises(svc.HTTPException) as exc:
        await svc.get_attribute_dto_by_id(fake_session, 1)
    assert exc.value.status_code == 404


async def test_get_attribute_by_id_ok(fake_session):
    row = types.SimpleNamespace(Id=9, Deleted=False)
    fake_session.get.return_value = row
    out = await svc.get_attribute_by_id(fake_session, 9)
    assert out is row


async def test_get_attribute_by_id_404_deleted(fake_session):
    fake_session.get.return_value = types.SimpleNamespace(Deleted=True)
    with pytest.raises(svc.HTTPException):
        await svc.get_attribute_by_id(fake_session, 9)


async def test_create_attribute_ok(fake_session, monkeypatch):
    # data model exists, not an extension
    dm = types.SimpleNamespace(Id=1, BaseDataModelId=None)
    monkeypatch.setattr(svc, "check_datamodel_by_id", AsyncMock(return_value=dm))
    # unique name does not exist
    monkeypatch.setattr(svc, "check_attribute_exists", AsyncMock(return_value=None))
    # value set check not hit (ValueSetId=None)
    monkeypatch.setattr(svc, "check_value_set_exists_by_id", AsyncMock())

    # Avoid constructing real ORM model
    monkeypatch.setattr(svc, "Attribute", lambda **kw: types.SimpleNamespace(**kw))

    class _CreateDTO:
        def __init__(self):
            self.UniqueName = "dm.height"
            self.Name = "height"
            self.DataModelId = 1
            self.Extension = False
            self.ValueSetId = None
            self.EntityId = None  # no association on this path

        def dict(self, exclude=None):
            data = {
                "UniqueName": self.UniqueName,
                "Name": self.Name,
                "DataModelId": self.DataModelId,
                "Extension": self.Extension,
                "ValueSetId": self.ValueSetId,
                "EntityId": self.EntityId,
            }
            for key in exclude or set():
                data.pop(key, None)
            return data

    out = await svc.create_attribute(fake_session, _CreateDTO())
    fake_session.commit.assert_awaited()
    fake_session.refresh.assert_awaited()
    # EntityId is None → attribute only, no association row
    assert fake_session.add.call_count == 1
    assert out.UniqueName == "dm.height"
    assert out.DataModelId == 1


async def test_create_attribute_with_entity_association(fake_session, monkeypatch):
    # #1028: when EntityId is supplied, create_attribute persists the attribute AND its entity
    # association in a single transaction (one commit) so a dropped response can never orphan.
    dm = types.SimpleNamespace(Id=1, BaseDataModelId=None)
    monkeypatch.setattr(svc, "check_datamodel_by_id", AsyncMock(return_value=dm))
    monkeypatch.setattr(svc, "check_attribute_exists", AsyncMock(return_value=None))
    monkeypatch.setattr(svc, "check_value_set_exists_by_id", AsyncMock())
    check_entity = AsyncMock()
    monkeypatch.setattr(svc, "check_entity_by_id", check_entity)
    # attribute.Id is assigned by flush() in real code; emulate with an Id-bearing stand-in.
    monkeypatch.setattr(svc, "Attribute", lambda **kw: types.SimpleNamespace(Id=42, **kw))
    monkeypatch.setattr(svc, "EntityAttributeAssociation", lambda **kw: types.SimpleNamespace(**kw))
    fake_session.flush = AsyncMock()

    class _CreateDTO:
        def __init__(self):
            self.UniqueName = "dm.weight"
            self.Name = "weight"
            self.DataModelId = 1
            self.Extension = False
            self.ValueSetId = None
            self.EntityId = 7
            self.Contributor = "MDRUser"
            self.ContributorOrganization = None

        def dict(self, exclude=None):
            data = {
                "UniqueName": self.UniqueName,
                "Name": self.Name,
                "DataModelId": self.DataModelId,
                "Extension": self.Extension,
                "ValueSetId": self.ValueSetId,
                "EntityId": self.EntityId,
            }
            for key in exclude or set():
                data.pop(key, None)
            return data

    out = await svc.create_attribute(fake_session, _CreateDTO())

    check_entity.assert_awaited_once_with(session=fake_session, id=7)
    fake_session.flush.assert_awaited()  # Id assigned before building the association
    fake_session.commit.assert_awaited_once()  # single transaction spans both rows
    assert fake_session.add.call_count == 2  # attribute + association
    association = fake_session.add.call_args_list[1].args[0]
    assert association.EntityId == 7
    assert association.AttributeId == 42
    assert association.ExtendedByDataModelId is None  # non-extension model
    assert out.UniqueName == "dm.weight"


async def test_create_attribute_duplicate_raises_400(fake_session, monkeypatch):
    dm = types.SimpleNamespace(Id=1, BaseDataModelId=None)
    monkeypatch.setattr(svc, "check_datamodel_by_id", AsyncMock(return_value=dm))
    # existing found
    monkeypatch.setattr(svc, "check_attribute_exists", AsyncMock(return_value=types.SimpleNamespace(Id=99)))

    class _Create:
        UniqueName = "dm.dup"
        Name = "dup"
        DataModelId = 1
        Extension = False
        ValueSetId = None

        def dict(self):
            return {}

    with pytest.raises(svc.HTTPException) as exc:
        await svc.create_attribute(fake_session, _Create())
    assert exc.value.status_code == 400


async def test_update_attribute_happy_path(fake_session, monkeypatch):
    # existing attribute
    current = types.SimpleNamespace(Id=5, Deleted=False, UniqueName="dm.height", DataModelId=1)
    fake_session.get.return_value = current

    monkeypatch.setattr(svc, "check_datamodel_by_id", AsyncMock())
    monkeypatch.setattr(svc, "check_attribute_exists", AsyncMock(return_value=None))

    class _UpdateDTO:
        def __init__(self):
            self.UniqueName = "dm.height_cm"
            self.DataModelId = 1
            self.ValueSetId = None

        def dict(self, exclude_unset=False):
            return {"UniqueName": self.UniqueName}

    out = await svc.update_attribute(fake_session, 5, _UpdateDTO())
    assert out.Id == 5
    fake_session.commit.assert_awaited()


async def test_update_attribute_conflict_raises_400(fake_session, monkeypatch):
    current = types.SimpleNamespace(Id=5, Deleted=False, UniqueName="x", DataModelId=1)
    fake_session.get.return_value = current
    monkeypatch.setattr(svc, "check_datamodel_by_id", AsyncMock())
    monkeypatch.setattr(svc, "check_attribute_exists", AsyncMock(return_value=types.SimpleNamespace(Id=999)))

    class _Update:
        UniqueName = "x"
        DataModelId = 1
        ValueSetId = None

        def dict(self, exclude_unset=False):
            return {}

    with pytest.raises(svc.HTTPException) as exc:
        await svc.update_attribute(fake_session, 5, _Update())
    assert exc.value.status_code == 400


async def test_delete_attribute_ok(fake_session):
    fake_session.get.return_value = types.SimpleNamespace(Id=3, Deleted=False)
    fake_session.execute.return_value = _ScalarListResult([])
    out = await svc.delete_attribute(fake_session, 3)
    assert out == {"ok": True}
    fake_session.commit.assert_awaited_once()


async def test_delete_attribute_404_missing(fake_session):
    fake_session.get.return_value = None
    with pytest.raises(svc.HTTPException) as exc:
        await svc.delete_attribute(fake_session, 3)
    assert exc.value.status_code == 404


async def test_soft_delete_attribute_ok_minimal(fake_session):
    attr = types.SimpleNamespace(Id=4, Deleted=False)
    fake_session.get.return_value = attr
    fake_session.execute.side_effect = [_ScalarListResult([]), _ScalarListResult([]), _ScalarListResult([])]
    out = await svc.soft_delete_attribute(fake_session, 4)
    assert out == {"ok": True}
    fake_session.commit.assert_awaited()


async def test_get_attributes_by_ids_maps_to_dtos(fake_session):
    fake_session.execute.return_value = _ScalarListResult(
        [
            types.SimpleNamespace(Id=1, UniqueName="dm.a", DataModelId=9, Deleted=False),
            types.SimpleNamespace(Id=2, UniqueName="dm.b", DataModelId=9, Deleted=False),
        ]
    )
    out = await svc.get_attributes_by_ids(fake_session, [1, 2])
    assert [(a.Id, a.UniqueName, a.DataModelId) for a in out] == [(1, "dm.a", 9), (2, "dm.b", 9)]


async def test_get_list_of_attributes_for_entity_baselif_path(fake_session, monkeypatch):
    fake_session.execute.side_effect = [
        _ScalarListResult([10, 11]),
        _CountResult(2),
        _ScalarListResult(
            [
                types.SimpleNamespace(Id=10, UniqueName="dm.a", DataModelId=1, Deleted=False),
                types.SimpleNamespace(Id=11, UniqueName="dm.b", DataModelId=1, Deleted=False),
            ]
        ),
    ]
    total, items = await svc.get_list_of_attributes_for_entity(
        fake_session, entity_id=99, data_model_id=1, data_model_type=None, pagination=False
    )
    assert total == 2
    assert [i.Id for i in items] == [10, 11]


async def test_get_list_of_attributes_for_data_model_baselif(fake_session, monkeypatch):
    dm = types.SimpleNamespace(Id=200, Type=getattr(svc, "DataModelType").BaseLIF, BaseDataModelId=None)
    monkeypatch.setattr(svc, "check_datamodel_by_id", AsyncMock(return_value=dm))

    fake_session.execute.side_effect = [
        _CountResult(1),
        _ScalarListResult([types.SimpleNamespace(Id=33, UniqueName="dm.x", DataModelId=200, Deleted=False)]),
    ]
    total, items = await svc.get_list_of_attributes_for_data_model(fake_session, data_model_id=200, pagination=True)
    assert total == 1
    assert len(items) == 1 and items[0].Id == 33 and items[0].UniqueName == "dm.x"


async def test_get_list_of_attributes_for_data_model_orglif_includes_base(fake_session, monkeypatch):
    dm_type = getattr(svc, "DataModelType")
    dm = types.SimpleNamespace(Id=100, Type=dm_type.OrgLIF, BaseDataModelId=1)
    base_dm = types.SimpleNamespace(Id=1, Type=dm_type.BaseLIF, BaseDataModelId=None)
    monkeypatch.setattr(svc, "check_datamodel_by_id", AsyncMock(side_effect=[dm, base_dm]))

    fake_session.execute.side_effect = [
        _CountResult(2),
        _ScalarListResult(
            [
                types.SimpleNamespace(Id=10, UniqueName="org.a", DataModelId=100, Deleted=False),
                types.SimpleNamespace(Id=11, UniqueName="base.b", DataModelId=1, Deleted=False),
            ]
        ),
    ]
    total, items = await svc.get_list_of_attributes_for_data_model(
        fake_session, data_model_id=100, pagination=False, check_base=True
    )
    assert total == 2
    assert [i.DataModelId for i in items] == [100, 1]


async def test_get_attributes_with_association_metadata_for_entity_base(fake_session):
    """Base (non-Org/Partner) flow: associations -> attributes -> enriched DTOs."""
    # Prepare two associations for entity 50
    assoc_rows = [
        types.SimpleNamespace(
            Id=900,
            EntityId=50,
            AttributeId=1,
            Notes="n1",
            CreationDate=None,
            ActivationDate=None,
            DeprecationDate=None,
            Contributor="alice",
            ContributorOrganization="OrgA",
            Deleted=False,
            ExtendedByDataModelId=None,
        ),
        types.SimpleNamespace(
            Id=901,
            EntityId=50,
            AttributeId=2,
            Notes="n2",
            CreationDate=None,
            ActivationDate=None,
            DeprecationDate=None,
            Contributor="bob",
            ContributorOrganization="OrgB",
            Deleted=False,
            ExtendedByDataModelId=None,
        ),
    ]
    attr_rows = [
        types.SimpleNamespace(
            Id=1,
            Name="Height",
            UniqueName="dm.height",
            DataModelId=10,
            DataType="number",
            Extension=False,
            Deleted=False,
        ),
        types.SimpleNamespace(
            Id=2,
            Name="Weight",
            UniqueName="dm.weight",
            DataModelId=10,
            DataType="number",
            Extension=False,
            Deleted=False,
        ),
    ]
    fake_session.execute.side_effect = [
        _ScalarListResult(assoc_rows),  # association query
        _ScalarListResult(attr_rows),  # attribute fetch
    ]
    out = await svc.get_attributes_with_association_metadata_for_entity(fake_session, entity_id=50, data_model_id=10)
    assert len(out) == 2
    by_id = {o.Id: o for o in out}
    assert by_id[1].EntityAttributeAssociationId == 900
    assert by_id[2].EntityAttributeAssociationId == 901
    assert by_id[1].AssociationNotes == "n1"
    assert by_id[2].AssociationContributor == "bob"


async def test_get_attributes_with_association_metadata_for_entity_none(fake_session):
    """No associations -> empty list."""
    fake_session.execute.return_value = _ScalarListResult([])
    out = await svc.get_attributes_with_association_metadata_for_entity(fake_session, entity_id=77, data_model_id=1)
    assert out == []


async def test_get_attributes_with_association_metadata_for_entity_orglif_public_filter(fake_session):
    """OrgLIF branch: filter via ExtInclusions (public_only)."""
    dm_type = getattr(svc, "DataModelType")
    assoc_rows = [
        types.SimpleNamespace(
            Id=910,
            EntityId=60,
            AttributeId=3,
            Notes=None,
            CreationDate=None,
            ActivationDate=None,
            DeprecationDate=None,
            Contributor=None,
            ContributorOrganization=None,
            Deleted=False,
            ExtendedByDataModelId=None,
        ),
        types.SimpleNamespace(
            Id=911,
            EntityId=60,
            AttributeId=4,
            Notes=None,
            CreationDate=None,
            ActivationDate=None,
            DeprecationDate=None,
            Contributor=None,
            ContributorOrganization=None,
            Deleted=False,
            ExtendedByDataModelId=999,  # extended by this data model
        ),
    ]
    # ext inclusion returns only attribute 4 (public filtering simulated)
    attr_rows_filtered = [
        types.SimpleNamespace(
            Id=4, Name="BMI", UniqueName="dm.bmi", DataModelId=999, DataType="number", Extension=False, Deleted=False
        )
    ]
    fake_session.execute.side_effect = [
        _ScalarListResult(assoc_rows),  # association query
        _ScalarListResult([4]),  # ext_inclusions_query (attribute ids after filter)
        _ScalarListResult(attr_rows_filtered),  # attribute fetch
    ]
    out = await svc.get_attributes_with_association_metadata_for_entity(
        fake_session, entity_id=60, data_model_id=999, data_model_type=dm_type.OrgLIF, public_only=True
    )
    assert len(out) == 1
    dto = out[0]
    assert dto.Id == 4
    # should map to association 911 not 910 (because attribute 4 only)
    assert dto.EntityAttributeAssociationId == 911
    assert dto.AssociationExtendedByDataModelId == 999

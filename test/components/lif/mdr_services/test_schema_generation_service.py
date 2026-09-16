import types
from collections import namedtuple
from unittest.mock import AsyncMock, MagicMock

import pandas as pd
import pytest

svc = pytest.importorskip("lif.mdr_services.schema_generation_service")


class _ScalarListResult:
    """Supports .scalars().all() (used for enums in one path)."""

    def __init__(self, items):
        self._items = list(items)

    def scalars(self):
        return self

    def all(self):
        return list(self._items)


class _FetchallResult:
    """Supports .fetchall() (used in most SELECTs in this module)."""

    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return list(self._rows)


class _ScalarFirstResult:
    """Supports .scalars().first() for single-object SELECTs (e.g., ValueSet)."""

    def __init__(self, obj):
        self._obj = obj

    def scalars(self):
        return self

    def first(self):
        return self._obj


class _Attr:
    def __init__(self, id, name, required):
        self.Id = id
        self.Name = name
        self.Required = required
        self.DataType = "string"
        self.Array = "No"
        self.ValueSetId = None

    def dict(self):
        return {
            "Description": None,
            "UseConsiderations": None,
            "Example": None,
            "Format": None,
            "Id": self.Id,
            "Name": self.Name,
            "Required": self.Required,
            "DataType": self.DataType,
            "Array": self.Array,
            "ValueSetId": self.ValueSetId,
        }


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


async def test_find_ancestors_simple_chain(fake_session):
    assoc_child = types.SimpleNamespace(ParentEntityId=2, ChildEntityId=3)
    assoc_parent = types.SimpleNamespace(ParentEntityId=1, ChildEntityId=2)

    fake_session.execute.side_effect = [
        _ScalarListResult([assoc_child]),
        _ScalarListResult([assoc_parent]),
        _ScalarListResult([]),
    ]

    out = await svc.find_ancestors(
        fake_session, child_id=3, data_model_type="BaseLIF", data_model_id=999, included_entity_ids=[]
    )
    assert out == [[1, 2]]


async def test_find_ancestors_multiple_roots(fake_session):
    assoc_first = types.SimpleNamespace(ParentEntityId=10, ChildEntityId=30)
    assoc_second = types.SimpleNamespace(ParentEntityId=20, ChildEntityId=30)

    fake_session.execute.side_effect = [
        _ScalarListResult([assoc_first, assoc_second]),
        _ScalarListResult([]),
        _ScalarListResult([]),
    ]

    out = await svc.find_ancestors(
        fake_session, child_id=30, data_model_type="BaseLIF", data_model_id=555, included_entity_ids=[]
    )
    assert out == [[10], [20]]
    assert fake_session.execute.await_count == 3


async def test_add_ref_reference_placement_root():
    Row = namedtuple("Row", ["Id", "Name"])
    df_entity = pd.DataFrame([Row(1, "Parent"), Row(2, "Child")])

    # Provide a Child schema so add_ref can locate and inline it. Child has 3 props, 2 required.
    openapi_spec = {
        "components": {
            "schemas": {
                "Parent": {"properties": {}},
                "Child": {
                    "type": "object",
                    "required": ["id", "displayName"],
                    "properties": {
                        "id": {"type": "string"},
                        "displayName": {"type": "string"},
                        "extra": {"type": "string"},
                    },
                },
            }
        }
    }
    parent_anc = []
    child_anc = []
    await svc.add_ref(
        parent_ancestors=parent_anc,
        child_ancestors=child_anc,
        df_entity=df_entity,
        parent_entity_name="Parent",
        child_entity_name="Child",
        openapi_spec=openapi_spec,
        key="Child",
    )
    child_inline = openapi_spec["components"]["schemas"]["Parent"]["properties"]["Child"]
    # Ensure it's an object with only the required fields inlined (no $ref, no extra field)
    assert child_inline["type"] == "object"
    assert set(child_inline["properties"].keys()) == {"id", "displayName"}
    assert "extra" not in child_inline["properties"]
    assert child_inline["required"] == ["id", "displayName"]


async def test_add_ref_nested_parent_path():
    Row = namedtuple("Row", ["Id", "Name"])
    df_entity = pd.DataFrame([Row(1, "Root"), Row(2, "Intermediate"), Row(3, "Parent"), Row(4, "Child")])

    # Build nested structure with a Child schema located at Root->Intermediate level, so child_ancestors path works.
    openapi_spec = {
        "components": {
            "schemas": {
                "Root": {
                    "properties": {
                        "Intermediate": {
                            "properties": {
                                "Parent": {"properties": {}},
                                "Child": {
                                    "type": "object",
                                    "required": ["a", "b"],
                                    "properties": {
                                        "a": {"type": "string"},
                                        "b": {"type": "string"},
                                        "c": {"type": "string"},
                                    },
                                },
                            }
                        }
                    }
                }
            }
        }
    }

    await svc.add_ref(
        parent_ancestors=[[1, 2]],
        child_ancestors=[[1, 2]],
        df_entity=df_entity,
        parent_entity_name="Parent",
        child_entity_name="Child",
        openapi_spec=openapi_spec,
        key="ChildRef",
    )

    parent_props = openapi_spec["components"]["schemas"]["Root"]["properties"]["Intermediate"]["properties"]["Parent"][
        "properties"
    ]
    child_ref_inline = parent_props["ChildRef"]
    assert child_ref_inline["type"] == "object"
    assert set(child_ref_inline["properties"].keys()) == {"a", "b"}
    assert "c" not in child_ref_inline["properties"]
    assert child_ref_inline["required"] == ["a", "b"]


async def test_add_ref_multiple_child_paths_error():
    Row = namedtuple("Row", ["Id", "Name"])
    df_entity = pd.DataFrame([Row(1, "Parent"), Row(2, "Child")])

    openapi_spec = {"components": {"schemas": {"Parent": {"properties": {}}}}}

    with pytest.raises(svc.HTTPException) as exc:
        await svc.add_ref(
            parent_ancestors=[],
            child_ancestors=[[1], [1]],
            df_entity=df_entity,
            parent_entity_name="Parent",
            child_entity_name="Child",
            openapi_spec=openapi_spec,
            key="Child",
        )

    assert exc.value.status_code == 400


async def test_get_all_entity_data_frame_builds_dataframe(fake_session):
    Row = namedtuple("Row", ["Id", "Name"])
    fake_session.execute.return_value = _FetchallResult([Row(1, "A"), Row(2, "B")])

    df = await svc.get_all_entity_data_frame(fake_session)
    assert list(df.columns) == ["Id", "Name"]
    assert df.set_index("Id")["Name"].to_dict() == {1: "A", 2: "B"}


async def test_generate_openapi_schema_baselif_minimal(fake_session, monkeypatch):
    """
    Minimal scenario:
      - DataModel is BaseLIF (no extension filtering)
      - No embedded associations (so tree starts empty)
      - One standalone entity (Id=1) in this DataModel
      - That entity has no attributes (simplest case)
      - No inter-entity 'Reference' links
    Expect:
      - components.schemas has one entry for the entity
      - type/object, required list present, empty properties
    """
    dm = types.SimpleNamespace(
        Id=123,
        Name="DemoDM",
        DataModelVersion="1.0",
        Type="BaseLIF",
        BaseDataModelId=None,
        ContributorOrganization="LIF",
    )
    monkeypatch.setattr(svc, "get_datamodel_by_id", AsyncMock(return_value=dm))

    entity_obj = types.SimpleNamespace(Id=1, Name="Learner", Array="No", UseConsiderations=None, Deleted=False)
    monkeypatch.setattr(svc, "get_entity_by_id", AsyncMock(return_value=entity_obj))

    monkeypatch.setattr(svc, "get_attributes_with_association_metadata_for_entity", AsyncMock(return_value=([])))

    RowIN = namedtuple("RowIN", ["Id", "Name"])

    fake_session.execute.side_effect = [
        _FetchallResult([]),
        _FetchallResult([(1,)]),
        _FetchallResult([RowIN(1, "Learner")]),
        _FetchallResult([]),
    ]

    out = await svc.generate_openapi_schema(
        fake_session, data_model_id=123, include_attr_md=False, include_entity_md=False, public_only=False
    )

    assert out["openapi"] == "3.0.0"
    assert out["info"]["title"].startswith("Machine-Readable Schema for ")
    assert "components" in out and "schemas" in out["components"]
    assert "Learner" in out["components"]["schemas"]

    learner_schema = out["components"]["schemas"]["Learner"]
    assert learner_schema["type"] == "object"
    assert learner_schema["required"] == []
    assert learner_schema["use_recommendations"] == ""
    assert learner_schema["properties"] == {}


async def test_generate_openapi_schema_enum_values_on_attribute(fake_session, monkeypatch):
    """
    Focus on enum population:
      - BaseLIF, one entity with one attribute that has a ValueSetId
      - The enum query returns values ["A", "B"]
    Result:
      - attribute dict has "enum": ["A","B"]
    """
    dm = types.SimpleNamespace(
        Id=55, Name="DM", DataModelVersion="0.1", Type="BaseLIF", BaseDataModelId=None, ContributorOrganization="LIF"
    )
    monkeypatch.setattr(svc, "get_datamodel_by_id", AsyncMock(return_value=dm))

    ent = types.SimpleNamespace(Id=10, Name="Thing", Array="No", UseConsiderations=None, Deleted=False)
    monkeypatch.setattr(svc, "get_entity_by_id", AsyncMock(return_value=ent))

    class _Attr:
        def __init__(self):
            self.Id = 999
            self.Name = "Status"
            self.Required = "Yes"
            self.DataType = "string"
            self.Array = "No"
            self.ValueSetId = 777

        def dict(self):
            return {
                "Description": None,
                "UseConsiderations": None,
                "Example": None,
                "Format": None,
                "DataType": self.DataType,
            }

    monkeypatch.setattr(svc, "get_attributes_with_association_metadata_for_entity", AsyncMock(return_value=([_Attr()])))

    RowIN = namedtuple("RowIN", ["Id", "Name"])
    fake_session.execute.side_effect = [
        _FetchallResult([]),
        _FetchallResult([(10,)]),
        _FetchallResult([RowIN(10, "Thing")]),
        _FetchallResult([("A",), ("B",)]),
        _FetchallResult([]),
    ]

    out = await svc.generate_openapi_schema(
        fake_session, data_model_id=55, include_attr_md=False, include_entity_md=False
    )
    props = out["components"]["schemas"]["Thing"]["properties"]
    assert "Status" in props
    assert props["Status"]["enum"] == ["A", "B"]
    assert out["components"]["schemas"]["Thing"]["required"] == ["Status"]


async def test_generate_openapi_schema_has_sub_entity_required_fields(fake_session, monkeypatch):
    """
    Given:
      - BaseLIF CompetencyFramework entity with child entity Association in EntityAssociations
      - BaseLIF has Attributes "competencyAssociationUri" and "competencyAssociationType" with Required="Yes"
      - The "Association" Entity has Attributes "competencyFrameworkId" and "competencyFrameworkType" indicated in the EntityAttributeAssociations table
    Result:
      - The generated schema for CompetencyFramework includes Association with its required attributes listed
    """
    dm = types.SimpleNamespace(
        Id=1,
        Name="BaseLIF",
        DataModelVersion="3.0",
        Type="BaseLIF",
        BaseDataModelId=None,
        ContributorOrganization="LIF",
    )
    monkeypatch.setattr(svc, "get_datamodel_by_id", AsyncMock(return_value=dm))

    def get_entity_by_id_side_effect(session=None, id=None, **_):
        if id == 101:
            return types.SimpleNamespace(
                Id=101, Name="CompetencyFramework", Array="No", UseConsiderations=None, Deleted=False
            )
        elif id == 202:
            return types.SimpleNamespace(Id=202, Name="Association", Array="Yes", UseConsiderations=None, Deleted=False)
        else:
            raise ValueError(f"Unexpected entity_id {id}")

    monkeypatch.setattr(svc, "get_entity_by_id", AsyncMock(side_effect=get_entity_by_id_side_effect))

    def get_attributes_with_association_metadata_for_entity_side_effect(entity_id, **_):
        if entity_id == 101:  # CompetencyFramework
            return [_Attr(1, "uri", "Yes"), _Attr(2, "name", "Yes"), _Attr(3, "description", "No")]
        elif entity_id == 202:  # Association
            return [_Attr(3, "competencyFrameworkId", "Yes"), _Attr(4, "competencyFrameworkType", "Yes")]
        else:
            raise ValueError(f"Unexpected entity_id {entity_id}")

    monkeypatch.setattr(
        svc,
        "get_attributes_with_association_metadata_for_entity",
        AsyncMock(side_effect=get_attributes_with_association_metadata_for_entity_side_effect),
    )

    RowIN = namedtuple("RowIN", ["Id", "Name"])
    fake_session.execute.side_effect = [
        # get embedded entity associations
        _FetchallResult([(101, 202)]),
        # get entities in DM not in union of associations
        _FetchallResult([]),
        # build df_entity (include both entities)
        _FetchallResult([RowIN(101, "CompetencyFramework"), RowIN(202, "Association")]),
        # find_children: get detailed association rows via .scalars().all()
        _ScalarListResult([types.SimpleNamespace(Relationship=None)]),
        # enums for attributes (none)
        _FetchallResult([]),
        _FetchallResult([]),
        # inter-entity "Reference" links
        _FetchallResult([]),
    ]

    out = await svc.generate_openapi_schema(
        fake_session, data_model_id=1, include_attr_md=False, include_entity_md=False
    )
    cf_schema = out["components"]["schemas"]["CompetencyFramework"]
    assert cf_schema["type"] == "object"
    assert cf_schema["required"] == ["uri", "name"]
    assert "Association" in cf_schema["properties"]
    assoc_schema = cf_schema["properties"]["Association"]
    assert assoc_schema["type"] == "array"
    assert assoc_schema["required"] == ["competencyFrameworkId", "competencyFrameworkType"]


async def test_generate_openapi_schema_has_sub_entity_required_entity(fake_session, monkeypatch):
    """
    Given:
      - BaseLIF CompetencyFramework entity with child entity Association in EntityAssociations
      - The Association Entity has Required="Yes" in EntityAssociations
    Result:
      - The generated schema for CompetencyFramework includes Association with its required fields listed
    """
    dm = types.SimpleNamespace(
        Id=1,
        Name="BaseLIF",
        DataModelVersion="3.0",
        Type="BaseLIF",
        BaseDataModelId=None,
        ContributorOrganization="LIF",
    )
    monkeypatch.setattr(svc, "get_datamodel_by_id", AsyncMock(return_value=dm))

    def get_entity_by_id_side_effect(session=None, id=None, **_):
        if id == 101:
            return types.SimpleNamespace(
                Id=101, Name="CompetencyFramework", Array="No", UseConsiderations=None, Deleted=False
            )
        elif id == 202:
            return types.SimpleNamespace(
                Id=202, Name="Association", Array="Yes", UseConsiderations=None, Deleted=False, Required="Yes"
            )
        else:
            raise ValueError(f"Unexpected entity_id {id}")

    monkeypatch.setattr(svc, "get_entity_by_id", AsyncMock(side_effect=get_entity_by_id_side_effect))

    def get_attributes_with_association_metadata_for_entity_side_effect(entity_id, **_):
        if entity_id == 101:  # CompetencyFramework
            return [_Attr(1, "uri", "Yes"), _Attr(2, "name", "Yes"), _Attr(3, "description", "No")]
        elif entity_id == 202:  # Association
            return [_Attr(1, "uri", "Yes"), _Attr(2, "name", "Yes"), _Attr(3, "description", "No")]
        else:
            raise ValueError(f"Unexpected entity_id {entity_id}")

    monkeypatch.setattr(
        svc,
        "get_attributes_with_association_metadata_for_entity",
        AsyncMock(side_effect=get_attributes_with_association_metadata_for_entity_side_effect),
    )

    RowIN = namedtuple("RowIN", ["Id", "Name"])
    fake_session.execute.side_effect = [
        # get embedded entity associations
        _FetchallResult([(101, 202)]),
        # get entities in DM not in union of associations
        _FetchallResult([]),
        # build df_entity (include both entities)
        _FetchallResult([RowIN(101, "CompetencyFramework"), RowIN(202, "Association")]),
        # find_children: get detailed association rows via .scalars().all()
        _ScalarListResult([types.SimpleNamespace(Relationship=None)]),
        # enums for attributes (none)
        _FetchallResult([]),
        _FetchallResult([]),
        # inter-entity "Reference" links
        _FetchallResult([]),
    ]

    out = await svc.generate_openapi_schema(
        fake_session, data_model_id=1, include_attr_md=False, include_entity_md=False
    )
    cf_schema = out["components"]["schemas"]["CompetencyFramework"]
    assert cf_schema["type"] == "object"
    assert "Association" in cf_schema["required"]
    assert "uri" in cf_schema["required"]
    assert "name" in cf_schema["required"]


async def test_generate_openapi_schema_full_export(fake_session, monkeypatch):
    """
    Given:
      - DataModel has type = BaseLIF
      - full_export=True
      - DataModel has one Entity with one child Entity in EntityAssociations
      - DataModel's Entity has one Attribute in EntityAttributeAssociations
      - DataModel's Attribute has ValueSetId
      - The ValueSet has two Values: ["A", "B"]
    Result:
      - The generated schema includes both Entities
      - The parent Entity includes the child Entity as a property
      - The parent Entity's Attribute includes the enum values: ["A", "B"]
    """
    dm = types.SimpleNamespace(
        Id=10, Name="DM", DataModelVersion="1.0", Type="BaseLIF", BaseDataModelId=None, ContributorOrganization="LIF"
    )
    monkeypatch.setattr(svc, "get_datamodel_by_id", AsyncMock(return_value=dm))

    def get_entity_by_id_side_effect(session=None, id=None, **_):
        if id == 100:
            return types.SimpleNamespace(Id=100, Name="Parent", Array="No", UseConsiderations=None, Deleted=False)
        elif id == 200:
            return types.SimpleNamespace(Id=200, Name="Child", Array="Yes", UseConsiderations=None, Deleted=False)
        else:
            raise ValueError(f"Unexpected entity_id {id}")

    monkeypatch.setattr(svc, "get_entity_by_id", AsyncMock(side_effect=get_entity_by_id_side_effect))

    class _Attr:
        def __init__(self):
            self.Id = 555
            self.Name = "Status"
            self.Required = "No"
            self.DataType = "string"
            self.Array = "No"
            self.ValueSetId = 777

        def dict(self):
            return {
                "Description": None,
                "UseConsiderations": None,
                "Example": None,
                "Format": None,
                "DataType": self.DataType,
                # association metadata fields that should be preserved in full_export
                "EntityAttributeAssociationId": 1234,
                "EntityId": 100,
                "AssociationNotes": None,
                "AssociationCreationDate": None,
                "AssociationActivationDate": None,
                "AssociationDeprecationDate": None,
                "AssociationContributor": None,
                "AssociationContributorOrganization": None,
                "AssociationExtendedByDataModelId": None,
            }

    def get_attributes_with_association_metadata_for_entity_side_effect(entity_id, **_):
        if entity_id == 100:  # Parent
            return [_Attr()]
        elif entity_id == 200:  # Child
            return []
        else:
            raise ValueError(f"Unexpected entity_id {entity_id}")

    monkeypatch.setattr(
        svc,
        "get_attributes_with_association_metadata_for_entity",
        AsyncMock(side_effect=get_attributes_with_association_metadata_for_entity_side_effect),
    )

    RowIN = namedtuple("RowIN", ["Id", "Name"])
    fake_session.execute.side_effect = [
        # get embedded entity associations
        _FetchallResult([(100, 200)]),
        # get entities in DM not in union of associations
        _FetchallResult([]),
        # build df_entity (include both entities)
        _FetchallResult([RowIN(100, "Parent"), RowIN(200, "Child")]),
        # enums for attributes
        _FetchallResult([("A",), ("B",)]),
        # ValueSet for attribute (single ValueSet object expected with .scalars().first())
        _ScalarFirstResult(types.SimpleNamespace(Id=777, Name="StatusVS", Deleted=False)),
        # ValueSetValues for attribute (full export metadata; expects scalars().all())
        _ScalarListResult([types.SimpleNamespace(Value="A"), types.SimpleNamespace(Value="B")]),
        # child association query inside find_children (expects scalars().all())
        _ScalarListResult(
            [
                types.SimpleNamespace(
                    Id=999,
                    ParentEntityId=100,
                    ChildEntityId=200,
                    Relationship=None,
                    Placement="Embedded",
                    Notes=None,
                    CreationDate=None,
                    ActivationDate=None,
                    DeprecationDate=None,
                    Contributor=None,
                    ContributorOrganization=None,
                    Extension=None,
                    ExtensionNotes=None,
                    ExtendedByDataModelId=None,
                )
            ]
        ),
        # inter-entity "Reference" links (empty fetchall)
        _FetchallResult([]),
    ]

    out = await svc.generate_openapi_schema(
        fake_session, data_model_id=10, include_attr_md=True, include_entity_md=True, full_export=True
    )

    assert "Parent" in out["components"]["schemas"]
    assert "Child" in out["components"]["schemas"]["Parent"]["properties"]
    assert "Status" in out["components"]["schemas"]["Parent"]["properties"]
    assert out["components"]["schemas"]["Parent"]["properties"]["Status"]["enum"] == ["A", "B"]
    assert "EntityAssociationId" in out["components"]["schemas"]["Parent"]["properties"]["Child"]
    assert "EntityAssociationParentEntityId" in out["components"]["schemas"]["Parent"]["properties"]["Child"]
    assert "EntityAssociationRelationship" in out["components"]["schemas"]["Parent"]["properties"]["Child"]
    assert "EntityAssociationPlacement" in out["components"]["schemas"]["Parent"]["properties"]["Child"]
    assert "EntityAssociationNotes" in out["components"]["schemas"]["Parent"]["properties"]["Child"]
    assert "EntityAssociationCreationDate" in out["components"]["schemas"]["Parent"]["properties"]["Child"]
    assert "EntityAssociationActivationDate" in out["components"]["schemas"]["Parent"]["properties"]["Child"]
    assert "EntityAssociationDeprecationDate" in out["components"]["schemas"]["Parent"]["properties"]["Child"]
    assert "EntityAssociationContributor" in out["components"]["schemas"]["Parent"]["properties"]["Child"]
    assert "EntityAssociationContributorOrganization" in out["components"]["schemas"]["Parent"]["properties"]["Child"]
    assert "EntityAssociationExtension" in out["components"]["schemas"]["Parent"]["properties"]["Child"]
    assert "EntityAssociationExtensionNotes" in out["components"]["schemas"]["Parent"]["properties"]["Child"]
    assert "EntityAssociationExtendedByDataModelId" in out["components"]["schemas"]["Parent"]["properties"]["Child"]
    assert "EntityAttributeAssociationId" in out["components"]["schemas"]["Parent"]["properties"]["Status"]
    assert "EntityId" in out["components"]["schemas"]["Parent"]["properties"]["Status"]
    assert "AssociationNotes" in out["components"]["schemas"]["Parent"]["properties"]["Status"]
    assert "AssociationCreationDate" in out["components"]["schemas"]["Parent"]["properties"]["Status"]
    assert "AssociationActivationDate" in out["components"]["schemas"]["Parent"]["properties"]["Status"]
    assert "AssociationDeprecationDate" in out["components"]["schemas"]["Parent"]["properties"]["Status"]
    assert "AssociationContributor" in out["components"]["schemas"]["Parent"]["properties"]["Status"]
    assert "AssociationContributorOrganization" in out["components"]["schemas"]["Parent"]["properties"]["Status"]
    assert "AssociationExtendedByDataModelId" in out["components"]["schemas"]["Parent"]["properties"]["Status"]


async def test_generate_openapi_schema_full_export_parent_and_child_valuesets(fake_session, monkeypatch):
    """Full export where both Parent and Child have attributes with ValueSets (two values each)."""
    dm = types.SimpleNamespace(
        Id=20, Name="DM2", DataModelVersion="1.0", Type="BaseLIF", BaseDataModelId=None, ContributorOrganization="LIF"
    )
    monkeypatch.setattr(svc, "get_datamodel_by_id", AsyncMock(return_value=dm))

    def get_entity_by_id_side_effect(session=None, id=None, **_):
        if id == 300:
            return types.SimpleNamespace(Id=300, Name="Parent2", Array="No", UseConsiderations=None, Deleted=False)
        elif id == 400:
            return types.SimpleNamespace(Id=400, Name="Child2", Array="Yes", UseConsiderations=None, Deleted=False)
        else:
            raise ValueError(f"Unexpected entity_id {id}")

    monkeypatch.setattr(svc, "get_entity_by_id", AsyncMock(side_effect=get_entity_by_id_side_effect))

    class _AttrParent:
        def __init__(self):
            self.Id = 801
            self.Name = "ParentStatus"
            self.Required = "Yes"
            self.DataType = "string"
            self.Array = "No"
            self.ValueSetId = 9001

        def dict(self):
            return {
                "Description": None,
                "UseConsiderations": None,
                "Example": None,
                "Format": None,
                "DataType": self.DataType,
                "EntityAttributeAssociationId": 7001,
                "EntityId": 300,
                "AssociationNotes": None,
                "AssociationCreationDate": None,
                "AssociationActivationDate": None,
                "AssociationDeprecationDate": None,
                "AssociationContributor": None,
                "AssociationContributorOrganization": None,
                "AssociationExtendedByDataModelId": None,
            }

    class _AttrChild:
        def __init__(self):
            self.Id = 802
            self.Name = "ChildStatus"
            self.Required = "No"
            self.DataType = "string"
            self.Array = "No"
            self.ValueSetId = 9002

        def dict(self):
            return {
                "Description": None,
                "UseConsiderations": None,
                "Example": None,
                "Format": None,
                "DataType": self.DataType,
                "EntityAttributeAssociationId": 7002,
                "EntityId": 400,
                "AssociationNotes": None,
                "AssociationCreationDate": None,
                "AssociationActivationDate": None,
                "AssociationDeprecationDate": None,
                "AssociationContributor": None,
                "AssociationContributorOrganization": None,
                "AssociationExtendedByDataModelId": None,
            }

    def get_attributes_with_association_metadata_for_entity_side_effect(entity_id, **_):
        if entity_id == 300:  # Parent2
            return [_AttrParent()]
        elif entity_id == 400:  # Child2
            return [_AttrChild()]
        else:
            raise ValueError(f"Unexpected entity_id {entity_id}")

    monkeypatch.setattr(
        svc,
        "get_attributes_with_association_metadata_for_entity",
        AsyncMock(side_effect=get_attributes_with_association_metadata_for_entity_side_effect),
    )

    RowIN = namedtuple("RowIN", ["Id", "Name"])
    fake_session.execute.side_effect = [
        # embedded associations
        _FetchallResult([(300, 400)]),
        # entities not in union
        _FetchallResult([]),
        # df_entity
        _FetchallResult([RowIN(300, "Parent2"), RowIN(400, "Child2")]),
        # enums for parent attribute
        _FetchallResult([("P1",), ("P2",)]),
        # valueset object for parent
        _ScalarFirstResult(types.SimpleNamespace(Id=9001, Name="ParentStatusVS", Deleted=False)),
        # full valueset values for parent (scalars all)
        _ScalarListResult([types.SimpleNamespace(Value="P1"), types.SimpleNamespace(Value="P2")]),
        # child association (scalars all)
        _ScalarListResult(
            [
                types.SimpleNamespace(
                    Id=1001,
                    ParentEntityId=300,
                    ChildEntityId=400,
                    Relationship=None,
                    Placement="Embedded",
                    Notes=None,
                    CreationDate=None,
                    ActivationDate=None,
                    DeprecationDate=None,
                    Contributor=None,
                    ContributorOrganization=None,
                    Extension=None,
                    ExtensionNotes=None,
                    ExtendedByDataModelId=None,
                )
            ]
        ),
        # enums for child attribute (called within find_children; uses scalars().all())
        _ScalarListResult(["C1", "C2"]),
        # valueset object for child
        _ScalarFirstResult(types.SimpleNamespace(Id=9002, Name="ChildStatusVS", Deleted=False)),
        # full valueset values for child (scalars all)
        _ScalarListResult([types.SimpleNamespace(Value="C1"), types.SimpleNamespace(Value="C2")]),
        # inter-entity reference links
        _FetchallResult([]),
    ]

    out = await svc.generate_openapi_schema(
        fake_session, data_model_id=20, include_attr_md=True, include_entity_md=True, full_export=True
    )

    parent_schema = out["components"]["schemas"]["Parent2"]
    assert parent_schema["properties"]["ParentStatus"]["enum"] == ["P1", "P2"]
    assert parent_schema["required"] == ["ParentStatus"]  # Required Yes on parent attr
    child_prop = parent_schema["properties"]["Child2"]
    assert child_prop["type"] == "array"
    assert "EntityAssociationId" in child_prop
    assert "EntityAssociationParentEntityId" in child_prop
    assert "EntityAssociationRelationship" in child_prop
    assert "EntityAssociationPlacement" in child_prop
    assert "EntityAssociationNotes" in child_prop
    assert "EntityAssociationCreationDate" in child_prop
    assert "EntityAssociationActivationDate" in child_prop
    assert "EntityAssociationDeprecationDate" in child_prop
    assert "EntityAssociationContributor" in child_prop
    assert "EntityAssociationContributorOrganization" in child_prop
    assert "EntityAssociationExtension" in child_prop
    assert "EntityAssociationExtensionNotes" in child_prop
    assert "EntityAssociationExtendedByDataModelId" in child_prop
    # Child attribute nested inside Child2 properties
    child_attr = child_prop["properties"]["ChildStatus"]
    assert child_attr["enum"] == ["C1", "C2"]
    # Attribute metadata fields (parent attr already covered implicitly; assert both explicitly)
    parent_attr = parent_schema["properties"]["ParentStatus"]
    for k in [
        "EntityAttributeAssociationId",
        "EntityId",
        "AssociationNotes",
        "AssociationCreationDate",
        "AssociationActivationDate",
        "AssociationDeprecationDate",
        "AssociationContributor",
        "AssociationContributorOrganization",
        "AssociationExtendedByDataModelId",
    ]:
        assert k in parent_attr
        assert k in child_attr  # child attr also should retain these in full_export
    # Child attr is not required (Required = No)
    assert "ChildStatus" not in child_prop["required"]


async def test_find_ancestors_orglif_filters_to_included_entity_ids(fake_session):
    """OrgLIF: ensure only associations with ParentEntityId in included_entity_ids are traversed.

    We simulate:
      - Child entity id = 500
      - Valid parent (100) included, invalid parent (200) excluded from included_entity_ids
      - Because the real query filters using ParentEntityId.in_(included_entity_ids), the 200 association
        would never be returned; we therefore only mock the allowed association.
      - Parent 100 has ancestor 50 (also included) and 50 has no further ancestors.

    Expect: [[50, 100]]
    """

    assoc_from_100 = types.SimpleNamespace(
        ParentEntityId=100, ChildEntityId=500, Placement=None, Deleted=False, ExtendedByDataModelId=None
    )
    assoc_from_50 = types.SimpleNamespace(
        ParentEntityId=50, ChildEntityId=100, Placement=None, Deleted=False, ExtendedByDataModelId=None
    )

    fake_session.execute.side_effect = [
        _ScalarListResult([assoc_from_100]),  # associations for child 500
        _ScalarListResult([assoc_from_50]),  # associations for parent 100
        _ScalarListResult([]),  # associations for parent 50
    ]

    out = await svc.find_ancestors(
        fake_session,
        child_id=500,
        data_model_type="OrgLIF",
        data_model_id=9999,
        included_entity_ids=[50, 100, 500],  # excluded parent 200 not present
    )

    assert out == [[50, 100]]
    assert fake_session.execute.await_count == 3


# === Issue #1252: find_children / add_ref key-spelling mismatch ===
#
# find_children keys an Embedded child as Relationship + EntityName (unless the
# relationship is NULL or starts with has/relevant). add_ref walks the parent's
# ancestor chain by bare entity name. When an Embedded association carries a name,
# the two disagree and add_ref raises an uncaught KeyError -> generic 500.
#
# Reported by Tammie Helmick 2026-08-11 against the CASE data model
# (CFPackage -CFItems-> CFItem embedded, then a Reference beneath it).


def _named_embedded_spec():
    """A spec shaped the way find_children actually writes it.

    'CFItem' is embedded under 'CFPackage' with Relationship='CFItems', so the
    property key is the concatenation 'CFItemsCFItem' -- NOT the bare 'CFItem'.
    """
    return {
        "components": {
            "schemas": {
                "CFPackage": {
                    "properties": {
                        "CFItemsCFItem": {
                            "properties": {
                                "CFRubric": {
                                    "type": "object",
                                    "required": ["identifier"],
                                    "properties": {"identifier": {"type": "string"}, "title": {"type": "string"}},
                                }
                            }
                        }
                    }
                }
            }
        }
    }


async def test_add_ref_resolves_named_embedded_ancestor_key():
    """Issue #1252: the parent-chain walk must use the key find_children wrote."""
    Row = namedtuple("Row", ["Id", "Name"])
    df_entity = pd.DataFrame([Row(1, "CFPackage"), Row(2, "CFItem"), Row(3, "CFRubric")])
    openapi_spec = _named_embedded_spec()

    await svc.add_ref(
        parent_ancestors=[[1]],
        child_ancestors=[[1, 2]],
        df_entity=df_entity,
        parent_entity_name="CFItem",
        child_entity_name="CFRubric",
        openapi_spec=openapi_spec,
        key="RefCFRubric",
        property_key_map={(1, 2): "CFItemsCFItem"},
        parent_entity_id=2,
        child_entity_id=3,
    )

    parent_props = openapi_spec["components"]["schemas"]["CFPackage"]["properties"]["CFItemsCFItem"]["properties"]
    assert "RefCFRubric" in parent_props, (
        "add_ref resolved the embedded ancestor by bare name 'CFItem' instead of the "
        "key find_children wrote ('CFItemsCFItem')"
    )
    assert parent_props["RefCFRubric"]["type"] == "object"


async def test_add_ref_named_embedded_midchain_is_resolved():
    """The same mismatch one level deeper, in the ancestor_line[1:] loop."""
    Row = namedtuple("Row", ["Id", "Name"])
    df_entity = pd.DataFrame([Row(1, "Root"), Row(2, "Mid"), Row(3, "Parent"), Row(4, "Child")])
    openapi_spec = {
        "components": {
            "schemas": {
                "Root": {
                    "properties": {
                        "ownedMid": {
                            "properties": {
                                "Parent": {"properties": {}},
                                "Child": {"type": "object", "required": ["a"], "properties": {"a": {"type": "string"}}},
                            }
                        }
                    }
                }
            }
        }
    }

    await svc.add_ref(
        parent_ancestors=[[1, 2]],
        child_ancestors=[[1, 2]],
        df_entity=df_entity,
        parent_entity_name="Parent",
        child_entity_name="Child",
        openapi_spec=openapi_spec,
        key="ChildRef",
        property_key_map={(1, 2): "ownedMid"},
        parent_entity_id=3,
        child_entity_id=4,
    )

    assert (
        "ChildRef"
        in openapi_spec["components"]["schemas"]["Root"]["properties"]["ownedMid"]["properties"]["Parent"]["properties"]
    )


def test_embedded_property_key_matches_find_children_rule():
    """The shared helper must reproduce find_children's rule exactly (#1252)."""
    assert svc.embedded_property_key("CFItems", "CFItem") == "CFItemsCFItem"
    assert svc.embedded_property_key(None, "CFItem") == "CFItem"
    assert svc.embedded_property_key("hasManager", "Employee") == "Employee"
    assert svc.embedded_property_key("relevantThing", "Thing") == "Thing"
    assert svc.embedded_property_key("issuedBy", "Org") == "issuedByOrg"


async def test_find_children_records_the_key_it_writes(monkeypatch):
    """Issue #1252: the map and the schema must be written from the same value.

    The add_ref tests above supply a hand-built property_key_map, so they prove
    add_ref *uses* a map but not that find_children *fills* one. Without this test
    the threading (generate_openapi_schema -> find_children -> add_ref) could break
    and every other test would still pass while production still 500s.
    """
    assoc = types.SimpleNamespace(Relationship="CFItems", ParentEntityId=1, ChildEntityId=2)

    class _Assocs:
        def scalars(self):
            return self

        def all(self):
            return [assoc]

        def fetchall(self):
            return []

    session = MagicMock()
    session.execute = AsyncMock(return_value=_Assocs())

    child_entity = types.SimpleNamespace(Name="CFItem", Array="No", UseConsiderations=None)
    monkeypatch.setattr(svc, "get_entity_by_id", AsyncMock(return_value=child_entity))
    monkeypatch.setattr(svc, "get_attributes_with_association_metadata_for_entity", AsyncMock(return_value=[]))

    property_key_map = {}
    parent_schema = {"properties": {}}
    await svc.find_children(
        {1: [2]},
        1,
        parent_schema,
        df_entity=pd.DataFrame([{"Id": 1, "Name": "CFPackage"}, {"Id": 2, "Name": "CFItem"}]),
        session=session,
        include_attr_md=False,
        data_model_id=17,
        data_model=types.SimpleNamespace(Type="BaseLIF"),
        include_entity_md=False,
        public_only=False,
        full_export=False,
        property_key_map=property_key_map,
    )

    written_key = "CFItemsCFItem"
    assert written_key in parent_schema["properties"], "find_children did not apply the relationship-qualified key"
    assert property_key_map == {(1, 2): written_key}, (
        "the recorded key must be the key actually written -- if these can differ, add_ref "
        "navigates a structure that does not exist"
    )

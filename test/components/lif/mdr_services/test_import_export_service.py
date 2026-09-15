"""Regression tests for import_datamodel (Issue #668), clone_datamodel (Issue #1205) and
export_datamodel (Issue #1210).

These exercise the real import_datamodel logic end-to-end with the create_* I/O
calls mocked out. Each test guards a specific #668 regression — see the docstring
on each test rather than a running list here (which would drift as tests are added).
"""

import types
from unittest.mock import ANY, AsyncMock, MagicMock, create_autospec

import pytest
from fastapi import HTTPException

from lif.datatypes.mdr_sql_model import DataModel, DataModelType, DatamodelElementType
from lif.mdr_dto.datamodel_dto import CreateDataModelDTO
from lif.mdr_dto.import_export_dto import (
    CreateCloneDTO,
    ImportAttributeDTO,
    ImportDataModelConstraintsDTO,
    ImportDataModelDTO,
    ImportEntityDTO,
)
from lif.mdr_dto.transformation_dto import TransformationListDTO

# Hard import (not importorskip): the premise of this suite is that the module used
# to blow up at import/call time, so a future import regression must FAIL, not skip.
from lif.mdr_services import import_export_service as svc

NEW_DATA_MODEL_ID = 42
ENTITY_ID = 100
ATTRIBUTE_ID = 200
SOURCE_DATA_MODEL_ID = 999  # the exporting install's id — a DB artifact that must be remapped


@pytest.fixture
def patched_services(monkeypatch):
    """Replace every create_* call import_datamodel makes with an AsyncMock."""
    mocks = {
        "create_datamodel": AsyncMock(return_value=types.SimpleNamespace(Id=NEW_DATA_MODEL_ID)),
        "create_entity": AsyncMock(return_value=types.SimpleNamespace(Id=ENTITY_ID)),
        "create_attribute": AsyncMock(return_value=types.SimpleNamespace(Id=ATTRIBUTE_ID)),
        "create_entity_attribute_association": AsyncMock(),
        "create_entity_association": AsyncMock(),
        "create_value_set_with_values": AsyncMock(),
        "create_data_model_constraint": AsyncMock(),
    }
    for name, mock in mocks.items():
        monkeypatch.setattr(svc, name, mock)
    return mocks


def _import_payload():
    return ImportDataModelDTO(
        DataModel=CreateDataModelDTO(Name="TestDM", Type=DataModelType.SourceSchema, DataModelVersion="1.0"),
        Entities=[ImportEntityDTO(Name="Person", UniqueName="Person")],
        Attributes=[ImportAttributeDTO(Name="firstName", DataType="string", EntityName="Person")],
        ValueSets=[],
        EntityAssociation=[],
        DataModelConstraints=[
            ImportDataModelConstraintsDTO(
                ForDataModelId=SOURCE_DATA_MODEL_ID,
                ElementType=DatamodelElementType.Entity,
                ElementName="Person",
                Contributor="tester",
                ContributorOrganization="UniconQA",
            )
        ],
    )


async def test_import_creates_entity_attribute_association_with_resolved_ids(patched_services):
    """Guards #668 bugs 1 & 2: the attribute name->id map used the create_attribute
    function object instead of created_attribute.Id, and create_entity_attribute_association
    was never imported (NameError mid-import for any attribute with an EntityName)."""
    # Before the fix this raised (NameError on the unimported function / AttributeError on the
    # function object's .Id) before ever reaching this assertion.
    await svc.import_datamodel(session=AsyncMock(), data=_import_payload())

    eaa = patched_services["create_entity_attribute_association"]
    eaa.assert_awaited_once()
    association = eaa.await_args.kwargs["data"]
    assert association.EntityId == ENTITY_ID  # resolved from entity_name_id map
    assert association.AttributeId == ATTRIBUTE_ID  # created_attribute.Id, not the function object


async def test_import_persists_constraint_with_remapped_ids(patched_services):
    """Guards #668 bug 3: the constraints loop clobbered element ids to None, never
    persisted the built DTO, and forwarded the source-DB ForDataModelId."""
    await svc.import_datamodel(session=AsyncMock(), data=_import_payload())

    create_constraint = patched_services["create_data_model_constraint"]
    create_constraint.assert_awaited_once()  # was never called before (clobbered to None + not persisted)
    constraint = create_constraint.await_args.kwargs["data"]
    assert constraint.ElementType == DatamodelElementType.Entity
    assert constraint.ElementId == ENTITY_ID  # name resolved against the freshly created entity
    assert constraint.ForDataModelId == NEW_DATA_MODEL_ID  # remapped off the source-DB artifact (999)


async def test_import_skips_constraint_with_unresolvable_element(patched_services):
    """An unresolvable constraint element is skipped (logged + reported in the
    response), not crashed or silently dropped (#668)."""
    payload = ImportDataModelDTO(
        DataModel=CreateDataModelDTO(Name="TestDM", Type=DataModelType.SourceSchema, DataModelVersion="1.0"),
        Entities=[ImportEntityDTO(Name="Person", UniqueName="Person")],
        Attributes=[],
        ValueSets=[],
        EntityAssociation=[],
        DataModelConstraints=[
            ImportDataModelConstraintsDTO(
                ForDataModelId=SOURCE_DATA_MODEL_ID,
                ElementType=DatamodelElementType.Entity,
                ElementName="NoSuchEntity",
                Contributor="tester",
                ContributorOrganization="UniconQA",
            )
        ],
    )

    result = await svc.import_datamodel(session=AsyncMock(), data=payload)

    patched_services["create_data_model_constraint"].assert_not_awaited()
    # the skip is reported back to the caller, not just logged (cbeach47 review)
    assert result["skipped_constraints"] == [
        {"element_type": str(DatamodelElementType.Entity), "element_name": "NoSuchEntity"}
    ]


# --- clone_datamodel (Issue #1205) -------------------------------------------------------------


def _clone_session(existing: DataModel | None) -> MagicMock:
    """A session whose only SELECT (the uniqueness check) yields `existing`."""
    result = MagicMock()
    result.scalars.return_value.first.return_value = existing
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    return session


def _clone_payload() -> CreateCloneDTO:
    return CreateCloneDTO(
        source_data_model_id=SOURCE_DATA_MODEL_ID,
        data_model_name="ClonedDM",
        data_model_type=DataModelType.OrgLIF,
        data_model_version="2.0",
    )


async def test_clone_rejects_duplicate_with_400():
    """Guards #1205: the uniqueness check was called with 3 of its 5 positional args, so every
    clone died with a TypeError (HTTP 500) before the duplicate branch could ever be reached."""
    session = _clone_session(existing=DataModel(Name="ClonedDM", DataModelVersion="2.0"))

    with pytest.raises(HTTPException) as exc_info:
        await svc.clone_datamodel(session=session, data=_clone_payload())

    assert exc_info.value.status_code == 400
    session.add.assert_not_called()


async def test_clone_uniqueness_check_matches_inserted_tuple(monkeypatch):
    """The duplicate check must look for the exact row the clone is about to insert: same name,
    version and type, with no contributor organization (CreateCloneDTO has none and the clone
    sets none), rather than blowing up or matching on a tuple the clone never writes."""
    for helper in (
        "clone_entities",
        "clone_value_sets",
        "clone_attributes",
        "clone_entity_attribute_association",
        "clone_entity_association",
        "clone_value_set_values",
        "clone_transformation_group",
        "clone_transformations",
        "clone_transformation_attributes",
    ):
        monkeypatch.setattr(svc, helper, AsyncMock(return_value={}))
    session = _clone_session(existing=None)

    new_model = await svc.clone_datamodel(session=session, data=_clone_payload())

    (uniqueness_query,) = session.execute.await_args.args
    compiled = uniqueness_query.compile()
    where = str(compiled)
    assert '"DataModels"."Type" = ' in where
    assert '"DataModels"."ContributorOrganization" IS NULL' in where
    assert set(compiled.params.values()) >= {"ClonedDM", "2.0", DataModelType.OrgLIF}

    inserted = session.add.call_args.args[0]
    assert inserted is new_model
    assert (inserted.Name, inserted.DataModelVersion, inserted.Type) == ("ClonedDM", "2.0", DataModelType.OrgLIF)
    assert inserted.ContributorOrganization is None
    assert inserted.BaseDataModelId == SOURCE_DATA_MODEL_ID  # OrgLIF clones point at their source


# --- export_datamodel (Issue #1210) --------------------------------------------------------------

EXTENDED_DATA_MODEL_ID = 17
BASE_DATA_MODEL_ID = 1


def _autospec_export_services(monkeypatch, data_model: DataModel, base_model: DataModel | None = None) -> dict:
    """Swap every service call export_datamodel makes for a signature-checking autospec.

    #1205 and #1210 were both stale call signatures into service functions. A plain AsyncMock accepts
    any kwargs and would hide that class of bug; create_autospec raises TypeError on a kwarg the real
    function does not take, exactly as production did."""
    returns = {
        "get_datamodel_by_id": data_model,
        "get_base_model_for_given_orglif": base_model,
        "get_list_of_entities_for_data_model": (0, []),
        "get_list_of_attributes_for_data_model": (0, []),
        "get_paginated_value_sets_by_data_model_id": (0, []),
        "get_transformations_by_data_model_id": TransformationListDTO(
            SourceTransformations=[], TargetTransformations=[]
        ),
        "get_entity_associations_by_data_model_id": [],
        "get_entity_attribute_associations_by_data_model_id": (0, []),
        "get_data_model_constraints_by_data_model_id": (0, []),
    }
    mocks = {}
    for name, value in returns.items():
        mocks[name] = create_autospec(getattr(svc, name), return_value=value)
        monkeypatch.setattr(svc, name, mocks[name])
    return mocks


async def test_export_base_model_requests_own_rows_only(monkeypatch):
    """Guards #1210: get_export_dto passed check_base=False to get_list_of_entities_for_data_model and
    get_entity_associations_by_data_model_id, neither of which accepted it, so every export died with a
    TypeError (HTTP 500) before any DTO was built."""
    base = DataModel(Id=BASE_DATA_MODEL_ID, Name="Base", Type=DataModelType.BaseLIF)
    mocks = _autospec_export_services(monkeypatch, base)

    result = await svc.export_datamodel(session=AsyncMock(), id=BASE_DATA_MODEL_ID)

    assert result.ExtendedDataModel is None
    assert result.BaseDataModel.DataModel.Id == BASE_DATA_MODEL_ID
    for name in ("get_list_of_entities_for_data_model", "get_list_of_attributes_for_data_model"):
        mocks[name].assert_awaited_once_with(
            session=ANY, data_model_id=BASE_DATA_MODEL_ID, pagination=False, check_base=False
        )
    mocks["get_entity_associations_by_data_model_id"].assert_awaited_once_with(
        session=ANY, data_model_id=BASE_DATA_MODEL_ID
    )


async def test_export_extended_model_exports_base_model_separately(monkeypatch):
    """An OrgLIF export carries its own rows under ExtendedDataModel and the base model's under
    BaseDataModel, so each lookup runs once per model with check_base=False instead of letting the
    extended lookup pull base rows in and duplicate them across the two sections."""
    org = DataModel(
        Id=EXTENDED_DATA_MODEL_ID, Name="Org", Type=DataModelType.OrgLIF, BaseDataModelId=BASE_DATA_MODEL_ID
    )
    base = DataModel(Id=BASE_DATA_MODEL_ID, Name="Base", Type=DataModelType.BaseLIF)
    mocks = _autospec_export_services(monkeypatch, org, base_model=base)

    result = await svc.export_datamodel(session=AsyncMock(), id=EXTENDED_DATA_MODEL_ID)

    assert result.ExtendedDataModel.DataModel.Id == EXTENDED_DATA_MODEL_ID
    assert result.BaseDataModel.DataModel.Id == BASE_DATA_MODEL_ID
    entity_calls = mocks["get_list_of_entities_for_data_model"].await_args_list
    assert [(c.kwargs["data_model_id"], c.kwargs["check_base"]) for c in entity_calls] == [
        (EXTENDED_DATA_MODEL_ID, False),
        (BASE_DATA_MODEL_ID, False),
    ]

"""Regression tests for import_datamodel (Issue #668).

These exercise the real import_datamodel logic end-to-end with the I/O service
calls mocked out, guarding the three bugs fixed alongside #668:

1. attribute name->id map used the `create_attribute` function object instead of
   the created row (`created_attribute.Id`), corrupting later reference resolution.
2. `create_entity_attribute_association` was never imported, so any attribute with
   an EntityName raised NameError mid-import (the #668 report).
3. the constraints loop clobbered Attribute/Entity element ids to None via a stray
   `else`, never persisted the built DTO, and forwarded the source-DB ForDataModelId.
"""

import types
import pytest
from unittest.mock import AsyncMock

from lif.datatypes.mdr_sql_model import DataModelType, DatamodelElementType
from lif.mdr_dto.datamodel_dto import CreateDataModelDTO
from lif.mdr_dto.import_export_dto import (
    ImportAttributeDTO,
    ImportDataModelConstraintsDTO,
    ImportDataModelDTO,
    ImportEntityDTO,
)

pytestmark = pytest.mark.asyncio

svc = pytest.importorskip("lif.mdr_services.import_export_service")

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
    # Before the fix this raised (NameError on the unimported function / AttributeError on the
    # function object's .Id) before ever reaching this assertion.
    await svc.import_datamodel(session=AsyncMock(), data=_import_payload())

    eaa = patched_services["create_entity_attribute_association"]
    eaa.assert_awaited_once()
    association = eaa.await_args.kwargs["data"]
    assert association.EntityId == ENTITY_ID  # resolved from entity_name_id map
    assert association.AttributeId == ATTRIBUTE_ID  # created_attribute.Id, not the function object


async def test_import_persists_constraint_with_remapped_ids(patched_services):
    await svc.import_datamodel(session=AsyncMock(), data=_import_payload())

    create_constraint = patched_services["create_data_model_constraint"]
    create_constraint.assert_awaited_once()  # was never called before (clobbered to None + not persisted)
    constraint = create_constraint.await_args.kwargs["data"]
    assert constraint.ElementType == DatamodelElementType.Entity
    assert constraint.ElementId == ENTITY_ID  # name resolved against the freshly created entity
    assert constraint.ForDataModelId == NEW_DATA_MODEL_ID  # remapped off the source-DB artifact (999)


async def test_import_skips_constraint_with_unresolvable_element(patched_services):
    # A constraint whose ElementName isn't among the imported elements must be skipped
    # (logged, not persisted) rather than crashing or silently being lost.
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

    await svc.import_datamodel(session=AsyncMock(), data=payload)

    patched_services["create_data_model_constraint"].assert_not_awaited()

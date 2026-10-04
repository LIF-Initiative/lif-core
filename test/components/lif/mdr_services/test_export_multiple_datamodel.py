"""Regression test for export_multiple_datamodel (Issue #1211).

It unpacked 6 of the 7 values get_export_dto returns and built SingleDataModelExportDTO without
the required DataModelConstraints, so every GET /import_export/export/multiple/ call raised.
The data-model lookup and get_export_dto are stubbed: this test is about the unpacking.
"""

from unittest.mock import AsyncMock

from lif.mdr_dto.datamodel_constraints_dto import DataModelConstraintsDTO
from lif.mdr_dto.datamodel_dto import DataModelDTO
from lif.mdr_services import import_export_service as svc


def _data_model(id: int) -> DataModelDTO:
    return DataModelDTO(
        Id=id,
        Name=f"DM{id}",
        Description=None,
        UseConsiderations=None,
        Type="SourceSchema",
        BaseDataModelId=None,
        Notes=None,
        DataModelVersion="1.0",
        CreationDate=None,
        ActivationDate=None,
        DeprecationDate=None,
        Contributor=None,
        ContributorOrganization="LIF",
        State="Draft",
    )


def _export_rows(data_model_id: int) -> tuple:
    constraint = DataModelConstraintsDTO(
        Id=data_model_id * 10,
        ForDataModelId=data_model_id,
        ElementType="Entity",
        ElementId=1,
        Contributor=None,
        ContributorOrganization="LIF",
    )
    no_transformations = {"SourceTransformations": [], "TargetTransformations": []}
    return ([], [], [], no_transformations, [], [], [constraint])


async def test_export_multiple_includes_each_models_constraints(monkeypatch):
    monkeypatch.setattr(svc, "get_datamodel_by_id", AsyncMock(side_effect=lambda session, id: _data_model(id)))
    monkeypatch.setattr(
        svc, "get_export_dto", AsyncMock(side_effect=lambda session, data_model_id: _export_rows(data_model_id))
    )

    exports = await svc.export_multiple_datamodel(session=AsyncMock(), ids=[3, 4])

    assert [export.DataModel.Id for export in exports] == [3, 4]
    assert [[c.ForDataModelId for c in export.DataModelConstraints] for export in exports] == [[3], [4]]

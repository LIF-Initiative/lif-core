"""Base-model lookup for an extension data model (Issue #1321).

Both callers of ``get_base_model_for_given_orglif`` used to 500 on a PartnerLIF, because the
lookup only matched ``Type == "OrgLIF"``. Ids come from the backup.sql seed: 1 is the BaseLIF,
17 a live OrgLIF and 18 a live PartnerLIF (both extending 1), and 19 a deleted PartnerLIF.
"""

from unittest.mock import AsyncMock

import pytest

from lif.mdr_services import import_export_service

BASE_LIF_ID = 1
ORG_LIF_ID = 17
PARTNER_LIF_ID = 18
DELETED_PARTNER_LIF_ID = 19
MISSING_ID = 999999


@pytest.mark.parametrize("extension_id", [ORG_LIF_ID, PARTNER_LIF_ID])
async def test_get_base_model_returns_base_for_extensions(async_client_mdr, mdr_api_headers, extension_id):
    response = await async_client_mdr.get(f"/datamodels/base/{extension_id}", headers=mdr_api_headers)

    assert response.status_code == 200, response.text
    assert response.json()["Id"] == BASE_LIF_ID


@pytest.mark.parametrize("model_id", [BASE_LIF_ID, DELETED_PARTNER_LIF_ID, MISSING_ID])
async def test_get_base_model_is_404_without_a_live_extension(async_client_mdr, mdr_api_headers, model_id):
    response = await async_client_mdr.get(f"/datamodels/base/{model_id}", headers=mdr_api_headers)

    assert response.status_code == 404, response.text


async def test_export_partner_lif_includes_base_model(test_db_session, monkeypatch):
    # get_export_dto is stubbed because it fails first on #1210 for every export today;
    # this test is about the base-model lookup that runs after it.
    no_transformations = {"SourceTransformations": [], "TargetTransformations": []}
    monkeypatch.setattr(
        import_export_service, "get_export_dto", AsyncMock(return_value=([], [], [], no_transformations, [], [], []))
    )

    export = await import_export_service.export_datamodel(session=test_db_session, id=PARTNER_LIF_ID)

    assert export.ExtendedDataModel.DataModel.Id == PARTNER_LIF_ID
    assert export.BaseDataModel.DataModel.Id == BASE_LIF_ID

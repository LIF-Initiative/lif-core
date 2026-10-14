"""
The Learner Data Export API keeps the learner identifier out of its request log (#1351).
"""

import logging
from unittest import mock

import lif.learner_data_export_api.learner_data_export_endpoints as _ep
from httpx import ASGITransport, AsyncClient
from lif.learner_data_export_api import core

# Matches the key configured in conftest.py (LDE_AUTH__API_KEYS).
DEFAULT_API_KEY = "test-lde-key"
IDENTIFIER = "SENTINEL-ID-4471"
MDR_RESPONSE = {
    "total": 1,
    "data": [
        {
            "Id": 42,
            "Name": "OpenBadges",
            "Type": "SourceSchema",
            "Description": None,
            "UseConsiderations": None,
            "BaseDataModelId": None,
            "Notes": None,
            "DataModelVersion": "3.0",
            "CreationDate": None,
            "ActivationDate": None,
            "DeprecationDate": None,
            "Contributor": None,
            "ContributorOrganization": "OB",
            "State": None,
        }
    ],
}


async def test_export_request_log_has_no_learner_id(caplog):
    params = {
        "learnerId": IDENTIFIER,
        "dataModelName": "OpenBadges",
        "dataModelVersion": "3.0",
        "dataModelContributorOrganization": "OB",
    }
    with (
        mock.patch.object(_ep, "fetch_data_models_from_mdr", return_value=MDR_RESPONSE),
        mock.patch.object(_ep, "fetch_query_from_query_planner", new=mock.AsyncMock(return_value=[{"Person": {}}])),
        mock.patch.object(_ep, "translate_learner_data", new=mock.AsyncMock(return_value={})),
        mock.patch.object(_ep.CONFIG, "openapi_data_model_id", "17"),
        caplog.at_level(logging.INFO, logger=_ep.__name__),
    ):
        async with AsyncClient(transport=ASGITransport(app=core.app), base_url="http://test") as client:
            response = await client.get("/exports", headers={"X-API-Key": DEFAULT_API_KEY}, params=params)

    assert response.status_code == 200, response.text
    assert "Received request for learner data export" in caplog.text
    assert IDENTIFIER not in caplog.text

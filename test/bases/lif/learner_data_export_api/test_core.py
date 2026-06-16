from unittest import mock

import lif.learner_data_export_api.learner_data_export_endpoints as _ep
import pytest
from deepdiff import DeepDiff
from httpx import ASGITransport, AsyncClient
from lif.learner_data_export_api import core
from lif.query_planner_client import QueryPlannerException

DEFAULT_API_KEY = "changeme6"


def get_client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=core.app), base_url="http://test")


async def test_health_check():
    async with get_client() as client:
        response = await client.get("/health")
        assert response.status_code == 200
        response_json = response.json()
        expected_response = {"status": "ok"}
        assert response_json == expected_response


async def test_available_data_formats_401():
    async with get_client() as client:
        response = await client.get("/available-data-formats")
        assert response.status_code == 401
        response_json = response.json()
        expected_response = {"detail": "Authentication required: Provide either Bearer token or API key"}
        assert response_json == expected_response


async def test_available_data_formats_default_token():
    async with get_client() as client:
        response = await client.get("/available-data-formats", headers={"X-API-Key": DEFAULT_API_KEY})
        assert response.status_code == 200
        response_json = response.json()
        expected_response = {
            "metadata": {"total": 3},
            "DataFormats": [
                {
                    "name": "OpenBadges 3.0",
                    "version": "1.0.3",
                    "contributorOrganization": "OB",
                    "TransformationVersions": ["1.0.0", "1.1.0"],
                },
                {
                    "name": "CEDS",
                    "version": "2.0.0",
                    "contributorOrganization": "CEDS Org",
                    "TransformationVersions": ["2.0.0"],
                },
                {
                    "name": "ExampleDataSource",
                    "version": "1.0.1",
                    "contributorOrganization": "Community",
                    "TransformationVersions": ["1.3.0"],
                },
            ],
        }
        diff = DeepDiff(expected_response, response_json)
        assert not diff, diff  # prints out the differences if any


async def test_export_401():
    async with get_client() as client:
        response = await client.get("/exports")
        assert response.status_code == 401
        response_json = response.json()
        expected_response = {"detail": "Authentication required: Provide either Bearer token or API key"}
        assert response_json == expected_response


async def test_export_default_token():
    mdr_response = {
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

    translator_mock_response = mock.Mock()
    translator_mock_response.status_code = 200
    translator_mock_response.json.return_value = {"name": "John Doe"}

    mock_http_client = mock.AsyncMock()
    mock_http_client.post.return_value = translator_mock_response

    mock_http_cls = mock.MagicMock()
    mock_http_cls.return_value.__aenter__ = mock.AsyncMock(return_value=mock_http_client)
    mock_http_cls.return_value.__aexit__ = mock.AsyncMock(return_value=False)

    params = {
        "learnerId": "learner-123",
        "dataModelName": "OpenBadges",
        "dataModelVersion": "3.0",
        "dataModelContributorOrganization": "OB",
        "transformationId": "transform-1",
    }

    with (
        mock.patch(
            "lif.learner_data_export_api.learner_data_export_endpoints.fetch_data_models_from_mdr",
            return_value=mdr_response,
        ),
        mock.patch(
            "lif.learner_data_export_api.learner_data_export_endpoints.fetch_query_from_query_planner",
            new=mock.AsyncMock(return_value=[{"Person": {"firstName": "John"}}]),
        ),
        mock.patch("lif.learner_data_export_api.learner_data_export_endpoints.httpx.AsyncClient", mock_http_cls),
        mock.patch.object(_ep.CONFIG, "openapi_data_model_id", "17"),
    ):
        async with get_client() as client:
            response = await client.get("/exports", headers={"X-API-Key": DEFAULT_API_KEY}, params=params)

    assert response.status_code == 200, response.text
    expected_response = {"name": "John Doe"}
    diff = DeepDiff(expected_response, response.json())
    assert not diff, diff


_MDR_RESPONSE = {
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

_EXPORT_PARAMS = {
    "learnerId": "learner-123",
    "dataModelName": "OpenBadges",
    "dataModelVersion": "3.0",
    "dataModelContributorOrganization": "OB",
    "transformationId": "transform-1",
}


@pytest.mark.parametrize("exc_msg", ["HTTP 500", "HTTP 503", "HTTP 404", "request timed out", "Failed to connect"])
async def test_export_query_planner_failure_returns_500(exc_msg):
    """Any QueryPlannerException should return 500 without leaking the internal message."""
    with (
        mock.patch(
            "lif.learner_data_export_api.learner_data_export_endpoints.fetch_data_models_from_mdr",
            return_value=_MDR_RESPONSE,
        ),
        mock.patch(
            "lif.learner_data_export_api.learner_data_export_endpoints.fetch_query_from_query_planner",
            new=mock.AsyncMock(side_effect=QueryPlannerException(exc_msg)),
        ),
        mock.patch.object(_ep.CONFIG, "openapi_data_model_id", "17"),
    ):
        async with get_client() as client:
            response = await client.get("/exports", headers={"X-API-Key": DEFAULT_API_KEY}, params=_EXPORT_PARAMS)

    assert response.status_code == 500
    assert "Query Planner" in response.json()["detail"]
    assert exc_msg not in response.json()["detail"]

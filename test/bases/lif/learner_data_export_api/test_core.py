from unittest import mock

import lif.learner_data_export_api.learner_data_export_endpoints as _ep
import pytest
from deepdiff import DeepDiff
from httpx import ASGITransport, AsyncClient
from lif.learner_data_export_api import core
from lif.mdr_client import MDRClientException
from lif.query_planner_client import QueryPlannerException
from lif.translator_client import TranslatorException

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

    params = {
        "learnerId": "learner-123",
        "dataModelName": "OpenBadges",
        "dataModelVersion": "3.0",
        "dataModelContributorOrganization": "OB",
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
        mock.patch(
            "lif.learner_data_export_api.learner_data_export_endpoints.translate_learner_data",
            new=mock.AsyncMock(return_value={"name": "John Doe"}),
        ),
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
}


async def test_export_empty_query_planner_result_returns_404():
    """A 200 with an empty list from the Query Planner means learner not found."""
    with (
        mock.patch(
            "lif.learner_data_export_api.learner_data_export_endpoints.fetch_data_models_from_mdr",
            return_value=_MDR_RESPONSE,
        ),
        mock.patch(
            "lif.learner_data_export_api.learner_data_export_endpoints.fetch_query_from_query_planner",
            new=mock.AsyncMock(return_value=[]),
        ),
        mock.patch.object(_ep.CONFIG, "openapi_data_model_id", "17"),
    ):
        async with get_client() as client:
            response = await client.get("/exports", headers={"X-API-Key": DEFAULT_API_KEY}, params=_EXPORT_PARAMS)

    assert response.status_code == 404
    assert response.json()["detail"] == "Query Planner did not find any results for learnerId: learner-123"


async def test_export_multiple_query_planner_results_returns_500():
    """Multiple results from the Query Planner is an unexpected internal state."""
    with (
        mock.patch(
            "lif.learner_data_export_api.learner_data_export_endpoints.fetch_data_models_from_mdr",
            return_value=_MDR_RESPONSE,
        ),
        mock.patch(
            "lif.learner_data_export_api.learner_data_export_endpoints.fetch_query_from_query_planner",
            new=mock.AsyncMock(return_value=[{"Person": {"firstName": "John"}}, {"Person": {"firstName": "Jane"}}]),
        ),
        mock.patch.object(_ep.CONFIG, "openapi_data_model_id", "17"),
    ):
        async with get_client() as client:
            response = await client.get("/exports", headers={"X-API-Key": DEFAULT_API_KEY}, params=_EXPORT_PARAMS)

    assert response.status_code == 500
    assert response.json()["detail"] == "Query Planner returned multiple results for learnerId: learner-123"


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


async def test_export_missing_openapi_data_model_id_returns_500():
    """A missing OPENAPI_DATA_MODEL_ID should return 500 before any service calls are made."""
    with mock.patch.object(_ep.CONFIG, "openapi_data_model_id", None):
        async with get_client() as client:
            response = await client.get("/exports", headers={"X-API-Key": DEFAULT_API_KEY}, params=_EXPORT_PARAMS)

    assert response.status_code == 500
    assert response.json()["detail"] == "OPENAPI_DATA_MODEL_ID is not configured"


@pytest.mark.parametrize("exc_msg", ["HTTP 500", "HTTP 503", "request timed out", "Failed to connect"])
async def test_export_mdr_failure_returns_500(exc_msg):
    """Any MDRClientException should return 500 without leaking the internal message."""
    with (
        mock.patch(
            "lif.learner_data_export_api.learner_data_export_endpoints.fetch_data_models_from_mdr",
            side_effect=MDRClientException(exc_msg),
        ),
        mock.patch.object(_ep.CONFIG, "openapi_data_model_id", "17"),
    ):
        async with get_client() as client:
            response = await client.get("/exports", headers={"X-API-Key": DEFAULT_API_KEY}, params=_EXPORT_PARAMS)

    assert response.status_code == 500
    assert response.json()["detail"] == "Unable to retrieve data models from MDR"


async def test_export_no_mdr_data_models_returns_400():
    """No matching data models in MDR should return 400."""
    mdr_empty = {"total": 0, "data": []}
    with (
        mock.patch(
            "lif.learner_data_export_api.learner_data_export_endpoints.fetch_data_models_from_mdr",
            return_value=mdr_empty,
        ),
        mock.patch.object(_ep.CONFIG, "openapi_data_model_id", "17"),
    ):
        async with get_client() as client:
            response = await client.get("/exports", headers={"X-API-Key": DEFAULT_API_KEY}, params=_EXPORT_PARAMS)

    assert response.status_code == 400
    assert response.json()["detail"] == "Unable to determine target data model from query parameters"


async def test_export_multiple_mdr_data_models_returns_400():
    """Ambiguous MDR results (total > 1) should return 400."""
    _data_model = {
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
    mdr_multi = {"total": 2, "data": [_data_model, {**_data_model, "Id": 43}]}
    with (
        mock.patch(
            "lif.learner_data_export_api.learner_data_export_endpoints.fetch_data_models_from_mdr",
            return_value=mdr_multi,
        ),
        mock.patch.object(_ep.CONFIG, "openapi_data_model_id", "17"),
    ):
        async with get_client() as client:
            response = await client.get("/exports", headers={"X-API-Key": DEFAULT_API_KEY}, params=_EXPORT_PARAMS)

    assert response.status_code == 400
    assert response.json()["detail"] == "Found multiple target data models from query parameters"


@pytest.mark.parametrize("exc_msg", ["HTTP 422", "HTTP 503", "request timed out", "Failed to connect"])
async def test_export_translator_failure_returns_500(exc_msg):
    """Any TranslatorException should return 500 without leaking the internal message."""
    with (
        mock.patch(
            "lif.learner_data_export_api.learner_data_export_endpoints.fetch_data_models_from_mdr",
            return_value=_MDR_RESPONSE,
        ),
        mock.patch(
            "lif.learner_data_export_api.learner_data_export_endpoints.fetch_query_from_query_planner",
            new=mock.AsyncMock(return_value=[{"Person": {"firstName": "John"}}]),
        ),
        mock.patch(
            "lif.learner_data_export_api.learner_data_export_endpoints.translate_learner_data",
            new=mock.AsyncMock(side_effect=TranslatorException(exc_msg)),
        ),
        mock.patch.object(_ep.CONFIG, "openapi_data_model_id", "17"),
    ):
        async with get_client() as client:
            response = await client.get("/exports", headers={"X-API-Key": DEFAULT_API_KEY}, params=_EXPORT_PARAMS)

    assert response.status_code == 500
    assert response.json()["detail"] == "Unable to translate the learner data from the LIF model into the target model"

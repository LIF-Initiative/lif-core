import pytest
from deepdiff import DeepDiff
from httpx import ASGITransport, AsyncClient
from lif.learner_data_export_api import core

DEFAULT_API_KEY = "changeme6"


def get_client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=core.app), base_url="http://test")


@pytest.mark.asyncio
async def test_health_check():
    async with get_client() as client:
        response = await client.get("/health-check")
        assert response.status_code == 200
        response_json = response.json()
        expected_response = {"status": 200, "message": "API is healthy"}
        diff = DeepDiff(expected_response, response_json)
        assert not diff, diff  # prints out the differences if any


@pytest.mark.asyncio
async def test_auth_info_401():
    async with get_client() as client:
        response = await client.get("/test/auth-info")
        assert response.status_code == 401
        response_json = response.json()
        expected_response = {"detail": "Authentication required: Provide either Bearer token or API key"}
        diff = DeepDiff(expected_response, response_json)
        assert not diff, diff  # prints out the differences if any


@pytest.mark.asyncio
async def test_auth_info_default_token():
    async with get_client() as client:
        response = await client.get("/test/auth-info", headers={"X-API-Key": DEFAULT_API_KEY})
        assert response.status_code == 200
        response_json = response.json()
        expected_response = {
            "authenticated_as": "service",
            "service-name": "service:learner-data-export-service",
            "auth_type": "API token",
        }
        diff = DeepDiff(expected_response, response_json)
        assert not diff, diff  # prints out the differences if any


@pytest.mark.asyncio
async def test_auth_info_401():
    async with get_client() as client:
        response = await client.get("/test/auth-info")
        assert response.status_code == 401
        response_json = response.json()
        expected_response = {"detail": "Authentication required: Provide either Bearer token or API key"}
        diff = DeepDiff(expected_response, response_json)
        assert not diff, diff  # prints out the differences if any


@pytest.mark.asyncio
async def test_auth_info_default_token():
    async with get_client() as client:
        response = await client.get("/test/auth-info", headers={"X-API-Key": DEFAULT_API_KEY})
        assert response.status_code == 200
        response_json = response.json()
        expected_response = {
            "authenticated_as": "service",
            "service-name": "service:learner-data-export-service",
            "auth_type": "API token",
        }
        diff = DeepDiff(expected_response, response_json)
        assert not diff, diff  # prints out the differences if any


@pytest.mark.asyncio
async def test_available_data_formats_401():
    async with get_client() as client:
        response = await client.get("/available-data-formats")
        assert response.status_code == 401
        response_json = response.json()
        expected_response = {"detail": "Authentication required: Provide either Bearer token or API key"}
        diff = DeepDiff(expected_response, response_json)
        assert not diff, diff  # prints out the differences if any


@pytest.mark.asyncio
async def test_available_data_formats_default_token():
    async with get_client() as client:
        response = await client.get("/available-data-formats", headers={"X-API-Key": DEFAULT_API_KEY})
        assert response.status_code == 200
        response_json = response.json()
        expected_response = {
            "metadata": {"total": 3},
            "dataFormats": [
                {
                    "name": "OpenBadges 3.0",
                    "version": "1.0.3",
                    "contributorOrganization": "OB",
                    "transformationVersions": ["1.0.0", "1.1.0"],
                },
                {
                    "name": "CEDS",
                    "version": "2.0.0",
                    "contributorOrganization": "CEDS Org",
                    "transformationVersions": ["2.0.0"],
                },
                {
                    "name": "ExampleDataSource",
                    "version": "1.0.1",
                    "contributorOrganization": "Community",
                    "transformationVersions": ["1.3.0"],
                },
            ],
        }
        diff = DeepDiff(expected_response, response_json)
        assert not diff, diff  # prints out the differences if any


@pytest.mark.asyncio
async def test_export_401():
    async with get_client() as client:
        response = await client.get("/export")
        assert response.status_code == 401
        response_json = response.json()
        expected_response = {"detail": "Authentication required: Provide either Bearer token or API key"}
        diff = DeepDiff(expected_response, response_json)
        assert not diff, diff  # prints out the differences if any


@pytest.mark.asyncio
async def test_export_default_token():
    async with get_client() as client:
        response = await client.get("/export", headers={"X-API-Key": DEFAULT_API_KEY})
        assert response.status_code == 200
        response_json = response.json()
        expected_response = {"total": "data"}
        diff = DeepDiff(expected_response, response_json)
        assert not diff, diff  # prints out the differences if any

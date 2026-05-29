from deepdiff import DeepDiff
from httpx import ASGITransport, AsyncClient
from lif.learner_data_export_api import core

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
    async with get_client() as client:
        response = await client.get("/exports", headers={"X-API-Key": DEFAULT_API_KEY})
        assert response.status_code == 200
        response_json = response.json()
        expected_response = {"total": "data"}
        diff = DeepDiff(expected_response, response_json)
        assert not diff, diff  # prints out the differences if any

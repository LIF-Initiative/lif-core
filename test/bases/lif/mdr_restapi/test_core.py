import pytest


@pytest.mark.asyncio
async def test_test_auth_info_graphql_api_key(async_client_mdr, mdr_api_headers):
    response = await async_client_mdr.get("/test/auth-info", headers=mdr_api_headers)
    assert response.status_code == 200, str(response.content)
    assert response.json() == {
        "auth_type": "API key",
        "authenticated_as": "microservice",
        "service_name": "graphql-service",
    }

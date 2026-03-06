import httpx
import pytest
from unittest import mock
from unittest.mock import MagicMock, patch

from lif.graphql_client import core
from lif.graphql_client.core import GraphQLClientException


def _create_mock_response(status_code: int, json_data: dict, url: str):
    mock_response = MagicMock()
    mock_response.status_code = status_code
    mock_response.json.return_value = json_data
    mock_response.text = str(json_data)
    if status_code >= 400:
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Error", request=httpx.Request("POST", url), response=mock_response
        )
    else:
        mock_response.raise_for_status.return_value = None
    return mock_response


@patch("lif.graphql_client.core._post")
async def test_graphql_query_with_api_key(mock_post):
    mock_post.return_value = _create_mock_response(200, {"data": {"person": []}}, "http://localhost:8000/graphql")

    result = await core.graphql_query(
        query="{ person { Name { firstName } } }", url="http://localhost:8000/graphql", api_key="test-key-123"
    )

    assert result == {"data": {"person": []}}
    mock_post.assert_called_once()
    call_kwargs = mock_post.call_args
    assert call_kwargs.kwargs["headers"] == {"X-API-Key": "test-key-123"}


@patch("lif.graphql_client.core._post")
async def test_graphql_query_without_api_key(mock_post):
    """When no api_key is passed and module-level env var is empty, no auth header is sent."""
    mock_post.return_value = _create_mock_response(200, {"data": {"person": []}}, "http://localhost:8000/graphql")

    with mock.patch.object(core, "LIF_GRAPHQL_API_KEY", ""):
        result = await core.graphql_query(
            query="{ person { Name { firstName } } }", url="http://localhost:8000/graphql"
        )

    assert result == {"data": {"person": []}}
    call_kwargs = mock_post.call_args
    assert call_kwargs.kwargs["headers"] == {}


@patch("lif.graphql_client.core._post")
async def test_graphql_query_env_var_fallback(mock_post):
    """When no api_key param is passed, falls back to module-level LIF_GRAPHQL_API_KEY."""
    mock_post.return_value = _create_mock_response(200, {"data": {"person": []}}, "http://localhost:8000/graphql")

    with mock.patch.object(core, "LIF_GRAPHQL_API_KEY", "env-key-456"):
        result = await core.graphql_query(
            query="{ person { Name { firstName } } }", url="http://localhost:8000/graphql"
        )

    assert result == {"data": {"person": []}}
    call_kwargs = mock_post.call_args
    assert call_kwargs.kwargs["headers"] == {"X-API-Key": "env-key-456"}


@patch("lif.graphql_client.core._post")
async def test_graphql_query_http_error_raises_exception(mock_post):
    mock_post.return_value = _create_mock_response(401, {"detail": "Unauthorized"}, "http://localhost:8000/graphql")

    with pytest.raises(GraphQLClientException, match="GraphQL HTTP error 401"):
        await core.graphql_query(query="{ person { Name { firstName } } }", url="http://localhost:8000/graphql")


@patch("lif.graphql_client.core._post")
async def test_graphql_query_connection_error_raises_exception(mock_post):
    mock_post.side_effect = httpx.ConnectError("Connection refused")

    with pytest.raises(GraphQLClientException, match="GraphQL client error"):
        await core.graphql_query(query="{ person { Name { firstName } } }", url="http://localhost:8000/graphql")


@patch("lif.graphql_client.core._post")
async def test_graphql_mutation_with_api_key(mock_post):
    mock_post.return_value = _create_mock_response(200, {"data": {"updatePerson": {}}}, "http://localhost:8000/graphql")

    result = await core.graphql_mutation(
        query="mutation { updatePerson(filter: {}, input: {}) { Name { firstName } } }",
        url="http://localhost:8000/graphql",
        api_key="test-key-123",
    )

    assert result == {"data": {"updatePerson": {}}}
    call_kwargs = mock_post.call_args
    assert call_kwargs.kwargs["headers"] == {"X-API-Key": "test-key-123"}


@patch("lif.graphql_client.core._post")
async def test_graphql_mutation_http_error_raises_exception(mock_post):
    mock_post.return_value = _create_mock_response(
        500, {"detail": "Internal Server Error"}, "http://localhost:8000/graphql"
    )

    with pytest.raises(GraphQLClientException, match="GraphQL HTTP error 500"):
        await core.graphql_mutation(
            query="mutation { updatePerson(filter: {}, input: {}) { Name { firstName } } }",
            url="http://localhost:8000/graphql",
        )


@patch("lif.graphql_client.core._post")
async def test_graphql_query_uses_default_url(mock_post):
    mock_post.return_value = _create_mock_response(200, {"data": {"person": []}}, core.LIF_GRAPHQL_API_URL)

    result = await core.graphql_query(query="{ person { Name { firstName } } }")

    assert result == {"data": {"person": []}}
    call_kwargs = mock_post.call_args
    assert call_kwargs.args[0] == core.LIF_GRAPHQL_API_URL


@patch("lif.graphql_client.core._post")
async def test_graphql_query_custom_timeout(mock_post):
    mock_post.return_value = _create_mock_response(200, {"data": {"person": []}}, "http://localhost:8000/graphql")

    result = await core.graphql_query(
        query="{ person { Name { firstName } } }", url="http://localhost:8000/graphql", timeout_read=60.0
    )

    assert result == {"data": {"person": []}}


def test_build_headers_with_key():
    headers = core._build_headers(api_key="my-key")
    assert headers == {"X-API-Key": "my-key"}


def test_build_headers_without_key():
    with mock.patch.object(core, "LIF_GRAPHQL_API_KEY", ""):
        headers = core._build_headers(api_key="")
        assert headers == {}


def test_build_headers_env_var_fallback():
    with mock.patch.object(core, "LIF_GRAPHQL_API_KEY", "env-key"):
        headers = core._build_headers(api_key="")
        assert headers == {"X-API-Key": "env-key"}


def test_graphql_client_exception():
    exc = GraphQLClientException("test error")
    assert str(exc) == "test error"

    exc_default = GraphQLClientException()
    assert str(exc_default) == "GraphQL client error occurred"

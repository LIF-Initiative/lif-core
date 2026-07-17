import os
from unittest import mock

import httpx
import pytest
from lif.query_planner_client import QueryPlannerException, fetch_query_from_query_planner
from lif.query_planner_client.core import (
    DEFAULT_QUERY_PLANNER_CLIENT_TIMEOUT_SECONDS,
    _get_query_planner_timeout_seconds,
)

_BASE_URL = "http://localhost:8008"
_QUERY = {"query": "{ Person { firstName } }"}


def _make_http_mock(status_code: int, json_return=None):
    mock_response = mock.Mock()
    mock_response.status_code = status_code
    mock_response.json.return_value = json_return or []
    mock_response.text = str(json_return or [])

    mock_client = mock.AsyncMock()
    mock_client.post.return_value = mock_response

    mock_cls = mock.MagicMock()
    mock_cls.return_value.__aenter__ = mock.AsyncMock(return_value=mock_client)
    mock_cls.return_value.__aexit__ = mock.AsyncMock(return_value=False)
    return mock_cls, mock_client


async def test_successful_query_returns_json():
    mock_cls, _ = _make_http_mock(200, [{"firstName": "John"}])
    with mock.patch("lif.query_planner_client.core.httpx.AsyncClient", mock_cls):
        result = await fetch_query_from_query_planner(_BASE_URL, _QUERY)
    assert result == [{"firstName": "John"}]


async def test_url_is_constructed_from_base():
    mock_cls, mock_client = _make_http_mock(200, [])
    with mock.patch("lif.query_planner_client.core.httpx.AsyncClient", mock_cls):
        await fetch_query_from_query_planner(_BASE_URL, _QUERY)
    mock_client.post.assert_called_once()
    call_url = mock_client.post.call_args[0][0]
    assert call_url == f"{_BASE_URL}/query"


async def test_trailing_slash_stripped_from_base_url():
    mock_cls, mock_client = _make_http_mock(200, [])
    with mock.patch("lif.query_planner_client.core.httpx.AsyncClient", mock_cls):
        await fetch_query_from_query_planner(_BASE_URL + "/", _QUERY)
    call_url = mock_client.post.call_args[0][0]
    assert call_url == f"{_BASE_URL}/query"


async def test_query_sent_as_json_body():
    mock_cls, mock_client = _make_http_mock(200, [])
    with mock.patch("lif.query_planner_client.core.httpx.AsyncClient", mock_cls):
        await fetch_query_from_query_planner(_BASE_URL, _QUERY)
    assert mock_client.post.call_args[1]["json"] == _QUERY


async def test_non_200_raises_query_planner_exception():
    mock_cls, _ = _make_http_mock(500)
    with mock.patch("lif.query_planner_client.core.httpx.AsyncClient", mock_cls):
        with pytest.raises(QueryPlannerException, match="HTTP 500"):
            await fetch_query_from_query_planner(_BASE_URL, _QUERY)


async def test_timeout_raises_query_planner_exception():
    with mock.patch("lif.query_planner_client.core.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__ = mock.AsyncMock(side_effect=httpx.TimeoutException("timed out"))
        mock_cls.return_value.__aexit__ = mock.AsyncMock(return_value=False)
        with pytest.raises(QueryPlannerException, match="timed out"):
            await fetch_query_from_query_planner(_BASE_URL, _QUERY)


async def test_connect_error_raises_query_planner_exception():
    with mock.patch("lif.query_planner_client.core.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__ = mock.AsyncMock(side_effect=httpx.ConnectError("connection refused"))
        mock_cls.return_value.__aexit__ = mock.AsyncMock(return_value=False)
        with pytest.raises(QueryPlannerException, match="connection refused"):
            await fetch_query_from_query_planner(_BASE_URL, _QUERY)


def test_timeout_defaults_when_env_var_absent():
    with mock.patch.dict(os.environ, {}, clear=True):
        assert _get_query_planner_timeout_seconds() == DEFAULT_QUERY_PLANNER_CLIENT_TIMEOUT_SECONDS


def test_timeout_reads_from_env_var():
    with mock.patch.dict(os.environ, {"QUERY_PLANNER_CLIENT_TIMEOUT_SECONDS": "5"}):
        assert _get_query_planner_timeout_seconds() == 5


async def test_default_timeout_passed_to_async_client():
    mock_cls, _ = _make_http_mock(200, [])
    with mock.patch.dict(os.environ, {}, clear=True):
        with mock.patch("lif.query_planner_client.core.httpx.AsyncClient", mock_cls):
            await fetch_query_from_query_planner(_BASE_URL, _QUERY)
    assert mock_cls.call_args.kwargs["timeout"] == DEFAULT_QUERY_PLANNER_CLIENT_TIMEOUT_SECONDS


async def test_configured_timeout_passed_to_async_client():
    mock_cls, _ = _make_http_mock(200, [])
    with mock.patch.dict(os.environ, {"QUERY_PLANNER_CLIENT_TIMEOUT_SECONDS": "7"}):
        with mock.patch("lif.query_planner_client.core.httpx.AsyncClient", mock_cls):
            await fetch_query_from_query_planner(_BASE_URL, _QUERY)
    assert mock_cls.call_args.kwargs["timeout"] == 7

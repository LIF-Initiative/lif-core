import os
from unittest import mock

import httpx
import pytest
from lif.translator_client import TranslatorException, translate_learner_data
from lif.translator_client.core import DEFAULT_TRANSLATOR_CLIENT_TIMEOUT_SECONDS, _get_translator_timeout_seconds

_BASE_URL = "http://localhost:8007"
_SOURCE_ID = "17"
_TARGET_ID = "42"
_LEARNER_DATA = {"Person": {"firstName": "John"}}


def _make_http_mock(status_code: int, json_return=None):
    mock_response = mock.Mock()
    mock_response.status_code = status_code
    mock_response.json.return_value = json_return or {}
    mock_response.text = str(json_return or {})

    mock_client = mock.AsyncMock()
    mock_client.post.return_value = mock_response

    mock_cls = mock.MagicMock()
    mock_cls.return_value.__aenter__ = mock.AsyncMock(return_value=mock_client)
    mock_cls.return_value.__aexit__ = mock.AsyncMock(return_value=False)
    return mock_cls, mock_client


async def test_successful_translation_returns_json():
    mock_cls, mock_client = _make_http_mock(200, {"name": "John Doe"})
    with mock.patch("lif.translator_client.core.httpx.AsyncClient", mock_cls):
        result = await translate_learner_data(_BASE_URL, _SOURCE_ID, _TARGET_ID, _LEARNER_DATA)
    assert result == {"name": "John Doe"}


async def test_url_is_constructed_from_base_and_ids():
    mock_cls, mock_client = _make_http_mock(200, {})
    with mock.patch("lif.translator_client.core.httpx.AsyncClient", mock_cls):
        await translate_learner_data(_BASE_URL, _SOURCE_ID, _TARGET_ID, _LEARNER_DATA)
    mock_client.post.assert_called_once()
    call_url = mock_client.post.call_args[0][0]
    assert call_url == f"{_BASE_URL}/translate/source/{_SOURCE_ID}/target/{_TARGET_ID}"


async def test_tenant_schema_header_sent_when_provided():
    mock_cls, mock_client = _make_http_mock(200, {})
    with mock.patch("lif.translator_client.core.httpx.AsyncClient", mock_cls):
        await translate_learner_data(_BASE_URL, _SOURCE_ID, _TARGET_ID, _LEARNER_DATA, tenant_schema="org1")
    headers = mock_client.post.call_args[1]["headers"]
    assert headers == {"X-API-Tenant-Schema": "org1"}


async def test_tenant_schema_header_omitted_when_none():
    mock_cls, mock_client = _make_http_mock(200, {})
    with mock.patch("lif.translator_client.core.httpx.AsyncClient", mock_cls):
        await translate_learner_data(_BASE_URL, _SOURCE_ID, _TARGET_ID, _LEARNER_DATA, tenant_schema=None)
    headers = mock_client.post.call_args[1]["headers"]
    assert headers == {}


async def test_non_200_raises_translator_exception():
    mock_cls, _ = _make_http_mock(500)
    with mock.patch("lif.translator_client.core.httpx.AsyncClient", mock_cls):
        with pytest.raises(TranslatorException, match="HTTP 500"):
            await translate_learner_data(_BASE_URL, _SOURCE_ID, _TARGET_ID, _LEARNER_DATA)


async def test_timeout_raises_translator_exception():
    with mock.patch("lif.translator_client.core.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__ = mock.AsyncMock(side_effect=httpx.TimeoutException("timed out"))
        mock_cls.return_value.__aexit__ = mock.AsyncMock(return_value=False)
        with pytest.raises(TranslatorException, match="timed out"):
            await translate_learner_data(_BASE_URL, _SOURCE_ID, _TARGET_ID, _LEARNER_DATA)


async def test_connect_error_raises_translator_exception():
    with mock.patch("lif.translator_client.core.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__ = mock.AsyncMock(side_effect=httpx.ConnectError("connection refused"))
        mock_cls.return_value.__aexit__ = mock.AsyncMock(return_value=False)
        with pytest.raises(TranslatorException, match="connection refused"):
            await translate_learner_data(_BASE_URL, _SOURCE_ID, _TARGET_ID, _LEARNER_DATA)


def test_timeout_defaults_when_env_var_absent():
    with mock.patch.dict(os.environ, {}, clear=True):
        assert _get_translator_timeout_seconds() == DEFAULT_TRANSLATOR_CLIENT_TIMEOUT_SECONDS


def test_timeout_reads_from_env_var():
    with mock.patch.dict(os.environ, {"TRANSLATOR_CLIENT_TIMEOUT_SECONDS": "5"}):
        assert _get_translator_timeout_seconds() == 5


async def test_default_timeout_passed_to_async_client():
    mock_cls, _ = _make_http_mock(200, {})
    with mock.patch.dict(os.environ, {}, clear=True):
        with mock.patch("lif.translator_client.core.httpx.AsyncClient", mock_cls):
            await translate_learner_data(_BASE_URL, _SOURCE_ID, _TARGET_ID, _LEARNER_DATA)
    assert mock_cls.call_args.kwargs["timeout"] == DEFAULT_TRANSLATOR_CLIENT_TIMEOUT_SECONDS


async def test_configured_timeout_passed_to_async_client():
    mock_cls, _ = _make_http_mock(200, {})
    with mock.patch.dict(os.environ, {"TRANSLATOR_CLIENT_TIMEOUT_SECONDS": "7"}):
        with mock.patch("lif.translator_client.core.httpx.AsyncClient", mock_cls):
            await translate_learner_data(_BASE_URL, _SOURCE_ID, _TARGET_ID, _LEARNER_DATA)
    assert mock_cls.call_args.kwargs["timeout"] == 7

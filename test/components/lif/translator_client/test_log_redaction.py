"""
A Translator error response is not logged (#1351).

A 422 from FastAPI echoes the request body (pydantic's `input`), so logging the response text
logs the posted record, learner data included.
"""

import logging
from unittest import mock

import pytest
from lif.translator_client import TranslatorException, translate_learner_data

FIELD_VALUE = "SENTINEL-ID-4471"


async def test_error_response_body_is_not_logged(caplog):
    response = mock.Mock(status_code=422, text=f'{{"detail": [{{"input": "{FIELD_VALUE}"}}]}}')
    client = mock.AsyncMock()
    client.post.return_value = response
    client_cls = mock.MagicMock()
    client_cls.return_value.__aenter__ = mock.AsyncMock(return_value=client)
    client_cls.return_value.__aexit__ = mock.AsyncMock(return_value=False)

    with (
        mock.patch("lif.translator_client.core.httpx.AsyncClient", client_cls),
        caplog.at_level(logging.ERROR, logger="lif.translator_client.core"),
        pytest.raises(TranslatorException),
    ):
        await translate_learner_data("http://translator.test", "17", "42", {"Person": {"firstName": FIELD_VALUE}})

    assert "returned HTTP 422" in caplog.text
    assert FIELD_VALUE not in caplog.text

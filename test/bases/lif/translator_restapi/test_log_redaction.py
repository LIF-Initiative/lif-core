"""
The Translator API keeps learner values out of its ValueError log (#1351), in the served app and in base_test.

A source-schema violation reaches the handler as a ValueError whose text quotes the learner value.
"""

import logging
from unittest.mock import AsyncMock, patch

from httpx import ASGITransport, AsyncClient
from lif.translator import core as translator_core
from lif.translator_restapi import base_test, core

FIELD_VALUE = "SENTINEL-ID-4471"


def _base_translator() -> translator_core.BaseTranslator:
    config = translator_core.BaseTranslatorConfig(
        source_schema={"type": "object", "properties": {"x": {"type": "integer"}}},
        target_schema={"type": "object"},
        mappings=[],
    )
    return translator_core.BaseTranslator(config)


def _schema_violation() -> ValueError:
    try:
        _base_translator().run({"x": FIELD_VALUE})
    except ValueError as e:
        return e
    raise AssertionError("expected a source-schema violation")


async def test_value_error_log_has_no_learner_value(caplog):
    translator = AsyncMock()
    translator.run.side_effect = _schema_violation()
    with (
        patch.object(core, "Translator", return_value=translator),
        caplog.at_level(logging.WARNING, logger="lif.translator_restapi.core"),
    ):
        async with AsyncClient(transport=ASGITransport(app=core.app), base_url="http://test") as client:
            response = await client.post("/translate/source/1/target/2", json={"x": FIELD_VALUE})

    assert response.status_code == 400
    assert "Value error" in caplog.text
    assert "$.x" in caplog.text
    assert FIELD_VALUE not in caplog.text


async def test_base_test_value_error_log_has_no_learner_value(caplog):
    with (
        patch.object(base_test, "translator", _base_translator()),
        caplog.at_level(logging.WARNING, logger="lif.translator_restapi.base_test"),
    ):
        async with AsyncClient(transport=ASGITransport(app=base_test.app), base_url="http://test") as client:
            response = await client.post("/translate", json={"x": FIELD_VALUE})

    assert response.status_code == 400
    assert "Value error" in caplog.text
    assert "$.x" in caplog.text
    assert FIELD_VALUE not in caplog.text

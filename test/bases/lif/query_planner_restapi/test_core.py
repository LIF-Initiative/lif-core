import asyncio
import logging
import os
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import Response

from lif.datatypes import (
    LIFPersonIdentifier,
    LIFPersonIdentifiers,
    LIFQuery,
    LIFQueryFilter,
    LIFQueryPersonFilter,
    LIFQueryStatusResponse,
    LIFRecord,
)

_CONFIG_ENV = {
    "LIF_QUERY_PLANNER_INFORMATION_SOURCES_CONFIG_PATH": os.path.dirname(__file__)
    + "/test_information_sources_config.yml"
}


class TestMyModule(unittest.TestCase):
    @patch.dict(os.environ, _CONFIG_ENV)
    def test_core(self):
        from lif.query_planner_restapi import core

        assert core is not None


# -------------------------------------------------------------------------
# #1269 — person data must never reach the logs.
# -------------------------------------------------------------------------
def _sentinel_query() -> LIFQuery:
    return LIFQuery(
        filter=LIFQueryFilter(
            root=LIFQueryPersonFilter(
                person=LIFPersonIdentifiers(
                    Identifier=LIFPersonIdentifier(identifier="Sentinel-1234", identifierType="School-assigned number")
                )
            )
        ),
        selected_fields=["person.name"],
    )


def _sentinel_record() -> LIFRecord:
    return LIFRecord.model_validate(
        {
            "person": [
                {
                    "identifier": [{"identifier": "Sentinel-1234", "identifierType": "School-assigned number"}],
                    "name": [{"givenName": ["Bellwether"], "familyName": "Canary"}],
                }
            ]
        }
    )


@patch.dict(os.environ, _CONFIG_ENV)
def test_sync_query_endpoint_does_not_log_returned_records(caplog):
    from lif.query_planner_restapi import core

    mock_service = AsyncMock()
    mock_service.run_query.side_effect = [
        LIFQueryStatusResponse(query_id="run-1", status="COMPLETED"),
        [_sentinel_record()],
    ]

    with patch.object(core, "service", mock_service), caplog.at_level(logging.DEBUG):
        asyncio.run(core.do_run_query_sync(_sentinel_query(), Response()))

    assert "Canary" not in caplog.text
    assert "Bellwether" not in caplog.text
    assert "Sentinel" not in caplog.text
    # The line still reports that the query completed, and with how many records.
    assert "Query completed successfully" in caplog.text


@patch.dict(os.environ, _CONFIG_ENV)
def test_async_query_endpoint_does_not_log_returned_records(caplog):
    from lif.query_planner_restapi import core

    mock_service = AsyncMock()
    mock_service.run_query.return_value = [_sentinel_record()]

    with patch.object(core, "service", mock_service), caplog.at_level(logging.DEBUG):
        asyncio.run(core.do_run_query(_sentinel_query(), Response()))

    assert "Canary" not in caplog.text
    assert "Bellwether" not in caplog.text
    assert "Sentinel" not in caplog.text
    assert "Query completed successfully" in caplog.text

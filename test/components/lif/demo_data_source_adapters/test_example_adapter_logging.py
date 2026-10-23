"""
The example REST API adapter keeps learner data out of its logs, at every level (#1351).

This adapter is in the Dagster job's default config. The real adapter runs against a stubbed HTTP
response, so every line it logs is checked, including DEBUG ones.
"""

import logging
from unittest import mock

import pytest

from lif.datatypes import LIFQueryPlanPart
from lif.demo_data_source_adapters.example_data_source_rest_api_to_lif_adapter import adapter as example

PERSON_ID = "SENTINEL-ID-4471"
SOURCE_VALUE = "SENTINEL-SOURCE-Marigold"


def _adapter() -> example.ExampleDataSourceRestAPIToLIFAdapter:
    part = LIFQueryPlanPart(
        information_source_id="src1",
        adapter_id="example-data-source-rest-api-to-lif",
        person_id={"identifier": PERSON_ID, "identifierType": "School-assigned number"},
        lif_fragment_paths=["Person.Name"],
    )
    return example.ExampleDataSourceRestAPIToLIFAdapter(part, {"host": "source.example", "token": "t"})


def _run(body: dict, caplog) -> None:
    response = mock.Mock()
    response.json.return_value = body
    caplog.set_level(logging.DEBUG, logger=example.logger.name)
    with mock.patch.object(example.requests, "get", return_value=response):
        _adapter().run()


def test_successful_run_logs_no_learner_data(caplog):
    _run({"user": {"name": SOURCE_VALUE}}, caplog)

    assert any(record.levelno == logging.DEBUG for record in caplog.records)
    assert PERSON_ID not in caplog.text
    assert SOURCE_VALUE not in caplog.text


def test_source_errors_are_logged_without_their_content(caplog):
    # A source can echo the requested identifier back in its error messages.
    with pytest.raises(Exception, match="Example Data Source REST API errors"):
        _run({"errors": [{"message": f"no user {PERSON_ID}"}]}, caplog)

    assert any(record.levelno == logging.ERROR for record in caplog.records)
    assert PERSON_ID not in caplog.text

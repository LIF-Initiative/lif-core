"""
The LIF-to-LIF adapter keeps learner data out of its logs, at every level (#1351).

The real adapter runs against a stubbed HTTP response, so every line it logs is checked, including
DEBUG ones, which reach Dagster's compute logs and CloudWatch whenever LOG_LEVEL=DEBUG.
"""

import logging
from unittest import mock

import pytest

from lif.data_source_adapters.lif_to_lif_adapter import adapter as lif_to_lif
from lif.datatypes import LIFQueryPlanPart

PERSON_ID = "SENTINEL-ID-4471"
SOURCE_VALUE = "SENTINEL-SOURCE-Marigold"


def _adapter() -> lif_to_lif.LIFToLIFAdapter:
    part = LIFQueryPlanPart(
        information_source_id="org2",
        adapter_id="lif-to-lif",
        person_id={"identifier": PERSON_ID, "identifierType": "School-assigned number"},
        lif_fragment_paths=["Person.Name"],
    )
    return lif_to_lif.LIFToLIFAdapter(part, {"host": "org2.example", "token": "t"})


def _run(body: dict, caplog) -> None:
    response = mock.Mock()
    response.json.return_value = body
    caplog.set_level(logging.DEBUG, logger=lif_to_lif.logger.name)
    with mock.patch.object(lif_to_lif.requests, "post", return_value=response):
        _adapter().run()


def test_successful_run_logs_no_learner_data(caplog):
    _run({"data": {"person": [{"Name": [{"firstName": SOURCE_VALUE}]}]}}, caplog)

    assert any(record.levelno == logging.DEBUG for record in caplog.records)
    assert PERSON_ID not in caplog.text
    assert SOURCE_VALUE not in caplog.text


def test_graphql_errors_are_logged_without_their_content(caplog):
    # A source can echo the query variables back in its error messages.
    with pytest.raises(Exception, match="GraphQL errors"):
        _run({"errors": [{"message": f"no person with identifier {PERSON_ID}"}]}, caplog)

    assert any(record.levelno == logging.ERROR for record in caplog.records)
    assert PERSON_ID not in caplog.text

"""
The Query Planner keeps learner data out of its error logs and error messages (#1351).

The cache and orchestrator answer some errors with a body that echoes the request (FastAPI's 422
quotes its input, filter included), and pydantic's ValidationError quotes the value it rejected.
These messages were logged, then wrapped in a LIFException that the REST layer logs again, so each
test checks both the captured logs (tracebacks included) and the raised message.
"""

import asyncio
import logging
from unittest.mock import patch

import httpx
import pytest

from lif.datatypes import (
    LIFPersonIdentifier,
    LIFPersonIdentifiers,
    LIFQuery,
    LIFQueryFilter,
    LIFQueryPersonFilter,
    LIFUpdate,
)
from lif.datatypes.core import LIFUpdatePersonPayload
from lif.datatypes.orchestration import OrchestratorJobRequest
from lif.exceptions.core import LIFException
from lif.query_planner_service import core
from lif.query_planner_service.core import OrchestratorJobResults

IDENTIFIER = "SENTINEL-ID-4471"
FIELD_VALUE = "Marigold"
URL = "https://api.example.com"
# FastAPI's 422 body: it quotes the request's input.
ECHOED_422 = f'{{"detail": [{{"type": "missing", "input": {{"identifier": "{IDENTIFIER}"}}}}]}}'


def _query() -> LIFQuery:
    return LIFQuery(
        filter=LIFQueryFilter(
            root=LIFQueryPersonFilter(
                person=LIFPersonIdentifiers(
                    Identifier=LIFPersonIdentifier(identifier=IDENTIFIER, identifierType="School-assigned number")
                )
            )
        ),
        selected_fields=["person.name"],
    )


def _service() -> core.LIFQueryPlannerService:
    sources = [
        {
            "information_source_id": "source_1",
            "information_source_organization": "Example Org 1",
            "adapter_id": "lif-to-lif",
            "ttl_hours": 24,
            "lif_fragment_paths": ["Person.name"],
        }
    ]
    config = core.LIFQueryPlannerConfig(lif_cache_url=URL, lif_orchestrator_url=URL, information_sources_config=sources)
    return core.LIFQueryPlannerService(config=config)


def _response(status_code: int, text: str) -> httpx.Response:
    return httpx.Response(status_code, text=text, request=httpx.Request("POST", URL))


def _assert_no_learner_data(caplog, error: Exception):
    # caplog.text holds every logger's output, tracebacks included.
    for text in (caplog.text, str(error)):
        assert IDENTIFIER not in text
        assert FIELD_VALUE not in text


@pytest.mark.parametrize(
    "call, expected_log",
    [
        (lambda: core.query_lif_cache(URL + "/query", _query(), 5), "LIF Cache query HTTP error: 422"),
        (
            lambda: core.post_orchestrator_job(URL + "/jobs", OrchestratorJobRequest(lif_query_plan=[]), 5),
            "Orchestrator job post HTTP error: 422",
        ),
    ],
    ids=["cache-query", "orchestrator-post"],
)
def test_an_echoing_error_body_is_not_logged(caplog, call, expected_log):
    with (
        patch("httpx.AsyncClient.post", return_value=_response(422, ECHOED_422)),
        caplog.at_level(logging.INFO),
        pytest.raises(LIFException) as raised,
    ):
        asyncio.run(call())

    assert expected_log in caplog.text
    _assert_no_learner_data(caplog, raised.value)


def test_a_rejected_cache_record_is_not_logged_on_the_way_up(caplog):
    """The ValidationError quotes the record; run_query logged it again, chained traceback and all."""
    body = f'[{{"person": "{FIELD_VALUE}"}}]'
    with (
        patch("httpx.AsyncClient.post", return_value=_response(200, body)),
        caplog.at_level(logging.INFO),
        pytest.raises(LIFException) as raised,
    ):
        asyncio.run(_service().run_query(_query(), first_run=True))

    assert "LIF Cache query error: ValidationError" in caplog.text
    # The stack is kept, so the failing frame can still be found.
    assert "in query_lif_cache" in caplog.text
    _assert_no_learner_data(caplog, raised.value)


def test_a_failed_update_is_not_logged_with_its_message(caplog):
    update = LIFUpdate(
        updatePerson=LIFUpdatePersonPayload(
            filter={"Person": {"Identifier": {"identifier": IDENTIFIER, "identifierType": "School-assigned number"}}},
            input={"Person": {"Name": FIELD_VALUE}},
        )
    )
    with (
        patch("httpx.AsyncClient.post", side_effect=ValueError(f"rejected {IDENTIFIER} / {FIELD_VALUE}")),
        caplog.at_level(logging.INFO),
        pytest.raises(LIFException) as raised,
    ):
        asyncio.run(_service().run_update(update))

    assert "LIF Query Planner error: ValueError" in caplog.text
    _assert_no_learner_data(caplog, raised.value)


def test_a_failed_results_save_is_not_logged_with_its_message(caplog):
    job = core.LIFQueryPlannerJob(job_id="run-1", status="PENDING", query=_query())
    results = OrchestratorJobResults(run_id="run-1", query_plan_part_results=[])
    with (
        patch.object(core, "JOB_STORE", {"run-1": job}),
        patch("httpx.AsyncClient.post", side_effect=ValueError(f"rejected {IDENTIFIER} / {FIELD_VALUE}")),
        caplog.at_level(logging.INFO),
        pytest.raises(LIFException) as raised,
    ):
        asyncio.run(_service().run_post_orchestration_results(results))

    assert "LIF Query Planner error: ValueError" in caplog.text
    _assert_no_learner_data(caplog, raised.value)


def test_an_echoing_orchestrator_body_is_not_logged_through_run_query(caplog):
    """run_query logs the submission failure with logger.exception, which prints the chained causes."""

    def route(url, *args, **kwargs):
        if str(url).endswith("/query"):
            return _response(200, '[{"person": [{}]}]')
        return _response(422, ECHOED_422)

    with patch("httpx.AsyncClient.post", side_effect=route), caplog.at_level(logging.INFO):
        asyncio.run(_service().run_query(_query(), first_run=True))

    assert "Orchestrator submission failed" in caplog.text
    assert IDENTIFIER not in caplog.text

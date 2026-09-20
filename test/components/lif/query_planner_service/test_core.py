import asyncio
import httpx
import json
import logging
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock, AsyncMock

from lif.datatypes import (
    LIFFragment,
    LIFQuery,
    LIFQueryFilter,
    LIFQueryPersonFilter,
    LIFQueryStatusResponse,
    LIFPersonIdentifier,
    LIFPersonIdentifiers,
    OrchestratorJobQueryPlanPartResults,
)
from lif.query_planner_service import core, statistics
from lif.exceptions.core import LIFException
from lif.datatypes.orchestration import OrchestratorJobQueryPlanPartResults
from lif.query_planner_service.core import OrchestratorJobResults, add_job_to_store


def test_sample():
    assert core is not None


@patch("httpx.AsyncClient.post")
def test_run_query_when_not_all_data_found_in_cache(mock_post):
    query = LIFQuery(
        filter=LIFQueryFilter(
            root=LIFQueryPersonFilter(
                person=LIFPersonIdentifiers(
                    Identifier=LIFPersonIdentifier(identifier="12345", identifierType="School-assigned number")
                )
            )
        ),
        selected_fields=["person.name", "person.employmentLearningExperience", "person.positionPreferences"],
    )

    information_sources_config = [
        {
            "information_source_id": "source_1",
            "information_source_organization": "Example Org 1",
            "adapter_id": "lif-to-lif",
            "ttl_hours": 24,
            "lif_fragment_paths": ["Person.name", "Person.identifier"],
        },
        {
            "information_source_id": "source_2",
            "information_source_organization": "Example Org 2",
            "adapter_id": "lif-to-lif",
            "ttl_hours": 24,
            "lif_fragment_paths": ["Person.employmentLearningExperience"],
        },
        {
            "information_source_id": "source_3",
            "information_source_organization": "Example Org 3",
            "adapter_id": "lif-to-lif",
            "ttl_hours": 24,
            "lif_fragment_paths": ["Person.positionPreferences"],
        },
    ]

    config: core.LIFQueryPlannerConfig = core.LIFQueryPlannerConfig(
        lif_cache_url="https://api.example.com",
        lif_orchestrator_url="https://api.example.com",
        information_sources_config=information_sources_config,
    )
    service: core.LIFQueryPlannerService = core.LIFQueryPlannerService(config=config)

    mock_cache_response = _create_mock_post_response(200, [{"person": [{}]}], "https://api.example.com/query")
    mock_post_job_response = _create_mock_post_response(200, {"run_id": "123"}, "https://api.example.com/jobs")
    mock_post.side_effect = [mock_cache_response, mock_post_job_response]

    async def run_test():
        lif_query_status_response: LIFQueryStatusResponse = await service.run_query(query, first_run=True)
        assert lif_query_status_response is not None
        assert lif_query_status_response.query_id == "123"

    asyncio.run(run_test())


@patch("httpx.AsyncClient.post")
def test_run_query_when_no_data_sources_found_for_any_fragment_paths(mock_post):
    query = LIFQuery(
        filter=LIFQueryFilter(
            root=LIFQueryPersonFilter(
                person=LIFPersonIdentifiers(
                    Identifier=LIFPersonIdentifier(identifier="12345", identifierType="School-assigned number")
                )
            )
        ),
        selected_fields=["person.unknownField1", "person.unknownField2"],
    )

    information_sources_config = [
        {
            "information_source_id": "source_1",
            "information_source_organization": "Example Org 1",
            "adapter_id": "lif-to-lif",
            "ttl_hours": 24,
            "lif_fragment_paths": ["Person.name", "Person.identifier"],
        }
    ]

    config: core.LIFQueryPlannerConfig = core.LIFQueryPlannerConfig(
        lif_cache_url="https://api.example.com",
        lif_orchestrator_url="https://api.example.com",
        information_sources_config=information_sources_config,
    )
    service: core.LIFQueryPlannerService = core.LIFQueryPlannerService(config=config)

    mock_cache_response = _create_mock_post_response(200, [{"person": [{}]}], "https://api.example.com/query")
    mock_post_job_response = _create_mock_post_response(200, {"run_id": "123"}, "https://api.example.com/jobs")
    mock_post.side_effect = [mock_cache_response, mock_post_job_response]

    async def run_test():
        # When no information sources match the requested fragment paths, the service
        # should return the cached LIF records (list of LIFRecord) instead of posting a job.
        lif_records_list = await service.run_query(query, first_run=True)
        assert lif_records_list is not None
        # Expect one cached record based on the mocked cache response
        assert isinstance(lif_records_list, list)
        assert len(lif_records_list) == 1

    asyncio.run(run_test())
    mock_post.assert_called_once()


@patch("lif.query_planner_service.core.post_orchestrator_job", new_callable=AsyncMock)
def test_run_query_logs_failure_reason_when_orchestrator_submission_fails(mock_post_orchestrator_job, caplog):
    query = LIFQuery(
        filter=LIFQueryFilter(
            root=LIFQueryPersonFilter(
                person=LIFPersonIdentifiers(
                    Identifier=LIFPersonIdentifier(identifier="12345", identifierType="School-assigned number")
                )
            )
        ),
        selected_fields=["person.name", "person.positionPreferences"],
    )

    information_sources_config = [
        {
            "information_source_id": "source_1",
            "information_source_organization": "Example Org 1",
            "adapter_id": "lif-to-lif",
            "ttl_hours": 24,
            "lif_fragment_paths": ["Person.name"],
        },
        {
            "information_source_id": "source_2",
            "information_source_organization": "Example Org 2",
            "adapter_id": "lif-to-lif",
            "ttl_hours": 24,
            "lif_fragment_paths": ["Person.positionPreferences"],
        },
    ]

    config: core.LIFQueryPlannerConfig = core.LIFQueryPlannerConfig(
        lif_cache_url="https://api.example.com",
        lif_orchestrator_url="https://api.example.com",
        information_sources_config=information_sources_config,
    )
    service: core.LIFQueryPlannerService = core.LIFQueryPlannerService(config=config)

    mock_post_orchestrator_job.side_effect = httpx.ReadTimeout("Read timed out.")

    mock_cache_response = _create_mock_post_response(200, [{"person": [{}]}], "https://api.example.com/query")
    with caplog.at_level(logging.ERROR, logger="lif.query_planner_service.core"):
        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.return_value = mock_cache_response

            async def run_test():
                # The partial-degrade is preserved: cached records are returned, not a hard failure.
                lif_records = await service.run_query(query, first_run=True)
                assert isinstance(lif_records, list)
                assert len(lif_records) == 1

            asyncio.run(run_test())

    mock_post_orchestrator_job.assert_awaited_once()

    failure_logs = [
        record
        for record in caplog.records
        if record.name == "lif.query_planner_service.core" and record.levelname == "ERROR"
    ]
    assert failure_logs
    assert any("Orchestrator submission failed" in record.getMessage() for record in failure_logs)
    assert any("1 cached records" in record.getMessage() for record in failure_logs)
    assert any(record.exc_info is not None and "Read timed out." in str(record.exc_info[1]) for record in failure_logs)


@patch("httpx.AsyncClient.post")
def test_orchestrator_timeout_type_survives_the_empty_message_wrapping(mock_post, caplog):
    """Issue #1204: the real failure chain, not a mocked stand-in.

    `post_orchestrator_job` renders the reason as f"...: {e}", and transport timeouts
    carry an EMPTY message, so it logs "Orchestrator job post error: " and re-raises a
    LIFException carrying that same empty message. This test lets that real erasure
    happen -- it patches the transport, not `post_orchestrator_job` -- and pins that
    `logger.exception` still surfaces the httpx type through the `raise ... from e`
    chain. A test that mocks `post_orchestrator_job` cannot show this: it would assert
    against an exception the production path never raises here.
    """
    query = LIFQuery(
        filter=LIFQueryFilter(
            root=LIFQueryPersonFilter(
                person=LIFPersonIdentifiers(
                    Identifier=LIFPersonIdentifier(identifier="12345", identifierType="School-assigned number")
                )
            )
        ),
        selected_fields=["person.name", "person.positionPreferences"],
    )

    information_sources_config = [
        {
            "information_source_id": "source_1",
            "information_source_organization": "Example Org 1",
            "adapter_id": "lif-to-lif",
            "ttl_hours": 24,
            "lif_fragment_paths": ["Person.name"],
        },
        {
            "information_source_id": "source_2",
            "information_source_organization": "Example Org 2",
            "adapter_id": "lif-to-lif",
            "ttl_hours": 24,
            "lif_fragment_paths": ["Person.positionPreferences"],
        },
    ]

    config: core.LIFQueryPlannerConfig = core.LIFQueryPlannerConfig(
        lif_cache_url="https://api.example.com",
        lif_orchestrator_url="https://api.example.com",
        information_sources_config=information_sources_config,
    )
    service: core.LIFQueryPlannerService = core.LIFQueryPlannerService(config=config)

    mock_cache_response = _create_mock_post_response(200, [{"person": [{}]}], "https://api.example.com/query")

    def route(url, *args, **kwargs):
        if str(url).endswith("/query"):
            return mock_cache_response
        # httpx timeout exceptions from the transport carry an empty message -- that is
        # the whole point, so do not give this one a message.
        raise httpx.ReadTimeout("")

    mock_post.side_effect = route

    with caplog.at_level(logging.ERROR, logger="lif.query_planner_service.core"):
        asyncio.run(service.run_query(query, first_run=True))

    messages = [r.getMessage() for r in caplog.records]
    # The upstream handler still erases the reason -- pinned so a future "cleanup" there
    # cannot quietly become the only record of the failure.
    assert "Orchestrator job post error: " in messages

    submission_failures = [r for r in caplog.records if "Orchestrator submission failed" in r.getMessage()]
    assert submission_failures
    record = submission_failures[0]
    assert record.exc_info is not None
    # The immediate exception is the LIFException with the empty message; the httpx type
    # survives only as its __cause__, which is what logger.exception renders.
    assert isinstance(record.exc_info[1], LIFException)
    assert isinstance(record.exc_info[1].__cause__, httpx.ReadTimeout)
    assert "ReadTimeout" in caplog.text


@patch("httpx.AsyncClient.post")
def test_run_post_orchestration_results(mock_post):
    information_sources_config = [
        {
            "information_source_id": "source_1",
            "information_source_organization": "Example Org 1",
            "adapter_id": "lif_to_lif",
            "ttl_hours": 24,
            "lif_fragment_paths": ["Person.name", "Person.identifier"],
        },
        {
            "information_source_id": "source_2",
            "information_source_organization": "Example Org 2",
            "adapter_id": "lif_to_lif",
            "ttl_hours": 24,
            "lif_fragment_paths": ["Person.employmentLearningExperience"],
        },
        {
            "information_source_id": "source_3",
            "information_source_organization": "Example Org 3",
            "adapter_id": "lif_to_lif",
            "ttl_hours": 24,
            "lif_fragment_paths": ["Person.positionPreferences"],
        },
    ]

    config: core.LIFQueryPlannerConfig = core.LIFQueryPlannerConfig(
        lif_cache_url="https://api.example.com/cache",
        lif_orchestrator_url="https://api.example.com/orchestrator",
        information_sources_config=information_sources_config,
    )
    service: core.LIFQueryPlannerService = core.LIFQueryPlannerService(config=config)

    mock_post_orchestration_response = _create_mock_post_response(200, [], "https://api.example.com/cache/save")
    mock_post.side_effect = [mock_post_orchestration_response]

    async def run_test():
        orchestration_results = OrchestratorJobResults(
            run_id="123",
            query_plan_part_results=[
                OrchestratorJobQueryPlanPartResults(
                    information_source_id="source_1",
                    adapter_id="lif_to_lif",
                    data_timestamp="2023-10-01T12:00:00Z",
                    person_id=LIFPersonIdentifier(identifier="12345", identifierType="School-assigned number"),
                    fragments=[
                        {
                            "fragment_path": "person.positionPreferences",
                            "fragment": [
                                {
                                    "id": "pp-1",
                                    "type": ["PositionPreferences"],
                                    "desiredPositionTitle": "Senior Software Engineer",
                                }
                            ],
                        },
                        {
                            "fragment_path": "person.name",
                            "fragment": [
                                {
                                    "identifier": [{"identifier": "12345", "identifierType": "School-assigned number"}],
                                    "name": [{"familyName": "Doe", "givenName": ["John"]}],
                                }
                            ],
                        },
                    ],
                    error=None,
                ),
                OrchestratorJobQueryPlanPartResults(
                    information_source_id="source_2",
                    adapter_id="lif_to_lif",
                    data_timestamp="2023-10-01T12:00:00Z",
                    person_id=LIFPersonIdentifier(identifier="12345", identifierType="School-assigned number"),
                    fragments=[
                        {
                            "fragment_path": "person.employmentLearningExperience",
                            "fragment": [
                                {"id": "ele-1", "type": ["EmploymentLearningExperience"], "title": "Software Engineer"}
                            ],
                        }
                    ],
                    error=None,
                ),
                OrchestratorJobQueryPlanPartResults(
                    information_source_id="source_3",
                    adapter_id="lif_to_lif",
                    data_timestamp="2023-10-01T12:00:00Z",
                    person_id=LIFPersonIdentifier(identifier="12345", identifierType="School-assigned number"),
                    fragments=[],
                    error="Pipeline did not run or failed.",
                ),
                OrchestratorJobQueryPlanPartResults(
                    information_source_id="org2",
                    adapter_id="lif-to-lif",
                    data_timestamp="2025-10-07T03:45:04.289683+00:00",
                    person_id=LIFPersonIdentifier(identifier="12345", identifierType="School-assigned number"),
                    fragments=[LIFFragment(fragment_path="person.all", fragment=[{"person": []}])],
                    error=None,
                ),
            ],
        )

        add_job_to_store(
            core.LIFQueryPlannerJob(
                job_id="123",
                status="PENDING",
                query=LIFQuery(
                    filter=LIFQueryFilter(
                        root=LIFQueryPersonFilter(
                            person=LIFPersonIdentifiers(
                                Identifier=LIFPersonIdentifier(
                                    identifier="12345", identifierType="School-assigned number"
                                )
                            )
                        )
                    ),
                    selected_fields=[
                        "person.name",
                        "person.employmentLearningExperience",
                        "person.positionPreferences",
                    ],
                ),
            )
        )
        await service.run_post_orchestration_results(orchestration_results)

    asyncio.run(run_test())
    mock_post.assert_called()
    mock_post.assert_called_with(
        "https://api.example.com/cache/save",
        json={
            "lif_query_filter": {
                "Person": {"Identifier": {"identifier": "12345", "identifierType": "School-assigned number"}}
            },
            "lif_fragments": [
                {
                    "fragment_path": "person.positionPreferences",
                    "fragment": [
                        {
                            "id": "pp-1",
                            "type": ["PositionPreferences"],
                            "desiredPositionTitle": "Senior Software Engineer",
                        }
                    ],
                },
                {
                    "fragment_path": "person.name",
                    "fragment": [
                        {
                            "identifier": [{"identifier": "12345", "identifierType": "School-assigned number"}],
                            "name": [{"familyName": "Doe", "givenName": ["John"]}],
                        }
                    ],
                },
                {
                    "fragment_path": "person.employmentLearningExperience",
                    "fragment": [
                        {"id": "ele-1", "type": ["EmploymentLearningExperience"], "title": "Software Engineer"}
                    ],
                },
            ],
        },
    )


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


@patch("httpx.AsyncClient.post")
def test_run_query_does_not_log_the_person_identifier(mock_post, caplog):
    config: core.LIFQueryPlannerConfig = core.LIFQueryPlannerConfig(
        lif_cache_url="https://api.example.com",
        lif_orchestrator_url="https://api.example.com",
        information_sources_config=[
            {
                "information_source_id": "source_1",
                "information_source_organization": "Example Org 1",
                "adapter_id": "lif-to-lif",
                "ttl_hours": 24,
                "lif_fragment_paths": ["Person.name"],
            }
        ],
    )
    service: core.LIFQueryPlannerService = core.LIFQueryPlannerService(config=config)

    mock_post.side_effect = [
        _create_mock_post_response(200, [{"person": [{}]}], "https://api.example.com/query"),
        _create_mock_post_response(200, {"run_id": "run-1"}, "https://api.example.com/jobs"),
    ]

    with patch.object(core, "JOB_STORE", {}), caplog.at_level(logging.DEBUG):
        asyncio.run(service.run_query(_sentinel_query(), first_run=True))

    assert "Sentinel" not in caplog.text
    # The query plan line still says which sources were planned.
    assert "source_1" in caplog.text


@patch("httpx.AsyncClient.post")
def test_run_post_orchestration_results_does_not_log_person_data(mock_post, caplog):
    config: core.LIFQueryPlannerConfig = core.LIFQueryPlannerConfig(
        lif_cache_url="https://api.example.com",
        lif_orchestrator_url="https://api.example.com",
        information_sources_config=[],
    )
    service: core.LIFQueryPlannerService = core.LIFQueryPlannerService(config=config)
    mock_post.return_value = _create_mock_post_response(200, {}, "https://api.example.com/save")

    results = OrchestratorJobResults(
        run_id="run-1",
        query_plan_part_results=[
            OrchestratorJobQueryPlanPartResults(
                information_source_id="source_1",
                adapter_id="lif-to-lif",
                data_timestamp="2026-01-01T00:00:00Z",
                person_id=LIFPersonIdentifier(identifier="Sentinel-1234", identifierType="School-assigned number"),
                fragments=[LIFFragment(fragment_path="person.name", fragment=[{"name": [{"familyName": "Canary"}]}])],
                error=None,
            )
        ],
    )

    job_store = {"run-1": core.LIFQueryPlannerJob(job_id="run-1", query=_sentinel_query(), status="PENDING")}
    with patch.object(core, "JOB_STORE", job_store), caplog.at_level(logging.DEBUG):
        asyncio.run(service.run_post_orchestration_results(results))

    assert "Sentinel" not in caplog.text
    assert "Canary" not in caplog.text
    # The run id and the source are still traceable.
    assert "run-1" in caplog.text
    assert "source_1" in caplog.text


# -------------------------------------------------------------------------
# #341 — query statistics emission.
# -------------------------------------------------------------------------
_FULL_CACHE_RECORD = {"person": [{"name": [{"givenName": ["John"], "familyName": "Doe"}]}]}

_STATS_SOURCES = [
    {
        "information_source_id": "source_1",
        "information_source_organization": "Example Org 1",
        "adapter_id": "lif-to-lif",
        "ttl_hours": 24,
        "lif_fragment_paths": ["Person.name"],
    }
]


def _stats_service() -> "core.LIFQueryPlannerService":
    return core.LIFQueryPlannerService(
        config=core.LIFQueryPlannerConfig(
            lif_cache_url="https://api.example.com",
            lif_orchestrator_url="https://api.example.com",
            information_sources_config=_STATS_SOURCES,
        )
    )


def _emitted_events(caplog) -> list:
    prefix = statistics.QUERY_STATISTICS_PREFIX + " "
    return [json.loads(line[line.index(prefix) + len(prefix) :]) for line in caplog.text.splitlines() if prefix in line]


@patch("httpx.AsyncClient.post")
def test_run_query_emits_orchestrated_query_statistics(mock_post, caplog):
    mock_post.side_effect = [
        _create_mock_post_response(200, [{"person": [{}]}], "https://api.example.com/query"),
        _create_mock_post_response(200, {"run_id": "run-1"}, "https://api.example.com/jobs"),
    ]

    with patch.object(core, "JOB_STORE", {}), caplog.at_level(logging.INFO):
        asyncio.run(_stats_service().run_query(_sentinel_query(), first_run=True))

    events = _emitted_events(caplog)
    assert len(events) == 1
    assert events[0]["outcome"] == statistics.OUTCOME_ORCHESTRATED
    assert events[0]["correlation_id"] == "run-1"
    assert events[0]["requested_paths"] == ["Person.name"]
    assert events[0]["sources"] == [{"information_source_id": "source_1", "adapter_id": "lif-to-lif", "path_count": 1}]
    assert "Sentinel" not in caplog.text


@patch("httpx.AsyncClient.post")
def test_run_query_emits_served_from_cache_statistics(mock_post, caplog):
    mock_post.side_effect = [_create_mock_post_response(200, [_FULL_CACHE_RECORD], "https://api.example.com/query")]

    with patch.object(core, "JOB_STORE", {}), caplog.at_level(logging.INFO):
        asyncio.run(_stats_service().run_query(_sentinel_query(), first_run=True))

    events = _emitted_events(caplog)
    assert len(events) == 1
    assert events[0]["outcome"] == statistics.OUTCOME_SERVED_FROM_CACHE
    assert events[0]["cache_hit"] is True


@patch("httpx.AsyncClient.post")
def test_sync_query_path_emits_exactly_one_planned_event(mock_post, caplog):
    # The sync /query endpoint calls run_query twice: once with first_run=True, then again with
    # first_run=False after polling. The second call lands on the served-from-cache branch, so
    # without the first_run guard every orchestrated query would be counted twice (#341 gap 3).
    mock_post.side_effect = [
        _create_mock_post_response(200, [{"person": [{}]}], "https://api.example.com/query"),
        _create_mock_post_response(200, {"run_id": "run-1"}, "https://api.example.com/jobs"),
        _create_mock_post_response(200, [_FULL_CACHE_RECORD], "https://api.example.com/query"),
    ]
    service = _stats_service()

    async def run_both():
        await service.run_query(_sentinel_query(), first_run=True)
        await service.run_query(_sentinel_query(), first_run=False)

    with patch.object(core, "JOB_STORE", {}), caplog.at_level(logging.INFO):
        asyncio.run(run_both())

    events = _emitted_events(caplog)
    assert len(events) == 1
    assert events[0]["outcome"] == statistics.OUTCOME_ORCHESTRATED


@patch("httpx.AsyncClient.post")
def test_run_post_orchestration_results_emits_completed_statistics(mock_post, caplog):
    mock_post.return_value = _create_mock_post_response(200, {}, "https://api.example.com/save")
    results = OrchestratorJobResults(
        run_id="run-1",
        query_plan_part_results=[
            OrchestratorJobQueryPlanPartResults(
                information_source_id="source_1",
                adapter_id="lif-to-lif",
                data_timestamp="2026-01-01T00:00:00Z",
                person_id=LIFPersonIdentifier(identifier="Sentinel-1234", identifierType="School-assigned number"),
                fragments=[LIFFragment(fragment_path="person.name", fragment=[{"name": [{"familyName": "Canary"}]}])],
                error=None,
            )
        ],
    )
    job_store = {"run-1": core.LIFQueryPlannerJob(job_id="run-1", query=_sentinel_query(), status="PENDING")}

    with patch.object(core, "JOB_STORE", job_store), caplog.at_level(logging.INFO):
        asyncio.run(_stats_service().run_post_orchestration_results(results))

    events = [e for e in _emitted_events(caplog) if e["event"] == "query_completed"]
    assert len(events) == 1
    assert events[0]["fulfilled_paths"] == ["Person.name"]
    assert events[0]["paths_not_fulfilled"] == []
    assert events[0]["sources"][0]["fragment_count"] == 1
    assert "Sentinel" not in caplog.text
    assert "Canary" not in caplog.text


@patch("httpx.AsyncClient.post")
def test_run_query_prunes_the_job_store_before_storing_a_new_job(mock_post):
    query = _prune_test_query()

    information_sources_config = [
        {
            "information_source_id": "source_1",
            "information_source_organization": "Example Org 1",
            "adapter_id": "lif-to-lif",
            "ttl_hours": 24,
            "lif_fragment_paths": ["Person.name"],
        }
    ]

    config: core.LIFQueryPlannerConfig = core.LIFQueryPlannerConfig(
        lif_cache_url="https://api.example.com",
        lif_orchestrator_url="https://api.example.com",
        information_sources_config=information_sources_config,
    )
    service: core.LIFQueryPlannerService = core.LIFQueryPlannerService(config=config)

    mock_cache_response = _create_mock_post_response(200, [{"person": [{}]}], "https://api.example.com/query")
    mock_post_job_response = _create_mock_post_response(200, {"run_id": "new-job"}, "https://api.example.com/jobs")
    mock_post.side_effect = [mock_cache_response, mock_post_job_response]

    # One more than the size bound, all expired, so exactly the oldest is eligible.
    job_store = {
        f"expired-{i}": _job_aged_hours(f"expired-{i}", core.JOB_EXPIRY_HOURS + 1)
        for i in range(core.JOB_MAX_CACHE_SIZE + 1)
    }

    async def run_test():
        lif_query_status_response: LIFQueryStatusResponse = await service.run_query(query, first_run=True)
        assert lif_query_status_response.query_id == "new-job"

    with patch.object(core, "JOB_STORE", job_store):
        asyncio.run(run_test())
        assert "expired-0" not in core.JOB_STORE
        assert "expired-1" in core.JOB_STORE
        assert "new-job" in core.JOB_STORE


def test_prune_job_store_keeps_the_most_recent_entries_regardless_of_age():
    overflow = 5
    job_store = {
        f"job-{i}": _job_aged_hours(f"job-{i}", core.JOB_EXPIRY_HOURS + 24)
        for i in range(core.JOB_MAX_CACHE_SIZE + overflow)
    }

    with patch.object(core, "JOB_STORE", job_store):
        core.prune_job_store()

        assert len(core.JOB_STORE) == core.JOB_MAX_CACHE_SIZE
        assert all(f"job-{i}" not in core.JOB_STORE for i in range(overflow))
        assert all(f"job-{i}" in core.JOB_STORE for i in range(overflow, core.JOB_MAX_CACHE_SIZE + overflow))


def test_prune_job_store_keeps_entries_younger_than_the_expiry_window():
    job_store = {f"job-{i}": _job_aged_hours(f"job-{i}", 0) for i in range(core.JOB_MAX_CACHE_SIZE + 5)}

    with patch.object(core, "JOB_STORE", job_store):
        core.prune_job_store()

        assert len(core.JOB_STORE) == core.JOB_MAX_CACHE_SIZE + 5


def test_prune_job_store_removes_an_expired_pending_entry():
    # A caller that gives up before the planner does leaves the entry PENDING forever (#572).
    job_store = {
        f"pending-{i}": _job_aged_hours(f"pending-{i}", core.JOB_EXPIRY_HOURS + 1, status="PENDING") for i in range(5)
    }
    job_store.update({f"recent-{i}": _job_aged_hours(f"recent-{i}", 0) for i in range(core.JOB_MAX_CACHE_SIZE)})

    with patch.object(core, "JOB_STORE", job_store):
        core.prune_job_store()

        assert all(f"pending-{i}" not in core.JOB_STORE for i in range(5))
        assert len(core.JOB_STORE) == core.JOB_MAX_CACHE_SIZE


def _prune_test_query() -> LIFQuery:
    return LIFQuery(
        filter=LIFQueryFilter(
            root=LIFQueryPersonFilter(
                person=LIFPersonIdentifiers(
                    Identifier=LIFPersonIdentifier(identifier="12345", identifierType="School-assigned number")
                )
            )
        ),
        selected_fields=["person.name"],
    )


def _job_aged_hours(job_id: str, hours: int, status: str = "COMPLETED") -> core.LIFQueryPlannerJob:
    timestamp = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    return core.LIFQueryPlannerJob(
        job_id=job_id,
        query=_prune_test_query(),
        status=status,
        created_timestamp=timestamp,
        updated_timestamp=timestamp,
    )


def _create_mock_post_response(status_code, json_data, uri):
    mock_response = MagicMock()
    mock_response.status_code = status_code
    mock_response.json.return_value = json_data
    if status_code >= 400:
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Error", request=httpx.Request("POST", uri), response=mock_response
        )
    else:
        mock_response.raise_for_status.return_value = None
    return mock_response

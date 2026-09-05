import asyncio
import httpx
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from lif.datatypes import (
    LIFFragment,
    LIFQuery,
    LIFQueryFilter,
    LIFQueryPersonFilter,
    LIFQueryPlan,
    LIFQueryStatusResponse,
    LIFPersonIdentifier,
    LIFPersonIdentifiers,
    LIFUpdate,
    OrchestratorJobQueryPlanPartResults,
)
from lif.datatypes.core import LIFUpdatePersonPayload
from lif.query_planner_service import core
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


def _make_query():
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


# -------------------------------------------------------------------------
# LIFQueryPlannerConfig timeout
# -------------------------------------------------------------------------
def test_query_planner_config_default_query_timeout_is_300():
    config = core.LIFQueryPlannerConfig(
        lif_cache_url="https://api.example.com",
        lif_orchestrator_url="https://api.example.com",
        information_sources_config=[],
    )
    assert config.query_timeout_seconds == 300


def test_query_planner_config_accepts_explicit_query_timeout():
    config = core.LIFQueryPlannerConfig(
        lif_cache_url="https://api.example.com",
        lif_orchestrator_url="https://api.example.com",
        information_sources_config=[],
        query_timeout_seconds=120,
    )
    assert config.query_timeout_seconds == 120


def test_query_planner_config_rejects_non_positive_query_timeout():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        core.LIFQueryPlannerConfig(
            lif_cache_url="https://api.example.com",
            lif_orchestrator_url="https://api.example.com",
            information_sources_config=[],
            query_timeout_seconds=0,
        )


def test_query_planner_config_default_service_request_timeout_is_10():
    """Short by design: these are fast service-to-service calls, not the orchestration wait."""
    config = core.LIFQueryPlannerConfig(
        lif_cache_url="https://api.example.com",
        lif_orchestrator_url="https://api.example.com",
        information_sources_config=[],
    )
    assert config.service_request_timeout_seconds == 10


def test_query_planner_config_rejects_non_positive_service_request_timeout():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        core.LIFQueryPlannerConfig(
            lif_cache_url="https://api.example.com",
            lif_orchestrator_url="https://api.example.com",
            information_sources_config=[],
            service_request_timeout_seconds=0,
        )


# -------------------------------------------------------------------------
# Internal HTTP clients use the short per-request timeout, not the query budget
# -------------------------------------------------------------------------
@patch("httpx.AsyncClient")
def test_query_lif_cache_uses_configured_timeout(mock_client_cls):
    mock_client = AsyncMock()
    mock_client.post.return_value = _create_mock_post_response(200, [], "https://api.example.com/query")
    mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

    asyncio.run(core.query_lif_cache("https://api.example.com/query", _make_query(), timeout=300))

    mock_client_cls.assert_called_once_with(timeout=300)


@patch("httpx.AsyncClient")
def test_post_orchestrator_job_uses_configured_timeout(mock_client_cls):
    mock_client = AsyncMock()
    mock_client.post.return_value = _create_mock_post_response(200, {"run_id": "123"}, "https://api.example.com/jobs")
    mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

    request = core.OrchestratorJobRequest(lif_query_plan=LIFQueryPlan(root=[]), async_=True)
    asyncio.run(core.post_orchestrator_job("https://api.example.com/jobs", request, timeout=300))

    mock_client_cls.assert_called_once_with(timeout=300)


@patch("httpx.AsyncClient")
def test_run_update_uses_service_request_timeout_not_query_budget(mock_client_cls):
    # Distinct values: asserting 7 rather than 123 is what pins the decoupling.
    config = core.LIFQueryPlannerConfig(
        lif_cache_url="https://api.example.com/cache",
        lif_orchestrator_url="https://api.example.com/orchestrator",
        information_sources_config=[],
        query_timeout_seconds=123,
        service_request_timeout_seconds=7,
    )
    service = core.LIFQueryPlannerService(config=config)

    mock_client = AsyncMock()
    mock_client.post.return_value = _create_mock_post_response(200, {}, "https://api.example.com/cache/update")
    mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

    update = LIFUpdate(
        updatePerson=LIFUpdatePersonPayload(
            filter={"Person": {"Identifier": {"identifier": "12345", "identifierType": "School-assigned number"}}},
            input={"Person": {"Name": "Test"}},
        )
    )
    asyncio.run(service.run_update(update))

    mock_client_cls.assert_called_once_with(timeout=7)


@patch("httpx.AsyncClient")
def test_run_post_orchestration_results_uses_service_request_timeout(mock_client_cls):
    config = core.LIFQueryPlannerConfig(
        lif_cache_url="https://api.example.com/cache",
        lif_orchestrator_url="https://api.example.com/orchestrator",
        information_sources_config=[
            {
                "information_source_id": "source_1",
                "information_source_organization": "Example Org 1",
                "adapter_id": "lif-to-lif",
                "ttl_hours": 24,
                "lif_fragment_paths": ["Person.name"],
            }
        ],
        query_timeout_seconds=123,
        service_request_timeout_seconds=7,
    )
    service = core.LIFQueryPlannerService(config=config)

    mock_client = AsyncMock()
    mock_client.post.return_value = _create_mock_post_response(200, [], "https://api.example.com/cache/save")
    mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

    add_job_to_store(core.LIFQueryPlannerJob(job_id="123", status="PENDING", query=_make_query()))
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
                        "fragment_path": "person.name",
                        "fragment": [
                            {"identifier": [{"identifier": "12345", "identifierType": "School-assigned number"}]}
                        ],
                    }
                ],
                error=None,
            )
        ],
    )
    asyncio.run(service.run_post_orchestration_results(orchestration_results))

    mock_client_cls.assert_called_once_with(timeout=7)

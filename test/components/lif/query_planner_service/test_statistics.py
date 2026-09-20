import json

from lif.datatypes.core import LIFFragment, LIFPersonIdentifier, LIFQueryPlan, LIFQueryPlanPart
from lif.datatypes.orchestration import OrchestratorJobQueryPlanPartResults, OrchestratorJobResults
from lif.query_planner_service import statistics


def _plan() -> LIFQueryPlan:
    return LIFQueryPlan(
        root=[
            LIFQueryPlanPart(
                information_source_id="source_1",
                adapter_id="lif-to-lif",
                person_id=LIFPersonIdentifier(identifier="Sentinel-1234", identifierType="School-assigned number"),
                lif_fragment_paths=["Person.name", "Person.identifier"],
            )
        ]
    )


def _results(error: str | None = None) -> OrchestratorJobResults:
    return OrchestratorJobResults(
        run_id="run-1",
        query_plan_part_results=[
            OrchestratorJobQueryPlanPartResults(
                information_source_id="source_1",
                adapter_id="lif-to-lif",
                data_timestamp="2026-01-01T00:00:00Z",
                person_id=LIFPersonIdentifier(identifier="Sentinel-1234", identifierType="School-assigned number"),
                fragments=[LIFFragment(fragment_path="person.name", fragment=[{"name": [{"familyName": "Canary"}]}])],
                error=error,
            )
        ],
    )


def test_build_query_planned_event_records_the_three_statistics():
    event = statistics.build_query_planned_event(
        statistics.OUTCOME_ORCHESTRATED,
        requested_paths=["person.name", "person.employmentLearningExperience"],
        paths_not_in_cache=["person.employmentLearningExperience"],
        lif_query_plan=_plan(),
        correlation_id="run-1",
    )

    # 1. elements requested
    assert event["requested_paths"] == ["Person.employmentLearningExperience", "Person.name"]
    assert event["requested_path_count"] == 2
    # 2. sources used
    assert event["sources"] == [{"information_source_id": "source_1", "adapter_id": "lif-to-lif", "path_count": 2}]
    # 3. data not found
    assert event["paths_not_in_cache"] == ["Person.employmentLearningExperience"]
    assert event["cache_hit"] is False
    assert event["outcome"] == statistics.OUTCOME_ORCHESTRATED
    assert event["correlation_id"] == "run-1"


def test_build_query_planned_event_marks_a_full_cache_hit():
    event = statistics.build_query_planned_event(
        statistics.OUTCOME_SERVED_FROM_CACHE, requested_paths=["person.name"], paths_not_in_cache=[]
    )

    assert event["cache_hit"] is True
    assert event["sources"] == []
    assert event["correlation_id"] is None


def test_build_query_planned_event_omits_person_data():
    event = statistics.build_query_planned_event(
        statistics.OUTCOME_ORCHESTRATED, ["person.name"], ["person.name"], _plan(), "run-1"
    )

    assert "Sentinel" not in json.dumps(event)


def test_build_query_completed_event_reports_fulfilled_and_missing_paths():
    event = statistics.build_query_completed_event(
        _results(), requested_paths=["person.name", "person.positionPreferences"]
    )

    assert event["fulfilled_paths"] == ["Person.name"]
    assert event["paths_not_fulfilled"] == ["Person.positionPreferences"]
    assert event["correlation_id"] == "run-1"
    assert event["sources"][0]["fragment_count"] == 1
    assert event["sources"][0]["error"] is None


def test_build_query_completed_event_carries_the_source_error():
    event = statistics.build_query_completed_event(_results(error="adapter exploded"), requested_paths=["person.name"])

    assert event["sources"][0]["error"] == "adapter exploded"


def test_build_query_completed_event_omits_person_data():
    event = statistics.build_query_completed_event(_results(), requested_paths=["person.name"])

    payload = json.dumps(event)
    assert "Sentinel" not in payload
    assert "Canary" not in payload


def test_format_event_is_a_marked_parseable_json_line():
    line = statistics.format_event(
        statistics.build_query_planned_event(statistics.OUTCOME_SERVED_FROM_CACHE, ["person.name"], [])
    )

    assert line.startswith(statistics.QUERY_STATISTICS_PREFIX + " ")
    parsed = json.loads(line[len(statistics.QUERY_STATISTICS_PREFIX) + 1 :])
    assert parsed["event"] == "query_planned"


def test_build_query_completed_event_matches_paths_across_the_casing_boundary():
    # Requested paths arrive PascalCase from get_lif_fragment_paths_from_query; the Orchestrator
    # returns fragment paths with the lowercase `person.` prefix. Comparing the two raw reports
    # every path as unfulfilled, which corrupts the "data not found" statistic #341 is for.
    event = statistics.build_query_completed_event(_results(), requested_paths=["Person.name"])

    assert event["fulfilled_paths"] == ["Person.name"]
    assert event["paths_not_fulfilled"] == []

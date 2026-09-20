"""
LIF Query Planner Query Statistics.

Builds the usage-pattern statistics #341 asks for -- which data elements are requested,
which information sources answer them, and how often data is not found -- as structured
events for CloudWatch Logs Insights.

Pure: no I/O, and no person data. `LIFQuery.filter` carries a `LIFPersonIdentifier`, so
these builders take fragment paths and plan/result metadata rather than the query itself.
"""

import json
from typing import Dict, List

from lif.datatypes.core import LIFQueryPlan
from lif.datatypes.orchestration import OrchestratorJobResults
from lif.lif_schema_config import PERSON_DOT, PERSON_DOT_LENGTH, PERSON_DOT_PASCAL

# Log-line marker, so Logs Insights can select these events:
#   filter @message like /LIF_QUERY_STATISTICS/ | parse @message "LIF_QUERY_STATISTICS *" as event
QUERY_STATISTICS_PREFIX: str = "LIF_QUERY_STATISTICS"

# Outcomes of the planning phase. Every query reaches exactly one of them.
OUTCOME_SERVED_FROM_CACHE: str = "served_from_cache"
OUTCOME_NO_SOURCES_AVAILABLE: str = "no_sources_available"
OUTCOME_ORCHESTRATOR_SUBMISSION_FAILED: str = "orchestrator_submission_failed"
OUTCOME_ORCHESTRATED: str = "orchestrated"


def _normalize_path(path: str) -> str:
    """
    Normalize a LIF fragment path to the PascalCase `Person.` prefix.

    Requested paths arrive already normalized from `get_lif_fragment_paths_from_query`, but
    fragment paths coming back from the Orchestrator use the lowercase `person.` prefix. Without
    this the two sets never intersect and every path looks unfulfilled.

    Args:
        path (str): A LIF fragment path in either casing.

    Returns:
        str: The path with a PascalCase `Person.` prefix.
    """
    if path.startswith(PERSON_DOT):
        return PERSON_DOT_PASCAL + path[PERSON_DOT_LENGTH:]
    return path


def build_query_planned_event(
    outcome: str,
    requested_paths: List[str],
    paths_not_in_cache: List[str],
    lif_query_plan: LIFQueryPlan | None = None,
    correlation_id: str | None = None,
) -> Dict:
    """
    Build the statistics event for the planning phase of a query.

    Args:
        outcome (str): One of the OUTCOME_* constants.
        requested_paths (List[str]): LIF fragment paths the query asked for.
        paths_not_in_cache (List[str]): Of those, the ones the cache could not answer.
        lif_query_plan (LIFQueryPlan | None): The plan, when one was built.
        correlation_id (str | None): The orchestrator run id, when one was obtained.

    Returns:
        Dict: The event. Contains no person data.
    """
    parts = lif_query_plan.root if lif_query_plan else []
    return {
        "event": "query_planned",
        "outcome": outcome,
        "correlation_id": correlation_id,
        "requested_paths": sorted(_normalize_path(path) for path in requested_paths),
        "requested_path_count": len(requested_paths),
        "paths_not_in_cache": sorted(_normalize_path(path) for path in paths_not_in_cache),
        "cache_hit": not paths_not_in_cache,
        "sources": [
            {
                "information_source_id": part.information_source_id,
                "adapter_id": part.adapter_id,
                "path_count": len(part.lif_fragment_paths or []),
            }
            for part in parts
        ],
    }


def build_query_completed_event(results: OrchestratorJobResults, requested_paths: List[str]) -> Dict:
    """
    Build the statistics event for the orchestration results of a query.

    Args:
        results (OrchestratorJobResults): The results posted back by the Orchestrator.
        requested_paths (List[str]): LIF fragment paths the original query asked for.

    Returns:
        Dict: The event. Contains no person data -- fragment paths, not fragments.
    """
    fulfilled_paths = {
        _normalize_path(fragment.fragment_path)
        for part_result in results.query_plan_part_results
        for fragment in (part_result.fragments or [])
        if fragment
    }
    normalized_requested = {_normalize_path(path) for path in requested_paths}
    return {
        "event": "query_completed",
        "correlation_id": results.run_id,
        "requested_paths": sorted(normalized_requested),
        "fulfilled_paths": sorted(fulfilled_paths),
        "paths_not_fulfilled": sorted(normalized_requested - fulfilled_paths),
        "sources": [
            {
                "information_source_id": part_result.information_source_id,
                "adapter_id": part_result.adapter_id,
                "fragment_count": len(part_result.fragments or []),
                "error": part_result.error,
            }
            for part_result in results.query_plan_part_results
        ],
    }


def format_event(event: Dict) -> str:
    """
    Render an event as a single log line.

    Args:
        event (Dict): An event from one of the builders above.

    Returns:
        str: The marker followed by the event as compact JSON.
    """
    return f"{QUERY_STATISTICS_PREFIX} {json.dumps(event, sort_keys=True, default=str)}"

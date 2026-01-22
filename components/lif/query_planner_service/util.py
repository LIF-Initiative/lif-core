"""
LIF Query Planner Utility Methods.

This component provides a utility/helper methods used by LIF Query Planner.
"""

from datetime import datetime, timedelta, timezone
from typing import List

from jsonpath_ng import parse

from lif.datatypes.core import LIFFragment, LIFQuery, LIFQueryPlan, LIFQueryPlanPart, LIFPersonIdentifier, LIFRecord
from lif.logging.core import get_logger
from lif.query_planner_service.datatypes import LIFQueryPlannerInfoSourceConfig


logger = get_logger(__name__)

PERSON_DOT: str = "person."
PERSON_DOT_ALL: str = "person.all"
PERSON_DOT_ZERO = "person.0"
PERSON_JSON_PATH_PREFIX: str = "$.person[0]."

PERSON_DOT_LENGTH: int = len(PERSON_DOT)


def _find_key_case_insensitive(d: dict, key: str) -> str | None:
    """Find a key in a dict using case-insensitive matching.

    Returns the actual key from the dict if found, None otherwise.
    This handles the case where translator returns "Person" but we're looking for "person".
    """
    if key in d:
        return key
    key_lower = key.lower()
    for k in d.keys():
        if k.lower() == key_lower:
            return k
    return None


# -------------------------------------------------------------------------
# Helper function to adjust the LIF fragments for the initial orchestrator
# simplification. Initially, fragments will contain a full person.  This
# function creates and returns a new list of fragments that includes a
# fragment for each list field.
# -------------------------------------------------------------------------
def adjust_lif_fragments_for_initial_orchestrator_simplification(
    lif_fragments: List[LIFFragment], desired_fragment_paths: List[str]
) -> List[LIFFragment]:
    """
    Adjust LIF fragments for initial orchestrator simplification (fragments will contain full person).

    Args:
        lif_fragments (List[LIFFragment]): List of LIF fragments to adjust.
        desired_fragment_paths (List[str]): List of desired fragment paths to include.

    Returns:
        List[LIFFragment]: Adjusted list of LIF fragments.
    """
    if len(lif_fragments) == 0:
        logger.warning("No LIF fragments provided for adjustment.")
        return []
    results: List[LIFFragment] = []
    for fragment in lif_fragments:
        if fragment.fragment_path == PERSON_DOT_ALL:
            for path in desired_fragment_paths:
                adjusted_path = PERSON_DOT_ZERO + path[PERSON_DOT_LENGTH - 1 : :]
                keys = adjusted_path.split(".")
                last_key = keys[-1]
                current_field = fragment.fragment[0]
                for key in keys:
                    # Handle case-insensitive lookup for "person"/"Person" root key
                    actual_key = _find_key_case_insensitive(current_field, key) if isinstance(current_field, dict) else key
                    if key == last_key:
                        if actual_key and actual_key in current_field:
                            current_field = current_field[actual_key]
                            new_fragment = LIFFragment(
                                fragment_path=path,
                                fragment=current_field if isinstance(current_field, list) else [current_field],
                            )
                            results.append(new_fragment)
                    elif isinstance(current_field, dict) and actual_key and actual_key in current_field:
                        current_field = current_field[actual_key]
                    elif isinstance(current_field, list) and len(current_field) == 0:
                        logger.info(f"list in lif record is empty for key: {key}")
                        break
                    elif isinstance(current_field, list) and key.isdigit():
                        current_field = current_field[int(key)]
                    else:
                        logger.info(f"key in lif record has unexpected type: {key}")
        else:
            results.append(fragment)
    return results


# -------------------------------------------------------------------------
# Helper function to get the LIF fragment paths from a LIFQuery.
# -------------------------------------------------------------------------
def get_lif_fragment_paths_from_query(query: LIFQuery) -> List[str]:
    """
    Get the LIF fragment paths from a LIFQuery.

    Args:
        query (LIFQuery): The LIF query to extract fragment paths from.

    Returns:
        List[str]: List of LIF fragment paths.
    """
    lif_fragment_paths = []
    for field in query.selected_fields:
        if field.startswith(PERSON_DOT):
            index_of_second_dot: int = field.find(".", PERSON_DOT_LENGTH)
            if index_of_second_dot != -1:
                path: str = field[0:index_of_second_dot]
                if path not in lif_fragment_paths:
                    lif_fragment_paths.append(path)
            else:
                if field not in lif_fragment_paths:
                    lif_fragment_paths.append(field)
    return lif_fragment_paths


# -------------------------------------------------------------------------
# Helper function to return the LIF fragment paths from an input list that are not found in a LIFRecord.
# -------------------------------------------------------------------------
def get_lif_fragment_paths_not_found_in_lif_record(lif_record: LIFRecord, lif_fragment_paths: List[str]) -> List[str]:
    """
    Given the input list of LIF fragment paths, return those not found in the LIFRecord.
    Args:
        lif_record (LIFRecord): The LIF record to check.
        lif_fragment_paths (List[str]): The LIF fragment paths to check for.
    Returns:
        List[str]: List of LIF fragment paths not found in the LIFRecord.
    """
    not_found_paths: List[str] = []

    if not lif_record or not lif_record.person or not lif_record.person.root:
        logger.warning("LIFRecord is empty or does not contain person data.")
        return lif_fragment_paths

    lif_record_dict = lif_record.model_dump()
    for path in lif_fragment_paths:
        if not path.startswith(PERSON_DOT):
            raise ValueError(f"Fragment path '{path}' must start with 'person.'")

        json_path: str = PERSON_JSON_PATH_PREFIX + path[PERSON_DOT_LENGTH:]
        path_expr = parse(json_path)
        matches = path_expr.find(lif_record_dict)
        if not matches and path not in not_found_paths:
            logger.info(f"Path '{path}' not found in LIFRecord.")
            not_found_paths.append(path)
        else:
            matches_str = ", ".join([str(match.value) for match in matches])
            logger.info(f"Matched path '{path}' with values: {matches_str}")

    return not_found_paths


# -------------------------------------------------------------------------
# Helper function to determine if an iso datetime string is older than a given number of hours.
# -------------------------------------------------------------------------
def is_iso_datetime_older_than_x_hours(iso_datetime: str, hours: int) -> bool:
    """
    Check if the given ISO datetime string is older than the specified number of hours.

    Args:
        iso_datetime (str): The ISO datetime string to check.
        hours (int): The number of hours to compare against.

    Returns:
        bool: True if the ISO datetime is older than the specified number of hours, False otherwise.
    """
    try:
        dt = datetime.fromisoformat(iso_datetime.replace("Z", "+00:00"))
        dt = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        x_hours_ago = datetime.now(timezone.utc) - timedelta(hours=hours)
        return dt < x_hours_ago
    except ValueError as e:
        logger.error(f"Invalid ISO datetime format: {iso_datetime}. Error: {e}")
        return False


# -------------------------------------------------------------------------
# Helper function to create the LIFQueryPlan from the information sources config.
# -------------------------------------------------------------------------
def create_lif_query_plan_from_information_sources_config(
    lif_person_id: LIFPersonIdentifier, config: List[LIFQueryPlannerInfoSourceConfig], lif_fragment_paths: List[str]
) -> LIFQueryPlan:
    """
    Create the LIFQueryPlan from the information sources config.

    Args:
        lif_person_id (LIFPersonIdentifier): The LIF person identifier.
        config (List[LIFQueryPlannerInfoSourceConfig): The information sources configuration.
        lif_fragment_paths (List[str]): The LIF fragment paths to include in the query plan.

    Returns:
        LIFQueryPlan: The created LIF query plan.
    """
    if not config:
        raise ValueError("Information sources config is empty or None.")

    lif_query_plan_parts: List[LIFQueryPlanPart] = []
    for info_source in config:
        if set(info_source.lif_fragment_paths) & set(lif_fragment_paths):
            lif_query_plan_parts.append(
                LIFQueryPlanPart(
                    information_source_id=info_source.information_source_id,
                    adapter_id=info_source.adapter_id,
                    person_id=lif_person_id,
                    lif_fragment_paths=list(set(info_source.lif_fragment_paths) & set(lif_fragment_paths)),
                    translation=info_source.translation,
                )
            )
    lif_query_plan: LIFQueryPlan = LIFQueryPlan(root=lif_query_plan_parts)
    return lif_query_plan

"""
LIF Fragment Utility Methods.

This component provides pure, dependency-light helpers for manipulating
LIFFragment lists. It has no I/O and no query-planner-specific business logic,
so it can be depended on by any consumer that only needs fragment shaping
(e.g. the Dagster orchestrator's translation step) without pulling in the
full `query_planner_service` brick.
"""

from typing import List

from lif.datatypes.core import LIFFragment
from lif.lif_schema_config import PERSON_DOT_ALL, PERSON_DOT_ZERO, PERSON_DOT_LENGTH
from lif.logging.core import get_logger

logger = get_logger(__name__)


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
                    actual_key = (
                        _find_key_case_insensitive(current_field, key) if isinstance(current_field, dict) else key
                    )
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

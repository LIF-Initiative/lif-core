"""
LIF Composer

This component provides functionality for composing LIF fragments into an existing LIF record.
"""

import json
from typing import List

from lif.datatypes.core import LIFFragment, LIFRecord
from lif.logging.core import get_logger

logger = get_logger(__name__)


def compose_json_with_single_fragment(lif_record_json: str, lif_fragment: LIFFragment) -> str:
    lif_record_dict = json.loads(lif_record_json)
    add_fragment_to_lif_record(lif_record_dict, lif_fragment.fragment_path, lif_fragment.fragment)
    return json.dumps(lif_record_dict)


def compose_json_with_fragment_list(
    lif_record_json: str, lif_fragments: List[LIFFragment], replace_existing: bool = True
) -> str:
    """Compose a list of fragments into a LIF record.

    Args:
        lif_record_json: The record to compose into, as JSON.
        lif_fragments: The fragments to compose in.
        replace_existing: When True (the default), each list targeted by a fragment is
            emptied once before that fragment's items are added, so the composed record
            reflects the fragments rather than the fragments *plus* whatever was there
            before. Several fragments targeting the same path still accumulate together
            within this one call, which is what multi-source composition needs.

    Why replace is the default (Issue #1165): the only production caller is the query
    cache's `save`, which re-composes fragments freshly fetched from the sources onto the
    record it just loaded from Mongo -- a record that already contains the results of
    every previous refresh. Appending there means every cache refresh re-adds data the
    record already had. On demo this ran until a single learner held 1,272 copies of the
    same Name and one query returned 6.3MB, past the Advisor model's context window.
    Replacing makes a refresh idempotent: composing the same fragments twice gives the
    same record.
    """
    lif_record_dict = json.loads(lif_record_json)
    compose_dict_with_fragment_list(lif_record_dict, lif_fragments, replace_existing=replace_existing)
    return json.dumps(lif_record_dict)


def compose_dict_with_fragment_list(
    lif_record_dict: dict, lif_fragments: List[LIFFragment], replace_existing: bool = True
) -> None:
    """Compose fragments into an already-parsed record dict, in place.

    Shared by the JSON- and record-level entrypoints so they cannot drift apart.
    See compose_json_with_fragment_list for the semantics of replace_existing.
    """
    if replace_existing:
        # Clear each distinct path once, before any items are added, so that two
        # fragments targeting the same path do not clear each other's work.
        for fragment_path in dict.fromkeys(fragment.fragment_path for fragment in lif_fragments):
            clear_fragment_list(lif_record_dict, fragment_path)

    for item in lif_fragments:
        add_fragment_to_lif_record(lif_record_dict, item.fragment_path, item.fragment)


# Both record-level entrypoints below compose on the dict rather than round-tripping through
# JSON (Issue #10). They used to do model_dump_json() -> loads -> mutate -> dumps -> loads:
# four full passes over the record where two will do.
#
# `mode="json"` rather than a plain model_dump() is deliberate. It coerces values to JSON
# primitives exactly as model_dump_json() did, so a record composed here is value-for-value
# what the old path produced -- a plain model_dump() would instead leave a non-JSON value
# (a datetime, say) as a native object, which query_cache_service.save() would then write to
# Mongo as a BSON date where it previously wrote a string. Nothing in the seed data carries
# such a value today, so the distinction is currently theoretical, but keeping the coercion
# means this change cannot alter what is stored.
def compose_with_single_fragment(lif_record: LIFRecord, lif_fragment: LIFFragment) -> LIFRecord:
    lif_record_dict = lif_record.model_dump(mode="json")
    add_fragment_to_lif_record(lif_record_dict, lif_fragment.fragment_path, lif_fragment.fragment)
    return LIFRecord(**lif_record_dict)


def compose_with_fragment_list(
    lif_record: LIFRecord, lif_fragments: List[LIFFragment], replace_existing: bool = True
) -> LIFRecord:
    """Compose fragments into a record. See compose_json_with_fragment_list for semantics."""
    lif_record_dict = lif_record.model_dump(mode="json")
    compose_dict_with_fragment_list(lif_record_dict, lif_fragments, replace_existing=replace_existing)
    return LIFRecord(**lif_record_dict)


def adjust_fragment_path_for_root_person_list(fragment_path: str) -> str:
    """Adjust fragment path to navigate into the person array.

    Handles both lowercase 'person.' and PascalCase 'Person.' prefixes.
    The internal LIF record structure uses lowercase 'person'.
    """
    if fragment_path.startswith("person."):
        return "person.0" + fragment_path[6::]
    elif fragment_path.startswith("Person."):
        # Convert PascalCase to lowercase for internal navigation
        return "person.0" + fragment_path[6:]
    else:
        return fragment_path


def resolve_fragment_target(lif_record_dict: dict, fragment_path: str, create_missing: bool):
    """Walk a fragment path and return (target, dot_map_path).

    `target` is whatever the path resolves to, or None if the path could not be walked.
    When create_missing is True a missing final key is created as an empty list.

    The final segment is identified by position rather than by name, so a path whose
    final segment repeats an earlier one (e.g. "person.0.Name.Name") walks the whole
    path instead of stopping at the first match.
    """
    dot_map_path = adjust_fragment_path_for_root_person_list(fragment_path)
    keys = dot_map_path.split(".")
    last_index = len(keys) - 1
    current_field = lif_record_dict
    for index, key in enumerate(keys):
        if index == last_index:
            if isinstance(current_field, dict) and key in current_field:
                current_field = current_field[key]
            elif isinstance(current_field, dict) and create_missing:
                logger.debug(f"Key '{key}' not found in lif record, creating new list.")
                current_field[key] = []
                current_field = current_field[key]
            else:
                return None, dot_map_path
        elif isinstance(current_field, dict) and key in current_field:
            current_field = current_field[key]
        elif isinstance(current_field, list) and key.isdigit() and int(key) < len(current_field):
            current_field = current_field[int(key)]
        else:
            logger.info(f"key in lif record has unexpected type: {key}")
            return None, dot_map_path
    return current_field, dot_map_path


def clear_fragment_list(lif_record_dict: dict, fragment_path: str):
    """Empty the list at fragment_path, if one is already there.

    A missing path is not an error -- there is simply nothing to replace.
    """
    target, dot_map_path = resolve_fragment_target(lif_record_dict, fragment_path, create_missing=False)
    if isinstance(target, list) and target:
        logger.info(f"Replacing {len(target)} existing item(s) at {dot_map_path}")
        target.clear()


def add_fragment_to_lif_record(lif_record_dict: dict, fragment_path: str, new_items: list):
    target, dot_map_path = resolve_fragment_target(lif_record_dict, fragment_path, create_missing=True)
    if target is None:
        return
    logger.info(f"Adding items to the list at {dot_map_path}")
    if isinstance(target, list):
        add_fragment_items_to_list(target, new_items)
    else:
        logger.error(f"Path in lif record is not a list: {dot_map_path}")
        raise ValueError(f"Path '{dot_map_path}' in lif record is not a list, cannot add items.")


def add_fragment_items_to_list(list_to_update: list, new_items: list):
    if not isinstance(list_to_update, list):
        logger.error(f"Expected a list but got: {type(list_to_update)}")
        raise ValueError("Expected a list to update")
    if not new_items:
        logger.warning("No items to add to the list, skipping")
        return
    for new_item in new_items:
        if isinstance(new_item, dict):
            list_to_update.append(new_item)
        else:
            msg = f"Input should be a valid dictionary: {new_item}"
            logger.error(msg)
            raise ValueError(msg)

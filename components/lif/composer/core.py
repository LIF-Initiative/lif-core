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


def compose_json_with_fragment_list(lif_record_json: str, lif_fragments: List[LIFFragment]) -> str:
    result = lif_record_json
    for item in lif_fragments:
        result = compose_json_with_single_fragment(lif_record_json=result, lif_fragment=item)
    return result


def compose_with_single_fragment(lif_record: LIFRecord, lif_fragment: LIFFragment) -> LIFRecord:
    lif_record_json = lif_record.model_dump_json()
    new_lif_record_json = compose_json_with_single_fragment(lif_record_json, lif_fragment)
    new_lif_record_dict = json.loads(new_lif_record_json)
    return LIFRecord(**new_lif_record_dict)


def compose_with_fragment_list(lif_record: LIFRecord, lif_fragments: List[LIFFragment]) -> LIFRecord:
    lif_record_json = lif_record.model_dump_json()
    new_lif_record_json = compose_json_with_fragment_list(lif_record_json=lif_record_json, lif_fragments=lif_fragments)
    new_lif_record_dict = json.loads(new_lif_record_json)
    return LIFRecord(**new_lif_record_dict)


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


def add_fragment_to_lif_record(lif_record_dict: dict, fragment_path: str, new_items: list):
    dot_map_path = adjust_fragment_path_for_root_person_list(fragment_path)
    keys = dot_map_path.split(".")
    last_key = keys[-1]
    current_field = lif_record_dict
    for key in keys:
        if key == last_key:
            if key in current_field:
                current_field = current_field[key]
            else:
                logger.debug(f"Key '{key}' not found in lif record, creating new list.")
                current_field[key] = []
                current_field = current_field[key]
        elif isinstance(current_field, dict) and key in current_field:
            current_field = current_field[key]
        elif isinstance(current_field, list) and key.isdigit():
            current_field = current_field[int(key)]
        else:
            logger.info(f"key in lif record has unexpected type: {key}")
            return
    logger.info(f"Adding items to the list at {dot_map_path}")
    if isinstance(current_field, list):
        add_fragment_items_to_list(current_field, new_items)
    else:
        logger.error(f"Key in lif record is not a list: {key}")
        raise ValueError(f"Key '{key}' in lif record is not a list, cannot add items.")


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

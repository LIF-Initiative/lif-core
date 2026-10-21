import json
from pathlib import Path

import pytest

from lif.mdr_portability import dump_canonical, parse_crosswalk_file, parse_mapping_group_file, parse_model_file

FIXTURES = Path(__file__).parent / "fixtures"
REFERENCE_FILES = [
    (parse_model_file, "test_reference_source_model_file.json"),
    (parse_model_file, "test_reference_target_model_file.json"),
    (parse_mapping_group_file, "test_reference_mapping_group_file.json"),
    (parse_crosswalk_file, "test_reference_crosswalk_file.json"),
]


def _reversed_lists(node):
    # Reverse every list, at every depth, so nothing is left in canonical order.
    if isinstance(node, dict):
        return {key: _reversed_lists(value) for key, value in node.items()}
    if isinstance(node, list):
        return [_reversed_lists(item) for item in reversed(node)]
    return node


@pytest.mark.parametrize(("parse", "fixture"), REFERENCE_FILES)
def test_reference_files_dump_back_byte_for_byte(parse, fixture):
    # Portability Spec §9. The reference files are canonical, so they come back unchanged.
    data = (FIXTURES / fixture).read_bytes()

    assert dump_canonical(parse(data)) == data


@pytest.mark.parametrize(("parse", "fixture"), REFERENCE_FILES)
def test_list_order_does_not_change_the_bytes(parse, fixture):
    data = (FIXTURES / fixture).read_bytes()
    shuffled = json.dumps(_reversed_lists(json.loads(data))).encode("utf-8")

    assert dump_canonical(parse(shuffled)) == data


def test_lists_are_sorted_by_code_point():
    # "Classifier" < "Entails" < "classifier": upper case sorts before lower case.
    file = parse_model_file((FIXTURES / "test_reference_target_model_file.json").read_bytes())
    file.Associations.reverse()

    written = json.loads(dump_canonical(file))

    assert [
        association["Name"]
        for association in written["Associations"]
        if association["Parent"]["Entity"] == "Competency"
    ] == ["Classifier", "Entails", "classifier", "identifier"]

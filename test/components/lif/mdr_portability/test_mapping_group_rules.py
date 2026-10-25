import json
from pathlib import Path

import pytest

from lif.mdr_portability import MappingGroupFile, PortabilityErrorCode, PortabilityErrorGroup
from lif.mdr_portability.mapping_group_rules import check_mapping_group_file

Code = PortabilityErrorCode
FIXTURE = Path(__file__).parent / "fixtures" / "test_reference_mapping_group_file.json"


def _group(**changes) -> MappingGroupFile:
    data = json.loads(FIXTURE.read_text())
    for index, mapping in changes.get("mappings", {}).items():
        data["Mappings"][index] |= mapping
    data["Mappings"] += changes.get("extra", [])
    return MappingGroupFile.model_validate(data)


def _refusals(file: MappingGroupFile) -> list[tuple[PortabilityErrorCode, str]]:
    with pytest.raises(PortabilityErrorGroup) as exc_info:
        check_mapping_group_file(file)
    return [(error.code, error.element) for error in exc_info.value.exceptions]


def _mapping(target: str, *sources: str) -> dict:
    return {
        "Target": {"Path": target},
        "Sources": [{"Path": source} for source in sources],
        "ExpressionLanguage": "JSONata",
        "Expression": "{}",
        "Name": target,
    }


def test_the_reference_file_passes():
    check_mapping_group_file(_group())


def test_two_mappings_writing_one_target_are_refused_once():
    file = _group(extra=[_mapping("Course,title", "Course,courseTitle")])
    assert _refusals(file) == [(Code.MAPPING_TARGET_SHARED, "Mappings[Course,title]")]


def test_a_source_listed_twice_is_a_duplicate_key():
    file = _group(extra=[_mapping("Course,code", "Course,courseCode", "Course,courseCode")])
    assert _refusals(file) == [(Code.DUPLICATE_KEY, "Mappings[Course,code].Sources[Course,courseCode]")]


def test_path_syntax_is_checked_on_targets_and_sources():
    file = _group(extra=[_mapping("1:Course,title2", "Course")])
    assert _refusals(file) == [
        (Code.ROW_ID_PRESENT, "Mappings[1:Course,title2].Target.Path"),
        (Code.PATH_INVALID, "Mappings[1:Course,title2].Sources[Course].Path"),
    ]


def test_every_rule_is_reported_together():
    file = _group(
        extra=[_mapping("Course,title", "Course,courseTitle"), _mapping("Course,code", "Course,a", "Course,a")]
    )
    assert {code for code, _ in _refusals(file)} == {Code.MAPPING_TARGET_SHARED, Code.DUPLICATE_KEY}

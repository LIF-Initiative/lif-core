import json
from pathlib import Path

import pytest

from lif.mdr_portability import CrosswalkFile, PortabilityErrorCode, PortabilityErrorGroup
from lif.mdr_portability.crosswalk_rules import check_crosswalk_file

Code = PortabilityErrorCode
FIXTURE = Path(__file__).parent / "fixtures" / "test_reference_crosswalk_file.json"


def _crosswalk(*extra: dict) -> CrosswalkFile:
    data = json.loads(FIXTURE.read_text())
    data["Entries"] += extra
    return CrosswalkFile.model_validate(data)


def test_the_reference_file_passes():
    # It maps two sources to one target, which is allowed.
    check_crosswalk_file(_crosswalk())


def test_a_source_mapped_twice_is_refused_once_naming_the_source():
    file = _crosswalk({"Source": "Home", "Target": "Postal"}, {"Source": "Home", "Target": "Residence"})
    with pytest.raises(PortabilityErrorGroup) as exc_info:
        check_crosswalk_file(file)
    assert [(e.code, e.element) for e in exc_info.value.exceptions] == [
        (Code.CROSSWALK_SOURCE_DUPLICATE, "Entries[Home]")
    ]

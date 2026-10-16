import json
from pathlib import Path

import pytest

from lif.mdr_portability import (
    CrosswalkFile,
    MappingGroupFile,
    ModelFile,
    PortabilityErrorCode,
    PortabilityErrorGroup,
    parse_crosswalk_file,
    parse_mapping_group_file,
    parse_model_file,
)

Code = PortabilityErrorCode
FIXTURES = Path(__file__).parent / "fixtures"
MODEL = "test_reference_target_model_file.json"
GROUP = "test_reference_mapping_group_file.json"
CROSSWALK = "test_reference_crosswalk_file.json"
PARSERS = {MODEL: parse_model_file, GROUP: parse_mapping_group_file, CROSSWALK: parse_crosswalk_file}


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def _refusals(fixture: str, data) -> list[tuple[PortabilityErrorCode, str]]:
    text = data if isinstance(data, (str, bytes)) else json.dumps(data)
    with pytest.raises(PortabilityErrorGroup) as exc_info:
        PARSERS[fixture](text)
    return [(error.code, error.element) for error in exc_info.value.exceptions]


def _set(path: list, value):
    def mutate(data: dict) -> dict:
        target = data
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
        return data

    return mutate


def _delete(path: list):
    def mutate(data: dict) -> dict:
        target = data
        for key in path[:-1]:
            target = target[key]
        del target[path[-1]]
        return data

    return mutate


@pytest.mark.parametrize(
    ("parse", "fixture", "file_class"),
    [
        (parse_model_file, "test_reference_source_model_file.json", ModelFile),
        (parse_model_file, MODEL, ModelFile),
        (parse_mapping_group_file, GROUP, MappingGroupFile),
        (parse_crosswalk_file, CROSSWALK, CrosswalkFile),
    ],
)
def test_reference_files_parse(parse, fixture, file_class):
    text = (FIXTURES / fixture).read_text()

    assert isinstance(parse(text), file_class)
    assert isinstance(parse(text.encode("utf-8")), file_class)


@pytest.mark.parametrize(
    ("text", "code", "element"),
    [
        pytest.param("{ not json", Code.FORMAT_UNKNOWN, "", id="not JSON"),
        pytest.param("[]", Code.FORMAT_UNKNOWN, "Format", id="not an object"),
        pytest.param("{}", Code.FORMAT_UNKNOWN, "Format", id="no Format"),
        pytest.param(
            '{"Format": {"Type": "lif-mdr-crosswalk", "Version": 1}}',
            Code.FORMAT_UNKNOWN,
            "Format.Type",
            id="other kind",
        ),
        pytest.param(
            '{"Format": {"Type": "lif-mdr-model", "Version": 2}}',
            Code.FORMAT_VERSION_UNSUPPORTED,
            "Format.Version",
            id="version 2",
        ),
        pytest.param(
            '{"Format": {"Type": "lif-mdr-model", "Version": true}}',
            Code.FORMAT_VERSION_UNSUPPORTED,
            "Format.Version",
            id="version true",
        ),
        pytest.param(
            '{"Format": {"Type": "lif-mdr-model", "Version": 1.0}}',
            Code.FORMAT_VERSION_UNSUPPORTED,
            "Format.Version",
            id="version 1.0",
        ),
        pytest.param(
            '{"Format": {"Type": "lif-mdr-model"}}', Code.FORMAT_VERSION_UNSUPPORTED, "Format.Version", id="no version"
        ),
    ],
)
def test_envelope_is_checked_first(text, code, element):
    # Portability Spec §4.1, §4.2: nothing past the envelope is reported for a file of the wrong format.
    assert _refusals(MODEL, text) == [(code, element)]


@pytest.mark.parametrize(
    ("fixture", "mutate", "code", "element"),
    [
        # Portability Spec §12.3
        (MODEL, _set(["Entities", 0, "Id"], 133), Code.ROW_ID_PRESENT, "Entities[Competency].Id"),
        (
            MODEL,
            _set(["Associations", 0, "Placement"], "Reference"),
            Code.DEPRECATED_FIELD,
            "Associations[Competency, Classifier].Placement",
        ),
        (MODEL, _set(["Details", "Type"], "OrgLIF"), Code.DEPRECATED_FIELD, "Details.Type"),
        (
            GROUP,
            _set(["Details", "ActivationDate"], "2026-10-06T00:00:00Z"),
            Code.FIELD_UNKNOWN,
            "Details.ActivationDate",
        ),
        (
            MODEL,
            _set(["Entities", 0, "CreationDate"], "2026-10-06T00:00:00Z"),
            Code.FIELD_UNKNOWN,
            "Entities[Competency].CreationDate",
        ),
        (MODEL, _set(["Includes"], []), Code.FIELD_UNKNOWN, "Includes"),
        (
            MODEL,
            _set(["Associations", 0, "Child"], {"Model": "State LIF", "Entity": "Competency.Classifier"}),
            Code.FIELD_UNKNOWN,
            "Associations[Competency, Classifier].Child.Model",
        ),
        (
            GROUP,
            _set(["Mappings", 0, "ExpressionLanguage"], "LIF_Pseudo_Code"),
            Code.EXPRESSION_LANGUAGE_NOT_PORTABLE,
            "Mappings[Course,AccreditedBy,name].ExpressionLanguage",
        ),
        # Row IDs and deprecated keys
        (
            MODEL,
            _set(["ValueSets", 0, "Values", 0, "OriginalValueId"], 9),
            Code.ROW_ID_PRESENT,
            "ValueSets[AddressType].Values[Postal].OriginalValueId",
        ),
        (MODEL, _set(["Details", "BaseDataModelId"], 1), Code.ROW_ID_PRESENT, "Details.BaseDataModelId"),
        (MODEL, _set(["Entities", 0, "Array"], "Yes"), Code.DEPRECATED_FIELD, "Entities[Competency].Array"),
        (MODEL, _set(["Format", "ExportedAt"], "2026-10-06T00:00:00Z"), Code.FIELD_UNKNOWN, "Format.ExportedAt"),
        # Model identity, wherever a file holds one
        (MODEL, _set(["Details", "Name"], " "), Code.MODEL_IDENTITY_INCOMPLETE, "Details.Name"),
        (
            MODEL,
            _delete(["Details", "CopiedFrom", "ContributorOrganization"]),
            Code.MODEL_IDENTITY_INCOMPLETE,
            "Details.CopiedFrom.ContributorOrganization",
        ),
        (GROUP, _set(["Details", "Source", "Version"], ""), Code.MODEL_IDENTITY_INCOMPLETE, "Details.Source.Version"),
        (
            CROSSWALK,
            _set(["Details", "Target", "Model", "Name"], None),
            Code.MODEL_IDENTITY_INCOMPLETE,
            "Details.Target.Model.Name",
        ),
        # Fields beside an identity are not part of it
        (MODEL, _set(["Details", "State"], 5), Code.FIELD_INVALID, "Details.State"),
        (GROUP, _set(["Details", "Version"], "v1"), Code.FIELD_INVALID, "Details.Version"),
        (GROUP, _set(["Details", "Name"], " "), Code.FIELD_INVALID, "Details.Name"),
        # Mapping targets (§6.2)
        (GROUP, _delete(["Mappings", 0, "Target"]), Code.MAPPING_TARGET_MISSING, "Mappings[0].Target"),
        (
            GROUP,
            _set(["Mappings", 0, "Target"], [{"Path": "A,b"}, {"Path": "A,c"}]),
            Code.MAPPING_TARGET_MULTIPLE,
            "Mappings[0].Target",
        ),
        # Everything else breaks a field table
        (MODEL, _set(["Entities", 0, "UniqueName"], " "), Code.FIELD_INVALID, "Entities[0].UniqueName"),
        (
            MODEL,
            _delete(["ValueSets", 0, "Values", 0, "ValueName"]),
            Code.FIELD_INVALID,
            "ValueSets[AddressType].Values[0].ValueName",
        ),
        (
            MODEL,
            _set(["Entities", 0, "LevelOfAccess"], "Secret"),
            Code.FIELD_INVALID,
            "Entities[Competency].LevelOfAccess",
        ),
        (MODEL, _set(["Entities", 0, "Queryable"], "Yes"), Code.FIELD_INVALID, "Entities[Competency].Queryable"),
        (
            MODEL,
            _set(["Associations", 0, "Child"], {"Foo": "x"}),
            Code.FIELD_INVALID,
            "Associations[Competency, Classifier].Child",
        ),
        (MODEL, _delete(["Associations"]), Code.FIELD_INVALID, "Associations"),
    ],
)
def test_refusals_are_named(fixture, mutate, code, element):
    assert _refusals(fixture, mutate(_load(fixture))) == [(code, element)]


def test_every_refusal_in_a_file_is_reported_together():
    data = _load(MODEL)
    data["Includes"] = []
    data["Entities"][0]["Id"] = 133
    data["Details"]["Name"] = ""

    assert sorted(_refusals(MODEL, data)) == sorted(
        [
            (Code.FIELD_UNKNOWN, "Includes"),
            (Code.ROW_ID_PRESENT, "Entities[Competency].Id"),
            (Code.MODEL_IDENTITY_INCOMPLETE, "Details.Name"),
        ]
    )

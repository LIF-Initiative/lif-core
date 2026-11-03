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


def _collect_refusals(fixture: str, data) -> list[tuple[PortabilityErrorCode, str]]:
    # data is a dict, text or bytes; the parsers take bytes, so the first two are encoded as UTF-8.
    if isinstance(data, dict):
        data = json.dumps(data)
    content = data.encode("utf-8") if isinstance(data, str) else data
    with pytest.raises(PortabilityErrorGroup) as exc_info:
        PARSERS[fixture](content)
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
    assert isinstance(parse((FIXTURES / fixture).read_bytes()), file_class)


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
    assert _collect_refusals(MODEL, text) == [(code, element)]


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
        (
            MODEL,
            _set(["Attributes", 0, "Array"], "Yes"),
            Code.DEPRECATED_FIELD,
            "Attributes[Competency.Classifier].Array",
        ),
        # Deprecated only on the objects §11 lists them on; elsewhere the same key is just unknown
        (MODEL, _set(["DataModelConstraints"], []), Code.DEPRECATED_FIELD, "DataModelConstraints"),
        (
            MODEL,
            _set(["ValueSets", 0, "Values", 0, "Extension"], True),
            Code.DEPRECATED_FIELD,
            "ValueSets[AddressType].Values[Postal].Extension",
        ),
        (
            GROUP,
            _set(["Mappings", 0, "InputAttributesCount"], 1),
            Code.DEPRECATED_FIELD,
            "Mappings[Course,AccreditedBy,name].InputAttributesCount",
        ),
        (
            GROUP,
            _set(["Mappings", 0, "Target", "Extension"], True),
            Code.DEPRECATED_FIELD,
            "Mappings[Course,AccreditedBy,name].Target.Extension",
        ),
        (MODEL, _set(["Entities", 0, "Type"], "OrgLIF"), Code.FIELD_UNKNOWN, "Entities[Competency].Type"),
        (MODEL, _set(["ValueSets", 0, "Array"], "Yes"), Code.FIELD_UNKNOWN, "ValueSets[AddressType].Array"),
        (
            MODEL,
            _set(["Associations", 0, "Child", "Placement"], "Reference"),
            Code.FIELD_UNKNOWN,
            "Associations[Competency, Classifier].Child.Placement",
        ),
        (GROUP, _set(["Mappings", 0, "Type"], "x"), Code.FIELD_UNKNOWN, "Mappings[Course,AccreditedBy,name].Type"),
        (CROSSWALK, _set(["Entries", 0, "Extension"], True), Code.FIELD_UNKNOWN, "Entries[Home].Extension"),
        (MODEL, _set(["Format", "ExportedAt"], "2026-10-06T00:00:00Z"), Code.FIELD_UNKNOWN, "Format.ExportedAt"),
        # A key named like a union tag is still a key, wherever it is
        (MODEL, _set(["Entities", 0, "EntityKey"], 1), Code.FIELD_UNKNOWN, "Entities[Competency].EntityKey"),
        (
            MODEL,
            _set(["Associations", 0, "Child", "EntityKey"], 1),
            Code.FIELD_UNKNOWN,
            "Associations[Competency, Classifier].Child.EntityKey",
        ),
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
        (
            CROSSWALK,
            _set(["Details", "Source", "Model", "Version"], " "),
            Code.MODEL_IDENTITY_INCOMPLETE,
            "Details.Source.Model.Version",
        ),
        (CROSSWALK, _delete(["Details", "Source", "Model"]), Code.MODEL_IDENTITY_INCOMPLETE, "Details.Source.Model"),
        # Fields beside an identity are not part of it
        (MODEL, _set(["Details", "State"], 5), Code.FIELD_INVALID, "Details.State"),
        (GROUP, _set(["Details", "Version"], "v1"), Code.FIELD_INVALID, "Details.Version"),
        (GROUP, _set(["Details", "Name"], " "), Code.FIELD_INVALID, "Details.Name"),
        # Mapping targets (§6.2)
        (GROUP, _delete(["Mappings", 0, "Target"]), Code.MAPPING_TARGET_MISSING, "Mappings[0].Target"),
        (GROUP, _set(["Mappings", 0, "Target"], None), Code.MAPPING_TARGET_MISSING, "Mappings[0].Target"),
        (GROUP, _set(["Mappings", 0, "Target"], []), Code.MAPPING_TARGET_MISSING, "Mappings[0].Target"),
        (GROUP, _set(["Mappings", 0, "Target"], [{"Path": "A,b"}]), Code.FIELD_INVALID, "Mappings[0].Target"),
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
    assert _collect_refusals(fixture, mutate(_load(fixture))) == [(code, element)]


def test_every_refusal_in_a_file_is_reported_together():
    data = _load(MODEL)
    data["Includes"] = []
    data["Entities"][0]["Id"] = 133
    data["Details"]["Name"] = ""

    assert sorted(_collect_refusals(MODEL, data)) == sorted(
        [
            (Code.FIELD_UNKNOWN, "Includes"),
            (Code.ROW_ID_PRESENT, "Entities[Competency].Id"),
            (Code.MODEL_IDENTITY_INCOMPLETE, "Details.Name"),
        ]
    )


@pytest.mark.parametrize(
    ("old", "new", "element"),
    [
        pytest.param(
            '"UniqueName": "Competency",',
            '"UniqueName": "SomethingElse", "UniqueName": "Competency",',
            "UniqueName",
            id="in a list item",
        ),
        pytest.param('"ValueSets": [', '"Entities": [], "ValueSets": [', "Entities", id="at the top level"),
        pytest.param('"Version": 1\n', '"Version": 1, "Version": 1\n', "Version", id="same value twice"),
    ],
)
def test_a_repeated_key_is_refused(old, new, element):
    # Portability Spec §4.2. json.loads would keep the last value without saying so. The error names
    # the key only: where the object is in the file is not known while it is being read.
    text = (FIXTURES / MODEL).read_text()
    assert text.count(old) >= 1

    assert _collect_refusals(MODEL, text.replace(old, new, 1)) == [(Code.FIELD_INVALID, element)]


def test_a_leading_byte_order_mark_is_accepted():
    # Portability Spec §9. A UTF-8 byte order mark carries no content.
    content = (FIXTURES / MODEL).read_bytes()

    assert parse_model_file(b"\xef\xbb\xbf" + content) == parse_model_file(content)


@pytest.mark.parametrize(
    "value",
    [
        pytest.param("9" * 4301, id="an integer longer than Python converts"),
        pytest.param("[" * 10_000 + "]" * 10_000, id="nesting deeper than Python reads"),
    ],
)
def test_json_python_cannot_read_is_refused(value):
    # Both are refused like any other unreadable file, so a caller only ever catches PortabilityErrorGroup.
    original = (FIXTURES / MODEL).read_text()
    text = original.replace('"Name": "Competency"', f'"Name": "Competency", "Notes": {value}', 1)
    assert text != original

    assert _collect_refusals(MODEL, text) == [(Code.FORMAT_UNKNOWN, "")]


@pytest.mark.parametrize(
    "encode",
    [
        pytest.param(lambda text: text.encode("utf-16"), id="UTF-16"),
        pytest.param(lambda text: text.encode("utf-32"), id="UTF-32"),
        pytest.param(lambda text: text.encode("utf-8") + b"\xff", id="not valid UTF-8"),
    ],
)
def test_bytes_that_are_not_utf8_are_refused(encode):
    # Portability Spec §9: files are UTF-8, whichever encoding a JSON reader could guess.
    assert _collect_refusals(MODEL, encode((FIXTURES / MODEL).read_text())) == [(Code.FORMAT_UNKNOWN, "")]


@pytest.mark.parametrize(
    ("escape", "refused"),
    [
        pytest.param(r"\ud800", True, id="lone high surrogate"),
        pytest.param(r"\udc00", True, id="lone low surrogate"),
        pytest.param(r"😀", False, id="a surrogate pair is one character"),
    ],
)
def test_text_utf8_cannot_encode_is_refused(escape, refused):
    # Portability Spec §9. A lone surrogate can be read but never written back out as UTF-8.
    original = (FIXTURES / MODEL).read_text()
    text = original.replace('"Name": "Competency"', f'"Name": "Competency", "Notes": "a{escape}b"', 1)
    assert text != original

    if refused:
        assert _collect_refusals(MODEL, text) == [(Code.FIELD_INVALID, "")]
    else:
        assert parse_model_file(text.encode("utf-8")).Entities[0].Notes == "a\N{GRINNING FACE}b"


def test_a_lone_surrogate_in_a_key_is_refused():
    original = (FIXTURES / MODEL).read_text()
    text = original.replace('"Name": "Competency"', r'"Name": "Competency", "\ud800": 1', 1)

    assert _collect_refusals(MODEL, text) == [(Code.FIELD_INVALID, "")]


@pytest.mark.parametrize(
    "value",
    [
        pytest.param(1700000000, id="Unix time"),
        pytest.param("1700000000", id="Unix time as text"),
        pytest.param("2026-02-11T10:04:02.1234567Z", id="seven fractional digits"),
        pytest.param("2026-02-11 10:04:02Z", id="space for T"),
        pytest.param("2026-02-11T10:04Z", id="no seconds"),
        pytest.param("2026-02-11", id="date only"),
        pytest.param("2026-02-11T10:04:02", id="no time zone"),
    ],
)
def test_a_timestamp_that_is_not_rfc_3339_is_refused(value):
    # Portability Spec §9: RFC 3339, up to microseconds. Nothing is guessed or cut short.
    data = _load(MODEL)
    data["Entities"][0]["ActivationDate"] = value

    assert _collect_refusals(MODEL, data) == [(Code.FIELD_INVALID, "Entities[Competency].ActivationDate")]


def test_items_that_share_a_key_are_named_by_index():
    # Two entities with the same UniqueName (refused later as DUPLICATE_KEY) cannot be told apart by
    # their key, so each is named by its position.
    data = _load(MODEL)
    data["Entities"][1]["UniqueName"] = data["Entities"][0]["UniqueName"]
    data["Entities"][0]["LevelOfAccess"] = "Secret"
    data["Entities"][1]["LevelOfAccess"] = "Secret"

    assert _collect_refusals(MODEL, data) == [
        (Code.FIELD_INVALID, "Entities[0].LevelOfAccess"),
        (Code.FIELD_INVALID, "Entities[1].LevelOfAccess"),
    ]


def test_a_key_with_brackets_is_named_by_index():
    data = _load(MODEL)
    data["Entities"][0]["UniqueName"] = "a]b"
    data["Entities"][0]["LevelOfAccess"] = "Secret"

    assert _collect_refusals(MODEL, data) == [(Code.FIELD_INVALID, "Entities[0].LevelOfAccess")]

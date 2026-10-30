import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from lif.mdr_portability import CrosswalkFile, MappingGroupFile, ModelFile
from lif.mdr_portability.v1.models import CrosswalkEntry, ModelIdentity

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def test_reference_files_form_one_consistent_set():
    # The mapping group and crosswalk name the two reference models, and the crosswalk's values exist in them.
    source = ModelFile.model_validate(_load("test_reference_source_model_file.json"))
    target = ModelFile.model_validate(_load("test_reference_target_model_file.json"))
    group = MappingGroupFile.model_validate(_load("test_reference_mapping_group_file.json"))
    crosswalk = CrosswalkFile.model_validate(_load("test_reference_crosswalk_file.json"))

    def identity(model: ModelFile) -> ModelIdentity:
        return ModelIdentity(
            Name=model.Details.Name,
            Version=model.Details.Version,
            ContributorOrganization=model.Details.ContributorOrganization,
        )

    def value_names(model: ModelFile, value_set: str) -> set[str]:
        return {value.ValueName for each in model.ValueSets if each.Name == value_set for value in each.Values}

    assert (group.Details.Source, group.Details.Target) == (identity(source), identity(target))
    assert (crosswalk.Details.Source.Model, crosswalk.Details.Target.Model) == (identity(source), identity(target))
    assert {entry.Source for entry in crosswalk.Entries} <= value_names(source, crosswalk.Details.Source.ValueSet)
    assert {entry.Target for entry in crosswalk.Entries} <= value_names(target, crosswalk.Details.Target.ValueSet)


def test_reference_false_imports_but_is_not_written():
    data = _load("test_reference_target_model_file.json")
    data["Associations"][0]["Reference"] = False

    association = ModelFile.model_validate(data).Associations[0]

    assert "Reference" not in association.model_dump(exclude_defaults=True)


def test_association_child_resolves_to_the_kind_it_names():
    # Competency has an entity and an attribute that share the UniqueName "Competency.Classifier".
    file = ModelFile.model_validate(_load("test_reference_target_model_file.json"))

    assert {
        association.Name: type(association.Child).__name__
        for association in file.Associations
        if association.Parent.Entity == "Competency"
    } == {"Classifier": "EntityKey", "Entails": "EntityKey", "classifier": "AttributeKey", "identifier": "AttributeKey"}


@pytest.mark.parametrize(
    ("given", "written"),
    [
        ("2026-02-11T00:00:00Z", "2026-02-11T00:00:00Z"),
        ("2026-02-11T10:04:02.843Z", "2026-02-11T10:04:02.843Z"),
        ("2026-02-11T10:04:02.000001Z", "2026-02-11T10:04:02.000001Z"),
        ("2026-02-11T10:04:02.500000Z", "2026-02-11T10:04:02.5Z"),
        ("2026-02-11T12:04:02+02:00", "2026-02-11T10:04:02Z"),
    ],
)
def test_timestamps_are_written_in_utc_with_trimmed_fractional_seconds(given, written):
    # Portability Spec §9.
    entry = CrosswalkEntry.model_validate({"Source": "F", "Target": "Female", "ActivationDate": given})

    assert entry.model_dump(mode="json")["ActivationDate"] == written


# Shape-level refusals from Portability Spec §12.3 and the field tables. Mapping them to named codes is the converter's job.


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
    ("mutate", "error_type"),
    [
        pytest.param(_set(["Includes"], []), "extra_forbidden", id="unknown top-level key"),
        pytest.param(_set(["Format", "ExportedAt"], "2026-10-06T00:00:00Z"), "extra_forbidden", id="extra Format key"),
        pytest.param(_set(["Format", "Version"], 2), "literal_error", id="format version 2"),
        pytest.param(_set(["Format", "Version"], True), "value_error", id="format version true"),
        pytest.param(_set(["Format", "Version"], 1.0), "value_error", id="format version 1.0"),
        pytest.param(_set(["Format", "Type"], "lif-mdr-crosswalk"), "literal_error", id="wrong format type"),
        pytest.param(_set(["Entities", 0, "Id"], 133), "extra_forbidden", id="row id"),
        pytest.param(_set(["Details", "Type"], "OrgLIF"), "extra_forbidden", id="deprecated model type"),
        pytest.param(_set(["Associations", 0, "Placement"], "Reference"), "extra_forbidden", id="deprecated placement"),
        pytest.param(
            _set(["Associations", 0, "Parent"], {"Model": "State LIF", "Entity": "Student"}),
            "extra_forbidden",
            id="model-qualified reference",
        ),
        pytest.param(_set(["Details", "ContributorOrganization"], ""), "value_error", id="empty identity"),
        pytest.param(_set(["Details", "Name"], " "), "value_error", id="blank identity"),
        pytest.param(_set(["Details", "CopiedFrom", "Version"], " "), "value_error", id="blank lineage identity"),
        pytest.param(_set(["Entities", 0, "UniqueName"], ""), "value_error", id="empty entity key"),
        pytest.param(_set(["Entities", 0, "Name"], " "), "value_error", id="blank entity name"),
        pytest.param(_set(["Attributes", 0, "UniqueName"], " "), "value_error", id="blank attribute key"),
        pytest.param(_set(["ValueSets", 0, "Name"], ""), "value_error", id="empty value set key"),
        pytest.param(_set(["ValueSets", 0, "Values", 0, "ValueName"], " "), "value_error", id="blank value key"),
        pytest.param(_set(["Associations", 0, "Name"], ""), "value_error", id="empty association name"),
        pytest.param(_set(["Details", "ContributorOrganization"], None), "string_type", id="null identity"),
        pytest.param(_delete(["ValueSets", 0, "Values", 0, "ValueName"]), "missing", id="value without ValueName"),
        pytest.param(_delete(["Entities", 0, "Queryable"]), "missing", id="missing flag"),
        pytest.param(_set(["Entities", 0, "Required"], "Yes"), "bool_type", id="free-text Required"),
        pytest.param(_set(["Entities", 0, "LevelOfAccess"], "Secret"), "enum", id="unknown LevelOfAccess"),
        pytest.param(_set(["Details", "State"], "Final"), "enum", id="unknown State"),
        pytest.param(
            _set(["Entities", 0, "ActivationDate"], "2026-10-06T00:00:00"), "value_error", id="naive timestamp"
        ),
        pytest.param(
            _set(["Entities", 0, "CreationDate"], "2026-10-06T00:00:00Z"), "extra_forbidden", id="creation date"
        ),
        pytest.param(_delete(["Associations"]), "missing", id="missing top-level list"),
    ],
)
def test_model_file_shape_refusals(mutate, error_type):
    data = mutate(_load("test_reference_target_model_file.json"))

    with pytest.raises(ValidationError) as exc_info:
        ModelFile.model_validate(data)

    assert error_type in {error["type"] for error in exc_info.value.errors()}


@pytest.mark.parametrize(
    ("mutate", "error_type"),
    [
        pytest.param(_set(["Details", "ActivationDate"], "2026-10-06T00:00:00Z"), "extra_forbidden", id="activation"),
        pytest.param(_set(["Details", "DeprecationDate"], "2026-10-06T00:00:00Z"), "extra_forbidden", id="deprecation"),
        pytest.param(_set(["Details", "Version"], "v1"), "value_error", id="non-numeric version"),
        pytest.param(_set(["Details", "Name"], "  "), "value_error", id="blank name"),
        pytest.param(
            _set(["Mappings", 0, "ExpressionLanguage"], "LIF_Pseudo_Code"), "literal_error", id="non-JSONata rule"
        ),
        pytest.param(_delete(["Mappings", 0, "Target"]), "missing", id="mapping without target"),
        pytest.param(
            _set(["Mappings", 0, "Target"], [{"Path": "A,b"}, {"Path": "A,c"}]), "model_type", id="several targets"
        ),
    ],
)
def test_mapping_group_file_shape_refusals(mutate, error_type):
    data = mutate(_load("test_reference_mapping_group_file.json"))

    with pytest.raises(ValidationError) as exc_info:
        MappingGroupFile.model_validate(data)

    assert error_type in {error["type"] for error in exc_info.value.errors()}


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(_set(["Details", "Source", "ValueSet"], " "), id="blank value set key"),
        pytest.param(_set(["Entries", 0, "Source"], ""), id="empty source value"),
        pytest.param(_set(["Entries", 0, "Target"], "  "), id="blank target value"),
    ],
)
def test_crosswalk_file_refuses_blank_keys(mutate):
    # Export refuses a blank stored Name or ValueName, so import must refuse it in a file (#1426).
    data = mutate(_load("test_reference_crosswalk_file.json"))

    with pytest.raises(ValidationError) as exc_info:
        CrosswalkFile.model_validate(data)

    assert "value_error" in {error["type"] for error in exc_info.value.errors()}


def test_crosswalk_value_set_reference_requires_full_model_identity():
    data = _load("test_reference_crosswalk_file.json")
    del data["Details"]["Source"]["Model"]["Version"]

    with pytest.raises(ValidationError) as exc_info:
        CrosswalkFile.model_validate(data)

    assert exc_info.value.errors()[0]["loc"] == ("Details", "Source", "Model", "Version")


@pytest.mark.parametrize(
    "value",
    ["2026-02-11T10:04:02.123456Z", "2026-02-11t10:04:02z", "2026-02-11T12:04:02+02:00"],
    ids=["six fractional digits", "lower-case t and z", "offset"],
)
def test_rfc_3339_timestamps_are_read(value):
    entry = CrosswalkEntry.model_validate({"Source": "F", "Target": "Female", "ActivationDate": value})

    assert entry.ActivationDate is not None


def test_a_timestamp_from_a_stored_row_is_accepted():
    # Export builds the models from rows, whose timestamps are datetimes rather than text.
    stored = datetime(2026, 2, 11, 10, 4, 2, tzinfo=timezone.utc)

    assert CrosswalkEntry(Source="F", Target="Female", ActivationDate=stored).ActivationDate == stored

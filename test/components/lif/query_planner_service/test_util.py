from datetime import datetime, timedelta, timezone
import json
import logging

from lif.datatypes.core import (
    LIFFragment,
    LIFPersonIdentifier,
    LIFQuery,
    LIFQueryFilter,
    LIFQueryPersonFilter,
    LIFQueryPlan,
    LIFQueryPlanPart,
    LIFPersonIdentifiers,
    LIFRecord,
)
from lif.datatypes.orchestration import OrchestratorJobQueryPlanPartResults, OrchestratorJobResults
from lif.query_planner_service import util


person_alan_json = """{
    "person": [
        {
            "name": [
                {
                  "lastName": "Doe",
                  "firstName": "John"
                }
            ],
            "identifier": [
                {
                    "identifier": "12345",
                    "identifier_type": "School-assigned number"
                }
            ],
            "employmentLearningExperience": [
                {
                    "name": "Compliance Manager",
                    "position": [
                        {
                            "description": "Oversee the compliance department to ensure adherence to industry regulations and company policies."
                        }
                    ],
                    "startDate": "2007-06"
                }
            ],
            "positionPreferences": [
                {
                    "travel": [
                        {
                            "percentage": 25.0,
                            "willingToTravelIndicator": true
                        }
                    ]
                }
            ]
        }
    ]
}"""
person_alan_dict = json.loads(person_alan_json)


def test_sample():
    assert util is not None


def test_get_lif_fragment_paths_from_query():
    person_identifier: LIFPersonIdentifier = LIFPersonIdentifier(
        identifier="100001", identifierType="School-assigned number"
    )
    person_filter_identifier: LIFPersonIdentifiers = LIFPersonIdentifiers(Identifier=person_identifier)
    person_filter = LIFQueryPersonFilter(person=person_filter_identifier)
    query_filter = LIFQueryFilter(root=person_filter)
    query = LIFQuery(
        filter=query_filter,
        selected_fields=[
            "person.name",
            "person.employmentLearningExperience",
            "person.positionPreferences",
            "person.identifier.identifierType",
            "person.credentialAward.awardStatus",
            "person.credentialAward.instanceOfCredential.name",
            "person.credentialAward.instanceOfCredential.issuerOrganization.description",
            "person.credentialAward.instanceOfCredential.alignedProgram.specialization",
        ],
    )

    fragment_paths = util.get_lif_fragment_paths_from_query(query)
    assert len(fragment_paths) == 5
    # Paths are normalized to PascalCase 'Person.' prefix for consistency with schema
    assert fragment_paths == [
        "Person.name",
        "Person.employmentLearningExperience",
        "Person.positionPreferences",
        "Person.identifier",
        "Person.credentialAward",
    ]


def test_get_lif_fragment_paths_from_query_with_pascal_case_input():
    """Test that PascalCase inputs are also handled correctly."""
    person_identifier: LIFPersonIdentifier = LIFPersonIdentifier(
        identifier="100001", identifierType="School-assigned number"
    )
    person_filter_identifier: LIFPersonIdentifiers = LIFPersonIdentifiers(Identifier=person_identifier)
    person_filter = LIFQueryPersonFilter(person=person_filter_identifier)
    query_filter = LIFQueryFilter(root=person_filter)
    query = LIFQuery(
        filter=query_filter,
        selected_fields=["Person.Name", "Person.CredentialAward", "Person.CourseLearningExperience"],
    )

    fragment_paths = util.get_lif_fragment_paths_from_query(query)
    assert len(fragment_paths) == 3
    assert fragment_paths == ["Person.Name", "Person.CredentialAward", "Person.CourseLearningExperience"]


def test_get_lif_fragment_paths_not_found_in_lif_record():
    lif_record: LIFRecord = LIFRecord(**person_alan_dict)
    lif_fragment_paths = [
        "person.name",
        "person.employmentLearningExperience",
        "person.positionPreferences",
        "person.identifier",
        "person.credentialAward",
    ]

    missing_paths = util.get_lif_fragment_paths_not_found_in_lif_record(lif_record, lif_fragment_paths)
    assert len(missing_paths) == 1
    assert missing_paths[0] == "person.credentialAward"


def test_get_lif_fragment_paths_not_found_when_all_fragments_found():
    lif_record: LIFRecord = LIFRecord(**person_alan_dict)
    lif_fragment_paths = [
        "person.name",
        "person.employmentLearningExperience",
        "person.positionPreferences",
        "person.identifier",
    ]

    missing_paths = util.get_lif_fragment_paths_not_found_in_lif_record(lif_record, lif_fragment_paths)
    assert len(missing_paths) == 0


def test_is_iso_datetime_older_than_x_hours():
    # Test with a date older than 2 hours
    old_date = datetime.now(timezone.utc) - timedelta(hours=3)
    assert util.is_iso_datetime_older_than_x_hours(old_date.isoformat(), 2) is True

    # Test with a date within the last 2 hours
    recent_date = datetime.now(timezone.utc) - timedelta(hours=1)
    assert util.is_iso_datetime_older_than_x_hours(recent_date.isoformat(), 2) is False

    # Test with the current time
    current_date = datetime.now(timezone.utc)
    assert util.is_iso_datetime_older_than_x_hours(current_date.isoformat(), 2) is False


def test_is_iso_datetime_older_than_x_hours_with_non_localized_datetime():
    old_date: datetime = datetime.now() - timedelta(hours=3)
    assert util.is_iso_datetime_older_than_x_hours(old_date.isoformat(), 2) is True


# -------------------------------------------------------------------------
# #1269 — person data must never reach the logs.
# -------------------------------------------------------------------------
_SENTINEL_RECORD = {
    "person": [
        {
            "identifier": [{"identifier": "Sentinel-1234", "identifierType": "School-assigned number"}],
            "name": [{"givenName": ["Bellwether"], "familyName": "Canary"}],
        }
    ]
}


def test_get_lif_fragment_paths_not_found_in_lif_record_does_not_log_field_values(caplog):
    lif_record = LIFRecord.model_validate(_SENTINEL_RECORD)

    with caplog.at_level(logging.DEBUG):
        util.get_lif_fragment_paths_not_found_in_lif_record(lif_record, ["person.name"])

    assert "Canary" not in caplog.text
    assert "Bellwether" not in caplog.text
    # The diagnostic value of the line is preserved: which path, and whether it matched.
    assert "person.name" in caplog.text


def test_summarize_query_plan_omits_person_identifier():
    plan = LIFQueryPlan(
        root=[
            LIFQueryPlanPart(
                information_source_id="source_1",
                adapter_id="lif-to-lif",
                person_id=LIFPersonIdentifier(identifier="Sentinel-1234", identifierType="School-assigned number"),
                lif_fragment_paths=["Person.name"],
            )
        ]
    )

    summary = util.summarize_query_plan(plan)

    assert "Sentinel" not in summary
    assert "source_1" in summary
    assert "lif-to-lif" in summary


def test_summarize_orchestration_results_omits_person_data():
    results = OrchestratorJobResults(
        run_id="run-1",
        query_plan_part_results=[
            OrchestratorJobQueryPlanPartResults(
                information_source_id="source_1",
                adapter_id="lif-to-lif",
                data_timestamp="2026-01-01T00:00:00Z",
                person_id=LIFPersonIdentifier(identifier="Sentinel-1234", identifierType="School-assigned number"),
                fragments=[LIFFragment(fragment_path="person.name", fragment=[{"name": [{"familyName": "Canary"}]}])],
                error=None,
            )
        ],
    )

    summary = util.summarize_orchestration_results(results)

    assert "Sentinel" not in summary
    assert "Canary" not in summary
    assert "source_1" in summary

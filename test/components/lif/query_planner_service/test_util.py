from datetime import datetime, timedelta, timezone
import json

from lif.datatypes.core import (
    LIFFragment,
    LIFPersonIdentifier,
    LIFQuery,
    LIFQueryFilter,
    LIFQueryPersonFilter,
    LIFPersonIdentifiers,
    LIFRecord,
)
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


def test_adjust_lif_fragments_for_initial_orchestrator_simplification():
    lif_fragments = [
        LIFFragment(fragment_path="person.all", fragment=[person_alan_dict]),
        LIFFragment(fragment_path="person.address", fragment=[{"city": "Seattle", "state": "WA"}]),
    ]
    desired_fragment_paths = ["person.employmentLearningExperience", "person.positionPreferences"]

    adjusted_fragments = util.adjust_lif_fragments_for_initial_orchestrator_simplification(
        lif_fragments, desired_fragment_paths
    )

    assert len(adjusted_fragments) == 3
    assert adjusted_fragments[0].fragment_path == "person.employmentLearningExperience"
    assert adjusted_fragments[0].fragment == person_alan_dict["person"][0]["employmentLearningExperience"]
    assert adjusted_fragments[1].fragment_path == "person.positionPreferences"
    assert adjusted_fragments[1].fragment == person_alan_dict["person"][0]["positionPreferences"]
    assert adjusted_fragments[2].fragment_path == "person.address"


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
        selected_fields=[
            "Person.Name",
            "Person.CredentialAward",
            "Person.CourseLearningExperience",
        ],
    )

    fragment_paths = util.get_lif_fragment_paths_from_query(query)
    assert len(fragment_paths) == 3
    assert fragment_paths == [
        "Person.Name",
        "Person.CredentialAward",
        "Person.CourseLearningExperience",
    ]


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

"""Integration tests for MongoDB layer.

Verifies that the sample data was correctly seeded into MongoDB
and matches the source JSON files.
"""

import pytest
from typing import Any

from utils.ports import OrgPorts
from utils.sample_data import SampleDataLoader, PersonData
from utils.comparison import compare_person_data, summarize_results, ComparisonResult


# Keys to ignore when comparing MongoDB data to sample files
# MongoDB adds _id, and there may be other internal fields
# Interactions are captured by the advisor app and are expected to be present
IGNORE_KEYS = {"_id", "Interactions"}


@pytest.mark.layer("mongodb")
class TestMongoDBDataIntegrity:
    """Tests for MongoDB data integrity."""

    def test_mongodb_has_expected_person_count(
        self,
        org_id: str,
        org_ports: OrgPorts,
        sample_data: SampleDataLoader,
        require_mongodb: None,
    ) -> None:
        """Verify MongoDB has at least the expected number of person documents.

        MongoDB may contain additional person records from data aggregation across
        organizations. This test verifies that at minimum, the expected persons
        from sample data are present (actual >= expected).
        """
        from pymongo import MongoClient

        expected_count = len(sample_data.persons)

        with MongoClient(org_ports.mongodb_uri) as client:
            db = client["LIF"]
            collection = db["person"]
            actual_count = collection.count_documents({})

        assert actual_count >= expected_count, (
            f"{org_id}: Expected at least {expected_count} persons in MongoDB, "
            f"found {actual_count}"
        )

    def test_all_persons_exist_in_mongodb(
        self,
        org_id: str,
        org_ports: OrgPorts,
        sample_data: SampleDataLoader,
        require_mongodb: None,
    ) -> None:
        """Verify all expected persons exist in MongoDB."""
        from pymongo import MongoClient

        missing_persons = []

        with MongoClient(org_ports.mongodb_uri) as client:
            db = client["LIF"]
            collection = db["person"]

            for person_data in sample_data.persons:
                school_num = person_data.school_assigned_number
                if not school_num:
                    continue

                # Query by school assigned number within nested Identifier array
                query = {
                    "Person.Identifier": {
                        "$elemMatch": {
                            "identifierType": "SCHOOL_ASSIGNED_NUMBER",
                            "identifier": school_num,
                        }
                    }
                }
                doc = collection.find_one(query)

                if not doc:
                    missing_persons.append(
                        f"{person_data.full_name} (ID: {school_num})"
                    )

        assert not missing_persons, (
            f"{org_id}: Missing persons in MongoDB:\n"
            + "\n".join(f"  - {p}" for p in missing_persons)
        )

    def test_person_data_matches_sample_files(
        self,
        org_id: str,
        org_ports: OrgPorts,
        sample_data: SampleDataLoader,
        require_mongodb: None,
    ) -> None:
        """Verify MongoDB person data contains all expected data from sample files.

        MongoDB may contain additional data from aggregation across organizations.
        This test verifies that all expected data from sample files is present,
        but allows for extra data from other sources (allow_extra=True).
        """
        from pymongo import MongoClient

        results: list[ComparisonResult] = []

        with MongoClient(org_ports.mongodb_uri) as client:
            db = client["LIF"]
            collection = db["person"]

            for person_data in sample_data.persons:
                school_num = person_data.school_assigned_number
                if not school_num:
                    continue

                # Find the document in MongoDB
                query = {
                    "Person.Identifier": {
                        "$elemMatch": {
                            "identifierType": "SCHOOL_ASSIGNED_NUMBER",
                            "identifier": school_num,
                        }
                    }
                }
                doc = collection.find_one(query)

                if doc:
                    # Remove MongoDB's _id for comparison
                    doc_copy = {k: v for k, v in doc.items() if k not in IGNORE_KEYS}

                    result = compare_person_data(
                        expected=person_data.raw_data,
                        actual=doc_copy,
                        person_name=person_data.full_name,
                        org_id=org_id,
                        layer="mongodb",
                        ignore_keys=IGNORE_KEYS,
                        allow_extra=True,  # Allow extra data from aggregation
                    )
                    results.append(result)
                else:
                    # Create a failure result for missing person
                    from utils.comparison import ComparisonResult, Difference
                    results.append(
                        ComparisonResult(
                            person_name=person_data.full_name,
                            org_id=org_id,
                            layer="mongodb",
                            differences=[
                                Difference(
                                    path="",
                                    expected=f"Person with ID {school_num}",
                                    actual=None,
                                    diff_type="missing",
                                )
                            ],
                        )
                    )

        # Check results
        failed = [r for r in results if not r.passed]
        if failed:
            report = summarize_results(results)
            pytest.fail(f"{org_id} MongoDB data validation failed:\n{report}")

    def test_mongodb_indexes_exist(
        self,
        org_id: str,
        org_ports: OrgPorts,
        require_mongodb: None,
    ) -> None:
        """Verify expected indexes exist in MongoDB."""
        from pymongo import MongoClient

        with MongoClient(org_ports.mongodb_uri) as client:
            db = client["LIF"]
            collection = db["person"]
            indexes = collection.index_information()

        # At minimum, we expect _id index
        assert "_id_" in indexes, f"{org_id}: Missing _id index in MongoDB"

    def test_entity_counts_per_person(
        self,
        org_id: str,
        org_ports: OrgPorts,
        sample_data: SampleDataLoader,
        require_mongodb: None,
    ) -> None:
        """Verify entity counts (credentials, courses, etc.) are at least what sample data expects.

        MongoDB may contain aggregated data from multiple organizations, so actual counts
        may be higher than the sample data for a single org. This test verifies that at
        minimum, the expected data is present (actual >= expected).
        """
        from pymongo import MongoClient

        missing_data = []
        entity_types = [
            "CredentialAward",
            "CourseLearningExperience",
            "EmploymentLearningExperience",
            "Proficiency",
        ]

        with MongoClient(org_ports.mongodb_uri) as client:
            db = client["LIF"]
            collection = db["person"]

            for person_data in sample_data.persons:
                school_num = person_data.school_assigned_number
                if not school_num:
                    continue

                query = {
                    "Person.Identifier": {
                        "$elemMatch": {
                            "identifierType": "SCHOOL_ASSIGNED_NUMBER",
                            "identifier": school_num,
                        }
                    }
                }
                doc = collection.find_one(query)

                if not doc:
                    continue

                # Get the Person record from MongoDB
                mongo_person = doc.get("Person", [{}])[0] if doc.get("Person") else {}

                for entity_type in entity_types:
                    expected_count = person_data.get_entity_count(entity_type)
                    actual_count = len(mongo_person.get(entity_type, []))

                    # Only fail if actual count is LESS than expected (missing data)
                    # Allow actual > expected for aggregated data from multiple orgs
                    if actual_count < expected_count:
                        missing_data.append(
                            f"{person_data.full_name}.{entity_type}: "
                            f"expected at least {expected_count}, found {actual_count}"
                        )

        if missing_data:
            pytest.fail(
                f"{org_id} missing entity data:\n"
                + "\n".join(f"  - {m}" for m in missing_data)
            )

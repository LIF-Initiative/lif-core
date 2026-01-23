"""Integration tests for Query Planner layer.

Verifies that the Query Planner API returns correct data.
Note: Query Planner is only exposed for org1 in the default docker-compose.
"""

import pytest
from typing import Any

from utils.ports import OrgPorts
from utils.sample_data import SampleDataLoader, PersonData
from utils.comparison import compare_person_data, summarize_results, ComparisonResult


@pytest.mark.layer("query_planner")
class TestQueryPlannerDataIntegrity:
    """Tests for Query Planner data integrity."""

    def _make_query_payload(
        self,
        identifier: str,
        identifier_type: str = "SCHOOL_ASSIGNED_NUMBER",
        selected_fields: list[str] | None = None,
    ) -> dict[str, Any]:
        """Build a LIFQuery payload for the Query Planner API."""
        if selected_fields is None:
            selected_fields = [
                "Person.Name",
                "Person.Contact",
                "Person.Identifier",
                "Person.CredentialAward",
                "Person.CourseLearningExperience",
                "Person.EmploymentLearningExperience",
                "Person.Proficiency",
                "Person.PositionPreferences",
                "Person.EmploymentPreferences",
            ]

        return {
            "filter": {
                "Person": {
                    "Identifier": {
                        "identifier": identifier,
                        "identifierType": identifier_type,
                    }
                }
            },
            "selected_fields": selected_fields,
        }

    def test_query_planner_health(
        self,
        org_id: str,
        org_ports: OrgPorts,
        http_client: Any,
        require_query_planner: None,
    ) -> None:
        """Verify Query Planner API is responding."""
        response = http_client.get(f"{org_ports.query_planner_url}/")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data

    def test_query_returns_person_by_school_number(
        self,
        org_id: str,
        org_ports: OrgPorts,
        sample_data: SampleDataLoader,
        http_client: Any,
        require_query_planner: None,
    ) -> None:
        """Verify Query Planner returns person data by school assigned number."""
        persons = sample_data.persons
        if not persons:
            pytest.skip(f"No sample data for {org_id}")

        person_data = persons[0]
        school_num = person_data.school_assigned_number
        if not school_num:
            pytest.skip(f"No school number for {person_data.full_name}")

        payload = self._make_query_payload(school_num)

        # Query Planner may take longer due to orchestration
        import httpx
        with httpx.Client(timeout=60.0) as client:
            response = client.post(
                f"{org_ports.query_planner_url}/query",
                json=payload,
            )

        assert response.status_code == 200, (
            f"Query Planner query failed: {response.status_code} - {response.text}"
        )

        records = response.json()
        assert len(records) > 0, (
            f"Query Planner returned no records for {person_data.full_name} "
            f"(school_num: {school_num})"
        )

    def test_all_persons_queryable(
        self,
        org_id: str,
        org_ports: OrgPorts,
        sample_data: SampleDataLoader,
        http_client: Any,
        require_query_planner: None,
    ) -> None:
        """Verify all persons from sample data can be queried."""
        missing_persons = []

        import httpx
        with httpx.Client(timeout=60.0) as client:
            for person_data in sample_data.persons:
                school_num = person_data.school_assigned_number
                if not school_num:
                    continue

                payload = self._make_query_payload(school_num)
                response = client.post(
                    f"{org_ports.query_planner_url}/query",
                    json=payload,
                )

                if response.status_code != 200:
                    missing_persons.append(
                        f"{person_data.full_name} (ID: {school_num}): "
                        f"HTTP {response.status_code}"
                    )
                    continue

                records = response.json()
                if not records:
                    missing_persons.append(
                        f"{person_data.full_name} (ID: {school_num}): no records returned"
                    )

        assert not missing_persons, (
            f"{org_id}: Persons not queryable via Query Planner:\n"
            + "\n".join(f"  - {p}" for p in missing_persons)
        )

    def test_person_name_matches_sample(
        self,
        org_id: str,
        org_ports: OrgPorts,
        sample_data: SampleDataLoader,
        http_client: Any,
        require_query_planner: None,
    ) -> None:
        """Verify Query Planner returns correct name data."""
        mismatches = []

        import httpx
        with httpx.Client(timeout=60.0) as client:
            for person_data in sample_data.persons:
                school_num = person_data.school_assigned_number
                if not school_num:
                    continue

                payload = self._make_query_payload(
                    school_num,
                    selected_fields=["Person.Name"],
                )
                response = client.post(
                    f"{org_ports.query_planner_url}/query",
                    json=payload,
                )

                if response.status_code != 200:
                    continue

                records = response.json()
                if not records:
                    continue

                record = records[0]
                person = record.get("Person", record.get("person", []))
                if not person:
                    continue

                person_obj = person[0] if isinstance(person, list) else person
                names = person_obj.get("Name", [])
                if not names:
                    mismatches.append(f"{person_data.full_name}: No Name in response")
                    continue

                response_name = names[0]
                expected_first = person_data.first_name
                expected_last = person_data.last_name
                actual_first = response_name.get("firstName", "").strip()
                actual_last = response_name.get("lastName", "").strip()

                if actual_first != expected_first or actual_last != expected_last:
                    mismatches.append(
                        f"{person_data.full_name}: expected '{expected_first} {expected_last}', "
                        f"got '{actual_first} {actual_last}'"
                    )

        if mismatches:
            pytest.fail(
                f"{org_id} name mismatches in Query Planner:\n"
                + "\n".join(f"  - {m}" for m in mismatches)
            )

    def test_entity_counts_match_sample(
        self,
        org_id: str,
        org_ports: OrgPorts,
        sample_data: SampleDataLoader,
        http_client: Any,
        require_query_planner: None,
    ) -> None:
        """Verify entity counts from Query Planner match sample data."""
        entity_types = [
            "CredentialAward",
            "CourseLearningExperience",
            "EmploymentLearningExperience",
            "Proficiency",
        ]
        mismatches = []

        import httpx
        with httpx.Client(timeout=60.0) as client:
            for person_data in sample_data.persons:
                school_num = person_data.school_assigned_number
                if not school_num:
                    continue

                selected_fields = [f"Person.{et}" for et in entity_types]
                payload = self._make_query_payload(school_num, selected_fields=selected_fields)

                response = client.post(
                    f"{org_ports.query_planner_url}/query",
                    json=payload,
                )

                if response.status_code != 200:
                    continue

                records = response.json()
                if not records:
                    continue

                record = records[0]
                person = record.get("Person", record.get("person", []))
                if not person:
                    continue

                person_obj = person[0] if isinstance(person, list) else person

                for entity_type in entity_types:
                    expected_count = person_data.get_entity_count(entity_type)
                    actual_count = len(person_obj.get(entity_type, []))

                    if expected_count != actual_count:
                        mismatches.append(
                            f"{person_data.full_name}.{entity_type}: "
                            f"expected {expected_count}, got {actual_count}"
                        )

        if mismatches:
            pytest.fail(
                f"{org_id} entity count mismatches in Query Planner:\n"
                + "\n".join(f"  - {m}" for m in mismatches)
            )

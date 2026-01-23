"""Integration tests for GraphQL API layer.

Verifies that the GraphQL API returns correct data for each organization.
This is the main integration point for frontend applications.
"""

import pytest
from typing import Any

from utils.ports import OrgPorts
from utils.sample_data import SampleDataLoader, PersonData
from utils.comparison import compare_person_data, summarize_results, ComparisonResult


# GraphQL query to fetch a person with all fields
# Note: Uses lowercase 'person' and 'PersonInput' per the generated schema
PERSON_QUERY = """
query GetPerson($filter: PersonInput!) {
    person(filter: $filter) {
        Name {
            firstName
            lastName
            informationSourceId
            informationSourceOrganization
            identifier
        }
        Contact {
            Email {
                emailAddress
            }
            Address {
                addressCity
                addressState
                addressPostalCode
                countryCode
            }
            Telephone {
                telephoneNumber
            }
        }
        Identifier {
            identifier
            identifierType
            informationSourceId
            informationSourceOrganization
        }
        CredentialAward {
            identifier
            awardIssueDate
            credentialAwardee
            informationSourceId
            informationSourceOrganization
        }
        CourseLearningExperience {
            identifier
            startDate
            endDate
            informationSourceId
            informationSourceOrganization
            RefCourse {
                identifier
                name
            }
        }
        EmploymentLearningExperience {
            identifier
            name
            startDate
            endDate
            informationSourceId
            informationSourceOrganization
        }
        Proficiency {
            identifier
            name
            description
            informationSourceId
            informationSourceOrganization
        }
    }
}
"""

# Simpler query for basic validation
PERSON_NAME_QUERY = """
query GetPersonName($filter: PersonInput!) {
    person(filter: $filter) {
        Name {
            firstName
            lastName
        }
        Identifier {
            identifier
            identifierType
        }
    }
}
"""


@pytest.mark.layer("graphql")
class TestGraphQLDataIntegrity:
    """Tests for GraphQL API data integrity."""

    def _make_graphql_request(
        self,
        http_client: Any,
        graphql_url: str,
        query: str,
        variables: dict[str, Any],
    ) -> dict[str, Any]:
        """Make a GraphQL request and return the response."""
        import httpx

        with httpx.Client(timeout=60.0) as client:
            response = client.post(
                graphql_url,
                json={"query": query, "variables": variables},
            )

        if response.status_code != 200:
            raise AssertionError(
                f"GraphQL request failed: {response.status_code} - {response.text}"
            )

        return response.json()

    def _make_filter(
        self,
        identifier: str,
        identifier_type: str = "SCHOOL_ASSIGNED_NUMBER",
    ) -> dict[str, Any]:
        """Build a GraphQL filter for person lookup."""
        return {
            "filter": {
                "Identifier": [
                    {
                        "identifier": identifier,
                        "identifierType": identifier_type,
                    }
                ]
            }
        }

    def test_graphql_schema_loads(
        self,
        org_id: str,
        org_ports: OrgPorts,
        http_client: Any,
        require_graphql: None,
    ) -> None:
        """Verify GraphQL schema loads successfully."""
        # Introspection query to verify schema
        introspection_query = """
        query {
            __schema {
                queryType {
                    name
                }
            }
        }
        """

        result = self._make_graphql_request(
            http_client,
            org_ports.graphql_url,
            introspection_query,
            {},
        )

        assert "errors" not in result or not result["errors"], (
            f"GraphQL introspection failed: {result.get('errors')}"
        )
        assert result.get("data", {}).get("__schema") is not None

    def test_query_returns_person_by_school_number(
        self,
        org_id: str,
        org_ports: OrgPorts,
        sample_data: SampleDataLoader,
        http_client: Any,
        require_graphql: None,
    ) -> None:
        """Verify GraphQL returns person data by school assigned number."""
        persons = sample_data.persons
        if not persons:
            pytest.skip(f"No sample data for {org_id}")

        person_data = persons[0]
        school_num = person_data.school_assigned_number
        if not school_num:
            pytest.skip(f"No school number for {person_data.full_name}")

        variables = self._make_filter(school_num)
        result = self._make_graphql_request(
            http_client,
            org_ports.graphql_url,
            PERSON_NAME_QUERY,
            variables,
        )

        assert "errors" not in result or not result["errors"], (
            f"GraphQL query failed for {person_data.full_name}: {result.get('errors')}"
        )

        person_list = result.get("data", {}).get("person", [])
        assert len(person_list) > 0, (
            f"GraphQL returned no Person records for {person_data.full_name} "
            f"(school_num: {school_num})"
        )

    def test_all_persons_queryable(
        self,
        org_id: str,
        org_ports: OrgPorts,
        sample_data: SampleDataLoader,
        http_client: Any,
        require_graphql: None,
    ) -> None:
        """Verify all persons from sample data can be queried via GraphQL."""
        missing_persons = []

        for person_data in sample_data.persons:
            school_num = person_data.school_assigned_number
            if not school_num:
                continue

            variables = self._make_filter(school_num)

            try:
                result = self._make_graphql_request(
                    http_client,
                    org_ports.graphql_url,
                    PERSON_NAME_QUERY,
                    variables,
                )

                if "errors" in result and result["errors"]:
                    missing_persons.append(
                        f"{person_data.full_name} (ID: {school_num}): "
                        f"GraphQL error: {result['errors']}"
                    )
                    continue

                person_list = result.get("data", {}).get("person", [])
                if not person_list:
                    missing_persons.append(
                        f"{person_data.full_name} (ID: {school_num}): no records returned"
                    )

            except Exception as e:
                missing_persons.append(
                    f"{person_data.full_name} (ID: {school_num}): {e}"
                )

        assert not missing_persons, (
            f"{org_id}: Persons not queryable via GraphQL:\n"
            + "\n".join(f"  - {p}" for p in missing_persons)
        )

    def test_person_name_matches_sample(
        self,
        org_id: str,
        org_ports: OrgPorts,
        sample_data: SampleDataLoader,
        http_client: Any,
        require_graphql: None,
    ) -> None:
        """Verify GraphQL returns correct name data."""
        mismatches = []

        for person_data in sample_data.persons:
            school_num = person_data.school_assigned_number
            if not school_num:
                continue

            variables = self._make_filter(school_num)

            try:
                result = self._make_graphql_request(
                    http_client,
                    org_ports.graphql_url,
                    PERSON_NAME_QUERY,
                    variables,
                )

                if "errors" in result and result["errors"]:
                    continue

                person_list = result.get("data", {}).get("person", [])
                if not person_list:
                    continue

                # GraphQL returns the Person array directly
                person_obj = person_list[0]
                names = person_obj.get("Name", [])
                if not names:
                    mismatches.append(f"{person_data.full_name}: No Name in response")
                    continue

                response_name = names[0]
                expected_first = person_data.first_name
                expected_last = person_data.last_name
                actual_first = (response_name.get("firstName") or "").strip()
                actual_last = (response_name.get("lastName") or "").strip()

                if actual_first != expected_first or actual_last != expected_last:
                    mismatches.append(
                        f"{person_data.full_name}: expected '{expected_first} {expected_last}', "
                        f"got '{actual_first} {actual_last}'"
                    )

            except Exception as e:
                mismatches.append(f"{person_data.full_name}: {e}")

        if mismatches:
            pytest.fail(
                f"{org_id} name mismatches in GraphQL:\n"
                + "\n".join(f"  - {m}" for m in mismatches)
            )

    def test_entity_counts_match_sample(
        self,
        org_id: str,
        org_ports: OrgPorts,
        sample_data: SampleDataLoader,
        http_client: Any,
        require_graphql: None,
    ) -> None:
        """Verify entity counts from GraphQL match sample data."""
        entity_types = [
            "CredentialAward",
            "CourseLearningExperience",
            "EmploymentLearningExperience",
            "Proficiency",
        ]
        mismatches = []

        for person_data in sample_data.persons:
            school_num = person_data.school_assigned_number
            if not school_num:
                continue

            variables = self._make_filter(school_num)

            try:
                result = self._make_graphql_request(
                    http_client,
                    org_ports.graphql_url,
                    PERSON_QUERY,
                    variables,
                )

                if "errors" in result and result["errors"]:
                    continue

                person_list = result.get("data", {}).get("person", [])
                if not person_list:
                    continue

                person_obj = person_list[0]

                for entity_type in entity_types:
                    expected_count = person_data.get_entity_count(entity_type)
                    actual_entities = person_obj.get(entity_type) or []
                    actual_count = len(actual_entities)

                    if expected_count != actual_count:
                        mismatches.append(
                            f"{person_data.full_name}.{entity_type}: "
                            f"expected {expected_count}, got {actual_count}"
                        )

            except Exception as e:
                mismatches.append(f"{person_data.full_name}: {e}")

        if mismatches:
            pytest.fail(
                f"{org_id} entity count mismatches in GraphQL:\n"
                + "\n".join(f"  - {m}" for m in mismatches)
            )

    def test_credential_award_details(
        self,
        org_id: str,
        org_ports: OrgPorts,
        sample_data: SampleDataLoader,
        http_client: Any,
        require_graphql: None,
    ) -> None:
        """Verify CredentialAward details match sample data."""
        mismatches = []

        for person_data in sample_data.persons:
            school_num = person_data.school_assigned_number
            if not school_num:
                continue

            expected_credentials = person_data.person.get("CredentialAward", [])
            if not expected_credentials:
                continue

            variables = self._make_filter(school_num)

            try:
                result = self._make_graphql_request(
                    http_client,
                    org_ports.graphql_url,
                    PERSON_QUERY,
                    variables,
                )

                if "errors" in result and result["errors"]:
                    continue

                person_list = result.get("data", {}).get("person", [])
                if not person_list:
                    continue

                actual_credentials = person_list[0].get("CredentialAward") or []

                # Check that each expected credential exists
                for exp_cred in expected_credentials:
                    exp_id = exp_cred.get("identifier")
                    found = any(
                        act.get("identifier") == exp_id
                        for act in actual_credentials
                    )
                    if not found:
                        mismatches.append(
                            f"{person_data.full_name}: Missing CredentialAward '{exp_id}'"
                        )

            except Exception as e:
                mismatches.append(f"{person_data.full_name}: {e}")

        if mismatches:
            pytest.fail(
                f"{org_id} CredentialAward mismatches:\n"
                + "\n".join(f"  - {m}" for m in mismatches)
            )

    def test_course_learning_experience_details(
        self,
        org_id: str,
        org_ports: OrgPorts,
        sample_data: SampleDataLoader,
        http_client: Any,
        require_graphql: None,
    ) -> None:
        """Verify CourseLearningExperience details match sample data."""
        mismatches = []

        for person_data in sample_data.persons:
            school_num = person_data.school_assigned_number
            if not school_num:
                continue

            expected_courses = person_data.person.get("CourseLearningExperience", [])
            if not expected_courses:
                continue

            variables = self._make_filter(school_num)

            try:
                result = self._make_graphql_request(
                    http_client,
                    org_ports.graphql_url,
                    PERSON_QUERY,
                    variables,
                )

                if "errors" in result and result["errors"]:
                    continue

                person_list = result.get("data", {}).get("person", [])
                if not person_list:
                    continue

                actual_courses = person_list[0].get("CourseLearningExperience") or []

                # Check that each expected course exists
                for exp_course in expected_courses:
                    exp_id = exp_course.get("identifier")
                    found = any(
                        act.get("identifier") == exp_id
                        for act in actual_courses
                    )
                    if not found:
                        mismatches.append(
                            f"{person_data.full_name}: Missing CourseLearningExperience '{exp_id}'"
                        )

            except Exception as e:
                mismatches.append(f"{person_data.full_name}: {e}")

        if mismatches:
            pytest.fail(
                f"{org_id} CourseLearningExperience mismatches:\n"
                + "\n".join(f"  - {m}" for m in mismatches)
            )

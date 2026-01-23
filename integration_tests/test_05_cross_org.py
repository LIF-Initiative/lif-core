"""Integration tests for cross-organization data consistency.

Verifies data isolation between organizations and consistency of shared persons.
"""

import pytest
from typing import Any

from utils.ports import OrgPorts, get_org_ports, get_all_org_ids
from utils.sample_data import SampleDataLoader, load_all_orgs


# GraphQL query for cross-org validation
PERSON_QUERY = """
query GetPerson($filter: PersonFilter!) {
    Person(filter: $filter) {
        Name {
            firstName
            lastName
        }
        Identifier {
            identifier
            identifierType
            informationSourceId
            informationSourceOrganization
        }
        informationSourceId
    }
}
"""


def _make_graphql_request(
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


def _check_graphql_available(graphql_url: str) -> bool:
    """Check if GraphQL endpoint is available."""
    import httpx

    try:
        response = httpx.get(
            graphql_url.replace("/graphql", ""),
            timeout=5.0,
        )
        return response.status_code < 500
    except httpx.RequestError:
        return False


@pytest.mark.layer("cross_org")
class TestCrossOrgDataIsolation:
    """Tests for data isolation between organizations."""

    def test_org_data_not_in_other_orgs(self, skip_unavailable: bool) -> None:
        """Verify each org's data is not accessible from other orgs."""
        all_loaders = load_all_orgs()
        all_org_ids = get_all_org_ids()

        cross_access_issues = []

        for source_org_id in all_org_ids:
            source_ports = get_org_ports(source_org_id)
            source_loader = all_loaders.get(source_org_id)

            if not source_loader:
                continue

            # Get school numbers from source org
            source_school_numbers = source_loader.get_all_school_numbers()

            for target_org_id in all_org_ids:
                if target_org_id == source_org_id:
                    continue

                target_ports = get_org_ports(target_org_id)

                # Skip if target GraphQL is not available
                if not _check_graphql_available(target_ports.graphql_url):
                    if skip_unavailable:
                        continue
                    else:
                        pytest.fail(
                            f"GraphQL not available for {target_org_id}"
                        )

                # Try to find source org's persons in target org
                for school_num in source_school_numbers:
                    variables = _make_filter(school_num)

                    try:
                        result = _make_graphql_request(
                            target_ports.graphql_url,
                            PERSON_QUERY,
                            variables,
                        )

                        person_list = result.get("data", {}).get("Person", [])

                        # Check if any returned persons have the source org's informationSourceId
                        for person in person_list:
                            person_source_id = person.get("informationSourceId", "")
                            if person_source_id == source_org_id.replace("org", "Org"):
                                cross_access_issues.append(
                                    f"{source_org_id} person (ID: {school_num}) "
                                    f"accessible from {target_org_id}"
                                )

                    except Exception:
                        # Query failures are expected for cross-org queries
                        pass

        if cross_access_issues:
            pytest.fail(
                "Data isolation issues found:\n"
                + "\n".join(f"  - {issue}" for issue in cross_access_issues)
            )


@pytest.mark.layer("cross_org")
class TestCrossOrgConsistency:
    """Tests for consistency across organizations."""

    def test_person_counts_per_org(self, skip_unavailable: bool) -> None:
        """Report person counts for each org."""
        all_loaders = load_all_orgs()
        all_org_ids = get_all_org_ids()

        org_counts = {}

        for org_id in all_org_ids:
            loader = all_loaders.get(org_id)
            if loader:
                org_counts[org_id] = len(loader.persons)

        # Just report, don't fail
        print("\n\nPerson counts per org:")
        for org_id, count in org_counts.items():
            print(f"  {org_id}: {count} persons")

    def test_all_orgs_graphql_available(self, skip_unavailable: bool) -> None:
        """Verify GraphQL is available for all orgs."""
        all_org_ids = get_all_org_ids()
        unavailable = []

        for org_id in all_org_ids:
            ports = get_org_ports(org_id)
            if not _check_graphql_available(ports.graphql_url):
                unavailable.append(f"{org_id} ({ports.graphql_url})")

        if unavailable:
            if skip_unavailable:
                pytest.skip(
                    f"GraphQL unavailable for: {', '.join(unavailable)}"
                )
            else:
                pytest.fail(
                    f"GraphQL unavailable for:\n"
                    + "\n".join(f"  - {u}" for u in unavailable)
                )

    def test_org_identifiers_unique(self) -> None:
        """Verify school assigned numbers are unique within each org."""
        all_loaders = load_all_orgs()

        duplicates = []

        for org_id, loader in all_loaders.items():
            school_numbers = loader.get_all_school_numbers()
            seen = set()

            for num in school_numbers:
                if num in seen:
                    duplicates.append(f"{org_id}: duplicate school number '{num}'")
                seen.add(num)

        if duplicates:
            pytest.fail(
                "Duplicate identifiers found:\n"
                + "\n".join(f"  - {d}" for d in duplicates)
            )

    def test_sample_data_structure_consistent(self) -> None:
        """Verify sample data files have consistent structure across orgs."""
        all_loaders = load_all_orgs()

        issues = []

        for org_id, loader in all_loaders.items():
            for person_data in loader.persons:
                # Check required fields exist
                if not person_data.person.get("Name"):
                    issues.append(
                        f"{org_id}/{person_data.filename}: Missing Name"
                    )

                if not person_data.person.get("Identifier"):
                    issues.append(
                        f"{org_id}/{person_data.filename}: Missing Identifier"
                    )

                # Check identifiers have required fields
                for ident in person_data.person.get("Identifier", []):
                    if not ident.get("identifier"):
                        issues.append(
                            f"{org_id}/{person_data.filename}: Identifier missing 'identifier'"
                        )
                    if not ident.get("identifierType"):
                        issues.append(
                            f"{org_id}/{person_data.filename}: Identifier missing 'identifierType'"
                        )

        if issues:
            pytest.fail(
                "Sample data structure issues:\n"
                + "\n".join(f"  - {issue}" for issue in issues)
            )


@pytest.mark.layer("cross_org")
class TestCrossOrgSummary:
    """Summary tests that report cross-org statistics."""

    def test_summary_report(self, skip_unavailable: bool) -> None:
        """Generate a summary report of all orgs."""
        all_loaders = load_all_orgs()
        all_org_ids = get_all_org_ids()

        report_lines = [
            "",
            "=" * 60,
            "CROSS-ORG SUMMARY REPORT",
            "=" * 60,
        ]

        for org_id in all_org_ids:
            ports = get_org_ports(org_id)
            loader = all_loaders.get(org_id)

            report_lines.append(f"\n{org_id.upper()}:")
            report_lines.append(f"  Sample data key: {ports.sample_data_key}")
            report_lines.append(f"  GraphQL URL: {ports.graphql_url}")
            report_lines.append(f"  MongoDB port: {ports.mongodb}")

            if loader:
                report_lines.append(f"  Persons in sample data: {len(loader.persons)}")

                # Count entity types
                entity_counts: dict[str, int] = {}
                for person in loader.persons:
                    for entity_type in [
                        "CredentialAward",
                        "CourseLearningExperience",
                        "EmploymentLearningExperience",
                        "Proficiency",
                    ]:
                        count = person.get_entity_count(entity_type)
                        entity_counts[entity_type] = entity_counts.get(entity_type, 0) + count

                for entity_type, count in entity_counts.items():
                    report_lines.append(f"  Total {entity_type}: {count}")

            # Check GraphQL availability
            graphql_available = _check_graphql_available(ports.graphql_url)
            report_lines.append(
                f"  GraphQL available: {'Yes' if graphql_available else 'No'}"
            )

        report_lines.append("")
        report_lines.append("=" * 60)

        print("\n".join(report_lines))

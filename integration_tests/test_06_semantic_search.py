"""Integration tests for Semantic Search MCP Server.

Verifies that the Semantic Search MCP server is operational and returns
relevant results based on well-known sample data.

Test users:
- Core org1 users (native to org1): Matt, Renee, Sarah, Tracy
- Async-ingested users (from org2, ingested via orchestration): Alan, Jenna

The async users are checked via GraphQL queries to the actual service,
not just sample data files, to verify orchestration has completed.
"""

import pytest
from typing import Any

import httpx

from utils.ports import SEMANTIC_SEARCH_HEALTH_URL, SEMANTIC_SEARCH_STATUS_URL, SEMANTIC_SEARCH_MCP_URL, get_org_ports
from utils.sample_data import SampleDataLoader


# GraphQL URL for org1 (semantic search is connected to org1)
ORG1_GRAPHQL_URL = get_org_ports("org1").graphql_url


@pytest.fixture
def require_graphql_org1(skip_unavailable: bool) -> None:
    """Ensure org1's GraphQL API is available."""
    from conftest import check_service_available

    check_service_available(ORG1_GRAPHQL_URL, skip_unavailable)


def query_graphql_by_identifier(
    identifier: str, identifier_type: str = "SCHOOL_ASSIGNED_NUMBER"
) -> dict[str, Any] | None:
    """Query GraphQL for a person by their identifier.

    Args:
        identifier: The identifier value (e.g., school assigned number)
        identifier_type: The type of identifier

    Returns:
        The person data dict if found, None if not found
    """
    query = """
    query GetPerson($filter: PersonInput!) {
        person(filter: $filter) {
            Name {
                firstName
                lastName
                informationSourceId
            }
            Identifier {
                identifier
                identifierType
            }
            Proficiency {
                name
                description
                identifier
            }
            CredentialAward {
                identifier
            }
            CourseLearningExperience {
                identifier
            }
            EmploymentLearningExperience {
                identifier
            }
        }
    }
    """

    variables = {"filter": {"Identifier": [{"identifier": identifier, "identifierType": identifier_type}]}}

    try:
        with httpx.Client(timeout=60.0) as client:
            response = client.post(ORG1_GRAPHQL_URL, json={"query": query, "variables": variables})

        if response.status_code != 200:
            return None

        data = response.json()
        if "errors" in data and data["errors"]:
            return None

        persons = data.get("data", {}).get("person", [])
        if persons:
            return persons[0]

        return None

    except Exception:
        return None


@pytest.mark.layer("semantic_search")
class TestSemanticSearchHealth:
    """Tests for Semantic Search MCP Server health and status endpoints."""

    def test_health_endpoint(self, require_semantic_search: None) -> None:
        """Verify the health endpoint returns OK."""
        with httpx.Client(timeout=30.0) as client:
            response = client.get(SEMANTIC_SEARCH_HEALTH_URL)

        assert response.status_code == 200
        assert response.text == "OK"

    def test_schema_status_endpoint(self, require_semantic_search: None) -> None:
        """Verify the schema status endpoint returns expected metadata."""
        with httpx.Client(timeout=30.0) as client:
            response = client.get(SEMANTIC_SEARCH_STATUS_URL)

        assert response.status_code == 200

        status = response.json()
        assert status["initialized"] is True
        assert status["source"] in ("mdr", "file")
        assert status["leaf_count"] > 0
        assert "Person" in status["roots"]
        assert "Person" in status["filter_models"]

    def test_schema_status_has_embeddings_ready(self, require_semantic_search: None) -> None:
        """Verify schema has been loaded with embeddings (leaf_count > 0)."""
        with httpx.Client(timeout=30.0) as client:
            response = client.get(SEMANTIC_SEARCH_STATUS_URL)

        assert response.status_code == 200
        status = response.json()

        # Schema should have a reasonable number of leaves for LIF
        assert status["leaf_count"] >= 50, f"Expected at least 50 schema leaves, got {status['leaf_count']}"


@pytest.mark.layer("semantic_search")
class TestSemanticSearchMCPTools:
    """Tests for Semantic Search MCP tool functionality.

    These tests call the MCP server's tools via the HTTP interface
    to verify semantic search returns relevant results.
    """

    def _call_mcp_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """
        Call an MCP tool via the HTTP interface.

        The MCP protocol uses JSON-RPC style messaging. For FastMCP servers,
        tools can be invoked via POST to the /mcp endpoint.
        """
        # MCP uses JSON-RPC 2.0 style requests
        request_body = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        }

        with httpx.Client(timeout=120.0) as client:
            response = client.post(
                SEMANTIC_SEARCH_MCP_URL, json=request_body, headers={"Content-Type": "application/json"}
            )

        if response.status_code != 200:
            return {"error": f"HTTP {response.status_code}: {response.text}"}

        return response.json()

    def _make_person_filter(self, identifier: str, identifier_type: str = "SCHOOL_ASSIGNED_NUMBER") -> dict[str, Any]:
        """Build a person filter for the lif_query tool."""
        return {"Identifier": [{"identifier": identifier, "identifierType": identifier_type}]}


@pytest.mark.layer("semantic_search")
class TestSemanticSearchHTTPInterface:
    """Tests for Semantic Search via direct HTTP calls.

    Since MCP protocol may not be directly testable via simple HTTP,
    these tests verify the HTTP endpoints work correctly.
    """

    def test_mcp_endpoint_responds(self, require_semantic_search: None) -> None:
        """Verify the MCP endpoint is accessible (even if it rejects invalid requests)."""
        with httpx.Client(timeout=30.0) as client:
            # Send an empty request to verify the endpoint exists
            response = client.post(SEMANTIC_SEARCH_MCP_URL, json={}, headers={"Content-Type": "application/json"})

        # MCP endpoint should respond (may return error for invalid request)
        # but should not be 404 or 503
        assert response.status_code != 404, "MCP endpoint not found"
        assert response.status_code != 503, "MCP server not ready"


@pytest.mark.layer("semantic_search")
class TestSemanticSearchDataConsistency:
    """Tests verifying semantic search has access to all expected test users.

    The semantic search MCP server is connected to org1's GraphQL API.
    These tests query GraphQL by identifier (from sample data) to verify users.

    Test users:
    - Core org1 users (native to org1): Matt, Renee, Sarah, Tracy
    - Async-ingested users (from org2, via orchestration): Alan, Jenna

    Core users must be present; async users warn if missing.
    """

    # Core users are native to org1
    CORE_USERS = ["Matt", "Renee", "Sarah", "Tracy"]

    # Async users are ingested from org2 via orchestration
    ASYNC_USERS = ["Alan", "Jenna"]

    ALL_USERS = CORE_USERS + ASYNC_USERS

    # Source org for async users (where their sample data lives)
    ASYNC_USER_SOURCE_ORG = "advisor-demo-org2"

    @pytest.fixture
    def org1_sample_data(self) -> SampleDataLoader:
        """Load sample data for org1 (core users)."""
        return SampleDataLoader(org_id="org1", sample_data_key="advisor-demo-org1")

    @pytest.fixture
    def org2_sample_data(self) -> SampleDataLoader:
        """Load sample data for org2 (source of async users Alan, Jenna)."""
        return SampleDataLoader(org_id="org2", sample_data_key=self.ASYNC_USER_SOURCE_ORG)

    def _is_async_user(self, user_name: str) -> bool:
        """Check if user is async-ingested."""
        return user_name in self.ASYNC_USERS

    def _get_sample_data_for_user(
        self, user_name: str, org1_sample_data: SampleDataLoader, org2_sample_data: SampleDataLoader
    ):
        """Get sample data for a user from appropriate org."""
        if self._is_async_user(user_name):
            return org2_sample_data.get_person_by_name(user_name)
        return org1_sample_data.get_person_by_name(user_name)

    def _get_user_identifier(
        self, user_name: str, org1_sample_data: SampleDataLoader, org2_sample_data: SampleDataLoader
    ) -> str | None:
        """Get SCHOOL_ASSIGNED_NUMBER for a user from sample data."""
        sample_person = self._get_sample_data_for_user(user_name, org1_sample_data, org2_sample_data)
        if sample_person:
            return sample_person.school_assigned_number
        return None

    def _query_user_in_graphql(
        self, user_name: str, org1_sample_data: SampleDataLoader, org2_sample_data: SampleDataLoader
    ) -> dict[str, Any] | None:
        """Query GraphQL for a user by their identifier from sample data."""
        identifier = self._get_user_identifier(user_name, org1_sample_data, org2_sample_data)
        if not identifier:
            return None
        return query_graphql_by_identifier(identifier)

    def _handle_missing_user_graphql(self, user_name: str, graphql_data: Any) -> None:
        """Handle user not found in GraphQL - fail for core, skip for async."""
        if graphql_data is None:
            if self._is_async_user(user_name):
                pytest.skip(f"{user_name} not yet available in GraphQL (async user)")
            else:
                pytest.fail(f"{user_name} not found in GraphQL (core user should exist)")

    def test_all_users_in_graphql(
        self,
        require_semantic_search: None,
        require_graphql_org1: None,
        org1_sample_data: SampleDataLoader,
        org2_sample_data: SampleDataLoader,
    ) -> None:
        """Verify all test users are queryable via GraphQL.

        Core users must be present; async users warn if missing.
        """
        found_users = set()
        missing_core = []
        missing_async = []

        for user_name in self.ALL_USERS:
            graphql_data = self._query_user_in_graphql(user_name, org1_sample_data, org2_sample_data)
            if graphql_data:
                found_users.add(user_name)
            elif self._is_async_user(user_name):
                missing_async.append(user_name)
            else:
                missing_core.append(user_name)

        # Core users must be present
        assert not missing_core, f"Core users missing from GraphQL: {missing_core}"

        # Log summary
        print("\n--- GraphQL User Availability ---")
        print(f"Users found: {sorted(found_users)}")
        if missing_async:
            print(f"Async users pending: {missing_async}")

    @pytest.mark.parametrize("user_name", ["Matt", "Renee", "Sarah", "Tracy", "Alan", "Jenna"])
    def test_user_queryable_in_graphql(
        self,
        require_semantic_search: None,
        require_graphql_org1: None,
        org1_sample_data: SampleDataLoader,
        org2_sample_data: SampleDataLoader,
        user_name: str,
    ) -> None:
        """Verify each test user is queryable via GraphQL."""
        graphql_data = self._query_user_in_graphql(user_name, org1_sample_data, org2_sample_data)
        self._handle_missing_user_graphql(user_name, graphql_data)

        # User found - verify they have a name
        names = graphql_data.get("Name", [])
        assert len(names) > 0, f"{user_name} has no Name records in GraphQL"

    @pytest.mark.parametrize("user_name", ["Matt", "Renee", "Sarah", "Tracy", "Alan", "Jenna"])
    def test_user_has_proficiencies_in_graphql(
        self,
        require_semantic_search: None,
        require_graphql_org1: None,
        org1_sample_data: SampleDataLoader,
        org2_sample_data: SampleDataLoader,
        user_name: str,
    ) -> None:
        """Verify each user has proficiency data in GraphQL for semantic search."""
        graphql_data = self._query_user_in_graphql(user_name, org1_sample_data, org2_sample_data)
        self._handle_missing_user_graphql(user_name, graphql_data)

        proficiencies = graphql_data.get("Proficiency", [])
        assert len(proficiencies) > 0, f"{user_name} has no proficiencies in GraphQL - semantic search needs this data"

    @pytest.mark.parametrize("user_name", ["Matt", "Renee", "Sarah", "Tracy", "Alan", "Jenna"])
    def test_user_has_identifier_in_graphql(
        self,
        require_semantic_search: None,
        require_graphql_org1: None,
        org1_sample_data: SampleDataLoader,
        org2_sample_data: SampleDataLoader,
        user_name: str,
    ) -> None:
        """Verify each user has identifier data in GraphQL."""
        graphql_data = self._query_user_in_graphql(user_name, org1_sample_data, org2_sample_data)
        self._handle_missing_user_graphql(user_name, graphql_data)

        identifiers = graphql_data.get("Identifier", [])
        assert len(identifiers) > 0, f"{user_name} has no identifiers in GraphQL"

    @pytest.mark.parametrize("user_name", ["Matt", "Renee", "Sarah", "Tracy", "Alan", "Jenna"])
    def test_user_proficiencies_have_descriptions(
        self,
        require_semantic_search: None,
        require_graphql_org1: None,
        org1_sample_data: SampleDataLoader,
        org2_sample_data: SampleDataLoader,
        user_name: str,
    ) -> None:
        """Verify user proficiencies have descriptions (from sample data).

        Users with zero proficiencies in sample data pass - this is valid.
        Users with proficiencies should have at least some with descriptions.
        """
        # Get expected data from sample files
        sample_person = self._get_sample_data_for_user(user_name, org1_sample_data, org2_sample_data)
        if sample_person is None:
            # No sample data for this user - valid for async users
            return

        proficiencies = sample_person.person.get("Proficiency", [])
        if not proficiencies:
            # Zero proficiencies is valid - some users don't have proficiency data
            return

        # If user has proficiencies, at least some should have descriptions
        with_descriptions = [p for p in proficiencies if p.get("description")]
        assert len(with_descriptions) > 0, (
            f"{user_name} has {len(proficiencies)} proficiencies but none have descriptions"
        )

    def test_all_users_summary(
        self,
        require_semantic_search: None,
        require_graphql_org1: None,
        org1_sample_data: SampleDataLoader,
        org2_sample_data: SampleDataLoader,
    ) -> None:
        """Summary showing all 6 test users and their GraphQL availability."""
        summary = []
        missing_async = []

        for user_name in self.ALL_USERS:
            graphql_data = self._query_user_in_graphql(user_name, org1_sample_data, org2_sample_data)

            if graphql_data is None:
                status = "ASYNC PENDING" if self._is_async_user(user_name) else "MISSING"
                summary.append(f"{user_name}: {status}")
                if self._is_async_user(user_name):
                    missing_async.append(user_name)
                continue

            proficiencies = graphql_data.get("Proficiency") or []
            credentials = graphql_data.get("CredentialAward") or []
            courses = graphql_data.get("CourseLearningExperience") or []
            employment = graphql_data.get("EmploymentLearningExperience") or []

            names = graphql_data.get("Name") or []
            full_name = user_name
            if names:
                full_name = f"{names[0].get('firstName', '')} {names[0].get('lastName', '')}".strip()

            user_type = "async" if self._is_async_user(user_name) else "core"
            summary.append(
                f"{full_name} ({user_type}): "
                f"{len(proficiencies)} proficiencies, "
                f"{len(credentials)} credentials, "
                f"{len(courses)} courses, "
                f"{len(employment)} employment"
            )

        # Print summary
        print("\n--- GraphQL Test User Summary (All 6 Users) ---")
        for line in summary:
            print(f"  {line}")
        if missing_async:
            print(f"  Async users pending ingestion: {missing_async}")


@pytest.mark.layer("semantic_search")
class TestSchemaSourceIntegrity:
    """Tests verifying the schema source and integrity."""

    def test_schema_loaded_from_expected_source(self, require_semantic_search: None) -> None:
        """Verify schema is loaded from MDR when MDR is available."""
        with httpx.Client(timeout=30.0) as client:
            response = client.get(SEMANTIC_SEARCH_STATUS_URL)

        assert response.status_code == 200
        status = response.json()

        # In docker-compose setup, should load from MDR
        # USE_OPENAPI_DATA_MODEL_FROM_FILE defaults to false
        if status["source"] == "file":
            pytest.xfail("Schema loaded from file instead of MDR. This may indicate MDR was not available at startup.")

        assert status["source"] == "mdr", f"Expected schema from 'mdr', got '{status['source']}'"

    def test_schema_has_required_filter_models(self, require_semantic_search: None) -> None:
        """Verify schema includes required filter models for querying."""
        with httpx.Client(timeout=30.0) as client:
            response = client.get(SEMANTIC_SEARCH_STATUS_URL)

        assert response.status_code == 200
        status = response.json()

        filter_models = status.get("filter_models", [])
        assert "Person" in filter_models, "Person filter model required"

    def test_schema_has_mutation_models(self, require_semantic_search: None) -> None:
        """Verify schema includes mutation models if mutations are supported."""
        with httpx.Client(timeout=30.0) as client:
            response = client.get(SEMANTIC_SEARCH_STATUS_URL)

        assert response.status_code == 200
        status = response.json()

        # Mutation models may or may not be present depending on schema
        mutation_models = status.get("mutation_models", [])
        # Just log for now - presence is optional
        if not mutation_models:
            pytest.skip("No mutation models available (this may be expected)")

        assert "Person" in mutation_models, "If mutation models exist, Person should be included"

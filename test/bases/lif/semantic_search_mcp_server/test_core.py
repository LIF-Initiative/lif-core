"""Tests for the Semantic Search MCP Server module.

Note on test strategy:
- The MCP server module initializes schema at import time (required for FastMCP
  tool registration which needs Pydantic models at decoration time).
- For unit tests, we use USE_OPENAPI_DATA_MODEL_FROM_FILE=true (set in conftest.py)
  to avoid requiring MDR to be running.
- MDR-based schema loading is tested at the component level in:
  test/components/lif/schema_state_manager/test_core.py
  which mocks the HTTP client and verifies MDR path works correctly.
- Integration tests (integration_tests/test_06_semantic_search.py) verify the full
  MDR-based flow with real services.
"""

# conftest.py sets USE_OPENAPI_DATA_MODEL_FROM_FILE=true before this import
from lif.semantic_search_mcp_server import core


class TestMCPServerModule:
    """Tests verifying the MCP server module loads and initializes correctly."""

    def test_module_loads(self):
        """Verify the semantic search MCP server module loads successfully."""
        assert core is not None

    def test_mcp_server_exists(self):
        """Verify the MCP server instance is created."""
        assert core.mcp is not None
        assert core.mcp.name == "LIF-Query-Server"

    def test_filter_model_exists(self):
        """Verify filter model is generated for the default root type."""
        assert core.Filter is not None

    def test_state_manager_initialized(self):
        """Verify the state manager is initialized with schema data."""
        state = core._state_manager.state
        assert state is not None
        assert len(state.leaves) > 0
        assert len(state.filter_models) > 0
        assert "Person" in state.filter_models

    def test_state_source_is_file_in_unit_tests(self):
        """Verify unit tests use file-based schema (MDR tested at component level)."""
        # This test documents that unit tests use file-based schema.
        # MDR-based loading is tested in test/components/lif/schema_state_manager/
        state = core._state_manager.state
        assert state.source == "file"


class TestMCPServerConfiguration:
    """Tests verifying MCP server configuration."""

    def test_default_root_node_is_person(self):
        """Verify default root node is Person."""
        assert core.DEFAULT_ROOT_NODE == "Person"

    def test_config_loaded_from_environment(self):
        """Verify configuration is loaded."""
        assert core.CONFIG is not None
        assert core.CONFIG.root_type_name == "Person"

    def test_lif_query_tool_registered(self):
        """Verify the lif_query tool is available."""
        # The tool should be registered with the MCP server
        assert hasattr(core, "lif_query")


class TestMCPServerEndpoints:
    """Tests for HTTP endpoint handlers (without running server)."""

    def test_health_check_handler_exists(self):
        """Verify health check endpoint handler is defined."""
        assert hasattr(core, "health_check")

    def test_schema_status_handler_exists(self):
        """Verify schema status endpoint handler is defined."""
        assert hasattr(core, "schema_status")

    def test_schema_refresh_handler_exists(self):
        """Verify schema refresh endpoint handler is defined."""
        assert hasattr(core, "schema_refresh")

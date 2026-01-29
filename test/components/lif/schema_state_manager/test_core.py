"""Tests for the SchemaStateManager component."""

import os
from unittest import mock
from unittest.mock import MagicMock, patch

import httpx
import pytest

from lif.lif_schema_config import LIFSchemaConfig
from lif.mdr_client import MDRClientException, MDRConfigurationError
from lif.schema_state_manager import SchemaState, SchemaStateManager


@pytest.fixture
def mock_config_file():
    """Create a test configuration that uses file."""
    return LIFSchemaConfig(
        root_type_name="Person",
        additional_root_types=["Course", "Organization"],
        mdr_api_url="http://localhost:8012",
        mdr_timeout_seconds=5,
        use_openapi_from_file=True,  # Force file
        semantic_search_model_name="all-MiniLM-L6-v2",
    )


@pytest.fixture
def mock_config_mdr():
    """Create a test configuration that uses MDR."""
    return LIFSchemaConfig(
        root_type_name="Person",
        additional_root_types=["Course", "Organization"],
        mdr_api_url="http://localhost:8012",
        mdr_timeout_seconds=5,
        openapi_data_model_id="test-model-123",
        use_openapi_from_file=False,  # Use MDR
        semantic_search_model_name="all-MiniLM-L6-v2",
    )


class TestSchemaStateManager:
    """Tests for SchemaStateManager class."""

    def test_init(self, mock_config_file):
        """Test SchemaStateManager initialization."""
        manager = SchemaStateManager(mock_config_file)
        assert manager._config == mock_config_file
        assert manager._initialized is False
        assert manager._state is None

    def test_is_initialized_false_before_init(self, mock_config_file):
        """Test is_initialized returns False before initialization."""
        manager = SchemaStateManager(mock_config_file)
        assert manager.is_initialized is False

    def test_state_raises_before_init(self, mock_config_file):
        """Test accessing state before initialization raises error."""
        manager = SchemaStateManager(mock_config_file)
        with pytest.raises(RuntimeError, match="not initialized"):
            _ = manager.state

    def test_initialize_sync_from_file(self, mock_config_file):
        """Test synchronous initialization from file."""
        manager = SchemaStateManager(mock_config_file)
        manager.initialize_sync()

        assert manager.is_initialized is True
        state = manager.state
        assert state.source == "file"
        assert len(state.leaves) > 0
        assert "Person" in state.filter_models
        assert state.model is not None
        assert state.embeddings is not None

    def test_initialize_sync_force_file(self, mock_config_mdr):
        """Test synchronous initialization with force_file=True ignores MDR config."""
        manager = SchemaStateManager(mock_config_mdr)
        manager.initialize_sync(force_file=True)

        assert manager.is_initialized is True
        state = manager.state
        assert state.source == "file"

    def test_initialize_sync_loads_leaves_by_root(self, mock_config_file):
        """Test that initialize_sync correctly organizes leaves by root."""
        manager = SchemaStateManager(mock_config_file)
        manager.initialize_sync()

        state = manager.state
        assert "Person" in state.leaves_by_root
        # Additional roots may or may not load depending on schema
        assert len(state.leaves_by_root) >= 1

    def test_get_status_before_init(self, mock_config_file):
        """Test get_status before initialization."""
        manager = SchemaStateManager(mock_config_file)
        status = manager.get_status()

        assert status["initialized"] is False
        assert status["source"] is None
        assert status["leaf_count"] == 0
        assert status["roots"] == []

    def test_get_status_after_init(self, mock_config_file):
        """Test get_status after initialization."""
        manager = SchemaStateManager(mock_config_file)
        manager.initialize_sync()

        status = manager.get_status()
        assert status["initialized"] is True
        assert status["source"] == "file"
        assert status["leaf_count"] > 0
        assert "Person" in status["roots"]
        assert "Person" in status["filter_models"]

    @pytest.mark.asyncio
    async def test_initialize_async_from_file(self, mock_config_file):
        """Test asynchronous initialization from file."""
        manager = SchemaStateManager(mock_config_file)
        await manager.initialize()

        assert manager.is_initialized is True
        state = manager.state
        assert state.source == "file"
        assert len(state.leaves) > 0

    @pytest.mark.asyncio
    async def test_refresh_before_init_fails(self, mock_config_file):
        """Test refresh before initialization returns error."""
        manager = SchemaStateManager(mock_config_file)
        result = await manager.refresh()

        assert result["success"] is False
        assert "not initialized" in result["error"]


class TestSchemaStateManagerMDR:
    """Tests for SchemaStateManager MDR integration."""

    @patch("lif.mdr_client.core._create_sync_client")
    def test_initialize_sync_from_mdr_success(self, mock_client_class, mock_config_mdr):
        """Test successful sync initialization from MDR."""
        # Load actual file content to return as MDR response
        from lif.mdr_client import get_openapi_lif_data_model_from_file

        openapi_data = get_openapi_lif_data_model_from_file()

        # Setup mock
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = openapi_data
        mock_response.raise_for_status.return_value = None

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_response
        mock_client_class.return_value = mock_client

        manager = SchemaStateManager(mock_config_mdr)
        manager.initialize_sync()

        assert manager.is_initialized is True
        state = manager.state
        assert state.source == "mdr"
        assert len(state.leaves) > 0

    @patch("lif.mdr_client.core._create_sync_client")
    def test_initialize_sync_mdr_failure_no_fallback(self, mock_client_class, mock_config_mdr):
        """Test that MDR failure does NOT fall back to file - exits instead."""
        # Setup mock to raise connection error
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.side_effect = httpx.ConnectError("Connection refused")
        mock_client_class.return_value = mock_client

        manager = SchemaStateManager(mock_config_mdr)

        # Should exit because MDR is configured but unavailable (no fallback)
        with pytest.raises(SystemExit):
            manager.initialize_sync()

    def test_initialize_sync_mdr_not_configured_fails(self):
        """Test that missing OPENAPI_DATA_MODEL_ID causes failure when MDR expected."""
        config = LIFSchemaConfig(
            root_type_name="Person",
            use_openapi_from_file=False,  # Expects MDR
            openapi_data_model_id=None,  # But no model ID!
            semantic_search_model_name="all-MiniLM-L6-v2",
        )

        manager = SchemaStateManager(config)

        # Should exit because MDR is expected but not configured
        with pytest.raises(SystemExit):
            manager.initialize_sync()


class TestSchemaStateManagerRefresh:
    """Tests for SchemaStateManager refresh functionality."""

    @pytest.mark.asyncio
    async def test_refresh_updates_state_from_file(self, mock_config_file):
        """Test that refresh updates the state when using file config."""
        manager = SchemaStateManager(mock_config_file)
        manager.initialize_sync()

        initial_leaf_count = len(manager.state.leaves)

        result = await manager.refresh()

        assert result["success"] is True
        assert result["previous_leaf_count"] == initial_leaf_count

    @pytest.mark.asyncio
    async def test_refresh_mdr_failure_preserves_state(self, mock_config_mdr):
        """Test that refresh failure preserves existing state."""
        # First initialize with mocked successful MDR
        with patch("lif.mdr_client.core._create_sync_client") as mock_client_class:
            from lif.mdr_client import get_openapi_lif_data_model_from_file

            openapi_data = get_openapi_lif_data_model_from_file()

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = openapi_data
            mock_response.raise_for_status.return_value = None

            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.get.return_value = mock_response
            mock_client_class.return_value = mock_client

            manager = SchemaStateManager(mock_config_mdr)
            manager.initialize_sync()

        initial_leaf_count = len(manager.state.leaves)
        initial_source = manager.state.source

        # Now make refresh fail
        with patch("lif.mdr_client.core._create_sync_client") as mock_client_class:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.get.side_effect = httpx.ConnectError("Connection refused")
            mock_client_class.return_value = mock_client

            result = await manager.refresh()

            # Refresh should fail
            assert result["success"] is False
            assert "error" in result

            # But state should be preserved
            assert len(manager.state.leaves) == initial_leaf_count
            assert manager.state.source == initial_source


class TestSchemaState:
    """Tests for SchemaState dataclass."""

    def test_schema_state_creation(self, mock_config_file):
        """Test SchemaState can be created with required fields."""
        import numpy as np
        from sentence_transformers import SentenceTransformer

        state = SchemaState(
            openapi={"openapi": "3.0.0"},
            leaves=[],
            leaves_by_root={},
            filter_models={},
            mutation_models={},
            embeddings=np.array([]),
            model=MagicMock(spec=SentenceTransformer),
            source="file",
        )

        assert state.openapi == {"openapi": "3.0.0"}
        assert state.source == "file"
        assert state.leaves == []


class TestSchemaStateManagerThreadSafety:
    """Tests for thread safety of SchemaStateManager."""

    def test_state_access_is_thread_safe(self, mock_config_file):
        """Test that state access uses locking."""
        manager = SchemaStateManager(mock_config_file)
        manager.initialize_sync()

        # Access state from multiple "threads" (simulated)
        # This test just verifies the lock exists and is used
        assert manager._lock is not None

        # Multiple accesses should work without issues
        for _ in range(10):
            _ = manager.state
            _ = manager.is_initialized
            _ = manager.get_status()

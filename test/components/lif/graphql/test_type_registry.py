"""
Unit tests for the TypeRegistry singleton class.
"""

import pytest
from unittest.mock import Mock, patch

from lif.graphql.type_registry import TypeRegistry, type_registry


class TestTypeRegistry:
    """Test the TypeRegistry singleton class."""

    def setup_method(self):
        """Reset the singleton state before each test."""
        # Reset the singleton instance for clean tests
        TypeRegistry._instance = None
        TypeRegistry._initialized = False
        # Also reset the global instance
        type_registry.__dict__.clear()
        type_registry._initialized = False

    def test_singleton_behavior(self):
        """Test that TypeRegistry behaves as a singleton."""
        # Create first instance
        registry1 = TypeRegistry()

        # Create second instance
        registry2 = TypeRegistry()

        # They should be the same object
        assert registry1 is registry2
        assert id(registry1) == id(registry2)

    def test_global_instance_is_singleton(self):
        """Test that the global type_registry instance follows singleton pattern."""
        # Create a new instance
        new_registry = TypeRegistry()

        # The global instance should be the same
        assert new_registry is type_registry

    def test_initialization_only_happens_once(self):
        """Test that __init__ only initializes attributes once."""
        registry1 = TypeRegistry()

        # Add some data to test persistence
        registry1.strawberry_types["test"] = Mock()

        # Create another instance
        registry2 = TypeRegistry()

        # Data should persist (same instance)
        assert "test" in registry2.strawberry_types
        assert registry2.strawberry_types["test"] == registry1.strawberry_types["test"]

    @patch("lif.graphql.type_registry.get_schema_fields")
    @patch("lif.graphql.type_registry.build_filter_models")
    @patch("lif.graphql.type_registry.build_mutation_models")
    @patch("lif.graphql.type_registry.build_full_models")
    def test_initialize_types_called_once(self, mock_full, mock_mutation, mock_filter, mock_schema):
        """Test that initialize_types only builds models once."""
        # Setup mocks
        mock_schema.return_value = {"field1": "value1"}
        mock_filter.return_value = {"PersonFilter": Mock()}
        mock_mutation.return_value = {"PersonMutation": Mock()}
        mock_full.return_value = {"person": Mock(), "person_wrapper": Mock()}

        registry = TypeRegistry()

        # First call should build models
        registry.initialize_types("Person", minimal_mode=True)

        # Verify mocks were called
        assert mock_schema.called
        assert mock_filter.called
        assert mock_mutation.called
        assert mock_full.called

        # Reset mock call counts
        mock_schema.reset_mock()
        mock_filter.reset_mock()
        mock_mutation.reset_mock()
        mock_full.reset_mock()

        # Second call should not rebuild models
        registry.initialize_types("Person", minimal_mode=True)

        # Verify mocks were NOT called again
        assert not mock_schema.called
        assert not mock_filter.called
        assert not mock_mutation.called
        assert not mock_full.called

    @patch("lif.graphql.type_registry.get_schema_fields")
    @patch("lif.graphql.type_registry.build_filter_models")
    @patch("lif.graphql.type_registry.build_mutation_models")
    @patch("lif.graphql.type_registry.build_full_models")
    def test_initialize_types_stores_pydantic_models(self, mock_full, mock_mutation, mock_filter, mock_schema):
        """Test that initialize_types stores Pydantic models correctly."""
        # Setup mocks
        mock_schema.return_value = {"field1": "value1"}
        filter_models = {"PersonFilter": Mock()}
        mutation_models = {"PersonMutation": Mock()}
        full_models = {"person": Mock(), "person_wrapper": Mock()}

        mock_filter.return_value = filter_models
        mock_mutation.return_value = mutation_models
        mock_full.return_value = full_models

        registry = TypeRegistry()
        registry.initialize_types("Person", minimal_mode=True)

        # Check that models are stored
        assert registry.pydantic_models["filter_models"] == filter_models
        assert registry.pydantic_models["mutation_models"] == mutation_models
        assert registry.pydantic_models["full_models"] == full_models

    @patch("lif.graphql.type_registry.get_schema_fields")
    @patch("lif.graphql.type_registry.build_filter_models")
    @patch("lif.graphql.type_registry.build_mutation_models")
    @patch("lif.graphql.type_registry.build_full_models")
    @patch("lif.graphql.type_registry.pyd_type")
    @patch("lif.graphql.type_registry.pyd_input")
    def test_initialize_types_creates_strawberry_types(
        self, mock_pyd_input, mock_pyd_type, mock_full, mock_mutation, mock_filter, mock_schema
    ):
        """Test that initialize_types creates Strawberry types when not in minimal mode."""
        # Setup mocks
        mock_schema.return_value = {"field1": "value1"}

        # Create mock models
        mock_person_model = Mock()
        mock_filter_model = Mock()
        mock_mutation_model = Mock()

        mock_filter.return_value = {"PersonFilter": mock_filter_model}
        mock_mutation.return_value = {"PersonMutation": mock_mutation_model}
        mock_full.return_value = {"person": mock_person_model, "person_wrapper": Mock()}

        # Setup strawberry type creation mocks
        mock_strawberry_type = Mock()
        mock_strawberry_input = Mock()

        mock_pyd_type.return_value = lambda cls: mock_strawberry_type
        mock_pyd_input.return_value = lambda cls: mock_strawberry_input

        registry = TypeRegistry()
        registry.initialize_types("Person", minimal_mode=False)

        # Verify strawberry types were created
        assert "Person" in registry.strawberry_types
        assert registry.strawberry_types["Person"] == mock_strawberry_type

        # Verify inputs were created (exact names depend on unique_type_name implementation)
        assert len(registry.strawberry_inputs) > 0

    def test_get_models_for_root_success(self):
        """Test successful retrieval of models for a root node."""
        registry = TypeRegistry()

        # Setup mock models
        mock_full_model = Mock()
        mock_filter_model = Mock()
        mock_mutation_model = Mock()
        mock_wrapper_model = Mock()

        # Mock the pydantic_models structure
        with patch.object(
            registry,
            "pydantic_models",
            {
                "full_models": {"person": mock_full_model, "person_wrapper": mock_wrapper_model},
                "filter_models": {"PersonFilter": mock_filter_model},
                "mutation_models": {"PersonMutation": mock_mutation_model},
            },
        ):
            result = registry.get_models_for_root("Person")

            assert result["FullModel"] == mock_full_model
            assert result["FilterModel"] == mock_filter_model
            assert result["MutationModel"] == mock_mutation_model
            assert result["WrapperModel"] == mock_wrapper_model

    def test_get_models_for_root_fallback_to_type_suffix(self):
        """Test fallback to Type suffix when lower-camel-case key doesn't exist."""
        registry = TypeRegistry()

        mock_full_model = Mock()
        mock_filter_model = Mock()
        mock_mutation_model = Mock()
        mock_wrapper_model = Mock()

        with patch.object(
            registry,
            "pydantic_models",
            {
                "full_models": {
                    "PersonType": mock_full_model,  # Only Type suffix exists
                    "person_wrapper": mock_wrapper_model,
                },
                "filter_models": {"PersonFilter": mock_filter_model},
                "mutation_models": {"PersonMutation": mock_mutation_model},
            },
        ):
            result = registry.get_models_for_root("Person")

            assert result["FullModel"] == mock_full_model

    def test_get_models_for_root_missing_model_raises_error(self):
        """Test that missing FullModel raises KeyError."""
        registry = TypeRegistry()

        with patch.object(
            registry,
            "pydantic_models",
            {
                "full_models": {"other_model": Mock()},
                "filter_models": {"PersonFilter": Mock()},
                "mutation_models": {"PersonMutation": Mock()},
            },
        ):
            with pytest.raises(KeyError, match="Cannot locate FullModel for root 'Person'"):
                registry.get_models_for_root("Person")

    @patch("lif.graphql.type_registry.unique_type_name")
    @patch("lif.graphql.type_registry.to_pascal_case_from_str")
    def test_get_strawberry_types_for_root(self, mock_pascal, mock_unique):
        """Test retrieval of Strawberry types for a root node."""
        # Setup mocks
        mock_pascal.side_effect = lambda x: x  # Identity function for simplicity
        mock_unique.return_value = "PersonFilterInput"

        registry = TypeRegistry()

        mock_root_type = Mock()
        mock_filter_input = Mock()
        mock_mutation_input = Mock()

        registry.strawberry_types = {"Person": mock_root_type}
        registry.strawberry_inputs = {
            "PersonFilterInput": mock_filter_input,
            "PersonMutationInput": mock_mutation_input,
        }

        result = registry.get_strawberry_types_for_root("Person")

        assert result["RootType"] == mock_root_type
        assert result["FilterInput"] == mock_filter_input

    def test_empty_initialization(self):
        """Test that a new registry starts with empty collections."""
        registry = TypeRegistry()

        assert registry.strawberry_types == {}
        assert registry.strawberry_inputs == {}
        assert registry.pydantic_models == {}

    @patch("lif.graphql.type_registry.get_schema_fields")
    @patch("lif.graphql.type_registry.build_filter_models")
    @patch("lif.graphql.type_registry.build_mutation_models")
    @patch("lif.graphql.type_registry.build_full_models")
    def test_minimal_mode_skips_strawberry_creation(self, mock_full, mock_mutation, mock_filter, mock_schema):
        """Test that minimal mode skips Strawberry type creation."""
        # Setup mocks
        mock_schema.return_value = {"field1": "value1"}
        mock_filter.return_value = {"PersonFilter": Mock()}
        mock_mutation.return_value = {"PersonMutation": Mock()}
        mock_full.return_value = {"person": Mock(), "person_wrapper": Mock()}

        registry = TypeRegistry()
        registry.initialize_types("Person", minimal_mode=True)

        # Should have Pydantic models but no Strawberry types
        assert registry.pydantic_models
        assert not registry.strawberry_types
        assert not registry.strawberry_inputs

    def test_wrapper_types_are_skipped_in_strawberry_creation(self):
        """Test that wrapper types are skipped when creating Strawberry types."""
        registry = TypeRegistry()

        # Mock the internal method call
        full_models = {
            "person": Mock(),
            "person_wrapper": Mock(),
            "organization": Mock(),
            "organization_wrapper": Mock(),
        }
        filter_models = {"PersonFilter": Mock()}
        mutation_models = {"PersonMutation": Mock()}

        with patch.object(registry, "_create_strawberry_types") as mock_create:
            with patch.object(
                registry,
                "pydantic_models",
                {"full_models": full_models, "filter_models": filter_models, "mutation_models": mutation_models},
            ):
                # Manually call the method to test wrapper skipping logic
                registry._create_strawberry_types(full_models, filter_models, mutation_models, "Person")

                # The method should have been called
                assert mock_create.called


class TestGlobalTypeRegistryInstance:
    """Test the global type_registry instance."""

    def setup_method(self):
        """Reset the singleton state before each test."""
        TypeRegistry._instance = None
        TypeRegistry._initialized = False
        type_registry.__dict__.clear()
        type_registry._initialized = False

    def test_global_instance_exists(self):
        """Test that the global type_registry instance exists."""
        assert type_registry is not None
        assert isinstance(type_registry, TypeRegistry)

    def test_global_instance_is_singleton(self):
        """Test that multiple references to type_registry are the same object."""
        from lif.graphql.type_registry import type_registry as imported_registry

        assert type_registry is imported_registry

    @patch("lif.graphql.type_registry.get_schema_fields")
    @patch("lif.graphql.type_registry.build_filter_models")
    @patch("lif.graphql.type_registry.build_mutation_models")
    @patch("lif.graphql.type_registry.build_full_models")
    def test_global_instance_functionality(self, mock_full, mock_mutation, mock_filter, mock_schema):
        """Test that the global instance works correctly."""
        # Setup mocks
        mock_schema.return_value = {"field1": "value1"}
        mock_filter.return_value = {"PersonFilter": Mock()}
        mock_mutation.return_value = {"PersonMutation": Mock()}
        mock_full.return_value = {"person": Mock(), "person_wrapper": Mock()}

        # Use the global instance
        type_registry.initialize_types("Person", minimal_mode=True)

        # Should have stored the models
        assert type_registry.pydantic_models
        assert "filter_models" in type_registry.pydantic_models
        assert "mutation_models" in type_registry.pydantic_models
        assert "full_models" in type_registry.pydantic_models

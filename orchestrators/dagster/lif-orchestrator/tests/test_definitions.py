"""Tests for Dagster orchestrator dependencies.

These tests verify that all required polylith bricks are included
in pyproject.toml and can be imported without errors.
"""


def test_lif_fragment_utils_imports():
    """Test that lif_fragment_utils imports work.

    This test verifies that lif_schema_config is included as a brick,
    since lif_fragment_utils imports from it.
    """
    from lif.lif_fragment_utils import adjust_lif_fragments_for_initial_orchestrator_simplification

    assert adjust_lif_fragments_for_initial_orchestrator_simplification is not None


def test_lif_schema_config_imports():
    """Test that lif_schema_config can be imported directly."""
    from lif.lif_schema_config import PERSON_DOT_PASCAL, PERSON_KEY_PASCAL, LIFSchemaConfig

    assert PERSON_DOT_PASCAL == "Person."
    assert PERSON_KEY_PASCAL == "Person"
    assert LIFSchemaConfig is not None


def test_data_source_adapters_imports():
    """Test that data_source_adapters can be imported."""
    from lif.data_source_adapters import get_adapter_by_id, get_adapter_class_by_id

    assert get_adapter_by_id is not None
    assert get_adapter_class_by_id is not None


def test_datatypes_imports():
    """Test that datatypes can be imported."""
    from lif.datatypes import LIFFragment, LIFQueryPlanPart, OrchestratorJobQueryPlanPartResults, OrchestratorJobResults

    assert LIFFragment is not None
    assert LIFQueryPlanPart is not None
    assert OrchestratorJobQueryPlanPartResults is not None
    assert OrchestratorJobResults is not None

"""Tests for Dagster orchestrator dependencies.

These tests verify that all required polylith bricks are included
in pyproject.toml and can be imported without errors.
"""


def test_query_planner_util_imports():
    """Test that query_planner_service.util imports work.

    This test verifies that lif_schema_config is included as a brick,
    since query_planner_service.util imports from it.
    """
    from lif.query_planner_service.util import (
        adjust_lif_fragments_for_initial_orchestrator_simplification,
        create_lif_query_plan_from_information_sources_config,
    )

    assert adjust_lif_fragments_for_initial_orchestrator_simplification is not None
    assert create_lif_query_plan_from_information_sources_config is not None


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

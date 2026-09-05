import pytest

from lif.data_source_adapters import ADAPTER_REGISTRY, LIFDataSourceAdapter, get_adapter_class_by_id
from lif.demo_data_source_adapters import DEMO_ADAPTERS, ExampleDataSourceRestAPIToLIFAdapter, register_demo_adapters

EXAMPLE_ADAPTER_ID = "example-data-source-rest-api-to-lif"


@pytest.fixture(autouse=True)
def clean_registry():
    """Registration mutates module-level state, so snapshot and restore it."""
    snapshot = dict(ADAPTER_REGISTRY)
    yield
    ADAPTER_REGISTRY.clear()
    ADAPTER_REGISTRY.update(snapshot)


def test_demo_adapters_are_not_registered_until_asked_for():
    """The point of the brick: importing it must not silently mutate the core registry."""
    assert EXAMPLE_ADAPTER_ID not in ADAPTER_REGISTRY


def test_register_demo_adapters_adds_every_demo_adapter():
    register_demo_adapters()

    for adapter_id, adapter_class in DEMO_ADAPTERS.items():
        assert get_adapter_class_by_id(adapter_id) is adapter_class


def test_registry_keys_match_the_adapter_id_class_attribute():
    """A mismatch here resolves to the wrong class at runtime, or to none at all."""
    for adapter_id, adapter_class in DEMO_ADAPTERS.items():
        assert adapter_class.adapter_id == adapter_id


def test_example_adapter_is_registered_under_the_id_the_configs_use():
    """`information_sources_config*.yml` and the demo seed data key off this exact string."""
    register_demo_adapters()

    assert get_adapter_class_by_id(EXAMPLE_ADAPTER_ID) is ExampleDataSourceRestAPIToLIFAdapter
    assert issubclass(ExampleDataSourceRestAPIToLIFAdapter, LIFDataSourceAdapter)


def test_register_demo_adapters_is_idempotent():
    """Called from a module import in the orchestrator; a reimport must not blow up."""
    register_demo_adapters()
    register_demo_adapters()

    assert get_adapter_class_by_id(EXAMPLE_ADAPTER_ID) is ExampleDataSourceRestAPIToLIFAdapter

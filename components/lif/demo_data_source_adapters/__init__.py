from lif.data_source_adapters import register_adapter
from lif.data_source_adapters.core import LIFDataSourceAdapter

from .example_data_source_rest_api_to_lif_adapter import ExampleDataSourceRestAPIToLIFAdapter

DEMO_ADAPTERS: dict[str, type[LIFDataSourceAdapter]] = {
    "example-data-source-rest-api-to-lif": ExampleDataSourceRestAPIToLIFAdapter
}


def register_demo_adapters() -> None:
    """Register all demo-tier adapters with the data_source_adapters registry.

    Call once at startup (e.g. in a Dagster job or base layer) before
    using ``get_adapter_by_id`` for demo adapter IDs.
    """
    for adapter_id, adapter_class in DEMO_ADAPTERS.items():
        register_adapter(adapter_id, adapter_class)


__all__ = ["ExampleDataSourceRestAPIToLIFAdapter", "DEMO_ADAPTERS", "register_demo_adapters"]

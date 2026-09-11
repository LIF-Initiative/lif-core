from .core import LIFDataSourceAdapter
from .lif_to_lif_adapter import LIFToLIFAdapter

# Core adapter registry
_CORE_ADAPTERS = {"lif-to-lif": LIFToLIFAdapter}

# External adapters registry — populated at startup via register_adapter()
_EXTERNAL_ADAPTERS: dict[str, type[LIFDataSourceAdapter]] = {}

# Combined registry
ADAPTER_REGISTRY = {**_CORE_ADAPTERS, **_EXTERNAL_ADAPTERS}


def register_adapter(adapter_id: str, adapter_class):
    """Register an external adapter."""
    if not issubclass(adapter_class, LIFDataSourceAdapter):
        raise ValueError("Adapter must be a subclass of LIFDataSourceAdapter")

    if adapter_id in _CORE_ADAPTERS:
        raise ValueError(f"Cannot override core adapter: {adapter_id}")

    _EXTERNAL_ADAPTERS[adapter_id] = adapter_class
    ADAPTER_REGISTRY[adapter_id] = adapter_class


def get_adapter_class_by_id(adapter_id: str) -> type[LIFDataSourceAdapter]:
    """Get adapter class by ID (for introspection, not instantiation)."""
    if adapter_id not in ADAPTER_REGISTRY:
        available = list(ADAPTER_REGISTRY.keys())
        raise ValueError(f"Unknown adapter_id '{adapter_id}'. Available: {available}")

    return ADAPTER_REGISTRY[adapter_id]


def get_adapter_by_id(adapter_id: str, **init_kwargs) -> LIFDataSourceAdapter:
    """Get adapter instance by ID."""
    if adapter_id not in ADAPTER_REGISTRY:
        available = list(ADAPTER_REGISTRY.keys())
        raise ValueError(f"Unknown adapter_id '{adapter_id}'. Available: {available}")

    adapter_class = ADAPTER_REGISTRY[adapter_id]
    return adapter_class(**init_kwargs)


__all__ = ["get_adapter_by_id", "get_adapter_class_by_id", "register_adapter", "LIFDataSourceAdapter"]

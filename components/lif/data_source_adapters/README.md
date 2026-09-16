# `data_source_adapters` — Component

Adapter framework for pulling LIF data from heterogeneous source systems. The orchestrator picks an adapter by id, the adapter handles the source-specific API contract (auth scheme, pagination, response shape), and returns LIF fragments that the orchestrator merges into a record.

## Public surface

```python
from lif.data_source_adapters import LIFDataSourceAdapter, ADAPTER_REGISTRY, register_adapter
```

`LIFDataSourceAdapter` is the abstract base class. Subclasses live in sibling directories (one per adapter):

| Adapter id | Directory | Notes |
|---|---|---|
| `lif-to-lif` | [`lif_to_lif_adapter/`](lif_to_lif_adapter/) | Reads from another LIF GraphQL API |

External adapters can be registered via `register_adapter(adapter_id, adapter_class)`.

Demo/example adapters live in [`demo_data_source_adapters/`](../demo_data_source_adapters/) (separate brick per [ADR 0004](../../../docs/design/adr/general/0004-components-are-the-unit-of-reuse.md)).

## Adding a new adapter

See [`docs/operations/guides/creating-a-data-source-adapter.md`](../../../docs/operations/guides/creating-a-data-source-adapter.md) for the class contract and design guidelines, or [`docs/operations/guides/add-data-source.md`](../../../docs/operations/guides/add-data-source.md) for the end-to-end tutorial.

## Used by
Pulled in by the orchestrator via configuration — the registry is consulted at adapter-dispatch time rather than by direct import from other components.

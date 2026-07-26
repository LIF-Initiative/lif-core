# `demo_data_source_adapters` — Demo-tier data source adapters

Demo/example adapters used by LIF demos and test fixtures. These are **not** product-tier — they live here to satisfy [ADR 0004 Rule 4](../../../../docs/design/adr/general/0004-components-are-the-unit-of-reuse.md) (core components must never depend on demo bricks).

Adopters who want only the product adapters (`data_source_adapters`) can ignore this brick entirely.

## Usage

```python
from lif.demo_data_source_adapters import register_demo_adapters

register_demo_adapters()  # call once at startup

from lif.data_source_adapters import get_adapter_by_id

adapter = get_adapter_by_id("example-data-source-rest-api-to-lif", ...)
```

## Contents

| Sub-package | Adapter ID | Purpose |
|---|---|---|
| `example_data_source_rest_api_to_lif_adapter/` | `example-data-source-rest-api-to-lif` | Pulls from the bundled example-data-source REST API |

## See also

- [`data_source_adapters`](../data_source_adapters/) — product-tier adapters
- [ADR 0004](../../../../docs/design/adr/general/0004-components-are-the-unit-of-reuse.md) — components are the unit of reuse

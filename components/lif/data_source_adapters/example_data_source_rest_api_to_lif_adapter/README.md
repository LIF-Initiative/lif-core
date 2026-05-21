# `example_data_source_rest_api_to_lif_adapter` — Adapter

Reference adapter that pulls from the bundled [`example_data_source_rest_api`](../../../../bases/lif/example_data_source_rest_api/) base. Treat as a worked example for how to write a custom adapter against a real source API — copy this directory, rename, swap in your auth + URL conventions.

## Files

| File | What it does |
|---|---|
| `adapter.py` | `ExampleDataSourceRestAPIToLIFAdapter` — implements the `LIFDataSourceAdapter` contract |

## Registered as
`example-data-source-rest-api-to-lif` (see [`../README.md`](../README.md) for the registry).

## See also
[`docs/operations/guides/add-data-source.md`](../../../../docs/operations/guides/add-data-source.md) walks through cloning this adapter as the starting point for a custom data source.

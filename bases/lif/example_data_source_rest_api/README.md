# `example_data_source_rest_api` — Base

Reference implementation of a non-LIF data source. Exists so the orchestrator's "external adapter" code path has something realistic to integrate with locally; production deployments swap in real SIS/LMS/HR systems via adapter components, not this base.

## Endpoints
A small set of CRUD-style endpoints over a sample person dataset, gated by `x-key` API-key auth (`require_api_key` dependency). See `core.py` for the current shape — it evolves as new adapter scenarios get demoed.

`GET /health` is exempt from auth.

## Composes
- `auth` — `verify_token` helper for API-key validation
- `example_data_source_service` — sample data + business logic
- `logging`

## Deployed as
`projects/lif_example_data_source_rest_api/`

## See also
[`docs/operations/guides/add-data-source.md`](../../../docs/operations/guides/add-data-source.md) walks through using this service end-to-end as the template for adding a custom data source.

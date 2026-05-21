# `query_cache_module` — Base (stub)

Empty placeholder base. `core.py` has no content; the brick is registered in pyproject and `__init__.py` re-exports `core`, but no application is mounted.

Likely the seed of a non-HTTP (importable-library) interface to query-cache functionality, kept around so a future project can compose `query_cache_module` directly instead of going through `query_cache_restapi`. Until that lands, treat this as scaffolding.

For the actually-deployed HTTP cache, see [`../query_cache_restapi/`](../query_cache_restapi/).

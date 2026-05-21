# `query_cache_read` — Component (stub)

Empty placeholder brick. `core.py` has no content.

Intended to host the future read-side interface for the Query Cache — once the cache's MongoDB-specific code in [`query_cache_service`](../query_cache_service/) is split into an abstract read protocol plus per-store implementations ([`query_cache_read_store_mongodb`](../query_cache_read_store_mongodb/), [`query_cache_read_store_in_memory`](../query_cache_read_store_in_memory/)). Until that refactor lands, this brick is scaffolding only — the cache still talks to Mongo directly via `query_cache_service`.

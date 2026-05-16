# `mongodb_connection` — Component

MongoDB client factory. Reads connection settings from environment and returns a `Database` handle ready for use. Sync and async variants are provided since the cache service uses both.

## Public surface

```python
from lif.mongodb_connection import get_database, get_database_async
```

Both honor `MONGODB_URI`, `MONGO_DB`, and `MONGO_COLLECTION` env vars.

## Used by
- `components/lif/query_cache_service` — single consumer today; this component exists to keep the Mongo coupling in one place so the eventual cache-read refactor (see [`query_cache_read`](../query_cache_read/) and siblings) has a clean swap point.

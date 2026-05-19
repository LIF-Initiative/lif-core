# `query_cache_service` — Component

Core cache logic for the LIF Query Cache. Implements the four cache operations (`query`, `update`, `add`, `save`) against MongoDB, including the MongoDB-specific update operator construction (`$set` / `$push` / etc.) that handles LIF's array-heavy data model.

## Public surface

```python
from lif.query_cache_service.core import query, update, add, save
```

| Function | Purpose |
|---|---|
| `async query(lif_query) -> List[LIFRecord]` | Read records matching a `LIFQuery` filter; projects selected fields |
| `async update(lif_update) -> LIFRecord` | Apply a `LIFUpdate` (filter + input pairs) to one record |
| `async add(lif_record) -> LIFRecord` | Insert a fresh `LIFRecord` |
| `async save(lif_query_filter, lif_fragments)` | Bulk merge fragments into a record selected by filter |

Helper functions (`clean_projection`, `extract_filter`, `build_mongo_update_ops`, `format_push_ops`, `extract_updated_fields`) are internal but exported for tests.

## Implementation notes

MongoDB is hard-coded today. The empty stub bricks [`query_cache_read`](../query_cache_read/), [`query_cache_read_store_in_memory`](../query_cache_read_store_in_memory/), and [`query_cache_read_store_mongodb`](../query_cache_read_store_mongodb/) are scaffolding for a future refactor that would extract the read interface and swap in alternative stores. Until that lands, this component owns the Mongo coupling directly.

## Used by
- `bases/lif/query_cache_restapi` — mounts these functions as HTTP endpoints

# `openapi_schema_parser` — Component

Walks a LIF OpenAPI schema and emits its "leaves" — the scalar attribute paths semantic search can match against. A leaf is a field like `person.Name.firstName` (entity-PascalCase + scalar-camelCase, per [`docs/specs/data-model-rules.md`](../../../docs/specs/data-model-rules.md)).

## Public surface

```python
from lif.openapi_schema_parser import load_schema_leaves
```

`load_schema_leaves(schema)` returns the full list of dotted paths plus their type metadata. Callers wrap the result into something searchable (typically Sentence-Transformers embeddings).

## Used by
- `components/lif/semantic_search_service` — uses leaves as the corpus for semantic matching
- `components/lif/schema_state_manager` — caches the parsed leaves alongside the raw schema

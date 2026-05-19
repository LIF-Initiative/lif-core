# `composer` — Component

Merges LIF fragments back into a `LIFRecord`. Used by the cache to assemble the final record returned to callers from many small fragment writes (one per data source, one per orchestration job).

## Public surface

```python
from lif.composer import compose_with_single_fragment, compose_with_fragment_list
```

| Function | Purpose |
|---|---|
| `compose_with_single_fragment` | Apply one `LIFFragment` to a base record |
| `compose_with_fragment_list` | Apply many fragments at once; order matters when they overlap |

Composition is path-driven: a fragment with `fragment_path = "person.Name"` is merged at that location. Path syntax follows the PascalCase/camelCase rules documented in [`docs/specs/data-model-rules.md`](../../../docs/specs/data-model-rules.md).

## Used by
- `components/lif/query_cache_service` — fragments arrive piecemeal; the composer stitches them into a complete record

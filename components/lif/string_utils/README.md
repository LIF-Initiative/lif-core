# `string_utils` — Component

Case-conversion and identifier-sanitization helpers used wherever LIF's PascalCase/camelCase data model rules need to be applied programmatically — typically when building GraphQL types from an OpenAPI schema or constructing semantic-search field paths.

## Public surface

```python
from lif.string_utils import (
    safe_identifier,
    to_pascal_case, to_snake_case, to_camel_case,
    camelcase_path,
    dict_keys_to_snake, dict_keys_to_camel,
    convert_dates_to_strings,
    to_value_enum_name,
)
```

| Function | What it does |
|---|---|
| `safe_identifier(s)` | Sanitize an arbitrary string into a valid Python/GraphQL identifier |
| `to_pascal_case(s)` / `to_camel_case(s)` / `to_snake_case(s)` | Self-explanatory |
| `camelcase_path(dotted)` | Apply camelCase to each segment of a dotted path |
| `dict_keys_to_snake(d)` / `dict_keys_to_camel(d)` | Recursive case conversion of dict keys |
| `convert_dates_to_strings(obj)` | Serializes `date` / `datetime` for JSON callers |
| `to_value_enum_name(value)` | Generates a stable enum member name from an arbitrary value |

See [`docs/specs/data-model-rules.md`](../../../docs/specs/data-model-rules.md) for *which* case applies *where* (entities vs scalars vs enums).

## Used by
- `components/lif/openapi_to_graphql` — generating Strawberry types
- `components/lif/semantic_search_service` — building search corpus paths

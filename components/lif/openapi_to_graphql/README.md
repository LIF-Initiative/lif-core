# `openapi_to_graphql` — Component

Generates a Strawberry GraphQL schema dynamically from a LIF OpenAPI schema. The whole point of this component is that the GraphQL API has no hand-written `.graphql` schema files — types, input filters, enums, and root queries are all constructed at runtime from whatever the MDR currently serves.

## Layout

| File | Contents |
|---|---|
| `core.py` | `generate_graphql_schema`, `generate_graphql_root_types` — top-level entrypoints |
| `type_factory.py` | Builds Strawberry types from OpenAPI schema definitions |
| `schema_tools.py` | Schema-traversal utilities (find references, resolve `$ref`, etc.) |

## Public surface

```python
from lif.openapi_to_graphql import generate_graphql_schema, generate_graphql_root_types
from lif.openapi_to_graphql import schema_tools
```

## Notes

- **`$ref` resolution:** MDR's `generate_openapi_schema` inlines all `$ref`s, so the `$ref` branch in `type_factory.py` exists but isn't exercised by production schemas. Don't delete it — file-based schemas (`USE_OPENAPI_DATA_MODEL_FROM_FILE=true`) still rely on it.
- **Strawberry `info` typing:** dynamic resolvers must annotate the `info` parameter as `strawberry.types.Info` (not `object` / `Any`). Strawberry 0.297+ identifies the parameter by type, not by name.
- **Field name preservation:** uses `strawberry.field(name=field_name)` so the wire shape preserves PascalCase entity / camelCase scalar conventions ([`docs/specs/data-model-rules.md`](../../../docs/specs/data-model-rules.md)).

## Used by
- `bases/lif/api_graphql` — single consumer; the GraphQL service's whole reason for existing is this component.

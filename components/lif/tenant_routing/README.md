# `tenant_routing` — Component

Pure functions that map Cognito group names to Postgres schema names + decide which schema a request should route to. The MDR auth middleware reads from here on every request to set `SET search_path` for the DB session.

## Public surface

```python
from lif.tenant_routing import (
    MAX_GROUP_NAME_LEN,
    SCHEMA_PREFIX,
    resolve_tenant_schema,
    sanitize_group_name,
    tenant_schema_for_group,
)
```

| Symbol | Purpose |
|---|---|
| `sanitize_group_name(name)` | Strips/normalizes a Cognito group name into a valid PG identifier component (or `None` if it sanitizes to empty) |
| `tenant_schema_for_group(name)` | Returns `tenant_<sanitized>` or `None` |
| `resolve_tenant_schema(enabled, is_service_principal, cognito_groups, service_schema)` | The full resolution logic — service principals route to `service_schema`; users route to their first group's `tenant_<group>`; group-less users fall back to `service_schema` |
| `SCHEMA_PREFIX` | `"tenant_"` |
| `MAX_GROUP_NAME_LEN` | `128` — matches Cognito's own group name limit |

## Why pure functions

These rules need to match exactly between the auth middleware (Python) and the Flyway-installed `clone_lif_schema()` Postgres function. Keeping the Python side as pure, testable functions makes it easy to verify the two implementations agree.

## Used by
- `components/lif/mdr_auth/core.py` — middleware sets `request.state.tenant_schema` per request
- `components/lif/mdr_services/tenant_service.py` — `provision_tenant` uses this to compute the target schema before calling `clone_lif_schema`

## See also
[`docs/design/cross-cutting/self-serve-tenant-auth.md`](../../../docs/design/cross-cutting/self-serve-tenant-auth.md) for the full schema-per-tenant story (issue #883).

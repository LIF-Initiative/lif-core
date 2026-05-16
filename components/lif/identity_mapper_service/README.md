# `identity_mapper_service` — Component

Business logic for mapping a person's identifiers across source systems. Owns the rules for creating, listing, and deleting `IdentityMapping`s without knowing how they're stored.

## Public surface

```python
from lif.identity_mapper_service.core import IdentityMapperService
```

`IdentityMapperService` is constructed with an `IdentityMapperStorage` (the interface in [`identity_mapper_storage`](../identity_mapper_storage/)) and operates against it. This split lets the same business logic work over an in-memory store for tests and a SQL store ([`identity_mapper_storage_sql`](../identity_mapper_storage_sql/)) in production.

## Used by
- `bases/lif/identity_mapper_restapi` — instantiates one service per app + dispatches HTTP handlers to it

# `identity_mapper_storage` — Component

Storage interface for `IdentityMapping`s. Defines the abstract contract that the identity mapper service depends on, separate from any concrete database implementation.

## Public surface

```python
from lif.identity_mapper_storage.core import IdentityMapperStorage
```

`IdentityMapperStorage` is the abstract base class. Concrete implementations live in sibling bricks; the only one in tree is [`identity_mapper_storage_sql`](../identity_mapper_storage_sql/) (SQLAlchemy/MariaDB).

The split exists so the identity mapper service can be tested against an in-memory or fake implementation without spinning up a database — and so a future swap to a different backend (Postgres, Redis, etc.) wouldn't require touching service logic.

## Used by
- `bases/lif/identity_mapper_restapi` — declares the interface type for lifecycle injection
- `components/lif/identity_mapper_storage_sql` — implements the interface
- `components/lif/identity_mapper_service` (transitively, via the base)

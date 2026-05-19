# `identity_mapper_storage_sql` — Component

SQL-backed implementation of [`identity_mapper_storage`](../identity_mapper_storage/). Uses SQLAlchemy against a MariaDB instance (deployed as `projects/lif_identity_mapper_mariadb/`).

## Layout

| File | Contents |
|---|---|
| `core.py` | `IdentityMapperSqlStorage` — the concrete `IdentityMapperStorage` impl |
| `model.py` | SQLAlchemy ORM model for the mapping table |
| `crud.py` | Low-level CRUD helpers used by `core` |
| `db.py` | Engine/session factory (`initialize_database`, `get_db_session_factory`, `dispose_db_engine`) |

## Public surface

```python
from lif.identity_mapper_storage_sql.core import IdentityMapperSqlStorage
from lif.identity_mapper_storage_sql.db import (
    initialize_database, get_db_session_factory, dispose_db_engine,
)
```

`db.py`'s lifecycle helpers are called by the base's `lifespan` handler — engine initialization is per-app, not per-request.

## Used by
- `bases/lif/identity_mapper_restapi` — instantiates the SQL storage and threads it into the service

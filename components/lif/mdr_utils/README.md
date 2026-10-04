# `mdr_utils` — Component

Utility plumbing for the MDR API: settings, database setup, logging, pagination, SQL helpers. MDR-internal — other services have their own utility modules (`lif.logging`, `lif.lif_schema_config`, etc.) and shouldn't import from here.

## Layout

| File | What it provides |
|---|---|
| `config.py` | `Settings` (`pydantic_settings.BaseSettings`) + `get_settings()` — all MDR env vars including CORS, auth, tenant routing, workspace cookie, invite tokens |
| `database_setup.py` | SQLAlchemy async engine, `get_session()` dependency, lifecycle management |
| `logger_config.py` | `get_logger(__name__)` — MDR's logger format (note: other services use `lif.logging` with a slightly different format) |
| `collection_utils.py` | `convert_csv_to_set` and similar CSV-string parsing helpers |
| `pagination_util.py` | Pagination helpers for list endpoints |

## Public surface

```python
from lif.mdr_utils.config import get_settings
from lif.mdr_utils.database_setup import get_session
from lif.mdr_utils.logger_config import get_logger
```

These three are the most-used entrypoints.

## Used by
- `bases/lif/mdr_restapi` — every endpoint, plus `core.py` (CORS / app setup)
- `components/lif/mdr_services` — services pull `get_session` and `get_logger`
- `components/lif/mdr_auth` — pulls `get_settings`, `get_logger`, `convert_csv_to_set`

## Removed

`sql_util.py`, `yaml_util.py`, `error_handling.py` and `sql_config.yaml` were a
self-contained psycopg2 raw-SQL path with no callers anywhere in the repo, plus
the helpers only they used. MDR queries through the SQLAlchemy async session
(`database_setup.get_session`) instead. `database_setup.get_db_connection`, which
only `run_sql` called, went with them. Removed in #1278.

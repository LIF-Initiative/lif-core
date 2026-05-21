# `mdr_utils` — Component

Utility plumbing for the MDR API: settings, database setup, logging, pagination, SQL helpers. MDR-internal — other services have their own utility modules (`lif.logging`, `lif.lif_schema_config`, etc.) and shouldn't import from here.

## Layout

| File | What it provides |
|---|---|
| `config.py` | `Settings` (`pydantic_settings.BaseSettings`) + `get_settings()` — all MDR env vars including CORS, auth, tenant routing, workspace cookie, invite tokens |
| `database_setup.py` | SQLAlchemy async engine, `get_session()` dependency, lifecycle management |
| `logger_config.py` | `get_logger(__name__)` — MDR's logger format (note: other services use `lif.logging` with a slightly different format) |
| `collection_utils.py` | `convert_csv_to_set` and similar CSV-string parsing helpers |
| `error_handling.py` | Common HTTPException helpers and error envelope shapes |
| `pagination_util.py` | Pagination helpers for list endpoints |
| `sql_util.py`, `sql_config.yaml` | SQL query templates and config-driven query construction |
| `yaml_util.py` | YAML loader helpers (used by SQL config and seed-data loaders) |

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

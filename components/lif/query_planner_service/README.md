# `query_planner_service` — Component

Business logic for the LIF Query Planner. Decides *how* to fulfill a `LIFQuery`: which information sources to hit, what comes from cache vs. fresh orchestration, which translations to apply. Manages in-memory job state for async queries.

## Public surface

```python
from lif.query_planner_service.core import (
    LIFQueryPlannerService,
    LIFQueryPlannerJob,
    prune_job_store,
    add_job_to_store,
    # ...
)
from lif.query_planner_service.datatypes import (
    LIFQueryPlannerConfig,
    LIFQueryPlannerInfoSourceConfig,
    LIFQueryPlannerPartialRecords,
)
from lif.query_planner_service import util
```

## Layout

| File | Contents |
|---|---|
| `core.py` | `LIFQueryPlannerService` (the planner), `LIFQueryPlannerJob` (async job state), in-memory job store helpers |
| `datatypes.py` | Planner-specific config models (`LIFQueryPlannerConfig`, `LIFQueryPlannerInfoSourceConfig`) and `LIFQueryPlannerPartialRecords`, which `run_query` returns in place of a plain list when it answers from cache without the requested fields (#1232) |
| `util.py` | Cross-cutting helpers used by `core` (fragment-shaping helpers now live in [`lif_fragment_utils`](../lif_fragment_utils/)) |

## Configuration

The planner is configured per-organization via YAML — `deployments/*/information_sources_config*.yml`. One planner instance runs per org in the reference deployment.

## Used by
- `bases/lif/query_planner_restapi` — mounts the service behind HTTP endpoints

# `orchestrator_service` — Component

Business logic for the LIF Orchestrator. Fans out a query plan across the configured data-source adapters, collects responses, runs translations, and merges results back into a unified `OrchestratorJob`.

## Public surface

```python
from lif.orchestrator_service.service import OrchestratorService
from lif.orchestrator_service import core
```

`OrchestratorService` is the entrypoint — the orchestrator HTTP base instantiates one at app startup (in its lifespan handler) and reuses it across requests.

## Layout

| File | Contents |
|---|---|
| `core.py` | Imports / re-exports surface; small helpers |
| `service.py` | `OrchestratorService` — submits jobs, tracks state, dispatches to adapters via `orchestrator_clients` |

## Used by
- `bases/lif/orchestrator_restapi` — mounts the service behind HTTP endpoints
- `components/lif/orchestrator_clients` — clients call back into the service when reporting job results

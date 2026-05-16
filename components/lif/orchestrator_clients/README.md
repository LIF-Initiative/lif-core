# `orchestrator_clients` — Component

Client implementations the [`orchestrator_service`](../orchestrator_service/) uses to talk to actual orchestration backends. The factory pattern lets a single orchestrator HTTP service drive different backends without code changes in the service layer.

## Layout

| File | Contents |
|---|---|
| `core.py` | Re-exports for the brick's public surface |
| `factory.py` | `OrchestratorFactory`, `OrchestratorNotFoundError` — chooses a client by backend id |
| `dagster.py` | Dagster-specific client implementation |

Today Dagster is the only backend in tree. Adding another (Airflow, Prefect, etc.) means a new sibling file plus a factory registration.

## Public surface

```python
from lif.orchestrator_clients.factory import OrchestratorFactory, OrchestratorNotFoundError
```

The factory looks up a client by id and returns an instance configured against the service's settings.

## Used by
- `components/lif/orchestrator_service` — `service.py` and `core.py` use the factory to obtain a client

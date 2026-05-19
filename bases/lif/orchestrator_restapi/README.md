# `orchestrator_restapi` — Base

FastAPI base for the LIF Orchestrator: receives query plans from the Query Planner, fans out to the configured data-source adapters, gathers + normalizes responses. Long-running work is tracked as `OrchestratorJob`s the caller polls.

## Endpoints
- `POST /jobs`             — submit an `OrchestratorJobRequest`; returns a job id (`OrchestratorJobRequestResponse`)
- `GET  /jobs/{job_id}`    — fetch current `OrchestratorJob` state
- `GET  /health`

A `DELETE /jobs/{job_id}` and `GET /jobs/{job_id}/result` are commented out in `core.py` — they were considered and deferred.

## Composes
- `datatypes` — `OrchestratorJob` request/response shapes
- `logging`
- `orchestrator_service` — actual fan-out, adapter dispatch, response merging

## Deployed as
`projects/lif_orchestrator_api/`

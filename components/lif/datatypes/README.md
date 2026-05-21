# `datatypes` — Component

Core Pydantic models that flow through the LIF data plane. Every service that handles LIF records, queries, or jobs imports from here. Single source of truth for the wire shapes — bases don't define their own.

## Layout

| File | Contents |
|---|---|
| `core.py` | `LIFRecord`, `LIFPerson`, `LIFFragment`, `LIFQuery`, `LIFQueryFilter`, `LIFUpdate`, `LIFQueryPlan*`, `LIFPersonIdentifier(s)`, `LIFQueryStatusResponse`, `LIFQueryPlanPartTranslation`, `HealthCheckResponse`, `TargetTransformationDataModel(s)DTO` |
| `identity_mapping.py` | `IdentityMapping` |
| `mdr_sql_model.py` | SQLModel-style classes used by MDR persistence |
| `orchestration.py` | `OrchestratorJob`, `OrchestratorJobDefinition`, `OrchestratorJobRequest`, request/response wrappers |

## Naming convention

Models follow the PascalCase/camelCase split documented in [`docs/specs/data-model-rules.md`](../../../docs/specs/data-model-rules.md): entities (containers) are PascalCase, scalars are camelCase. Many models use `populate_by_name=True` with `alias="EntityName"` so they accept either case on input but normalize internally.

## Used by
Practically everything: every REST base, the cache and planner services, the orchestrator, the translator, and the MDR services. Changes here ripple widely; treat additions as a stable-API extension.

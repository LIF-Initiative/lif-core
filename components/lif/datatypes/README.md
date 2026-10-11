# `datatypes` — Component

Core Pydantic models that flow through the LIF data plane. Every service that handles LIF records, queries, or jobs imports from here. Single source of truth for the wire shapes — bases don't define their own.

## Layout

| File | Contents |
|---|---|
| `core.py` | `LIFRecord`, `LIFPerson`, `LIFFragment`, `LIFQuery`, `LIFQueryFilter`, `LIFUpdate`, `LIFQueryPlan*`, `LIFPersonIdentifier(s)`, `LIFQueryStatusResponse`, `LIFQueryPlanPartTranslation`, `HealthCheckResponse`, `TargetTransformationDataModel(s)DTO` |
| `identity_mapping.py` | `IdentityMapping` |
| `orchestration.py` | `OrchestratorJob`, `OrchestratorJobDefinition`, `OrchestratorJobRequest`, request/response wrappers |

MDR-specific persistence/consumer models used to live here (`mdr_sql_model.py`, `mdr_consumer.py`) but have moved to [`mdr_sql_model`](../mdr_sql_model/) and [`mdr_dto`](../mdr_dto/) respectively, so that services which only need core LIF types don't have to pull in MDR's SQLAlchemy/SQLModel dependency.

## Naming convention

Models follow the PascalCase/camelCase split documented in [`docs/specs/data-model-rules.md`](../../../docs/specs/data-model-rules.md): entities (containers) are PascalCase, scalars are camelCase. Many models use `populate_by_name=True` with `alias="EntityName"` so they accept either case on input but normalize internally.

## Used by
Practically everything: every REST base, the cache and planner services, the orchestrator, the translator, and the MDR services. Changes here ripple widely; treat additions as a stable-API extension.

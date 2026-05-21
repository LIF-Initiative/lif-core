# `identity_mapper_restapi` — Base

FastAPI base for the LIF Identity Mapper: stores mappings between a person's identifiers across source systems (e.g., SIS ID ↔ LMS ID ↔ HR ID). Required when a single learner shows up under different identifiers in different systems and the orchestrator needs to know they're the same person.

## Endpoints
Identity mappings are scoped per `{org_id}/{person_id}`:

- `POST   /organizations/{org_id}/persons/{person_id}/mappings`                  — create a new `IdentityMapping`
- `GET    /organizations/{org_id}/persons/{person_id}/mappings` (and variants)   — list / fetch mappings
- `DELETE /organizations/{org_id}/persons/{person_id}/mappings/{mapping_id}`     — delete a mapping (204 on success)

Plus exception handlers translating `DataNotFoundException`, `LIFException`, and validation errors into stable HTTP responses.

## Storage
Backed by SQL (MariaDB in the reference deployment) via `identity_mapper_storage_sql`. The storage layer is pluggable through the `IdentityMapperStorage` interface; SQLAlchemy is the only implementation today.

## Composes
- `datatypes` — `IdentityMapping`
- `exceptions`
- `identity_mapper_service` — business logic
- `identity_mapper_storage` — storage interface
- `identity_mapper_storage_sql` — SQLAlchemy-backed implementation
- `logging`

## Deployed as
`projects/lif_identity_mapper_api/` (the API) + `projects/lif_identity_mapper_mariadb/` (the database)

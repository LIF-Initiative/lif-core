# `identity_mapper_restapi` — Base

FastAPI base for the LIF Identity Mapper: stores mappings between a person's identifiers across source systems (e.g., SIS ID ↔ LMS ID ↔ HR ID). Required when a single learner shows up under different identifiers in different systems and the orchestrator needs to know they're the same person.

## Endpoints
Identity mappings are scoped per `{org_id}/{person_id}`:

- `POST   /organizations/{org_id}/persons/{person_id}/mappings`                  — create a new `IdentityMapping`
- `GET    /organizations/{org_id}/persons/{person_id}/mappings` (and variants)   — list / fetch mappings
- `DELETE /organizations/{org_id}/persons/{person_id}/mappings/{mapping_id}`     — delete a mapping (204 on success)

A refused `DELETE` answers `404` whether no mapping has that ID or the mapping exists but belongs to a different organization or person. The two are deliberately indistinguishable, so a caller cannot probe IDs to discover which ones are real (#1177); the not-owned case is logged at the server instead.

A `POST` body field wider than its database column (191 for the organization, person and target-system IDs, 100 for the identifier type, 255 for the target-system person ID) is rejected with a `422` naming the field, instead of reaching MariaDB and coming back as a `500`. The limits are read from the SQLAlchemy model, which mirrors `projects/lif_identity_mapper_mariadb/02-ddl.sql` (#1300).

A `POST` that collides with a concurrent save of the same natural key (organization, person, target system, identifier type) is retried once inside the storage layer. If the retry collides too, it answers `409` with a message saying the request may be retried, rather than the `500` given for a datastore failure, and carries no correlation UUID (#1261).

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

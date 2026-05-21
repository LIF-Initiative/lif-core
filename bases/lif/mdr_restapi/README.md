# `mdr_restapi` — Base

FastAPI base for the LIF **Metadata Repository (MDR)**: the control-plane service that holds the LIF schema(s), transformation definitions, value sets, and per-tenant configuration. Most LIF services load their schema and transformation rules from here at startup.

The base is split into many endpoint modules (one per concern) which `core.py` mounts under stable URL prefixes.

## Endpoint groups

| Prefix | Module | What it does |
|---|---|---|
| `/datamodels` | `datamodel_endpoints` | LIF data models — Base LIF, Org LIF, target transformation models |
| `/entities` | `entity_endpoints` | Entity definitions within a data model |
| `/entity_associations` | `entity_association_endpoints` | Entity-to-entity relationships |
| `/attributes` | `attribute_endpoints` | Scalar attributes within entities |
| `/entity_attribute_associations` | `entity_attribute_association_endpoints` | Which attributes belong to which entities |
| `/inclusions` | `inclusions_endpoints` | Reusable attribute groups (e.g., Contact, Address) |
| `/value_sets` + `/value_set_values` | `valueset_endpoint`, `value_set_values_endpoint` | Strict + extensible enumerations |
| `/transformation_groups` | `transformation_endpoint` | JSONata-based source→target transformations |
| `/value_mappings` | `value_mapping_endpoints` | Code/value crosswalks used during transformation |
| `/search` | `search_endpoint` | MDR-wide full-text search |
| `/datamodel_constraints` | `datamodel_constraints_endpoints` | Constraint rules per model |
| `/import_export` | `import_export_endpoints` | Bulk import/export of MDR content |
| `/generate_jinja` | `generate_jinja_endpoint` | Template generation for derived schemas |
| `/tenants` | `tenant_endpoints` | Self-serve tenant lifecycle (#883/#884): provision, workspace listing/selection, invite tokens |

## Auth
`AuthMiddleware` (from `mdr_auth/core`) supports three principals: API-key (services), Cognito JWT (end users), and legacy HS256 JWT (pre-Cognito callers). The middleware also resolves `request.state.tenant_schema` per request based on Cognito groups + optional workspace-selection cookie — see [`docs/design/cross-cutting/self-serve-tenant-auth.md`](../../../docs/design/cross-cutting/self-serve-tenant-auth.md).

## Composes
- `datatypes` — common payload shapes
- `mdr_auth` — auth middleware + JWT/cookie/invite-token helpers
- `mdr_dto` — wire-format DTOs
- `mdr_services` — business logic (tenant_service, transformation_service, etc.)
- `mdr_utils` — config, DB session factory, logger

## Deployed as
`projects/lif_mdr_api/` (API) + `projects/lif_mdr_database/` (Postgres + Flyway migrations).
Frontend: `frontends/mdr-frontend/`.

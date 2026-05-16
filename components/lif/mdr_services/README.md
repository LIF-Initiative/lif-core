# `mdr_services` — Component

Business logic for the MDR API. Each `*_service.py` module owns a slice of MDR functionality and is invoked by the matching endpoint module in `bases/lif/mdr_restapi/`. Services depend on `mdr_dto` for shapes and `mdr_utils` for session/config plumbing, but never on FastAPI directly — they're plain async functions and classes.

## Layout

| File | Concern |
|---|---|
| `attribute_service.py` | Scalar attributes within entities |
| `datamodel_service.py` | LIF data models (Base LIF, Org LIF, target transformation models) |
| `datamodel_constraints_service.py` | Constraint rules per model |
| `entity_service.py` | Entity definitions |
| `entity_association_service.py` | Entity-to-entity relationships |
| `entity_attribute_association_service.py` | Attribute membership in entities |
| `helper_service.py` | Cross-cutting helpers used by multiple services |
| `import_export_service.py` | Bulk import/export of MDR content |
| `inclusions_service.py` | Reusable attribute groups (Contact, Address, etc.) |
| `jinja_helper_service.py`, `jinja_translation_service.py` | Jinja-based template + translation generation |
| `schema_generation_service.py` | Builds OpenAPI schemas from MDR content (the schema `mdr_client` fetches) |
| `schema_upload_service.py` | Accepts a new schema upload and persists it |
| `search_service.py` | MDR-wide full-text search |
| `tag_service.py` | Tagging for entities/attributes |
| `tenant_service.py` | Self-serve tenant lifecycle (#883/#884): `provision_tenant`, exception types |
| `transformation_service.py` | JSONata transformation groups, source→target mappings |
| `value_mapping_service.py` | Code/value crosswalks |
| `valueset_service.py`, `value_set_values_service.py` | Strict + extensible enums |

## Used by
- `bases/lif/mdr_restapi` — every endpoint module imports its matching service

## See also
- [`docs/design/cross-cutting/self-serve-tenant-auth.md`](../../../docs/design/cross-cutting/self-serve-tenant-auth.md) for what `tenant_service.provision_tenant` is doing under the hood (`clone_lif_schema` Postgres function).
- [`docs/specs/data-model-rules.md`](../../../docs/specs/data-model-rules.md) for the schema rules these services enforce.

# `schemas/` — LIF data model source of truth

Canonical JSON definition of the LIF data model and the rules every implementation must honor.

## Files

| File | Purpose |
|---|---|
| `lif-schema.json` | The LIF data model schema — entities, attributes, relationships, allowed value sets, and policy fields (`queryable`, `modifiable`, required-field rules) |

## Relationship to the rest of LIF

- **MDR (Metadata Repository)** is loaded from this schema and then extended by each deployer with org-specific entities. Once MDR is running, it becomes the runtime source of truth for most services — they fetch the schema from MDR (via [`lif.mdr_client`](../components/lif/mdr_client/)) rather than reading this file directly.
- **Seed data** under `projects/mongodb/sample_data/` must validate against the schema MDR serves (which started from this file).
- **GraphQL queries** in `components/lif/data_source_adapters/**/*.graphql` should align with this schema's entity and attribute names.

See [`docs/specs/data-model-rules.md`](../docs/specs/data-model-rules.md) for the human-readable interpretation of the rules — PascalCase entities, camelCase scalars, naming conventions, required-field policies, the No Loss Capture principle, and so on.

## Versioning

The schema evolves via MDR's data-model versioning machinery (`/datamodels` endpoints). Changes that need to land at the file level go through normal PR review; downstream services pick them up after their next MDR refresh.

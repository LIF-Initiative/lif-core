# LIF Metadata Registry (MDR) — Overview

**Audience:** Developers and data engineers evaluating the LIF Metadata Registry for their project, especially those considering it as an alternative or complement to general data catalogs like OpenMetadata.

## What is MDR?

The LIF Metadata Registry (MDR) is a service in the [Learner Information Framework](https://github.com/LIF-Initiative/lif-core) (LIF) that manages data model definitions and the transformation mappings between them. MDR is the source of truth for:

- **LIF data models** — the entities and attributes that describe a learner record (e.g., `Person`, `Contact`, `Identifier`, `EmploymentPreferences`)
- **Source schemas** — lightweight models describing the shape of data returned by upstream systems (e.g., an SIS REST API response)
- **Transformation mappings** — JSONata expressions that translate source-schema records into LIF-shaped records

Downstream LIF services (the Translator, GraphQL API, and semantic search MCP server) load their schemas from MDR at startup, so adding a new data source or evolving the LIF data model does not require changes to service code.

## How MDR Fits in the LIF Pipeline

```
Upstream data source ──► Adapter ──► Source Schema ──► MDR Mappings ──► LIF Data Model
                                    (registered          (JSONata         (served by GraphQL,
                                     in MDR)              expressions)     consumed by Advisor,
                                                                           Translator, MCP)
```

When a new data source is added to a LIF deployment, the integrator:

1. Registers a source schema in MDR describing the upstream data format
2. Draws transformation mappings from that source schema to the target LIF data model
3. Wires the data source into the orchestrator

At runtime, MDR serves the resulting OpenAPI schema and transformation rules to the services that consume them.

## Scope: MDR vs. General Metadata Catalogs

MDR is **purpose-built for LIF's schema-and-transformation flow** — it is not a general-purpose data catalog. If you are coming from OpenMetadata (or similar platforms like DataHub, Amundsen, Atlan), the mental model is quite different.

| Capability | MDR | OpenMetadata |
|---|---|---|
| Data model definition (entities, attributes, types) | Yes — first-class feature | Yes |
| Schema inheritance and extension (base model → org model) | Yes — core design | Partial |
| Transformation rule management (source → target) | Yes — JSONata mappings | No (handled externally) |
| Runtime schema serving via API | Yes — core use case | No |
| Data catalog and cross-system discovery | No | Yes |
| Column-level lineage across systems | No | Yes |
| Data profiling and quality checks | No | Yes |
| Dataset classification / PII tagging | No | Yes |
| Stewardship and collaboration workflows | No | Yes |
| Dashboards, pipelines, and ML model catalog | No | Yes |

**In short:** OpenMetadata is a platform for *cataloging and governing* existing data assets. MDR is a platform for *defining and translating* data models in a runtime data integration pipeline. If the goal is to answer "what data do we have, where does it live, and who owns it," OpenMetadata is the right fit. If the goal is to define a canonical data model and translate between it and a set of upstream source systems at runtime, MDR is a better match.

The two are not mutually exclusive — OpenMetadata could serve as the organizational data catalog while MDR serves as the runtime schema registry for a specific data integration pipeline.

## Data Model Concepts

MDR organizes data models into three tiers:

- **Base LIF** — the canonical, shared LIF data model. Not modified by deployers.
- **Org LIF** — a deployment's working data model. Extends Base LIF and can add organization-specific entities and attributes.
- **Source schemas** — lightweight models describing external data sources; each is mapped into the Org LIF model via JSONata expressions.

Entities and attributes carry dot-path unique names (e.g., `person.contact.address.city`) and can be marked as arrays or scalars. Only attributes (leaf fields) participate in mappings.

## Architecture

- **MDR API** — FastAPI service backed by PostgreSQL (Aurora in AWS deployments). Serves data models and mappings via REST; exports OpenAPI schemas for runtime consumption by other services.
- **MDR Frontend** — React/TypeScript single-page app for visually defining entities, attributes, and mappings. Deployed to S3 + CloudFront in AWS environments.
- **Authentication** — currently a small set of hardcoded demo users. Self-serve Cognito registration with per-tenant PostgreSQL schema isolation is in design (see `docs/proposals/mdr-self-serve-registration.md`).

## Try It

A live demo environment is available for evaluation. It is pre-seeded with:

- The **Base LIF** reference data model
- A sample **Org LIF** model that extends Base LIF
- Example source schemas and JSONata mappings for the reference data sources

**Demo access, credentials, and video walkthroughs are available on request** — contact the LIF team (see below). Short video walkthroughs covering the MDR UI, data model definition, and transformation mappings exist but are shared privately.

A suggested first walkthrough once you have access:

1. **Data Models tab** — open the Base LIF model and browse the `Person` entity and its nested structures (`Name`, `Contact`, `Identifier`, etc.)
2. **Data Models tab** — switch to the Org LIF model and note how it extends Base LIF with organization-specific fields
3. **Source schema** — open one of the example source schemas to see how an upstream system is described in MDR
4. **Mappings tab** — inspect the JSONata mappings that translate a source schema into the Org LIF model
5. **API export** — call `/datamodels/open_api_schema/{id}` on the MDR API to see how services consume MDR at runtime

## Learn More

- **Source code:** [LIF-Initiative/lif-core](https://github.com/LIF-Initiative/lif-core). MDR lives under `bases/lif/mdr_restapi/` (API) and `frontends/mdr-frontend/` (UI).
- **MDR design document:** [`docs/design/components/mdr.md`](../design/components/mdr.md)
- **LIF schema source of truth:** `schemas/lif-schema.json` in the repo
- **Add a data source walkthrough:** [`docs/operations/guides/add-data-source.md`](../operations/guides/add-data-source.md) — step-by-step guide covering source schema creation, JSONata mappings, and pipeline wiring
- **Data source adapter reference:** [`docs/operations/guides/creating-a-data-source-adapter.md`](../operations/guides/creating-a-data-source-adapter.md) — what an adapter is, how it consumes MDR schemas at runtime
- **Self-serve registration proposal:** `docs/operations/proposals/mdr-self-serve-registration.md` — planned multi-tenant evolution with Cognito and per-tenant schema isolation *(currently untracked; will be relocated when committed)*
- **LIF services overview:** [`docs/overview/services-overview.md`](services-overview.md) — how MDR fits alongside the other LIF services

## Contact

For demo access, credentials, video walkthroughs, or questions about MDR's fit for your use case, reach out to the LIF team maintainer listed in the repository `README.md` or `COMMITTERS.md`.

# 3. The data model and the MDR

What a LIF data model is, where it lives (the MDR), how services use it, and how mappings turn other standards into LIF.

*Checked against main `2967cb9`, November 2026.* The model list, activation state and generated schema were read from a freshly
seeded local MDR.

---

## The idea

A LIF record is one JSON document per learner. Its shape is not hard-coded anywhere in the services.
It's a **data model** stored in the **MDR** (Metadata Repository), and every service that needs the
shape loads it from the MDR when it starts:

- the GraphQL API generates its whole GraphQL schema from it ([chapter 4](04-follow-the-data.md), step 1),
- the Translator validates input and output against it,
- the semantic search server indexes it.

So "add a field to LIF" is mostly an MDR change, not a code change. Change the model, restart the
services, and the new field is queryable.

## The parts of a model

These are the MDR's tables (`components/lif/mdr_sql_model/`), in the order you'll meet them:

| Concept | Table | What it is |
|---|---|---|
| **Data model** | `DataModels` | A named, versioned schema: `Name`, `DataModelVersion`, `ContributorOrganization` |
| **Entity** | `Entities` | An object type: `Person`, `Contact`, `Course` |
| **Attribute** | `Attributes` | A scalar field: `firstName`, `identifierType` |
| **Entity–attribute association** | `EntityAttributeAssociation` | Puts an attribute on an entity |
| **Entity association** | `EntityAssociation` | Puts an entity under another (`Contact` under `Person`). It has a **`Name`**, which is the key you see in the record, and an **`Array`** flag (a list or a single object) |
| **Value set / value** | `ValueSets`, `ValueSetValues` | Allowed values for an attribute (an enumeration) |
| **Constraint** | `Constraints` | Extra rules on attributes |

Flags on attributes and entities control what the services expose. The two you'll see most in the
generated schema are **`x-queryable`** (can be used in a GraphQL `filter`) and **`x-mutable`** (can be
changed by a GraphQL mutation).

### The case rule

Entities and anything that holds them are **PascalCase** (`Person`, `Contact`, `EmploymentPreferences`);
scalar attributes are **camelCase** (`firstName`, `identifierType`). This isn't style: stored documents,
GraphQL fields, the planner's fragment paths (`Person.Contact`) and the query files all use it, and a
wrong-case path silently matches nothing. The full rule: [`docs/specs/data-model-rules.md`](../../specs/data-model-rules.md).

## The models in the seed

The local MDR is seeded from `projects/lif_mdr_database/backup.sql`. It holds 21 live models:

| Id | Name | Type | What it's for |
|---|---|---|---|
| 1 | LIF | `BaseLIF` | The base LIF model |
| 17 | StateU LIF | `OrgLIF` (built on 1) | **What the services load locally**: the demo organization's LIF |
| 18 | Org2 LIF | `PartnerLIF` (built on 1) | Another organization's LIF |
| 2–16, 29 | HR Open, CLR v2, CEDS v14, Ed-Fi v5, CTDL, Open Badges v2/v3, … | `SourceSchema` | Other standards, kept so they can be mapped to LIF |
| 26 | R1 Demo Source Data Model | `SourceSchema` | The example source system's shape ([chapter 4](04-follow-the-data.md)'s translation) |
| 25 | Test2UpdatedSourceModel | `SourceSchema` | Test data |

The GraphQL API, semantic search and the Learner Data Export API pick their model by **name, version and
contributor organization**, not by Id. The Translator works by Id: its caller passes the source and target
Ids in the URL (the planner's sources config sends 26 → 17). In the compose file: `OPENAPI_DATA_MODEL_NAME=StateU LIF`, `OPENAPI_DATA_MODEL_VERSION=1.0`,
`OPENAPI_DATA_MODEL_CONTRIBUTOR_ORGANIZATION=StateU`.

### Overlays are on their way out (dev: converted; demo and the local seed: not yet, #1513)

Models 17 and 18 are **overlays** on demo and in the local seed, and were on dev until #1388: they build
on model 1 and add or include parts of it, rather than holding everything themselves. ADR data_model/0004
([`docs/design/adr/data_model/0004-retire-overlays-variants-as-copies.md`](../../design/adr/data_model/0004-retire-overlays-variants-as-copies.md), Accepted) retires this:

- every model will be **self-contained**, with one kind of model instead of four types;
- a variant of a model is a **copy**, and **schema diff** shows how two models differ;
- 17 and 18 are converted once, in place, so they produce the same schema as before (#1388, done:
  `scripts/convert_overlays.py`, #1489). The conversion is applied on dev, in all 10 schemas. Demo isn't
  converted yet, and the local seed (`projects/lif_mdr_database/backup.sql`) still has 17 and 18 as
  overlays; #1513 converts both.

Older docs and ADRs (metadata_repository/0004, 0008; data_model/0002) describe the overlay model:
inclusions, extensions, Org LIF vs Partner LIF. Read them as history.

**What that means on an overlay (demo and the local seed, until #1513).** Model 17 shows only what it *includes* from
model 1, plus its own *extensions*:

- Entities like `Person` and `Name` are defined in model 1 (`Entities.DataModelId = 1`). Model 17 includes
  37 of model 1's entities and 169 of its attributes (`ExtInclusionsFromBaseDM`), not all of them: model 1's
  `Name` has 18 attributes, and model 17's generated `Name` has 6.
- Some entities exist only in 17, as extensions: `EmploymentPreferences` is one.
- So a field added to model 1 doesn't appear in the services until model 17 also includes it. A field
  added to model 17 as an extension appears directly.

**The rule: on dev, model 17 holds everything itself and is edited directly. On the local seed, add new
fields to model 1, then include them in model 17** ([chapter 7](07-recipes.md) has the steps).

### Two schema files you'll find in the repo

- `reference_data/schemas/lif-schema.json`: the canonical LIF schema the MDR's base model was loaded
  from. [`CLAUDE.md`](../../../CLAUDE.md) calls it the source of truth; at runtime the MDR is.
- `components/lif/mdr_client/resources/openapi_constrained_with_interactions.json`: a snapshot of a
  generated schema, used only when `USE_OPENAPI_DATA_MODEL_FROM_FILE=true` (development or offline
  tests). It doesn't follow MDR changes.

## Looking at a model

**The generated schema** is what services actually consume: an OpenAPI document with one entry per
entity. Locally, with the GraphQL API's service key from the compose defaults:

```bash
curl -s -H "X-API-Key: changeme1" "http://localhost:8012/datamodels/open_api_schema/17?include_attr_md=true" | jq '.components.schemas.Person.properties | keys'
```

(The MDR requires auth: without the header you get `401`. Each service has its own key, set by
`MDR__AUTH__SERVICE_API_KEY__*` on the MDR and `LIF_MDR_API_AUTH_TOKEN` on the service.)

**The MDR UI** (`frontends/mdr-frontend`, see the frontend handbook) shows models, mappings and
transformations, and is the usual way to edit them. [`docs/operations/guides/test-driving-mdr.md`](../../operations/guides/test-driving-mdr.md) runs the
MDR on its own; [`docs/operations/guides/mdr-guide.md`](../../operations/guides/mdr-guide.md) is a user's guide to it.

## Mappings: turning another standard into LIF

A **transformation group** maps one model to another, for example *R1 Demo Source Data Model* (26) to
*StateU LIF* (17). It holds one **transformation** per target field: a **JSONata** expression that builds
that field from the source.

| Concept | Table | What it is |
|---|---|---|
| Transformation group | `TransformationsGroup` | Source model → target model, with a `GroupVersion` and an **`ActivationDate`** |
| Transformation | `Transformations` | One mapping: a target path and a JSONata expression |
| Transformation attribute | `TransformationAttributes` | The source and target attributes it touches |

Two rules decide what the Translator uses ([chapter 4](04-follow-the-data.md), step 7a):

- **Only an active group counts** (#1350). It needs an `ActivationDate` that isn't in the future and no
  past `DeprecationDate`. A group without one is a draft. If a pair has several active versions, the
  latest wins; versions are never merged.
- **Paths are written with association names** (ADR metadata_repository/0010): a top-level entity, then
  the `Name` of each association down to the attribute.

To learn JSONata as used here: [`docs/operations/guides/jsonata-quick-start-guide.md`](../../operations/guides/jsonata-quick-start-guide.md).

> **`reference_data/transformations/` is a mirror, not the source.** The running transformations live in
> the MDR. Edit them there, or go through `scripts/import-transformations.sh`. Editing the files directly
> makes the repo disagree with what's running (#1127/#1128).

## Moving models between MDRs

Models and mapping groups can be exported to and imported from **portable files** (`/portable/*`
endpoints, `components/lif/mdr_portability/`). The format is specified in
[`docs/specs/mdr-portable-file-format.md`](../../specs/mdr-portable-file-format.md). That spec still calls itself a draft, but it is implemented.

## Tenants

The MDR keeps each workspace's data in its own Postgres schema: `public` for the shared seed, and
`tenant_<name>` schemas created by self-serve sign-up (the seed includes `tenant_lif_team`). A request
picks a tenant with the `X-API-Tenant-Schema` header (that's what `mdr_client` sends). Most local work
uses `public`. Background: [`docs/design/cross-cutting/self-serve-tenant-auth.md`](../../design/cross-cutting/self-serve-tenant-auth.md) (parts of it are out
of date: the paths under "Where the code lives" and the status table).

## Changing the MDR's own tables

The MDR's database schema changes through **Flyway migrations** in
`sam/mdr-database/flyway/flyway-files/flyway/sql/mdr/V1.*.sql`. Two things to know before you write one
(more in [chapter 7](07-recipes.md)):

- Locally, the restore job (`projects/lif_mdr_database/restore.sh`) loads `backup.sql`, then replays every
  `V1.*.sql` except V1.1 (whose content is already in `backup.sql`) with `psql`, with no Flyway history.
  So **every migration from V1.2 on must be idempotent** (`CREATE OR REPLACE`, `IF NOT EXISTS`). V1.0 is
  replayed too, which is where the two expected errors come from (settings for the team's AWS-hosted database).
- **A migration reaches only the schemas it names.** Tenant data lives in `tenant_*` schemas, so a change
  to the MDR's tables has to loop over `public` and every `tenant_*` schema. V1.7
  (`V1.7__portability_columns.sql`) is the pattern to copy.
- **Merging a migration doesn't apply it** to dev or demo. That is a manual step:
  [`docs/operations/guides/applying-mdr-migrations.md`](../../operations/guides/applying-mdr-migrations.md).

---

## Where to go next

- [`docs/specs/data-model-rules.md`](../../specs/data-model-rules.md): the normative rules (case, arrays, references, required fields).
- [`docs/design/cross-cutting/schema-loading.md`](../../design/cross-cutting/schema-loading.md): how services load the schema, and why they fail loudly
  when the MDR is unreachable.
- [`docs/overview/data-model-guide.md`](../../overview/data-model-guide.md) and [`docs/overview/why-we-created-a-new-data-model.md`](../../overview/why-we-created-a-new-data-model.md): why LIF's
  model looks the way it does.
- [Chapter 7](07-recipes.md) for the recipes: adding a field, a mapping, a migration.

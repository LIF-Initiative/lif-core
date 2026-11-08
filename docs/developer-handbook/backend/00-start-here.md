# LIF backend developer handbook

Start here — what LIF is, how this handbook is organized, and the words you'll meet.

Written for a developer who knows Python and web APIs but is new to LIF, Polylith, the MDR and
Dagster, and has no AWS access. Frontend work has
[its own handbook](../frontend/00-start-here.md).

*Checked against main `2967cb9`, November 2026.*

---

## What LIF is, in one paragraph

LIF (Learner Information Framework) collects what different systems know about a learner (a student
information system, a learning platform, an HR system, another institution) and serves it as **one
record in one standard shape**. The shape is a data model kept in the **MDR**, so it can change without
code changes. A client asks for a learner through a **GraphQL API**. LIF answers from its **cache** if it
can; otherwise it fetches the missing pieces from configured **sources**, translates them into the LIF
shape, stores them, and answers. The why: [`docs/overview/use-cases.md`](../../overview/use-cases.md) and
[`docs/overview/why-we-created-a-new-data-model.md`](../../overview/why-we-created-a-new-data-model.md).

## LIF doesn't require AWS

LIF is a set of containers plus PostgreSQL and MongoDB, and the whole system runs on one machine with
Docker Compose ([chapter 1](01-dev-environment.md)). **To date (November 2026), the team has hosted its
shared dev and demo environments on AWS**, so you'll see AWS names in the repo and in this handbook: ECS,
CloudFormation, SSM, Cognito, S3. That is how we've been deploying for demo purposes, not a requirement
of LIF. The deploy scripts and CloudFormation templates are a reference to adapt, not something an adopter
must use ([`docs/operations/guides/deploying-lif-at-your-institution.md`](../../operations/guides/deploying-lif-at-your-institution.md), #1004).

Two features do use an AWS service directly today, both through Amazon Cognito, and neither is on the
query path:

- the MDR's self-serve sign-up and workspace invites. Without Cognito configured, the MDR and its UI use
  username and password, which is how the local stack runs;
- the control plane's developer-key endpoints (`control_plane_restapi`, still being built under #1041).
  They accept only Cognito tokens, so without Cognito every non-public path answers 401.

Wherever this handbook says "in AWS", read it as "in the team's AWS-hosted demo environments".

## How to read this

Read 1 → 4 in order on your first days; dip into the rest when you need them.

| # | Chapter | Read it when |
|---|---|---|
| 1 | Your development environment | Day one: get the checks and the local stack running |
| 2 | The codebase map | Before your first change: where code lives and how services are assembled |
| 3 | The data model and the MDR | Before touching anything about fields, models or mappings |
| 4 | Follow the data | To understand how the services fit: one query, end to end, with commands to try |
| 5 | Cross-cutting concerns | Auth, configuration, schema loading, timeouts, and what can't be logged |
| 6 | How we work | Before your first PR |
| 7 | Recipes | When you need to add a field, mapping, data source, service, brick or migration |
| 8 | Debugging and traps | When something doesn't work, or before you ship |
| 9 | Environments and deployment | To know what happens after merge |
| 10 | Extending LIF | To run part of LIF on its own, or decide where a new feature plugs in |

**Looking for something specific?**

| I want to… | Go to |
|---|---|
| run the code and the tests | [chapter 1](01-dev-environment.md) |
| understand how a query flows | [chapter 4](04-follow-the-data.md) |
| add or change a field, mapping, or data source | [chapter 3](03-data-model-and-mdr.md), then [chapter 7](07-recipes.md) |
| change a shared component safely | [chapter 2](02-codebase-map.md) (blast radius), [chapter 7](07-recipes.md) |
| open my first PR | [chapter 6](06-how-we-work.md) |
| figure out why something returns `null` or times out | [chapter 8](08-debugging-and-traps.md) |
| run only part of LIF, or build something on one part | [chapter 10](10-extending-lif.md) |

The handbook **links** to the repo's other docs instead of repeating them. Where one of those docs is out
of date, the handbook says so. When the handbook and the code disagree, the code is right: please fix the
handbook.

## Glossary

**Learner record / LIF record.** One JSON document per learner, shaped by the data model. Stored per
organization in MongoDB by the Query Cache.

**Fragment / fragment path.** A piece of a record, named by a two-level path such as `Person.Contact`. The
unit the Query Planner reasons in.

**Information source.** A place a planner can fetch fragments from, configured in its
`information_sources_config*.yml`: another org's LIF, or a non-LIF system.

**Adapter.** The code that fetches raw data from one kind of source (`lif-to-lif`,
`example-data-source-rest-api-to-lif`). Run by Dagster.

**Query plan / plan part.** The planner's list of which sources to ask for which fragment paths. One part
per source.

**Orchestrator / Dagster.** The Orchestrator API submits a plan as a run of a Dagster job; Dagster runs the
adapters and the translation, then posts results back to the planner.

**MDR (Metadata Repository).** The service and database that hold data models, mappings and
transformations, and generate the schemas other services load.

**Data model.** A named, versioned schema in the MDR (`StateU LIF` 1.0 by `StateU`). Types today: Base LIF,
Org LIF, Partner LIF, Source Schema; these are being retired in favor of one self-contained kind (ADR
data_model/0004).

**Entity / attribute / association.** An object type (`Contact`, PascalCase); a scalar field (`firstName`,
camelCase); the link that puts one entity under another, with a `Name` and an `Array` flag.

**Overlay.** A model built on another (Org LIF and Partner LIF on Base LIF) through inclusions and
extensions. Being converted to self-contained copies.

**Source schema.** A model of another standard (Ed-Fi, CEDS, Open Badges…), kept so it can be mapped
to LIF.

**Transformation group / transformation.** A mapping from one model to another, and one JSONata
expression within it. Only an **activated** group is used.

**JSONata.** The expression language the mappings are written in.

**Portable file.** The export/import format for moving models and mappings between MDRs.

**Tenant / workspace.** A separate Postgres schema in the MDR (`tenant_<name>`) for one sign-up's data.

**Brick / component / base / project.** Polylith's units: reusable code; an entry point; a deployable
combining them ([chapter 2](02-codebase-map.md)).

**org1 / org2 / org3.** The three demo organizations in the local stack and the demo environment, each
with its own GraphQL API, planner, cache and seed data. **StateU** (State University) is org1's
institution: org1's records name it as their `informationSourceOrganization`, and its model, *StateU LIF*,
is the one the local services load.

**LDE (Learner Data Export API).** A service that exports a learner's record in another standard's format
(`GET /exports`; the formats on offer come from `GET /available-data-formats`), using the MDR's mappings.

**Control plane.** The service for developer keys and workspaces (`control_plane_restapi`).

**dev / demo.** The team's two shared environments, hosted on AWS to date for demo purposes
([chapter 9](09-environments-and-deploys.md)).

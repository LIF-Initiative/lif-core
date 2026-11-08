# 10. Extending LIF: which parts run on their own

Which LIF services can run without the full system, what each one needs, and which part to build on for a new feature.

*Checked against main `2967cb9`, November 2026.* Sections marked **Run on 11-07** or **11-08** were brought up and called
on the local stack, with the other services stopped or unreachable. The rest comes from the compose file
and the code.

---

## Why this matters

The local stack starts 22 services ([chapter 1](01-dev-environment.md)), but LIF isn't one program. It's a set of services that
each do one job, and many of them are useful alone: a team that only wants to manage data models, or only
wants to translate one standard into another, doesn't need Dagster, MongoDB or the GraphQL API. This
chapter says what each part needs, which combinations have been run, and where a new feature should plug in.

## What each part needs

"Depends on" is what the service is configured to reach (its `depends_on` and URLs in
`deployments/advisor-demo-docker/docker-compose.yml`); "Calls per request" is what it calls while answering.

| Part | Depends on | Calls per request | Runs alone? |
|---|---|---|---|
| **MDR API** (+ MDR UI) | its PostgreSQL (seeded by the restore job) | nothing | **Yes** |
| **Translator** | the MDR | the MDR (both schemas and the active mappings, every request) | With the MDR |
| **Query Cache** | MongoDB | MongoDB | **Yes** |
| **Query Planner** | the Query Cache, the Orchestrator API, its sources YAML | the Query Cache; the Orchestrator API only when a path is missing | With the cache |
| **GraphQL API** | the MDR at startup (to build its schema), or a bundled schema file; the Query Planner | the Query Planner | With the planner and cache |
| **Orchestrator API** | Dagster's webserver | Dagster's webserver | With Dagster |
| **Dagster** (webserver, daemon, code location) | its PostgreSQL | the sources, the Translator, and the planner (to post results) | With those |
| **Example Data Source** | nothing | nothing | **Yes** |
| **Identity Mapper** | its MariaDB | its MariaDB | **Yes** |
| **Learner Data Export API (LDE)** | the MDR, the Query Planner, the Translator | the MDR, the Query Planner, the Translator | With those |
| **Semantic Search MCP server** | the MDR (or the bundled schema), the GraphQL API | the GraphQL API | With the read path |
| **Advisor API** (+ Advisor app) | the GraphQL API, the Semantic Search server, an OpenAI key | the GraphQL API and the Semantic Search server | With those |
| **Control plane** | its PostgreSQL | its PostgreSQL; callers need Cognito tokens | Alone, but every non-public path answers 401 without Cognito ([chapter 0](00-start-here.md)) |

## Combinations that work

Run the `docker compose` commands below from `deployments/advisor-demo-docker`, as in
[chapter 1](01-dev-environment.md).

### The MDR alone

The MDR database, its restore job and the MDR API (add the MDR UI to edit through a browser). That's
enough to create and edit data models, write and activate mappings, and move models between MDRs with
portable files ([chapter 3](03-data-model-and-mdr.md)). The MDR calls no other LIF service.
[`docs/operations/guides/test-driving-mdr.md`](../../operations/guides/test-driving-mdr.md) runs exactly this.

```bash
docker compose up -d lif-mdr-database lif-mdr-database-restore lif-mdr-api
```

### The MDR and the Translator: translation without the query path

**Run on 11-07.** The Translator turns a record in one model into another using the MDR's active mapping,
with no planner, cache or Dagster involved. Take a record from the example source (model 26, *R1 Demo Source
Data Model*) and translate it into StateU LIF (model 17):

```bash
curl -s -H 'x-key: changeme' localhost:8011/r1-demo/users/100005 > source.json
curl -s -X POST localhost:8007/translate/source/26/target/17 \
  -H 'content-type: application/json' --data @source.json
# {"Person":[{"EmploymentPreferences":[{"organizationTypes":["Non-Profit","Private Sector"]}]}]}
```

The Translator's log shows three MDR calls per request (both schemas, then the active mappings), so the
MDR must stay up. The Translator has no inbound auth ([chapter 5](05-cross-cutting.md)).

### The read path without orchestration

**Run on 11-07.** The GraphQL API, Query Planner, Query Cache and MongoDB serve learner records with no
Dagster, no Translator and no sources: LIF as a store of records you load yourself. There are two ways:

- **Configure no sources.** With an empty sources YAML, the planner's plan has no parts and nothing is ever
  fetched. That's how org2 and org3 run locally (their planners log `Created LIF Query Plan: 0 part(s)`).
- **Leave the Orchestrator out.** Cached fields still answer normally. A query for a field that isn't
  cached returns quickly with that field `null`, and the planner logs
  `Orchestrator submission failed; returning 1 cached records`.

The GraphQL API still needs the MDR when it starts, unless you use the bundled schema (next section).

### Services without the MDR

**Run on 11-07.**

- A **running** GraphQL API keeps answering when the MDR goes down: it built its schema at startup.
- A GraphQL API **started** while the MDR is down exits (code 3, `Failed to connect to MDR`). That's
  deliberate: services fail loudly rather than run on a stale schema
  ([`docs/design/cross-cutting/schema-loading.md`](../../design/cross-cutting/schema-loading.md)).
- With **`USE_OPENAPI_DATA_MODEL_FROM_FILE=true`** it starts without the MDR, using the bundled snapshot
  `components/lif/mdr_client/resources/openapi_constrained_with_interactions.json`, and answers queries.
  The snapshot doesn't follow MDR changes, so use it for development and offline work, not to run without
  an MDR for real. (The Translator needs the MDR on every request regardless.)

### The Query Cache alone

**Run on 11-07.** The cache needs only MongoDB; it doesn't load a schema. You can query it directly:

```bash
curl -s -X POST localhost:8001/query -H 'content-type: application/json' \
  -d '{"filter":{"Person":{"Identifier":{"identifier":"100005","identifierType":"SCHOOL_ASSIGNED_NUMBER"}}},"selected_fields":["Person.Name"]}'
```

If this answers 500 with `ServerSelectionTimeoutError` in the cache's log, MongoDB isn't running
(see the first-start failure in [chapter 1](01-dev-environment.md)).

### The Identity Mapper

**Run on 11-07.** The Identity Mapper stores which ID a learner has in which system
(`/organizations/{org_id}/persons/{person_id}/mappings`: `POST` to save, `GET` to list, `DELETE` one). It
needs only its MariaDB, and the local seed includes example mappings. Nothing else in LIF calls it today
([chapter 4](04-follow-the-data.md)), so it's a building block on its own. Locally it isn't in the
query-path service list, listens on port 8006, and has no published port: call it from inside the Docker
network, or add a port mapping.

```bash
docker compose up -d lif-identity-mapper-db-org1 lif-identity-mapper-org1
```

### The Example Data Source

A stand-in source system with no dependencies (port 8011, header `x-key: changeme` locally). Use it as a
pattern for a source system's API, or to feed the Translator as above.

### The Semantic Search MCP server: learner data for an AI assistant

**Run on 11-08.** The MCP server lets an AI client (Claude, Cursor, any MCP client) query learner records
without knowing the GraphQL schema. It needs the MDR when it starts (or the bundled schema, as for the
GraphQL API) and the read path behind it: the GraphQL API, Query Planner, Query Cache and MongoDB. It
doesn't need the Advisor or an LLM key: its embedding model (`all-MiniLM-L6-v2`, set by
`SEMANTIC_SEARCH__MODEL_NAME`) runs on the CPU inside the container. The model isn't in the image. It's
downloaded from Hugging Face when a new container starts (about 25 seconds here), so that start needs
internet access; the server was healthy about 90 seconds after starting.

```bash
docker compose up -d --no-deps lif-semantic-search-mcp-server   # with the read path already running
curl -s localhost:8003/schema/status
# {"initialized":true,"source":"mdr","leaf_count":247,"roots":["Person","Course","Credential"],
#  "filter_models":["Person","Course"],"mutation_models":["Person"]}
```

Point an MCP client at `http://localhost:8003/mcp` (streamable HTTP). It offers two tools: `lif_query`,
which takes a `filter` (a learner's `Identifier`) and a plain-language `query`, and `lif_mutation`. A
`lif_query` call for learner `100005` returned that learner's record. What happens inside: the server matches
the query against the field descriptions it loaded from the MDR, builds a GraphQL query selecting the
closest fields (the top 200 by default, `semantic_search_top_k`), and sends it to the GraphQL API. The
selection is broad by design, so expect most of a record back rather than one field.

Calls took about 8 seconds locally, almost all of it in the read path: the matching took milliseconds, but
the broad selection includes fields the cache doesn't hold, so the planner went to the Orchestrator first
([chapter 4](04-follow-the-data.md)). The server has no inbound auth, and `lif_mutation` can change records, so keep it
on a private network.

The image is large and slow to build (it includes PyTorch): about 40 minutes the first time on the machine
used here.

### The Learner Data Export API

**Run on 11-07.** The LDE exports a learner's record in another standard's format. It needs the MDR, the
Query Planner (and what's behind it) and the Translator. Locally it starts, but
`GET /available-data-formats` returns an empty list: the seed has no active mapping *from* StateU LIF
(model 17) to another model, and that's what an export format is. To export, create and activate one
([chapter 7](07-recipes.md), "Add or change a mapping"). Locally the LDE has no inbound auth
(`LDE_AUTH__API_KEYS` unset).

## Where a new feature plugs in

| You want to… | Build on | Start with |
|---|---|---|
| Bring in a new source system | An adapter run by Dagster (the `lif-to-lif` adapter already reads another LIF organization's GraphQL API) | [chapter 7](07-recipes.md), "Add a data source" |
| Support another data standard | A model and mappings in the MDR (no code) | [chapter 3](03-data-model-and-mdr.md), [chapter 7](07-recipes.md) |
| Give an application learner data | The GraphQL API; or the LDE for another standard's format | [chapter 4](04-follow-the-data.md) |
| Give an AI assistant learner data | The Semantic Search MCP server | "The Semantic Search MCP server" above |
| Translate records in a batch or pipeline of your own | The Translator, with an MDR | "The MDR and the Translator" above |
| Add a new service | A new base composing existing components | [chapter 7](07-recipes.md), "Add a new microservice"; [chapter 2](02-codebase-map.md) |
| Reuse logic in your own Python | The components under `components/lif/`; they're libraries | [chapter 2](02-codebase-map.md) |

## Before something outside LIF depends on a part

- **Check its auth.** The Query Planner, Query Cache, Orchestrator, Translator, Identity Mapper and
  Semantic Search have no inbound auth ([chapter 5](05-cross-cutting.md)). Don't expose them outside a
  private network.
- **Know which interfaces are contracts.** Only the docs in [`docs/specs/`](../../specs/) are contracts. The
  service-to-service HTTP calls used above (the planner's and cache's `/query`, the Translator's
  `/translate`) aren't documented as stable interfaces, so ask a maintainer before an outside system relies
  on one.
- **Mind what you don't run.** Leaving out a service changes behaviour quietly rather than failing: no
  orchestrator means uncached fields come back `null`; a stopped MDR is only noticed at the next restart or
  translation.

---

## Where to go next

- [`docs/overview/services-overview.md`](../../overview/services-overview.md) for what each service is for.
- [`docs/operations/guides/deploying-lif-at-your-institution.md`](../../operations/guides/deploying-lif-at-your-institution.md) for running LIF (or part of it) for real.
- [Chapter 7](07-recipes.md) for the step-by-step changes.

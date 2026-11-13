# 2. The codebase map

How the repo is laid out (Polylith), how a service is assembled from it, and why one edit can ship in many services.

*Checked against main `2967cb9`, November 2026.* Counts are the folders under `components/lif/`, `bases/lif/` and `projects/`.

---

## Polylith in five minutes

LIF uses [Polylith](https://davidvujic.github.io/python-polylith-docs/): all the Python code lives in
one repo, split into small **bricks** that are combined into deployable **projects**. There are three
kinds of folder:

| Folder | What it holds | How many | Example |
|---|---|---|---|
| `components/lif/<name>/` | Reusable logic: a client, a service, a data type, a helper | 41 | `query_planner_service`, `composer`, `mdr_client` |
| `bases/lif/<name>/` | An entry point that turns components into something runnable: a FastAPI app, an MCP server | 13 | `query_planner_restapi`, `api_graphql` |
| `projects/<name>/` | A deployable: picks one base plus the components it needs, and has its own `pyproject.toml`, `uv.lock` and Dockerfile | 19 (16 with Python bricks) | `lif_query_planner_api` |

Every brick lives in the `lif` namespace (`workspace.toml`), so whatever folder it's in, you import it
as `lif.<brick>`: `from lif.composer.core import compose_with_fragment_list`.

**The intent** (ADR 0004, [`docs/design/adr/general/0004-components-are-the-unit-of-reuse.md`](../../design/adr/general/0004-components-are-the-unit-of-reuse.md)):
components are the unit of reuse, and deployment concerns (auth wiring, the web app, demo fixtures)
belong in bases and projects. In practice the line isn't perfectly clean: some components do I/O (the
HTTP clients, the Mongo-backed cache service), and `mdr_services` imports FastAPI. Follow the intent in
new code; don't be surprised by the exceptions.

### Anatomy of a brick

```
components/lif/composer/
  __init__.py     # re-exports the public names
  core.py         # the main code (larger bricks add more modules)
  README.md       # purpose, public surface, who uses it   ← start here
test/components/lif/composer/   # tests mirror the source tree
```

The brick READMEs were checked against the code in November 2026: 37 of 51 were accurate and the rest
had only minor drift, so they're the most reliable docs in the repo for "what's in this brick".

## Two ways the same code is installed

**For development**, the root `pyproject.toml` lists *every* brick under `[tool.polylith.bricks]`, so one
`uv sync` gives you one virtualenv where everything imports. That's convenient, but it means a missing
dependency in a *project* won't show up locally.

**For deployment**, each project lists only its own bricks:

```toml
# projects/lif_query_planner_api/pyproject.toml
[tool.polylith.bricks]
"../../bases/lif/query_planner_restapi" = "lif/query_planner_restapi"
"../../components/lif/query_planner_service" = "lif/query_planner_service"
"../../components/lif/lif_fragment_utils" = "lif/lif_fragment_utils"
"../../components/lif/datatypes" = "lif/datatypes"
"../../components/lif/exceptions" = "lif/exceptions"
"../../components/lif/logging" = "lif/logging"
"../../components/lif/lif_schema_config" = "lif/lif_schema_config"
```

plus its own third-party `dependencies`. The `hatch-polylith-bricks` build hook copies those bricks into
the project's wheel, and the project's Dockerfile installs the wheel.

Local compose builds `projects/<name>/Dockerfile2`. It exports the project's `uv.lock` as a constraints
file and installs the wheel against it. The deploy workflows build the default `Dockerfile` instead, after
`build.sh` (`uv export --frozen` to a `requirements.txt`, then `uv build`), and it installs the wheel plus
that `requirements.txt`. Either way the image gets the versions in the project's lock.

> **Two rules that follow:**
> 1. A third-party library a brick needs must be in **each project's** `dependencies` (and its `uv.lock`),
>    not just the root `pyproject.toml`. Locally it will import fine either way.
> 2. A new brick a service needs must be added to **that project's** brick list. For Dagster, that means
>    all three `projects/dagster_*/pyproject.toml` plus `orchestrators/dagster/lif-orchestrator/pyproject.toml`
>    (#1455: nothing checks this yet).

**The Dagster projects are different.** `projects/dagster_*` have no `uv.lock`, and their images install
from PyPI without one. That is how the images drifted to versions that don't work together (#1490,
#1491, fixed by pinning them in #1504; [chapter 1](01-dev-environment.md)). The job code itself lives in `orchestrators/dagster/lif-orchestrator/`, and the
`Dockerfile.code_location` copies it in.

## Blast radius: shared bricks

A change to a component ships in **every project that packages it**. Measured across the 16 projects:

| Brick | Packaged by |
|---|---|
| `logging` | 15 projects |
| `datatypes`, `exceptions` | 12 each |
| `lif_schema_config` | 9 |
| `auth` | 6 |
| `lif_fragment_utils`, `mdr_client` | 4 each |
| `data_source_adapters`, `demo_data_source_adapters` | 3 each (the Dagster projects) |

To see who packages a brick: `grep -l 'components/lif/<brick>"' projects/*/pyproject.toml`.

Two consequences:

- **Test every consumer you can**, not just the brick's own tests.
- **Deploys are path-filtered.** Each service's GitHub Actions deploy workflow rebuilds only when files
  under its `paths:` change. If a shared brick isn't in a workflow's filter, editing it won't rebuild
  that service, and the change silently doesn't ship (#1171). `scripts/check_workflow_paths.py` (run by
  pre-commit and CI) checks those filters against the brick lists. Run the repo's scripts with
  `uv run python scripts/<script>.py`: they need Python 3.13, and a system `python3` may be older.
- **Each project's `uv.lock` must match its `pyproject.toml`.** CI only syncs the root lock, so
  `scripts/check_project_locks.py` (run in CI) catches a project dependency added without re-locking,
  which would otherwise crash the service at startup (#1125).

## The component catalog, by area

| Area | Components |
|---|---|
| Query path ([chapter 4](04-follow-the-data.md)) | `query_planner_service`, `query_planner_client`, `query_cache_service`, `composer`, `lif_fragment_utils`, `orchestrator_service`, `orchestrator_clients`, `data_source_adapters`, `demo_data_source_adapters` |
| Translation | `translator`, `translator_client` |
| MDR (Metadata Repository) | `mdr_services`, `mdr_sql_model`, `mdr_dto`, `mdr_utils`, `mdr_client`, `mdr_auth`, `mdr_portability`, `tenant_routing` |
| Schema and GraphQL | `lif_schema_config`, `schema_state_manager`, `openapi_schema_parser`, `openapi_to_graphql` |
| Auth and keys | `auth` (the single auth brick, ADR 0007), `developer_keys` |
| Identity Mapper | `identity_mapper_service`, `identity_mapper_storage`, `identity_mapper_storage_sql` |
| AI | `langchain_agent`, `semantic_search_service` |
| Demo and example | `demo_personas`, `example_data_source_service` |
| Shared basics | `datatypes`, `exceptions`, `logging`, `string_utils`, `mongodb_connection`, `graphql_client` |

**Not used by anything** (no project packages them): `query_cache_read`, `query_cache_read_store_in_memory`,
`query_cache_read_store_mongodb` and the base `query_cache_module` are empty stubs. If you see
`api_key_auth`, `api_token_auth` or `cognito_auth` folders locally, they're leftover `__pycache__` from
before `auth` replaced them; they aren't in git.

## The bases (what actually runs)

| Base | Project | Local port (org1) | Deploys to dev via |
|---|---|---|---|
| `api_graphql` | `lif_graphql_api` | 8010 | `lif_graphql_api.yml` |
| `query_planner_restapi` | `lif_query_planner_api` | 8002 | `lif_query_planner_api.yml` |
| `query_cache_restapi` | `lif_query_cache_api` | 8001 | `lif_query_cache_api.yml` |
| `orchestrator_restapi` | `lif_orchestrator_api` | 8005 | `lif_orchestrator_api.yml` |
| `translator_restapi` | `lif_translator_api` | 8007 | `lif_translator_api.yml` |
| `mdr_restapi` | `lif_mdr_api` | 8012 | `lif_mdr_api.yml` |
| `identity_mapper_restapi` | `lif_identity_mapper_api` | not published (compose network only) | `lif_identity_mapper_api.yml` |
| `learner_data_export_api` | `lif_learner_data_export_api` | 8013 | `lif_learner_data_export_api.yml` |
| `control_plane_restapi` | `lif_control_plane_api` | 8014 | `lif_control_plane_api.yml` (manual only, `workflow_dispatch`, until its AWS stack exists, #1182) |
| `example_data_source_rest_api` | `lif_example_data_source_rest_api` | 8011 | `lif_example_data_source_rest_api.yml` |
| `advisor_restapi` | `lif_advisor_api` | 8004 | `lif_advisor_api.yml` |
| `semantic_search_mcp_server` | `lif_semantic_search_mcp_server` | 8003 | `lif_semantic_search_mcp_server.yml` |
| `query_cache_module` | (none: empty stub) | | |

The Dagster images deploy through `dagster.yml` (webserver and daemon) and `dagster_code_location.yml`,
both from `projects/dagster_oss_ecs` (ECS is the team's AWS demo hosting). `projects/dagster_docker_compose` is for local compose only, and
`projects/dagster_plus_hybrid` has no workflow. Workflows live in `.github/workflows/`; the service
workflows call the shared `_deploy-service.yml`, while the Dagster, MongoDB and frontend workflows have
their own steps.

## The rest of the repo

| Path | What's there |
|---|---|
| `orchestrators/dagster/lif-orchestrator/` | The Dagster job ([chapter 4](04-follow-the-data.md), step 7) |
| `deployments/advisor-demo-docker/` | The local stack ([chapter 1](01-dev-environment.md)) |
| `projects/mongodb/sample_data/` | Learner seed data per org |
| `projects/lif_mdr_database/backup.sql` | The MDR seed (models, mappings, transformations) |
| `sam/mdr-database/flyway/…/sql/mdr/` | MDR schema migrations ([chapter 7](07-recipes.md)) |
| `reference_data/` | The LIF schema JSON and transformation copies (edit transformations only through `scripts/import-transformations.sh`) |
| `cloudformation/`, `.github/workflows/` | The team's AWS hosting for dev and demo (one way to deploy LIF, not a requirement), and the deploy workflows ([chapter 9](09-environments-and-deploys.md)) |
| `scripts/` | Repo checks and operational scripts |
| `frontends/` | React apps (frontend handbook) |
| `integration_tests/` | Tests against the running stack ([chapter 1](01-dev-environment.md)) |

## Polylith commands

```bash
uv run poly info                   # bricks × projects matrix
uv run poly deps                   # which bricks use which
uv run poly create component --name my_thing
```

`uv run poly check` currently fails on `main` (`Cannot locate jwt in lif_graphql_api`), and CI doesn't
run it. Don't read its failure as something you broke.

To add a whole new service, follow [`docs/operations/guides/adding-a-new-microservice.md`](../../operations/guides/adding-a-new-microservice.md).

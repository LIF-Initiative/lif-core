# 1. Your development environment

Install the tools, run the checks, and bring up the local stack, with the traps a first run actually hits.

*Checked against main `2967cb9`, November 2026.* Built from a real first run on a fresh clone.

---

## What you need

| Tool | Why | Version |
|---|---|---|
| `git` | | any recent |
| [`uv`](https://docs.astral.sh/uv/) | installs Python and every dependency; runs every command | any recent for daily work (0.12.7 used here). CI pins **0.7.15** (`.github/workflows/pr-ci.yml`); when you re-lock a project, use that version, because a lock written by a newer uv may not satisfy CI's lock check. |
| Python 3.13 | the whole backend | `uv` installs it for you (`requires-python = ">=3.13,<3.14"`, `.python-version` = 3.13.4) |
| Docker with Compose v2 | the local stack | Compose v2 syntax (`docker compose`, not `docker-compose`) |
| `gh` (optional) | issues and PRs from the terminal | |

You do **not** need AWS (LIF doesn't require it; see [chapter 0](00-start-here.md)), an OpenAI key, or Node (Node is for the frontends; see the frontend
handbook).

## Set up the repo

```bash
git clone https://github.com/LIF-Initiative/lif-core.git && cd lif-core
uv sync                                            # creates .venv with every brick's dependencies
uv run pre-commit install                          # runs the checks on every commit
uv run pre-commit install --hook-type commit-msg   # enforces the commit message format
```

The first `uv sync` is large: the semantic-search bricks pull in PyTorch.

Either push branches to the main repo (if you have write access) or work from a fork
([`CONTRIBUTING.md`](../../../CONTRIBUTING.md) → Getting Started). The team does both.

## The checks

These are the same checks pre-commit runs on each commit, and CI runs on each PR
(`.github/workflows/pr-ci.yml`).

```bash
uv run ruff check          # lint
uv run ruff format         # format
uv run ty check            # type check
uv run pytest test/        # unit tests (narrow it: uv run pytest test/components/lif/composer/)
uv run pre-commit run --all-files
```

Pre-commit also runs `uv-lock`, `cspell` (spelling, on changed files only), `commitlint`, and
`check-workflow-paths` (see [chapter 6](06-how-we-work.md)).

### The tests that skip without Postgres

A full local run on a machine without PostgreSQL (main `2967cb9`, November 2026):
**1493 passed, 347 skipped, in about 4 minutes.** 345 of those skips are
`PostgreSQL not available locally: command not found: initdb`. (The other two: one test waits for
`LIF_UPDATE_SCHEMA_SNAPSHOTS=1`, and one needs `psql`.)

So about a fifth of the suite needs a real PostgreSQL server: the MDR tests under
`test/bases/lif/mdr_restapi/`, which include the Translator ↔ MDR end-to-end tests, plus
`test/bases/lif/control_plane_restapi/`, `test/components/lif/developer_keys/`,
`test/components/lif/mdr_services/test_schema_drift_service.py` and six files under `test/scripts/`. They use
`testing.postgresql`, which starts its own throwaway server by running `initdb`. If `initdb` isn't on
your `PATH`, those tests **skip, and pytest still exits 0**. CI's runner has Postgres, so they do run
there.

So a green local run can hide a failure that CI will catch. If you change `mdr_client`, `translator`,
`mdr_services`, `mdr_restapi`, `developer_keys`, `control_plane_restapi`, the scripts under `scripts/` or the
seed, either:

- install PostgreSQL locally. On Debian/Ubuntu that's enough: `testing.postgresql` finds `initdb` under
  `/usr/lib/postgresql/*/bin` itself, even though it isn't on `PATH` (that's why CI needs no setup). With a
  Homebrew-style or custom install, put its `bin/` on `PATH`. `psql` must be on `PATH` either way, for the
  seed load. Run the tests as your normal user (`initdb` refuses root). Or
- run them in a container that has Postgres and a non-root user (`initdb` refuses to run as root, and
  needs a real user entry for your uid). Checked 11-07 on main `2967cb9`, the whole
  `test/bases/lif/mdr_restapi/` folder: **373 passed, 1 skipped, in 31 minutes** (the skip is the
  snapshot test waiting for `LIF_UPDATE_SCHEMA_SNAPSHOTS=1`).

  ```dockerfile
  # Dockerfile.pgtest (keep it outside the repo, e.g. ~/.cache/lif-pgtest/)
  FROM python:3.13-slim
  RUN apt-get update && apt-get install -y --no-install-recommends \
        postgresql postgresql-client build-essential libpq-dev curl ca-certificates \
      && rm -rf /var/lib/apt/lists/*
  # use your own uid/gid here (id -u / id -g)
  RUN groupadd -g 1000 tester && useradd -u 1000 -g 1000 -m -s /bin/bash tester
  ENV PATH="/usr/lib/postgresql/17/bin:${PATH}"
  COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
  ENV UV_LINK_MODE=copy PYTHONDONTWRITEBYTECODE=1
  WORKDIR /repo
  ```

  ```bash
  docker build -t lif-pgtest - < ~/.cache/lif-pgtest/Dockerfile.pgtest
  docker volume create lif-pgtest-venv
  docker run --rm -v lif-pgtest-venv:/cache python:3.13-slim chown 1000:1000 /cache   # once
  docker run --rm -v "$PWD":/repo -w /repo -u 1000:1000 -v lif-pgtest-venv:/cache \
    -e UV_PROJECT_ENVIRONMENT=/cache/venv -e UV_CACHE_DIR=/cache/uv -e UV_PYTHON_INSTALL_DIR=/cache/python \
    -e UV_LINK_MODE=hardlink lif-pgtest \
    sh -c 'uv sync --frozen && uv run --frozen --no-sync pytest test/bases/lif/mdr_restapi/ -q'
  ```

  The virtualenv lives in the `lif-pgtest-venv` volume, so only the first run is slow (it downloads
  PyTorch: expect tens of minutes). The tests themselves are slow too: the slowest part is
  `test_schema_snapshots.py`, which generates every seed model's full schema; the 11-07 run printed
  nothing for over 15 minutes on the large source models (CTDL has 2,501 attributes), so a silent run
  isn't necessarily a hung one. To work on one area, narrow the path,
  e.g. `pytest test/bases/lif/mdr_restapi/test_value_mapping_service_db.py`. CI's whole Python job
  took about 13 minutes on 11-07. `UV_PYTHON_INSTALL_DIR` matters: without it the venv points at a Python
  inside the throwaway container and is rebuilt every time. Don't hide `uv sync`'s errors: a failed sync
  followed by skipped tests looks like a pass.

Check the summary line: if it says `N skipped`, look at why before you trust it.

## The local stack

Everything runs from one compose file: `deployments/advisor-demo-docker/docker-compose.yml`. It defines
35 services for three demo organizations. You rarely need all of them.

### First time

```bash
cd deployments/advisor-demo-docker
cp .env.example .env     # three required secrets; the example values are fine locally
```

If you already had a `.env`, compare it with `.env.example`. Compose refuses to even parse the file
when a required variable is missing, for example
`required variable MDR__AUTH__JWT_SECRET_KEY is missing a value` from an `.env` made before ADR 0007.

### Bring up what you need

The query path from [chapter 4](04-follow-the-data.md) (22 services, no Advisor, no LLM key):

```bash
docker compose up -d --build \
  mongodb-org1 mongodb-org2 mongodb-org3 \
  lif-query-cache-org1 lif-query-cache-org2 lif-query-cache-org3 \
  lif-query-planner-org1 lif-query-planner-org2 lif-query-planner-org3 \
  lif-graphql-api-org1 lif-graphql-api-org2 lif-graphql-api-org3 \
  lif-orchestrator-api-org1 postgres-dagster dagster-code-location dagster-daemon dagster-webserver \
  lif-translator-org1 lif-example-data-source-rest-api \
  lif-mdr-database lif-mdr-database-restore lif-mdr-api
```

For a single layer, check that service's `depends_on` in the compose file and start only that.

**Ports you'll use:**

| | org1 | org2 | org3 |
|---|---|---|---|
| GraphQL API | 8010 | 8110 | 8210 |
| Query Planner | 8002 | 8102 | 8202 |
| Query Cache | 8001 | 8101 | 8201 |
| MongoDB | 27017 | 27018 | 27019 |

Shared: Orchestrator API 8005, Dagster UI 3000, MDR API 8012. [Chapter 4](04-follow-the-data.md) has a query to try.

### Looking inside the stack

```bash
docker ps -a --format '{{.Names}}\t{{.Status}}'   # what's running, and what has EXITED
docker compose up -d <service>                       # start one service (from deployments/advisor-demo-docker)
docker logs --since 10m <container>                  # recent logs
docker exec -it advisor-demo-docker-lif-mdr-database-1 psql -U postgres -d LIF   # the MDR database (host port 5445)
docker exec mongodb-org1 mongosh LIF                 # an org's learner cache
```

Read-only queries are a good way to learn the MDR's tables: `\d "TransformationsGroup"` shows a table's
columns. Table and column names are quoted PascalCase.

### Known problems on a fresh build (November 2026)

- **Orchestrated queries fail on a stack built before 11-12** (anything not already in an org's
  cache): the Dagster images installed versions that don't fit together (#1490: `POST /jobs` returns 500;
  #1491: runs fail with `No module named 'psycopg'` and the query times out with 408). #1504 pinned
  them. If your Dagster images are older than that, rebuild them:
  `docker compose up -d --build dagster-webserver dagster-daemon dagster-code-location`.
- **A MongoDB container can fail its first start** with
  `AssertionError: Could not shutdown mongod for init db successfully`. Seen on 11-07 both when three
  started together and on a single-org reset. The seed has already loaded by then, so the container exits
  a few seconds *after* it looks fine. `docker start mongodb-org1` (not `rm`) fixes it.

### Data doesn't reset the way you'd expect

Both databases keep their data on anonymous Docker volumes, so `docker compose up` and `docker restart`
**do not** reload the seed data.

- **MongoDB** (learner records): anything the cache fetched stays. To reset one org:
  `docker compose rm -sfv mongodb-org1 && docker compose up -d mongodb-org1`. Wait half a minute, then
  check `docker ps -a` still shows it `Up` (see the first-start failure above). While it's down, the cache
  answers 500 and its log shows `ServerSelectionTimeoutError`.
- **MDR Postgres** (models, mappings, transformations): `up` reuses an existing database container, and
  the restore job then replays `backup.sql` over the old data, which wins. A stack first started weeks
  ago is still running that week's seed. To reload from the current `projects/lif_mdr_database/backup.sql`:

  ```bash
  docker compose rm -sfv lif-mdr-database lif-mdr-database-restore
  docker compose up -d lif-mdr-database lif-mdr-database-restore
  docker restart lif-mdr-api    # then the services that load a schema (and the Translator, to clear its cache):
  docker restart lif-graphql-api-org1 lif-graphql-api-org2 lif-graphql-api-org3 advisor-demo-docker-lif-translator-org1-1
  ```

  The restore log always shows two errors, `extension "pgaudit" is not available` and
  `role "rds_iam" does not exist`. They come from settings for the team's AWS-hosted database, and are
  harmless locally.

### Integration tests

`integration_tests/` checks the running stack layer by layer. It is **local only**: no CI workflow runs
it, so a green PR says nothing about it.

```bash
uv run pytest integration_tests/ --org org1 --skip-unavailable
```

Without `--org`, it runs for all three orgs. Details: [`docs/operations/guides/testing.md`](../../operations/guides/testing.md).

**Expect 6 failures today (November 2026).** On main `2967cb9`, before #1504, with a manual Dagster
workaround that #1504 has since made unnecessary (not re-measured since):
6 failed, 31 passed, 33 skipped for org1, in about 4 minutes. The failures are the data-integrity
checks in `test_03_query_planner.py` and `test_04_graphql.py`, and the run itself causes them. The
tests ask for fields the seed records don't have, so the planner re-fetches the learner from the
partner orgs, and the cache replaces org1's own lists with what comes back (#1492). The run also
leaves duplicate learners behind, so **reset org1's MongoDB after every run** (the recipe above). If
you get a different set of failures, look at them. org2 and org3 pass (37 passed, 33 skipped each): locally they have no
partner sources configured, so nothing is re-fetched.
*(Update this when #1492 is resolved.)*

---

## Where to go next

- [Chapter 2](02-codebase-map.md) for how the code is laid out.
- [Chapter 4](04-follow-the-data.md) to watch a query go through the stack you just started.
- [`docs/operations/guides/testing.md`](../../operations/guides/testing.md) for what's worth testing, and the seed-schema snapshot tests.
- [`docs/operations/guides/test-driving-mdr.md`](../../operations/guides/test-driving-mdr.md) to run the MDR on its own.

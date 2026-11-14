# 8. Debugging, and the traps we keep relearning

How to find where a request went wrong, and the mistakes that have cost this team real time.

*Checked against main `2967cb9`, November 2026.* Each trap cites the issue or file it comes from.

---

## Following a request through the logs

**First, check everything is running**: `docker ps -a`. A stopped service doesn't log an error; its log
just stops. Then follow the logs; every service logs to stdout (`docker logs -f <container>`). For a
query ([chapter 4](04-follow-the-data.md)), read in this order:

1. **GraphQL API** (`lif-graphql-api-org1`): `Query: Person, filter on ['Identifier'], N selected field(s)`.
2. **Query Planner** (`lif-query-planner-org1`): the most useful log in the system. It says what the cache
   had (`missing: [...]`), the plan (`Created LIF Query Plan: …`), and ends each query with a
   `LIF_QUERY_STATISTICS` JSON line whose `outcome` is one of:
   - `served_from_cache`: everything was cached;
   - `orchestrated`: a Dagster run was started;
   - `no_sources_available`: something was missing and no configured source supplies it;
   - `orchestrator_submission_failed`: the Orchestrator API refused or failed.
3. **Orchestrator API** (`lif-orchestrator-api-org1`): `Dagster run submitted: <run id>`. The planner's
   `correlation_id` **is** that Dagster run id, so you can match the two. On a cache hit it's `null`:
   nothing past the planner ran.
4. **Dagster** (UI at http://localhost:3000, or `docker logs dagster-code-location`): the run's steps,
   `run_lif_adapter[…]` and `run_translation[…]`, with each step's error. Launch failures show in
   `docker logs dagster-daemon` instead.
5. **Translator** (`advisor-demo-docker-lif-translator-org1-1`) and the **MDR** (`lif-mdr-api`) for
   translation failures.

To see which services a query touched, note the time first, then `docker logs --since <time> <container>`
for each. Expected noise: the GraphQL API's `Result objects is list nested in list` warning appears on every
successful query.

Logs show shapes and counts, never learner values ([chapter 5](05-cross-cutting.md)). To see the actual data, query the cache's
MongoDB directly:

```bash
docker exec mongodb-org1 mongosh LIF --quiet --eval 'printjson(db.person.findOne({"Person.Identifier.identifier":"100006"}))'
```

## Symptoms and causes we've seen

| Symptom | Likely cause | Where to look |
|---|---|---|
| A GraphQL field is `null` but the source has data | A source failed during orchestration. The planner sent `X-LIF-Partial`, but GraphQL doesn't pass it on (#1308) | Planner log: `Sources failed during orchestration`; then Dagster |
| A learner has fewer items than the seed, or appears more than once in MongoDB | An orchestrated refresh replaced org1's lists with partner data and dropped `identifierType` (#1492). The integration tests trigger it | `db.person.countDocuments()` in `mongodb-org1` (seed: 4); reset with [chapter 1](01-dev-environment.md)'s recipe |
| A field is `null`, the planner says `served_from_cache`, and another org has the value | The cache check is per two-level path: the learner already has that path (`Person.Name`), so nothing is fetched | [Chapter 4](04-follow-the-data.md), step 3 |
| Planner: `Pipeline did not run or failed`, `Sources failed during orchestration`; Dagster: `ConnectionError` in `run_lif_adapter` or `run_translation` | A service the job calls is down or unreachable (the Translator, a source system) | `docker ps -a`; then test the hop from inside the container, e.g. `docker exec dagster-code-location python -c "import urllib.request; print(urllib.request.urlopen('http://lif-translator-org1:8007/health').status)"` |
| `"Query failed: 408"` | The planner's wait ran out (`LIF_QUERY_TIMEOUT_SECONDS`) | Dagster daemon log: did the run launch at all? |
| Planner: `orchestrator_submission_failed` | Orchestrator API 500 | Orchestrator log. On Dagster images built before 11-12: #1490, rebuild them ([chapter 1](01-dev-environment.md)) |
| Planner `503` (`No records found and the query failed: orchestrator_submission_failed`); Orchestrator API log: `TypeError: deprecated locations must be specified as a collection of DirectiveLocation enum values` | An Orchestrator API built before 11-13: its graphql-core can't parse the 1.13.26 Dagster webserver's schema (#1515). With some data cached, the planner answers `200` with `X-LIF-Partial` instead | Rebuild `lif-orchestrator-api-org1` ([chapter 1](01-dev-environment.md)) |
| Dagster: `No module named 'psycopg'` | SQLAlchemy 2.1 in a Dagster image built before 11-12 (#1491) | Rebuild the Dagster images ([chapter 1](01-dev-environment.md)) |
| Translator 404 `No active transformation group` | The group isn't activated, or your local MDR is an old seed | [Chapter 3](03-data-model-and-mdr.md) (activation); [chapter 1](01-dev-environment.md) (reseeding) |
| MDR `401` | Missing or wrong `X-API-Key` / login | [Chapter 5](05-cross-cutting.md) |
| A service won't start: `required variable … is missing` | `.env` is out of date | [Chapter 1](01-dev-environment.md) |
| A service crash-loops after merge: `ModuleNotFoundError` | A dependency added to the root `pyproject.toml` but not the project's (or the project's `uv.lock` not refreshed) | [Chapter 2](02-codebase-map.md); `scripts/check_project_locks.py` |
| A merged change isn't running on dev | The service's deploy workflow `paths:` doesn't cover the file you changed | #1171; `scripts/check_workflow_paths.py` |
| A new model field doesn't appear in GraphQL | The service loaded the schema before you changed it | Restart it ([chapter 5](05-cross-cutting.md)) |

## Traps

**Tests**
- **A skip is not a pass.** Without `initdb`, 345 tests skip and pytest exits 0 ([chapter 1](01-dev-environment.md)). Read the
  summary line.
- **Piping hides failures.** `uv run pre-commit run --all-files | tail` reports `tail`'s exit code, not
  pre-commit's. Run the check bare, or use `set -o pipefail`, before you believe a green result.
- **Locally, everything imports.** One dev virtualenv holds every brick, so a missing dependency in a
  project only shows up in its Docker image ([chapter 2](02-codebase-map.md)).
- **Integration tests aren't in CI.** A green PR says nothing about them ([chapter 1](01-dev-environment.md)).

**Data model**
- **Case is meaning.** `Person.Contact`, not `person.contact` ([chapter 3](03-data-model-and-mdr.md)). Lower-case paths match nothing,
  silently.
- **Schemas load once.** Restart after a model change.
- **The local MDR doesn't reseed itself** ([chapter 1](01-dev-environment.md)).

**Dependencies**
- **`~=` in a version pin**: `~=0.275` means `>=0.275, <1.0`, not `<0.276`. Write `~=0.275.0` to stay on
  a minor range. This once crashed production through a Docker image's dependency resolution ([`CLAUDE.md`](../../../CLAUDE.md)).
- **An unpinned `pip install` in a Dockerfile** drifts with every build (#1383, #1490, #1491).

**Migrations and deploys**
- **Migrations must be idempotent** and **merging doesn't apply them** ([chapter 7](07-recipes.md)).
- **A shared brick ships wherever it's packaged, but only rebuilds where the workflow's `paths:` say so**
  (#1171).
- **Deploy one stack at a time** to the team's AWS-hosted dev and demo: parallel deploys collide on the
  AWS SSO login ([`CLAUDE.md`](../../../CLAUDE.md)). See [chapter 9](09-environments-and-deploys.md).

**GitHub**
- **"close #N" anywhere in a PR body closes #N** on merge, even in a sentence. Use `Refs #N` unless you
  mean it ([chapter 6](06-how-we-work.md)).
- **A note in a PR body doesn't stop a merge.** Use draft status.

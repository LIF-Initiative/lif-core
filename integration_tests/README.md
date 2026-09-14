# Integration Tests

Integration tests for verifying data consistency across LIF service layers.

## Overview

These tests verify that data flows correctly through the service stack:
```
MongoDB -> Query Cache -> Query Planner -> GraphQL
```

Tests are organized by layer:
- `test_01_mongodb.py` - Verifies MongoDB data matches sample files
- `test_02_query_cache.py` - Verifies Query Cache returns correct data
- `test_03_query_planner.py` - Verifies Query Planner returns correct data
- `test_04_graphql.py` - Verifies GraphQL API returns correct data
- `test_05_cross_org.py` - Verifies data isolation and consistency across orgs

## Prerequisites

1. **A `.env` file** in `deployments/advisor-demo-docker/`:
   ```bash
   cp deployments/advisor-demo-docker/.env.example deployments/advisor-demo-docker/.env
   ```
   `LIF_DEMO_USER_PASSWORD` and `SECRET_KEY` lost their fallback defaults in #1191, and
   compose will not even parse this file without them — including for services that do
   not use them.
2. Docker environment running with `docker compose up` from `deployments/advisor-demo-docker/`
3. Sample data seeded in MongoDB (automatic when containers start)
4. Python dependencies: `uv sync` at the repo root, or `pip install pytest pymongo httpx`

### You usually do not need the whole stack

`docker compose up` starts ~29 services, including MDR, Postgres, Dagster and an
LLM-backed Advisor. Most layers need far less. The Query Cache, for instance, depends
only on its MongoDB:

```bash
docker compose up -d mongodb-org1 lif-query-cache-org1
```

For that layer there is a script that brings those two up, waits for readiness, and runs
the tests:

```bash
scripts/run-query-cache-integration-tests.sh            # leaves the containers running
scripts/run-query-cache-integration-tests.sh --down     # tears them down afterwards
scripts/run-query-cache-integration-tests.sh -- -k save # extra args are passed to pytest
```

### These tests are not run by CI

No workflow runs `integration_tests/`. They are a local-only suite, so a regression they
would catch can still merge. Treat a green PR as saying nothing about the layers covered
here, and run the relevant ones yourself when changing a service's data path.

### Write-path tests mutate the database

`test_02_query_cache.py::TestQueryCacheWritePath` exercises `/add`, `/update` and
`/save`, so it writes to the same MongoDB the read-path tests assert against. Each test
uses a unique synthetic identifier prefixed `it1200-` and deletes its documents on
teardown. Cleanup is best-effort by design: the compose file mounts no volume for
`mongodb-org*`, so restarting the container reseeds from the sample data regardless.

## Running Tests

### Run all tests
```bash
cd integration_tests
pytest -v
```

### Run tests for a specific org
```bash
pytest -v --org org1
pytest -v --org org2
pytest -v --org org1 --org org2
```

### Run tests for a specific layer
```bash
pytest -v -k "mongodb"
pytest -v -k "graphql"
pytest -v -k "cross_org"
```

### Skip unavailable services
If some services aren't running, use `--skip-unavailable` to skip those tests:
```bash
pytest -v --skip-unavailable
```

### Verbose output for failures
```bash
pytest -v -s --tb=long
```

## Port Configuration

Ports are based on `deployments/advisor-demo-docker/docker-compose.yml`:

| Service        | org1  | org2  | org3  |
|----------------|-------|-------|-------|
| MongoDB        | 27017 | 27018 | 27019 |
| GraphQL        | 8010  | 8110  | 8210  |
| Query Cache    | 8001  | 8101  | 8201  |
| Query Planner  | 8002  | 8102  | 8202  |

## Sample Data

Tests dynamically load sample data from:
```
projects/mongodb/sample_data/advisor-demo-org{1,2,3}/*.json
```

Each JSON file represents a person record. Tests compare API responses against this source data.

## Test Output

Tests provide verbose output for failures, including:
- Which person failed
- Expected vs actual values
- Path to the differing field

Example failure output:
```
[FAIL] org1/Tracy Thatcher @ graphql
       3 difference(s) found:
         - MISMATCH Person.Name[0].firstName: expected 'Tracy', got 'Terry'
         - MISSING  Person.CredentialAward[2]: expected {...}
         - EXTRA    Person.Contact[1]: found {...}
```

## Utilities

The `utils/` directory contains helper modules:
- `ports.py` - Port configuration for each org
- `sample_data.py` - Dynamic sample data loading
- `comparison.py` - Data comparison and diff reporting

## Troubleshooting

### "MongoDB not available"
Ensure Docker containers are running:
```bash
docker ps | grep mongodb
```

### "GraphQL query failed"
Check GraphQL service logs:
```bash
docker logs lif-graphql-api-org1
```

### "No sample data"
Verify sample data exists:
```bash
ls projects/mongodb/sample_data/advisor-demo-org1/
```

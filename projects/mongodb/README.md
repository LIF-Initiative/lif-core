# MongoDB (LIF cache + advisor data store)

Docker build for the MongoDB instances backing the LIF Query Cache and Advisor APIs. Not a Python project — `pyproject.toml` is absent on purpose; this directory only packages a configured MongoDB image plus seed-data loaders.

## Files

| File | Purpose |
|---|---|
| `Dockerfile` | Image definition — base `mongo` plus seed-data and entrypoint |
| `entrypoint.sh` | Loads `sample_data/<SEED_DATA_KEY>/` into the database on first start |
| `build-docker.sh` | Convenience build script |
| [`sample_data/`](sample_data/) | Seed datasets for demos + tests (per-org partitions: `advisor-demo-org1`, `-org2`, `-org3`, plus `dev-single-org`) |

## Usage

The reference deployments wire this image up as `mongodb-org1`, `mongodb-org2`, `mongodb-org3` in [`../../deployments/advisor-demo-docker/docker-compose.yml`](../../deployments/advisor-demo-docker/docker-compose.yml). Each picks a `SEED_DATA_KEY` matching its org partition.

See [`sample_data/README.md`](sample_data/README.md) for what's in each dataset and the user-test-coverage table.

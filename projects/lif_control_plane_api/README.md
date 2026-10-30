# Control Plane API

The **Control Plane API** is the LIF service that will own developer keys, and later identity and admin, outside MDR (EPIC #1041). So far it's the service and its own database, with a health check and Cognito auth; the key endpoints come next (#1182, #1190). See [`bases/lif/control_plane_restapi/README.md`](../../bases/lif/control_plane_restapi/README.md).

# Example usage

## Build the project
Navigate to this folder (where the `pyproject.toml` file is)

1. Export the dependencies from the project lock:
``` shell
uv export --frozen --no-emit-project --output-file requirements.txt
```

2. Build a wheel:
``` shell
uv build --out-dir ./dist
```

## Build a docker image from root

``` shell
./build-docker.sh
```

## Run it with its database (local compose)

``` shell
cd deployments/advisor-demo-docker
docker compose up -d lif-control-plane-api   # also starts lif-control-plane-database
```

## Example calls

``` shell
curl http://localhost:8014/health-check
# {"status":"ok"}  (503 {"status":"unavailable"} if the database is down)

curl -H "Authorization: Bearer <token>" http://localhost:8014/anything
# 401 {"detail":"Cognito auth is not configured"} without CONTROL_PLANE_AUTH__USER_POOL_ID
```

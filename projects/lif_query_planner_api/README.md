# Overview

The **Query Planner** is the central component of LIF. It processes and serves *LIF queries* from the **LIF API**.  It provides a uniform and unified query interface for the **LIF API** by hiding the complexity that arises from interacting with different internal and external data source systems to fetch required data to fulfill the *LIF query* with a *LIF record* that complies with the **LIF Data Model**.

# Example usage

## Build the project
Navigate to this folder (where the `pyproject.toml` file is)

1. Export the dependencies (when using uv workspaces and having no project-specific lock-file):
``` shell
uv export --no-emit-project --output-file requirements.txt
```

2. Build a wheel:
``` shell
uv build --out-dir ./dist
```

## Build a docker image

``` shell
./build-docker.sh
```

## Run the image

``` shell
docker run -d --name lif_query_planner -p 8002:8002 lif_query_planner
```

The OpenAPI specification of this FastAPI app can now be accessed at http://localhost:8002/docs#

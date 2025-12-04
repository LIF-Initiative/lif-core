# Overview

The **Query Cache** component provides caching support for previous LIF queries in order to save time and cost needed to run the **Orchestrator** to fetch data for a query that can be satisfied by the cache.

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
docker run -d --name lif_query_cache -p 8001:8001 lif_query_cache
```

The OpenAPI specification of this FastAPI app can now be accessed at http://localhost:8001/docs#

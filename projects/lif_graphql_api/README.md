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
docker run -d --name lif_graphql_api -p 8000:8000 lif_graphql_api
```

The graphql api (and GraphiQL UI) can now be accessed at http://localhost:8000/graphql

## API Key Authentication

The GraphQL API supports optional API key authentication via the `X-API-Key` header.

### Configuration

Authentication is configured via environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `GRAPHQL_AUTH__API_KEYS` | Comma-separated `key:name` pairs | Empty (auth disabled) |
| `GRAPHQL_AUTH__PUBLIC_PATHS` | Paths that bypass auth | `/health,/health-check` |
| `GRAPHQL_AUTH__PUBLIC_PATH_PREFIXES` | Path prefixes that bypass auth | `/docs,/openapi.json` |

### Enable Authentication

```shell
# Run with API key authentication enabled
docker run -d --name lif_graphql_api -p 8000:8000 \
  -e GRAPHQL_AUTH__API_KEYS="key1:client1,key2:client2" \
  lif_graphql_api
```

### Usage

When authentication is enabled, include the API key in requests:

```shell
curl -X POST http://localhost:8000/graphql \
  -H "Content-Type: application/json" \
  -H "X-API-Key: key1" \
  -d '{"query": "{ person { Name { firstName } } }"}'
```

When `GRAPHQL_AUTH__API_KEYS` is not set or empty, authentication is disabled and all requests are allowed.

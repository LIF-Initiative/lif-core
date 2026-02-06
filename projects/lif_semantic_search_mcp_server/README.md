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
docker run -d --name lif_semantic_search_mcp_server -p 8003:8003 -e LIF_GRAPHQL_ROOT_NODE=Person -e LIF_QUERY_PLANNER_URL=http://host.docker.internal:8002 lif_semantic_search_mcp_server
```

The MCP server can now be accessed at http://localhost:8003/mcp. There is no UI, so the mcp server
should be accessed with a FastMCP client (see development/mcp_client/client.py for development).

## MDR Integration

The Semantic Search MCP Server loads its schema from MDR at startup. It uses the `SchemaStateManager` component which:
- Fetches the OpenAPI schema from MDR using the configured data model ID
- Fails with a clear error if MDR is unavailable (no silent fallback to file)
- Can be forced to use the bundled file by setting `USE_OPENAPI_DATA_MODEL_FROM_FILE=true`

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `LIF_MDR_API_URL` | MDR API base URL | `http://localhost:8012` |
| `LIF_MDR_API_AUTH_TOKEN` | API key for MDR authentication | Required |
| `OPENAPI_DATA_MODEL_ID` | MDR data model ID to fetch | Required |
| `USE_OPENAPI_DATA_MODEL_FROM_FILE` | Force use of bundled file | `false` |

## AWS Deployment Setup

The Semantic Search service requires an MDR API key stored in AWS SSM Parameter Store. The key must match what MDR expects for the semantic search service.

### Create SSM Parameters

For each environment (dev, demo, prod), create matching parameters:

```bash
# Generate a secure API key
API_KEY=$(openssl rand -hex 32)

# Set environment name
ENV=demo  # or dev, prod

# Create parameter that Semantic Search reads
aws ssm put-parameter \
  --name "/${ENV}/semantic-search/MdrApiKey" \
  --value "${API_KEY}" \
  --type "SecureString" \
  --overwrite

# Create parameter that MDR validates against (must match)
aws ssm put-parameter \
  --name "/${ENV}/mdr-api/MdrAuthServiceApiKeySemanticSearch" \
  --value "${API_KEY}" \
  --type "SecureString" \
  --overwrite
```

### Verify Parameters

```bash
# Check parameters exist and match
aws ssm get-parameter --name "/${ENV}/semantic-search/MdrApiKey" --with-decryption --query 'Parameter.Value' --output text
aws ssm get-parameter --name "/${ENV}/mdr-api/MdrAuthServiceApiKeySemanticSearch" --with-decryption --query 'Parameter.Value' --output text
```

### Parameter Naming Convention

| Service | ServiceName | Reads From | MDR Validates Against |
|---------|-------------|------------|----------------------|
| GraphQL | `graphql-org1` | `/${ENV}/graphql-org1/MdrApiKey` | `/${ENV}/mdr-api/MdrAuthServiceApiKeyGraphql` |
| Semantic Search | `semantic-search` | `/${ENV}/semantic-search/MdrApiKey` | `/${ENV}/mdr-api/MdrAuthServiceApiKeySemanticSearch` |
| Translator | `translator` | `/${ENV}/translator/MdrApiKey` | `/${ENV}/mdr-api/MdrAuthServiceApiKeyTranslator` |

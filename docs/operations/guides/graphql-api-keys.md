# GraphQL API Key Authentication

GraphQL org1 supports API key authentication. Keys are managed in AWS SSM Parameter Store.

**How it works:**
- Server-side: `/{env}/graphql-org1/ApiKeys` stores comma-separated `key:client-name` pairs (e.g., `abc123:semantic-search,def456:workshop-01`)
- Client-side: Each client has its own SSM param with the bare key (e.g., `/{env}/semantic-search/GraphqlApiKey`)
- The `graphql_client` component reads `LIF_GRAPHQL_API_KEY` env var and sends it as `X-API-Key` header
- GraphQL server validates incoming keys against its `GRAPHQL_AUTH__API_KEYS` env var
- When `GRAPHQL_AUTH__API_KEYS` is empty/unset, authentication is disabled (local dev default)

**Key env vars:**
| Variable | Service | Purpose |
|----------|---------|---------|
| `GRAPHQL_AUTH__API_KEYS` | GraphQL org1 | Server-side: comma-separated `key:label` pairs to accept |
| `LIF_GRAPHQL_API_KEY` | Semantic search | Client-side: bare API key to send with requests |

**Managing keys:**
```bash
# Preview what will happen
AWS_PROFILE=lif ./scripts/setup-graphql-api-keys.sh demo

# Create/update service key (semantic-search)
AWS_PROFILE=lif ./scripts/setup-graphql-api-keys.sh demo --apply

# Generate workshop participant keys
AWS_PROFILE=lif ./scripts/setup-graphql-api-keys.sh demo --workshop 10 --apply

# Remove all workshop keys (preserves service keys)
AWS_PROFILE=lif ./scripts/setup-graphql-api-keys.sh demo --workshop 0 --apply
```

After key changes, redeploy affected services:
```bash
./aws-deploy.sh -s demo --only-stack demo-lif-semantic-search
./aws-deploy.sh -s demo --only-stack demo-lif-graphql-org1
```

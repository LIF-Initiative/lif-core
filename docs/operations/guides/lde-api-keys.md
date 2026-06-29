# Learner Data Export (LDE) API Key Authentication

The LDE API authenticates inbound callers (downstream applications, integrators, workshop
attendees) with API keys, using the shared [`api_key_auth`](../../../components/lif/api_key_auth/)
middleware — the same component the GraphQL API uses (see [graphql-api-keys.md](graphql-api-keys.md)).

> This is the **interim** model (#1000). The target adds Cognito sign-in + self-service,
> per-user key minting from a UI; this static-key flow evolves into it (the middleware stays,
> the key store becomes dynamic). See the #1000 design spike.

**How it works:**
- Server-side: `/{env}/learner-data-export-api/ApiKeys` stores comma-separated `key:label`
  pairs (e.g. `abc123:integrator-01,def456:workshop-02`), injected into the task as
  `LDE_AUTH__API_KEYS`.
- Callers send the bare key as the `X-API-Key` header.
- When `LDE_AUTH__API_KEYS` is empty/unset, authentication is **disabled** (local-dev default) —
  so the SSM parameter must exist with real keys before exposing the service.
- The inbound key is independent of LDE's **outbound** credential to MDR
  (`LIF_MDR_API_AUTH_TOKEN` / `/{env}/learner-data-export-api/MdrApiKey`) — changing one does
  not affect the other.

**Key env vars:**
| Variable | Purpose |
|----------|---------|
| `LDE_AUTH__API_KEYS` | Server-side: comma-separated `key:label` pairs to accept |
| `LDE_AUTH__PUBLIC_PATHS` | Exact paths that skip auth (default `/health,/health-check`) |
| `LDE_AUTH__PUBLIC_PATH_PREFIXES` | Path prefixes that skip auth (default `/docs,/openapi.json`) |

**Managing keys** (service-agnostic script — also works for any service with an `ApiKeys` param):
```bash
# Preview (dry-run)
AWS_PROFILE=lif ./scripts/setup-api-keys.sh learner-data-export-api demo --temporary 10

# Generate 10 keys (printed once for distribution)
AWS_PROFILE=lif ./scripts/setup-api-keys.sh learner-data-export-api demo --temporary 10 --apply

# Custom label prefix
AWS_PROFILE=lif ./scripts/setup-api-keys.sh learner-data-export-api demo --temporary 5 --prefix integrator --apply

# Remove all 'temporary-*' keys (preserves other entries)
AWS_PROFILE=lif ./scripts/setup-api-keys.sh learner-data-export-api demo --temporary 0 --apply
```

> **Deploy ordering:** the task definition references the `ApiKeys` SSM parameter as a required
> secret. Run the script with `--apply` to **create the parameter first**, then deploy — otherwise
> the task fails to start with `invalid ssm parameters`.

After key changes, redeploy the service to pick them up:
```bash
./aws-deploy.sh -s demo --only-stack demo-lif-learner-data-export-api
```

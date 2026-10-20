# Auth configuration per service

Every LIF service with inbound auth uses the one [`lif.auth`](../../../components/lif/auth/) brick ([ADR 0007](../../design/adr/general/0007-single-auth-brick-with-provider-adapters.md)). Variable names differ per service, but the mechanism is the same: signing secrets go through `lif.auth.config.resolve_secret` / `require_env`. A secret that is unset, blank, or a published placeholder (`changeme`, `changeme1`–`6`, `change4`, `replace`, …, see `KNOWN_PLACEHOLDERS` in [`config.py`](../../../components/lif/auth/config.py)) **stops the service at import**, with an error naming the variable.

This guide lists, for each service: what the code requires, where local compose sets it, where AWS reads it from, and how that value gets created.

- In AWS, the SSM path of every value below is `/{env}/<service>/<name>`, with `{env}` = `dev` or `demo`. The service names are the same in both environments (`ServiceName` in `cloudformation/{env}-lif-*.params`).
- "Local" means [`deployments/advisor-demo-docker/docker-compose.yml`](../../../deployments/advisor-demo-docker/docker-compose.yml) unless stated otherwise.

## Advisor API

| Variable | Required | If missing | Local | AWS (SSM) | Created by |
|---|---|---|---|---|---|
| `SECRET_KEY` | yes | stops at import (`JwtConfig.from_environment`, [`advisor_restapi/core.py:42`](../../../bases/lif/advisor_restapi/core.py)) | `${SECRET_KEY:?…}` (`:438`); also `development/docker-compose.yml:186`. The 1-org/3-org compose files pass `${SECRET_KEY}` through without `:?`, so set it in your shell or `.env` before starting the Advisor there. | `/{env}/advisor-api/JwtSecretKey` ([`lif-advisor-api-taskdef-includes.yml:29`](../../../cloudformation/lif-advisor-api-taskdef-includes.yml)) | **no script**; see [Creating secrets without a script](#creating-secrets-without-a-script) |
| `LIF_DEMO_USER_PASSWORD` | yes | stops at import (`core.py:17-26`) | `.env` | `/{env}/advisor-api/DemoUserPassword` | `scripts/setup-demo-user-password.sh <env>` |

## Example Data Source API

| Variable | Required | If missing | Local | AWS (SSM) | Created by |
|---|---|---|---|---|---|
| `API_TOKEN` | yes | stops at import ([`example_data_source_rest_api/core.py:22`](../../../bases/lif/example_data_source_rest_api/core.py)); placeholders are allowed (`reject_placeholders=False`), because it is a shared credential, not a signing secret | `${API_TOKEN:-changeme}` (`:369`) | `/{env}/example-data-source-rest-api/apiToken` | **no script** |

Callers send it as `x-key`. Dagster is the caller, with `ADAPTERS__EXAMPLE_DATA_SOURCE_REST_API_TO_LIF__ORG1_EXAMPLE_DATA_SOURCE__CREDENTIALS__TOKEN`:
- Locally it is a literal `changeme` (`:633`).
- In AWS it is `/{env}/dagster-ose-example-data-source-rest-api-token` ([`dagster-ose-taskdef-includes.yml:45`](../../../cloudformation/dagster-ose-taskdef-includes.yml)).
- **The two SSM values must be equal**, and nothing keeps them in sync.

## GraphQL API (org1–org3)

| Variable | Required | If missing | Local | AWS (SSM) | Created by |
|---|---|---|---|---|---|
| `GRAPHQL_AUTH__API_KEYS` (`key:name,…`) | no | auth is **off**, logged at info ([`api_graphql/core.py:53`](../../../bases/lif/api_graphql/core.py)) | `${GRAPHQL_AUTH__API_KEYS:-}` (`:64`), so auth is off | `/{env}/graphql-org{1,2,3}/ApiKeys` | org1: `scripts/setup-graphql-api-keys.sh <env>` (see [graphql-api-keys.md](graphql-api-keys.md)); org2/org3: `scripts/setup-api-keys.sh graphql-org2 <env> …` |
| `LIF_MDR_API_AUTH_TOKEN` (its MDR key) | yes, to load the schema from MDR | MDR rejects it | `${LIF_GRAPHQL__LIF_MDR_API_AUTH_TOKEN:-changeme1}` (`:59`) | `/{env}/graphql-org{1,2,3}/MdrApiKey` | `scripts/setup-mdr-api-keys.sh <env> --apply` |

## Learner Data Export API

`LDE_AUTH__MODE` selects the strategies ([`learner_data_export_api/core.py:31`](../../../bases/lif/learner_data_export_api/core.py), default `api_key`):

| Mode | Strategies | Variables |
|---|---|---|
| `api_key` (local default) | `api_key` | `LDE_AUTH__API_KEYS`. When unset, auth is **off** with a warning. Locally it is unset (the MDR export playground calls LDE with an MDR bearer token, which `api_key` mode can't accept). |
| `composite` (**what AWS runs**, `lif-learner-data-export-api-taskdef-includes.yml:46`) | developer key (a stub that returns `None` until #1038), then Cognito | `LDE_AUTH__USER_POOL_ID` / `__CLIENT_ID` from `/{env}/mdr/CognitoUserPoolId` and `CognitoSpaClientId`, which `cloudformation/cognito-selfserve.yml` creates. `LDE_AUTH__API_KEYS` is supplied (`/{env}/learner-data-export-api/ApiKeys`) **but not used in this mode.** |

Its MDR key, `LIF_MDR_API_AUTH_TOKEN`:
- Locally: `${LDE__LIF_MDR_API_AUTH_TOKEN:-${MDR__AUTH__SERVICE_API_KEY__LEARNER_DATA_EXPORT:-changeme6}}` (`:339`).
- AWS: `/{env}/learner-data-export-api/MdrApiKey`, created by `setup-mdr-api-keys.sh`.

## MDR API

Wired by `add_mdr_auth` ([`mdr_auth/core.py`](../../../components/lif/mdr_auth/core.py)). Strategies, in order: service API key, Cognito, HS256.

| Variable | Required | If missing | Local | AWS (SSM) | Created by |
|---|---|---|---|---|---|
| `MDR__AUTH__JWT_SECRET_KEY` | yes. It also signs the workspace cookie and invite tokens. | stops at import | `${MDR__AUTH__JWT_SECRET_KEY:?…}` (`:512`); [`.env.example`](../../../deployments/advisor-demo-docker/.env.example) | `/{env}/mdr-api/MdrAuthJwtSecretKey` | **no script** |
| `MDR__AUTH__SERVICE_API_KEY__{GRAPHQL,SEMANTIC_SEARCH,TRANSLATOR,POST_CONFIRM,LEARNER_DATA_EXPORT}` | each optional | startup warning naming it; that caller's key is rejected (no default) | `:-changeme1/2/3/5/6` (`:513-519`) | `/{env}/mdr-api/MdrAuthServiceApiKey{Graphql,SemanticSearch,Translator,PostConfirm,LearnerDataExport}` | `scripts/setup-mdr-api-keys.sh <env> --apply` (writes each server key and its client copy) |
| `MDR__AUTH__COGNITO_USER_POOL_ID` / `_SPA_CLIENT_ID` | optional | no pool: Cognito off. Pool without a client id: stops at import. | unset (off) | `/{env}/mdr/CognitoUserPoolId`, `CognitoSpaClientId` | `cognito-selfserve.yml` |
| `LIF_DEMO_USER_PASSWORD` | yes, unless `MDR__AUTH__LOCAL_USERS` is set (see [test-driving-mdr.md](test-driving-mdr.md)) | stops at import ([`mdr_restapi/core.py:45-54`](../../../bases/lif/mdr_restapi/core.py)) | `.env` | `/{env}/mdr-api/DemoUserPassword` | `setup-demo-user-password.sh` |

- Give each service key a **different value**. Identical keys collapse into one caller name.
- An unknown `X-API-Key` is a 401, even if a valid Bearer token is also sent.

## Client keys must match server keys

| Client (variable) | Server it calls | Must equal |
|---|---|---|
| GraphQL org1–3 (`LIF_MDR_API_AUTH_TOKEN`) | MDR | `MDR__AUTH__SERVICE_API_KEY__GRAPHQL` |
| Semantic search (`LIF_MDR_API_AUTH_TOKEN`) | MDR | `…__SEMANTIC_SEARCH` |
| Translator org1 (`LIF_MDR_API_AUTH_TOKEN`) | MDR | `…__TRANSLATOR` |
| LDE (`LIF_MDR_API_AUTH_TOKEN`) | MDR | `…__LEARNER_DATA_EXPORT` |
| Post-confirm Lambda (`/{env}/mdr-post-confirm/MdrApiKey`) | MDR | `…__POST_CONFIRM` |
| Semantic search (`LIF_GRAPHQL_API_KEY`) | GraphQL org1 | a key in `/{env}/graphql-org1/ApiKeys` |
| Dagster (`…ORG1_EXAMPLE_DATA_SOURCE__CREDENTIALS__TOKEN`) | Example Data Source | `API_TOKEN` |

`setup-mdr-api-keys.sh` and `setup-graphql-api-keys.sh` write both sides of their pairs. The local defaults line up (`changeme1`–`6`), but overriding a server key locally means overriding the client's own variable too. The exception is LDE, whose local default falls back to the server variable.

## Creating secrets without a script

Four SSM parameters have no setup script. Create each one as a `SecureString` with a strong random value:

```bash
ENV=dev   # or demo
aws ssm put-parameter --type SecureString --name "/$ENV/advisor-api/JwtSecretKey" --value "$(openssl rand -base64 48)"
aws ssm put-parameter --type SecureString --name "/$ENV/mdr-api/MdrAuthJwtSecretKey" --value "$(openssl rand -base64 48)"

# The Example Data Source token and Dagster's copy must be equal:
TOKEN="$(openssl rand -hex 32)"
aws ssm put-parameter --type SecureString --name "/$ENV/example-data-source-rest-api/apiToken" --value "$TOKEN"
aws ssm put-parameter --type SecureString --name "/$ENV/dagster-ose-example-data-source-rest-api-token" --value "$TOKEN"
```

Add `--overwrite` to rotate an existing value, then redeploy the services that read it. Rotating a JWT secret invalidates every token it signed: Advisor sessions, MDR's HS256 sessions, workspace-selection cookies, and outstanding invite tokens. Cognito sign-ins are unaffected.

## Verifying a deployment has what it needs

This is read-only: it prints each parameter's name, or an error for a missing one, and never shows values.

```bash
ENV=dev   # or demo
for p in advisor-api/JwtSecretKey advisor-api/DemoUserPassword \
         example-data-source-rest-api/apiToken dagster-ose-example-data-source-rest-api-token \
         graphql-org1/ApiKeys graphql-org2/ApiKeys graphql-org3/ApiKeys \
         graphql-org1/MdrApiKey graphql-org2/MdrApiKey graphql-org3/MdrApiKey \
         learner-data-export-api/ApiKeys learner-data-export-api/MdrApiKey \
         mdr-api/MdrAuthJwtSecretKey mdr-api/DemoUserPassword \
         mdr-api/MdrAuthServiceApiKeyGraphql mdr-api/MdrAuthServiceApiKeySemanticSearch \
         mdr-api/MdrAuthServiceApiKeyTranslator mdr-api/MdrAuthServiceApiKeyPostConfirm \
         mdr-api/MdrAuthServiceApiKeyLearnerDataExport mdr-post-confirm/MdrApiKey \
         semantic-search/MdrApiKey semantic-search/GraphqlApiKey translator-org1/MdrApiKey \
         mdr/CognitoUserPoolId mdr/CognitoSpaClientId; do
  aws ssm get-parameter --name "/$ENV/$p" --query Parameter.Name --output text 2>&1 | sed "s|^|$p: |"
done
```

ECS can't start a task whose `Secrets` parameter is missing. A missing name here therefore explains a service that won't start after a deploy.

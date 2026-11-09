# 5. Cross-cutting concerns

The rules every service shares — authentication, configuration, schema loading, timeouts, and what may never go in a log.

*Checked against main `2967cb9`, November 2026.* The auth table comes from searching each base for `lif.auth` / `lif.mdr_auth`.

---

## Authentication

There is **one auth brick**, `components/lif/auth/` (ADR 0007,
[`docs/design/adr/general/0007-single-auth-brick-with-provider-adapters.md`](../../design/adr/general/0007-single-auth-brick-with-provider-adapters.md)). A service builds an
`AuthMiddleware` from a list of **strategies**, and the first strategy that recognizes the caller wins:

- `api_key_strategy`: an `X-API-Key` header checked against a configured list;
- `jwt_strategy`: our own HS256 tokens (the MDR and Advisor logins);
- `cognito_strategy`: Amazon Cognito tokens (self-serve sign-up, in the team's AWS-hosted environments;
  optional, and off locally).

A strategy returns a `Principal` (authenticated), `None` (not my kind of credential, try the next one), or
raises `AuthError` (my kind, but invalid → 401). The middleware puts the result on
`request.state.principal`. Details and the contract: [`components/lif/auth/README.md`](../../../components/lif/auth/README.md).

**Which services check callers today:**

| Service | Inbound auth |
|---|---|
| GraphQL API | API key (`GRAPHQL_AUTH__API_KEYS`), **off when unset**, which it is locally |
| MDR API | JWT, API keys per service, Cognito when configured, plus tenant selection (`lif.mdr_auth`) |
| Learner Data Export API | Cognito in the team's AWS environments (`LDE_AUTH__MODE=composite`). Developer keys aren't accepted yet: that strategy is a stub that returns `None` (`learner_data_export_api/core.py`) |
| Control-plane API, Advisor API, Example Data Source | yes (`lif.auth`) |
| Query Planner, Query Cache, Orchestrator, Translator, Identity Mapper, Semantic Search | **none**: in the team's AWS environments they rely on not being reachable from outside the private network (Query Planner auth is #1108). Locally most of their ports *are* published to your machine, so anything on it can call them |

When a service *calls* the MDR, it sends its own key in `X-API-Key` (`LIF_MDR_API_AUTH_TOKEN`; the
compose defaults are `changeme1`… placeholders). Per-service variables, and what happens when one is
missing: [`docs/operations/guides/auth-configuration.md`](../../operations/guides/auth-configuration.md).

## Configuration

Every service is configured by **environment variables**. The patterns you'll see:

- `os.getenv("NAME", default)` at module level, for simple settings.
- **Fail fast for secrets**: `lif.auth.config.require_env` / `resolve_secret` stop the service at startup
  and name the missing variable, rather than running with a default. The MDR also refuses known
  placeholder secrets.
- **Double underscores group names by service and area** (`MDR__AUTH__…`, `GRAPHQL_AUTH__…`,
  `LDE_AUTH__…`). They're a naming convention, not nesting: the MDR's pydantic `Settings`
  (`components/lif/mdr_utils/config.py`) has flat fields such as `mdr__auth__jwt_secret_key`.
- **Shared schema settings** come from `LIFSchemaConfig.from_environment()`
  (`components/lif/lif_schema_config/`): which model to load (`OPENAPI_DATA_MODEL_NAME`, `…_VERSION`,
  `…_CONTRIBUTOR_ORGANIZATION`), where the MDR is (`LIF_MDR_API_URL`), the planner URL, and so on.

Locally, values come from `deployments/advisor-demo-docker/docker-compose.yml` and your `.env`. In the
team's AWS-hosted dev and demo they come from each service's `cloudformation/*-taskdef-includes.yml` and SSM ([chapter 9](09-environments-and-deploys.md)).

## Schema loading

Services that need the data model load it **from the MDR at startup** and **fail loudly if the MDR is
configured but unreachable**. There is no silent fallback to a bundled file.
`USE_OPENAPI_DATA_MODEL_FROM_FILE=true` forces the bundled file, for development only. Because the schema
is read once at startup, **restart a service after changing its model**. (The Translator is different: it
caches each schema for `TRANSLATOR_CACHE_TTL_SECONDS`, default 300, so it picks up a change within 5 minutes.) The pattern and the
`SchemaStateManager` component: [`docs/design/cross-cutting/schema-loading.md`](../../design/cross-cutting/schema-loading.md).

## Timeouts

Each hop on a request path has its own timeout, and they must shrink as you go inward: the caller has
to wait longer than the service it calls, or it gives up on an answer that was about to arrive. The
ladders for the query and export paths, and the rule: [`docs/design/cross-cutting/timeouts.md`](../../design/cross-cutting/timeouts.md). Locally
the planner's budget is 120 s (compose), the code default is 300 s.

## Logging, and keeping learner data out of it

Use `from lif.logging import get_logger; logger = get_logger(__name__)`. `LOG_LEVEL` sets the level
(default `INFO`). The MDR's internals use their own logger config.

**Learner data must not reach the logs**, at any level that runs in an environment. Logs leave the
service (CloudWatch) and are read by more people than the data's owners. The codebase has been cleaned of
this several times (#1269, #1319, #1340, #1351), and the comments left behind show the rules:

- **Don't log request or response bodies**, and don't log an upstream error's body: a 422 echoes back the
  learner data that was posted.
- **Don't log a GraphQL query document**: its filter holds the learner's identifier.
- **Don't put an exception's message in a response**, and be careful logging one: many messages quote the
  value that failed.
- **Log the shape, not the content**: counts, field names, sizes (`_shape(...)` in the orchestrator's `lif_job.py`,
  `summarize_query_plan` in `query_planner_service/util.py`, "`(393-byte body)`").
- **Watch URLs.** uvicorn's access log records the full path and query string, so an identifier in a URL
  (`/users/100006`) is logged by default (#1372, open).

A test that checks a log line for learner values is worth writing whenever you touch a code path that
handles them.

## Errors

- Services raise `LIFException` (`components/lif/exceptions/`) and its subclasses; bases turn them into
  HTTP responses.
- A failure must not look like "no data". The GraphQL API raises on a non-200 from the planner instead of
  returning `[]` (#1264), and the planner returns 503 when a query fails with nothing to show (#1232).
  Keep that property when you add a code path.

---

## Where to go next

- [`docs/operations/guides/auth-configuration.md`](../../operations/guides/auth-configuration.md), [`docs/operations/guides/graphql-api-keys.md`](../../operations/guides/graphql-api-keys.md) (the latter
  is partly out of date: the `--workshop` flag is now `--temporary`).
- [`docs/design/cross-cutting/self-serve-tenant-auth.md`](../../design/cross-cutting/self-serve-tenant-auth.md) for the Cognito sign-up flow (partly out of date).
- [Chapter 8](08-debugging-and-traps.md) for debugging when one of these goes wrong.

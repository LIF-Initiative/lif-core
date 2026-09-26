# Test-Driving the MDR Without AWS

Run the Metadata Repository (MDR) on any Docker host, such as a cloud VM, with a single schema and logins you configure yourself. No AWS and no Cognito required (#1316).

This is the MDR-only first stage of [#1290](https://github.com/lif-initiative/lif-core/issues/1290). Adding a full organization (GraphQL, Query Planner, and the rest of the stack) is tracked in #1317. For the whole-stack picture, start at [`deploying-lif-at-your-institution.md`](deploying-lif-at-your-institution.md).

## What you get

| Piece | Default port | Notes |
|---|---|---|
| MDR UI | 5173 | Password sign-in form, because the UI is built without Cognito settings |
| MDR API | 8012 | `/health-check` is public; the rest needs a sign-in token or a service API key |
| MDR Postgres | 5445 | Seeded with the LIF baseline data model on first start |

It runs as a single schema: tenant routing is off by default, so every request uses `public` (`mdr__tenant_routing__enabled` in `components/lif/mdr_utils/config.py`). Cognito is off whenever `MDR__AUTH__COGNITO_USER_POOL_ID` is empty (`components/lif/mdr_auth/core.py`), and the compose file never sets it.

## Prerequisites

- Docker with Compose v2
- `git`
- `python3`, standard library only, to generate password hashes

## 1. Get the code

```bash
git clone https://github.com/lif-initiative/lif-core.git
cd lif-core
```

Build from a fresh clone. The MDR UI image has no `.dockerignore`, so a stale `frontends/mdr-frontend/node_modules` left by a local `npm install` gets copied over the image's clean install and can fail the build with TypeScript errors.

## 2. Create the logins

Generate a hash for each person. The script prompts twice and prints the hash:

```bash
python3 scripts/hash-mdr-password.py
```

The output looks like `scrypt:16384:8:1:<salt>:<key>`. It contains no `$`, `,` or `=`, so it pastes into `.env` as-is.

## 3. Write `deployments/advisor-demo-docker/.env`

Compose reads `.env` from the directory it runs in, and the file is gitignored. Every value marked "replace" has a well-known default in the compose file or in MDR's settings, so leaving one unset on a reachable host gives away access.

```bash
# --- Logins (#1316) -------------------------------------------------------
# Comma-separated username=hash pairs from scripts/hash-mdr-password.py.
# When set, these replace the built-in demo personas.
MDR__AUTH__LOCAL_USERS=alice@example.org=scrypt:...,bob@example.org=scrypt:...

# --- Secrets: replace every value ------------------------------------------
# Signs MDR sign-in tokens (compose default: change4).
MDR__AUTH__JWT_SECRET_KEY=replace-with-a-long-random-string
# Service API keys. Anyone holding one gets service-level API access
# (defaults: changeme1, changeme2, changeme3, changeme5, changeme6).
MDR__AUTH__SERVICE_API_KEY__GRAPHQL=replace
MDR__AUTH__SERVICE_API_KEY__SEMANTIC_SEARCH=replace
MDR__AUTH__SERVICE_API_KEY__TRANSLATOR=replace
MDR__AUTH__SERVICE_API_KEY__POST_CONFIRM=replace
MDR__AUTH__SERVICE_API_KEY__LEARNER_DATA_EXPORT=replace
# Postgres password (default: postgres). The three must match.
LIF_MDR__DATABASE__PASSWORD=replace
LIF_MDR__DATABASE_RESTORE__PASSWORD=replace
LIF_MDR__API__DATABASE_PASSWORD=replace

# --- Required by compose even for an MDR-only run ---------------------------
# Compose interpolates the whole file, so these must be set even though the
# services that use them are not started. With MDR__AUTH__LOCAL_USERS set,
# MDR ignores LIF_DEMO_USER_PASSWORD.
LIF_DEMO_USER_PASSWORD=replace
SECRET_KEY=replace

# --- Public URLs: only when not on localhost --------------------------------
# Baked into the UI at build time. Rebuild the UI after changing it.
# The GraphQL services read the same variable as their in-network MDR address.
# That doesn't matter for an MDR-only run, which doesn't start them (see #1317).
LIF_MDR_API_URL=https://mdr-api.example.org
# Browser origins allowed to call the API. The LDE service reads the same variable.
CORS_ALLOW_ORIGINS=https://mdr.example.org
```

Generate random values with something like `python3 -c "import secrets; print(secrets.token_hex(32))"`.

## 4. Start it

```bash
cd deployments/advisor-demo-docker
docker compose up -d --build lif-mdr-app
```

Naming `lif-mdr-app` starts only the MDR slice. Compose follows its dependencies: the API waits for Postgres to start and for the one-shot restore container to load the baseline and migrations, then the UI starts. The restore container shows as `Exited (0)` afterwards, which is expected.

## 5. Check it

```bash
curl -s localhost:8012/health-check
curl -s -X POST localhost:8012/login -H 'content-type: application/json' \
  -d '{"username":"alice@example.org","password":"<password for alice>"}'
```

The sign-in returns an `access_token`. Pass it as `Authorization: Bearer <token>`, for example to `GET /datamodels/`, which should list the seeded data models. Then open the UI on port 5173 and sign in with the same credentials.

A wrong password, or a demo persona once `MDR__AUTH__LOCAL_USERS` is set, gets `401`.

## Running on a reachable host

- **Put TLS in front.** The containers speak plain HTTP. Terminate HTTPS at a reverse proxy (Caddy, nginx, or your cloud's load balancer) that forwards to ports 5173 and 8012, and firewall those ports and 5445 from everything but the proxy.
- **Set the public API URL before building.** The UI calls whatever `LIF_MDR_API_URL` was at build time. The default is `http://localhost:8012`, which only works in a browser on the same machine. After changing it, run `docker compose build lif-mdr-app` and start the slice again.
- **Allow the UI's origin.** `CORS_ALLOW_ORIGINS` must include the URL the UI is served from, or the browser blocks its API calls.

## Data lifetime

The database keeps its data across `docker compose stop`/`start` and repeated `up`s. On each `up` the restore container runs again: it logs "already exists" errors for the baseline objects and leaves existing data unchanged. The database has no named volume, so treat `docker compose down` as a reset back to the baseline.

## Adding or changing a login

Edit `MDR__AUTH__LOCAL_USERS`, then recreate the API so it picks up the new value:

```bash
docker compose up -d lif-mdr-api
```

MDR refuses to start if an entry is malformed, such as a missing `=`, a hash not produced by the script, or the same username listed twice, and the error names the entry. Check `docker compose logs lif-mdr-api`.

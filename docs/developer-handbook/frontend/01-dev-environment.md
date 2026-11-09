# 1. Your development environment

Install and run either app, configure it, point it at the backend, and log in.

*Checked against main `2967cb9`, November 2026.* Commands were run in a `node:20` container against the local stack.

---

## Install and run

You need **Node 20** (CI uses it) and npm. Each app is independent:

```bash
cd frontends/mdr-frontend        # or frontends/lif_advisor_app
npm ci                           # exact install from package-lock.json, as CI does
npm run dev                      # Vite dev server, with live reload
```

`npm ci` installs exactly what `package-lock.json` lists. Use it rather than `npm install`, which may
update the lock file and put an unrelated change in your PR.

### No Node on your machine?

Run the same commands in a container. That's how this handbook checked them:

```bash
# install and run the tests
docker run --rm -v "$PWD":/app -w /app -u "$(id -u):$(id -g)" -e HOME=/tmp node:20 sh -c 'npm ci && npm test'

# the dev server: --host 0.0.0.0 makes Vite listen beyond the container's own localhost, so -p can reach it.
# The browser, not the dev server, calls the APIs, so VITE_API_URL stays http://localhost:8012.
docker run --rm --name mdr-ui-dev -p 5173:5173 -v "$PWD":/app -w /app -u "$(id -u):$(id -g)" -e HOME=/tmp \
  -e VITE_API_URL=http://localhost:8012 node:20 npx vite --host 0.0.0.0 --port 5173 --strictPort
# stop it with Ctrl-C, or `docker stop mdr-ui-dev` from another terminal
```

`-u "$(id -u):$(id -g)"` makes the files the container writes (`node_modules/`, `dist/`) belong to you
rather than to root.

If Docker is the snap package (Ubuntu), it can't bind-mount paths under `/tmp`: the container silently gets an
empty directory instead. Keep anything you mount under your home directory or inside the repo.

## Configuration is baked in at build time

Both apps read `import.meta.env.VITE_*` values, which Vite **writes into the code when it builds**
([chapter 0](00-start-here.md), "How a web app like this works"). Changing an environment variable on a
running container does nothing; rebuild. For `npm run dev`, put the values in a `.env` file in the app
directory (it's git-ignored) or export them before starting the server.

There are no defaults and no `.env` in the repo. Leave `VITE_API_URL` unset and the MDR UI's API calls
don't reach the MDR.

| App | Variable | Docker build arg | Purpose |
|---|---|---|---|
| MDR UI | `VITE_API_URL` | `LIF_MDR_API_URL` | MDR API base URL |
| MDR UI | `VITE_LDE_API_URL` | `LDE_API_URL` | Learner Data Export API (Export Playground) |
| MDR UI | `VITE_COGNITO_DOMAIN`, `VITE_COGNITO_CLIENT_ID` | `COGNITO_DOMAIN`, `COGNITO_CLIENT_ID` | Cognito sign-in. **If either is unset, the UI uses username/password login** (the local default) |
| both | `VITE_GA_MEASUREMENT_ID` | `GA_MEASUREMENT_ID` | Google Analytics; a no-op when unset |
| Advisor | `VITE_LIF_ADVISOR_API_URL` | `LIF_ADVISOR_API_URL` | Advisor API base URL |

For a Docker build the names differ: you pass the build arg (`LIF_MDR_API_URL`), and the Dockerfile writes
it into a `.env` as `VITE_API_URL` before running `npm run build`. The resulting image is nginx serving
static files; no part of it reads the container's environment.

## Running against the backend

The UI is only useful with its API running. Start the backend from `deployments/advisor-demo-docker`
(backend [chapter 1](../backend/01-dev-environment.md)); your `.env` there comes from `.env.example`.

- **MDR UI:** `docker compose up -d lif-mdr-api` (it brings its database). Then either `npm run dev`
  with `VITE_API_URL=http://localhost:8012`, or start the compose service `lif-mdr-app`, which serves a
  production build on :5173. Use the dev server while you're changing code; it reloads on save.
- **Advisor app:** needs the Advisor API (`lif-advisor-api`), which needs `OPENAI_API_KEY` in `.env` and,
  behind it, the GraphQL API, the MDR and the Semantic Search server. Without a key the app loads, but chat
  can't work. See [chapter 4](04-advisor-app.md).

To rebuild a compose-served app after a change: `docker compose up -d --build lif-mdr-app` (or
`lif-advisor-app`).

### CORS: use port 5173 for the MDR UI

The MDR API only answers browsers from the origins listed in its `CORS_ALLOW_ORIGINS` (set on
`lif-mdr-api` in the compose file; locally `http://localhost:3000`, `:5173`, `:8080` and the team's two
hosted origins). A dev server on any other port gets every API call blocked. The Learner Data Export API
(`lif-learner-data-export-api`) has the same list, so the Export Playground's calls fail the same way.

Both apps' dev servers default to 5173: the MDR UI by Vite's default, the Advisor app in its
`vite.config.ts`. Whichever starts second moves to 5174, which isn't in the list. So start the MDR UI
first, or start the Advisor app with `npm run dev -- --port 5174`. The Advisor API allows any origin, so
the Advisor app works on any port. (5174 is also the Advisor app's port in compose, where it's a
container rather than a dev server.)

What that looks like: the page itself loads, because Vite serves it, but every API call fails. The app
shows a vague failure, because axios reports a generic `Network Error` with no status. The browser's
developer tools tell you the real cause. The console says the request was "blocked by CORS policy", and the
Network tab shows the `OPTIONS` request answered `400` with no follow-up request.

Check from the command line with the same preflight request the browser sends:

```bash
curl -s -o /dev/null -D - -X OPTIONS http://localhost:8012/datamodels/ \
  -H "Origin: http://localhost:5173" -H "Access-Control-Request-Method: GET" | grep -i allow-origin
```

An allowed origin is echoed back in `access-control-allow-origin`; a disallowed one gets
`400 Disallowed CORS origin` with no such header. The MDR UI sends cookies (`withCredentials`,
[chapter 2](02-mdr-ui.md)), and browsers refuse a `*` wildcard for requests with cookies, so the API has to
name the origin exactly.

The Advisor app doesn't have this problem: the Advisor API allows any origin (`allow_origins=["*"]` in
`bases/lif/advisor_restapi/core.py`), and the app sends its token in a header, not a cookie.

### Log in

With username/password login (the local default), use one of the demo personas, for example
`atsatrian_lifdemo@stateu.edu`, and the `LIF_DEMO_USER_PASSWORD` from your backend `.env` (the value in
`.env.example` works locally). The full list of personas is in `components/lif/demo_personas/core.py`.
Checked 11-07: the MDR API returns access and refresh tokens for that login.

The Advisor app takes the same personas and the same password.

## Where to go next

[Chapter 2](02-mdr-ui.md) for how the MDR UI is put together, or [chapter 4](04-advisor-app.md) for the Advisor app.

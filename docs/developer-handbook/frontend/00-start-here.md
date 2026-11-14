# 0. Start here: the frontend

What the two LIF web apps are, how a web app like this fits together, the few MDR ideas you need, and the order to read the rest.

*Checked against main `2967cb9`, November 2026.* Install, lint, test and build were run for both apps in a `node:20` container.

---

## The two apps

| | MDR UI (`frontends/mdr-frontend/`) | Advisor app (`frontends/lif_advisor_app/`) |
|---|---|---|
| What it is | The editor for the MDR: data models, entities, attributes, value sets, mappings and transformations, workspaces, API keys, an export playground | A demo chat client for the Advisor, an LLM agent that answers questions about a learner's LIF record |
| Talks to | MDR API (`VITE_API_URL`, :8012 locally) and the Learner Data Export API (`VITE_LDE_API_URL`, :8013) | Advisor API (`VITE_LIF_ADVISOR_API_URL`, :8004) |
| Size (Nov 2026) | 89 TypeScript files | 17 TypeScript files |
| Stack | React 18, TypeScript, Vite, Radix UI Themes, React Router 6, axios, `jsonata`, `ajv` | React 18, TypeScript, Vite, Tailwind, axios, `react-markdown` |
| Local URL | http://localhost:5173 (dev server and compose) | dev server http://localhost:5173, compose http://localhost:5174 |
| Team's demo hosting (AWS, to date) | Static site on S3 + CloudFront | Container on ECS |

They share nothing: separate `package.json`, lock file, lint config, and conventions. There's no shared
component library.

What the less common libraries in the MDR UI are for:

| Library | Used for |
|---|---|
| **Radix UI Themes** | The UI components: dialogs, buttons, layout (`Dialog`, `Flex`, `Box`…) |
| **React Router 6** | Which page shows for which URL (chapter 2) |
| **axios** | HTTP calls to the APIs |
| **`@xyflow/react`** | Nothing that runs: it's in `package.json`, but only two unused types come from it (`types.ts`). The mapping editor's wires are SVG paths the app draws itself (chapter 2) |
| **`jsonata`** | Running mapping expressions in the browser, with the same language the backend uses |
| **`ajv`** | Checking a mapping's previewed output against the target model's JSON Schema, the same check the Translator makes (`utils/schemaValidation.ts`) |

## How a web app like this works

If you've built server-rendered web apps or APIs but not a single-page app, this is the part that
explains most of the surprises later.

1. **The app is a bundle of static files.** `npm run build` turns the TypeScript into JavaScript, CSS and
   one `index.html` in `dist/`. Any web server can serve them: locally an nginx container, in the team's
   demo hosting an S3 bucket. The server that hands out these files runs no LIF code.
2. **The user's browser runs the app, and the browser calls the APIs.** When the MDR UI loads a data
   model, the request goes from the browser on your machine to the MDR API. It doesn't go through the
   container that served the files.
3. **So the API URL must be one the browser can reach.** That's `http://localhost:8012`, not
   `http://lif-mdr-api:8012`. The `lif-mdr-api` name only resolves inside Docker's network, and the browser
   isn't in it. The compose file says this next to the build args: "Web client needs to access the API
   outside the container" (`deployments/advisor-demo-docker/docker-compose.yml`, `lif-mdr-app` and
   `lif-advisor-app`).
4. **The URL is fixed when the app is built.** Vite replaces `import.meta.env.VITE_API_URL` with the actual
   string while it builds. There's nothing to read at runtime, so setting an environment variable on the
   running container does nothing. To point a built app somewhere else, build it again.
5. **The browser enforces CORS.** The app is served from one origin (`http://localhost:5173`) and calls
   another (`http://localhost:8012`). The browser only lets the page read the answer if the API says that
   origin is allowed. Getting this wrong looks like a "Network Error" in the app ([chapter 1](01-dev-environment.md)).

## The MDR in four sentences

You'll meet these words on every MDR screen. A **data model** is a named, versioned schema: **entities**
(object types such as `Person`) holding **attributes** (scalar fields such as `firstName`). A
**transformation group** (the UI calls it a mapping) turns records in one data model into another, with
one **JSONata** expression per target field. Only an **activated** group is used: the Translator reads the
live version of each source-and-target pair on every request, so activating a new version changes what the
system produces with no restart. A **workspace** (a tenant) is a separate copy of all of this per team.

That's enough to run and change the UI. Before you change how a feature *behaves*, read backend
[chapter 3](../backend/03-data-model-and-mdr.md) for the full picture, and [chapter 4](../backend/04-follow-the-data.md) to see where
the Translator fits.

## Reading order

| # | Chapter | Read it when |
|---|---|---|
| 1 | [Your development environment](01-dev-environment.md) | First: install, run against the API, log in |
| 2 | [The MDR UI](02-mdr-ui.md) | Before you change the MDR UI: layout, auth, workspaces, features |
| 3 | [Follow a click](03-follow-a-click.md) | Next: one button traced from the screen to the database and back |
| 4 | [The Advisor app](04-advisor-app.md) | If you'll work on the chat app |
| 5 | [Recipes](05-recipes.md) | When you make your first change |
| 6 | [Checks, CI and shipping](06-checks-ci-and-shipping.md) | Before you open a PR |

How the team works (issues, commits, PRs) is the same for frontend and backend: backend
[chapter 6](../backend/06-how-we-work.md).

## Words you'll see

| Term | Meaning |
|---|---|
| **Vite** | The dev server and build tool for both apps. `npm run dev` serves the source with live reload; `npm run build` makes `dist/` |
| **`import.meta.env.VITE_*`** | Configuration values that Vite writes into the code at build time. Only names starting with `VITE_` are exposed |
| **axios instance** | A preconfigured HTTP client (base URL, timeout, cookies) that the services share; one per API the app calls |
| **Interceptor** | A function axios runs on every request or every response. Both apps use a response interceptor to catch `401` and refresh the login |
| **Access / refresh / ID token** | Access token: sent with each request, short-lived. Refresh token: used once the access token expires, to get a new one without logging in again. ID token: Cognito's token describing the user; with Cognito, the MDR UI sends this one |
| **`localStorage`** | Per-browser key-value storage that survives reloads. Both apps keep their tokens there |
| **HttpOnly cookie** | A cookie the browser stores and sends but the page's JavaScript can't read. The MDR's workspace selection is one |
| **Origin** | Scheme, host and port together: `http://localhost:5173`. CORS rules are per origin |
| **Preflight** | The `OPTIONS` request a browser sends before a cross-origin call, asking the API whether it's allowed |
| **Data routes** | React Router's style of declaring every URL and its page in one object (`createBrowserRouter`) instead of in JSX |
| **Service** (in the MDR UI) | A file in `src/services/` with one function per API endpoint for one resource |

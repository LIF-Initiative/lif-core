# LIF Metadata Repository (MDR) Frontend

The **Metadata Repository (MDR)** is a key component of LIF. It provides the capabilities to maintain the *LIF data model* in all of its iterations---including an *organization-specific LIF data model* and *partner LIF data models.* The **MDR** and *LIF data model* will be maintained by the steward or organization governing LIF.

The **MDR** is a standalone component that serves as the LIF system of record. It is where individuals from implementing organizations maintain their *organization-specific LIF data model* and *partner LIF data models* through a graphical user interface.

Additionally, the **MDR** provides the capability for the organization to maintain source data model(s) and mappings to transform data into a structure aligned to the *organization-specific LIF data model*.

The **MDR** will enable the organization to define which elements of its *organization-specific LIF data model* can be shared externally as its *partner-accessible LIF data model*. As a Possible Future Roadmap Item, the **MDR** will also allow the retrieval of the *partner-accessible LIF data model* from partners that have allowed for queries via **LIF API**.

## Project Structure

A Vite + React 18 + TypeScript single-page app, styled with Radix UI Themes.

```
mdr-frontend/
├── Dockerfile          # Two-stage build: node (vite build) → nginx (static serve)
├── nginx.conf          # SPA fallback for the Docker image
├── public/             # Static assets copied as-is (logo, robots.txt)
└── src/
    ├── main.tsx        # Entry point
    ├── types.ts        # Shared types
    ├── components/     # Reusable UI — one folder per component: <Name>/<Name>.tsx (+ <Name>.css)
    ├── config/         # Build-time config (Cognito)
    ├── context/        # React context providers (Auth, Mdr, Toast)
    ├── pages/          # Route-level views; Routes.tsx defines the router
    │   └── Explore/    # Data Models, Mappings, LIF Model, Extensions, Search tabs
    │       └── Mappings/{components,hooks}/   # Mappings-only UI and hooks
    ├── services/       # API clients (axios); api.ts is the shared MDR client, ldeApi.ts the LDE client
    └── utils/          # Pure helpers; unit tests sit next to them (*.test.ts)
```

Conventions:

- **Naming:** components, pages and their CSS files are PascalCase (`ModelExplorer.tsx`, `LifModel.css`). Services, hooks and utils are camelCase (`modelService.ts`, `useMappingWires.ts`).
- **Placement:** a component used only by one feature lives next to that feature (for example `pages/Explore/Mappings/components/`); shared ones go in `src/components/`.
- **Imports:** `@/` maps to `src/` (`tsconfig.app.json` `paths` + `vite.config.ts` `resolve.alias`). Use `./` or a single `../` for nearby files and `@/…` for anything further away. Use double quotes and no file extensions.

## Scripts

| Command | What it does |
|---------|--------------|
| `npm run dev` | Vite dev server on http://localhost:5173 |
| `npm run build` | `tsc -b` type-check, then `vite build` into `dist/` |
| `npm run lint` | ESLint |
| `npm test` | vitest (node environment, `src/**/*.test.ts`) |
| `npm run preview` | Serve the built `dist/` |

## Environment Variables

All values are read at **build time** (`import.meta.env`) and baked into the bundle. For local development, put them in a `.env` file here or export them before `npm run dev`. The Docker build writes them to `.env` from build args.

| Variable | Docker build arg | Purpose |
|----------|------------------|---------|
| `VITE_API_URL` | `LIF_MDR_API_URL` | MDR API base URL (`lif_mdr_api`, port 8012 locally) |
| `VITE_LDE_API_URL` | `LDE_API_URL` | Learner Data Export API, used by the Export Playground (port 8013 locally) |
| `VITE_COGNITO_DOMAIN` | `COGNITO_DOMAIN` | Cognito hosted-UI domain. If this or the client ID is unset, the app uses username/password login instead |
| `VITE_COGNITO_CLIENT_ID` | `COGNITO_CLIENT_ID` | Cognito app client ID |
| `VITE_GA_MEASUREMENT_ID` | `GA_MEASUREMENT_ID` | Google Analytics 4 ID. Optional; analytics is a no-op when unset |

## Local Development

Prerequisites: `npm`, `docker` and Docker Compose. The native and image-only options below also need a reachable `lif_mdr_api` (Compose starts it for you).

### Docker Compose (recommended)

From the repository root:

```bash
cd deployments/advisor-demo-docker
docker compose up -d --build
```

The MDR UI is served at http://localhost:5173. To rebuild just this app:

```bash
docker compose build --no-cache lif-mdr-app && docker compose up -d lif-mdr-app
```

`LIF_MDR_API_URL` (default `http://localhost:8012`) and `LDE_API_URL` (default `http://localhost:8013`) can be overridden in the environment.

### Native (Vite dev server)

```bash
cd frontends/mdr-frontend
npm install
export VITE_API_URL=http://localhost:8012
npm run dev
```

### Docker image only

```bash
cd frontends/mdr-frontend
docker build --build-arg LIF_MDR_API_URL=http://localhost:8012 -t mdr-frontend:latest .
docker run -p 9000:80 mdr-frontend:latest   # http://localhost:9000
```

## Deployment

The MDR frontend is a static site on S3 + CloudFront, not an ECS service.

- **dev:** [`.github/workflows/lif_mdr_frontend.yml`](../../.github/workflows/lif_mdr_frontend.yml) runs on push to `main` that touches this directory. It builds with values from SSM, syncs `dist/` to S3, and invalidates CloudFront.
- **demo:** [`scripts/release-demo-frontend.sh`](../../scripts/release-demo-frontend.sh), as part of the [demo promotion](../../docs/operations/guides/demo-environment-update.md).
- **PR CI:** [`.github/workflows/pr-ci.yml`](../../.github/workflows/pr-ci.yml) runs `npm ci`, `npm run build` and `npm run test` for this app.

## Tests

```bash
npm install
npm test
```

Unit tests use vitest and sit next to the code they cover (for example `src/utils/schemaValidation.test.ts`). For browser end-to-end tests, see [`docs/operations/guides/mdr-ui-e2e-playwright.md`](../../docs/operations/guides/mdr-ui-e2e-playwright.md).

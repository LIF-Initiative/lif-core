# 6. Checks, CI and shipping

What to run before you push, what CI checks (and what it misses), the traps, and how a merged change reaches the team's hosting.

*Checked against main `2967cb9`, November 2026.* Every command was run in a `node:20` container.

---

## The checks

| | MDR UI | Advisor app |
|---|---|---|
| `npm run lint` | ESLint | ESLint |
| `npm test` | vitest, `src/**/*.test.ts`, node environment | vitest |
| `npm run build` | `tsc -b && vite build`: **type-checks** | `vite build` only: **no type-check**; run `npx tsc --noEmit -p tsconfig.app.json` yourself |
| Measured 11-07 (node:20 container) | `npm ci` 11 s; lint 6 s, **0 errors, 696 warnings**; 54 tests in ~2 s; build 20 s | `npm ci` 19 s; lint 3 s, clean; 23 tests in ~1 s; build 7 s; `npx tsc --noEmit -p tsconfig.app.json` passes |

Before you push, run all of them for the app you changed, plus the type-check for the Advisor app. They take
under a minute.

The MDR UI's 696 lint warnings are existing debt and don't fail the lint. Don't add to them
([chapter 5](05-recipes.md) shows how to check), and don't mix a mass cleanup into a feature PR.

> **The Advisor app's types are not checked anywhere in CI.** Its `npm run build` is `vite build`, which
> strips types without checking them, and its lint isn't type-aware. Checked 11-07: a file with a type error
> passes build, lint and tests, and only `npx tsc --noEmit -p tsconfig.app.json` fails. Run that yourself
> before you push an Advisor change.

## CI

`.github/workflows/pr-ci.yml`, job "Frontend build", runs for both apps on Node 20: `npm ci`, `npm run build`,
`npm run lint`, `npm run test --if-present`. Both apps' builds are **required checks** on `main`, so a
frontend break blocks every PR, including backend ones.

The tests are unit tests on helpers and services; there are no component-rendering tests
([chapter 5](05-recipes.md), "Test a helper"). For a change you need to see, run it against the real API, or
drive it with Playwright:
[`docs/operations/guides/mdr-ui-e2e-playwright.md`](../../operations/guides/mdr-ui-e2e-playwright.md).

Frontend PRs follow the same issue, commit and PR rules as the backend (backend [chapter 6](../backend/06-how-we-work.md)).

## Traps

- vitest treats a function **returned** from `beforeEach` as teardown: `beforeEach(() => mock.mockReset())`
  runs `mockReset`'s result after each test. Use braces: `beforeEach(() => { mock.mockReset(); })`.
- `tsc -b` writes `tsconfig.*.tsbuildinfo` files, which aren't git-ignored. Don't commit them.
- A production build bakes in the API URL; a build made for localhost won't work anywhere else
  ([chapter 0](00-start-here.md)).
- `npm install` can rewrite `package-lock.json`. Use `npm ci` unless you mean to change dependencies, and
  then commit the lock file with the change.

## Shipping

To date (November 2026), the team hosts both apps on AWS for its dev and demo environments. That's how
we've deployed for demos, not a requirement: the MDR UI builds to static files (`dist/`) that any static
host can serve, and the Advisor app is a container. Cognito sign-in is optional too: without it, the MDR UI
uses username and password ([chapter 1](01-dev-environment.md)).

- **MDR UI → dev:** `.github/workflows/lif_mdr_frontend.yml`, on a push to `main` touching
  `frontends/mdr-frontend/**`. It writes its own `.env` with the dev URLs and Cognito values from SSM, builds,
  syncs `dist/` to S3, and invalidates CloudFront.
- **MDR UI → demo:** `scripts/release-demo-frontend.sh`, during demo promotion.
- **Advisor app → dev:** `.github/workflows/lif_advisor_app.yml` builds an image and updates its ECS service.
- Like the backend, merging is the deploy to dev, and demo is promoted by hand (backend [chapter 9](../backend/09-environments-and-deploys.md)).

## Where to go next

- [`frontends/mdr-frontend/README.md`](../../../frontends/mdr-frontend/README.md) (accurate) and [`frontends/lif_advisor_app/README.md`](../../../frontends/lif_advisor_app/README.md) (Docker section
  out of date; [chapter 4](04-advisor-app.md) has the right command).
- [`docs/operations/guides/mdr-guide.md`](../../operations/guides/mdr-guide.md), a user's guide to the MDR UI.

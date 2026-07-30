# End to End testing

[Playwright](https://playwright.dev/) was chosen to facilitate testing the UI end to end with the backend services.

First install the dependencies with

```shell
npm install
```

Next run the playwright install which will download the chromium browser used by playwright to run tests

```shell
npx playwright install
```

To run the tests locally you need to define the following ENVs

### Advisor tests

```shell
export E2E_USERNAME="atsatrian_lifdemo@stateu.edu"
export E2E_PASSWORD="liffy4life!"
export BASE_URL="localhost:5174/"
```

### MDR tests

```shell
export MDR_USERNAME="your-demo-user@stateu.edu"
export MDR_PASSWORD="your-password"
export BASE_URL="http://localhost:5173/"
```

After starting up the UI and backend, execute the tests with

```shell
npm run test                                    # run all tests
npx playwright test --grep @mdr                 # run only MDR tests
npx playwright test --grep @cognito             # run only Cognito-specific tests
npx playwright test --grep "@mdr and @legacy"   # run only MDR legacy login tests
npx playwright test --grep @happy-path          # run only the happy-path monitors
```

## Synthetic monitoring (periodic, against a live env)

The `@happy-path` tests are **outage monitors** — walk a real user flow end to end so a
break is caught before someone reports it:

- **Advisor** (`@chat`): login → chat → the assistant replies (exercises advisor → MCP →
  GraphQL → Query Planner).
- **MDR** (`@mdr @cognito @happy-path`): Cognito login → Export Playground → run an export →
  a result renders (exercises MDR + LDE + the composite Cognito auth in one flow).

They run periodically via **`.github/workflows/synthetic-e2e.yml`** (every 4h + on demand)
against **demo**, using dedicated e2e accounts whose passwords are read from SSM at run time
(`/demo/advisor-api/DemoUserPassword`, `/demo/e2e/mdr-playwright-pw`) — never committed.
MDR login here is **Cognito Hosted UI** (`MDR_USERNAME`/`MDR_PASSWORD` are the Cognito creds),
not the legacy password form. The e2e Cognito user is `lif-e2e-test@unicon.net` (member of
`lif-team`; provisioned on both the dev and demo pools).

> The MDR Export-Playground monitor requires the LDE playground go-live to be deployed in the
> target env (done on dev; on demo it passes once #1076 is promoted there).

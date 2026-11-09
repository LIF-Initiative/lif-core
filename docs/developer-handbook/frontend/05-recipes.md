# 5. Recipes

Step-by-step versions of the frontend changes people make most, each following a pattern already in the code.

*Checked against main `2967cb9`, November 2026.* The lint check below was measured in a scratch copy of the repo.

---

All MDR UI paths are under `frontends/mdr-frontend/src/`. Every recipe ends with the checks in
[chapter 6](06-checks-ci-and-shipping.md).

## Call an MDR endpoint from a screen

The pattern to copy is `getLiveVersionForPair` in `services/transformationsService.ts`, its test in
`services/transformationsService.test.ts`, and its use in `MappingsView.tsx` ([chapter 3](03-follow-a-click.md), step 7).

1. **Find the endpoint** in `http://localhost:8012/docs`, or in `bases/lif/mdr_restapi/`. Note the method,
   the path, and what it returns, including its error codes.
2. **Add a function to the resource's service** in `src/services/` (`modelService.ts` for data models,
   `transformationsService.ts` for mappings, and so on). One function per endpoint. Use the shared `api`
   instance so the token, the workspace cookie and the timeout come with it. Type what it returns.
3. **Decide what errors mean** to the screen. If a status code means something ("no live version" for a
   `404`), turn it into a value the page can show, as `getLiveVersionForPair` does. Otherwise let it throw
   and let the page show it.
4. **Test the function** with the `api` module mocked, so no server is needed:

   ```ts
   import { describe, it, expect, vi, beforeEach } from "vitest";
   vi.mock("./api", () => ({ default: { get: vi.fn(), post: vi.fn() } }));
   import api from "./api";
   import { yourFunction } from "./yourService";

   describe("yourFunction", () => {
       beforeEach(() => {
           vi.mocked(api.get).mockReset();   // braces matter: see "Traps" in chapter 6
       });

       it("calls the right path and returns the data", async () => {
           vi.mocked(api.get).mockResolvedValue({ data: { Id: 1 } });
           expect(await yourFunction(1)).toEqual({ Id: 1 });
           expect(vi.mocked(api.get).mock.calls[0][0]).toContain("/the/path/1");
       });
   });
   ```

   Test what's worth testing: the path you build, and how each status code is turned into a result. A
   function that only passes `result.data` through doesn't need a test.
5. **Call it from the page or component** that owns the state, inside `try`/`catch`. Show failures with
   the toast (`useToast` from `context/ToastContext`), as `onActivateVersion` does. Keep dialogs free of API
   calls: they take callbacks.
6. **Try it against the real API** (below).

## Test a helper

Pure functions go in `src/utils/`, with a `<name>.test.ts` next to them. The pattern is
`utils/jsonataUtils.test.ts`: `describe`, `it`, and `it.each` for a table of cases.

The tests run in Node, not a browser (`environment: "node"` in `vite.config.ts`), and only files named
`src/**/*.test.ts` are picked up. A `.test.tsx` file won't run, and there's no DOM. So you can test helpers
and services, but not render components; adding component tests would mean adding a DOM test environment to
the config first, which is a change worth discussing with a maintainer before you make it.

The Advisor app's tests follow the same style (`src/utils/*.test.ts`).

## Add a page

1. **Create the page** in `src/pages/` (PascalCase file name, a default-exported component).
2. **Add a route** in `pages/Routes.tsx`. Put it among the `children` of the `/` entry so it gets the header,
   footer and login check, and give it a `handle: { name: "…" }` for the breadcrumbs:

   ```tsx
   { path: "your-page", element: <YourPage />, handle: { name: "Your Page" } },
   ```

3. **Link to it** from the header, `components/Header/Header.tsx`, next to the `to="/api-keys"` and
   `to="/export-playground"` links.

## Add a build-time setting

A new `VITE_*` value has to be added everywhere the app is built. For the MDR UI, that's five places:

| Where | What to add |
|---|---|
| The code | Read it as `import.meta.env.VITE_YOUR_SETTING`, and behave sensibly when it's empty, as Cognito and Google Analytics do |
| `frontends/mdr-frontend/Dockerfile` | An `ARG` and `ENV`, and an `echo "VITE_YOUR_SETTING=…" >> .env` line before `npm run build` |
| `deployments/advisor-demo-docker/docker-compose.yml` | A build arg on `lif-mdr-app` with a local default |
| `.github/workflows/lif_mdr_frontend.yml` | An `echo … >> .env` line in the build step (the dev deploy writes its own `.env`) |
| `scripts/release-demo-frontend.sh` | The same, for demo promotion |

The last two are deploy paths: changing them changes the team's dev and demo hosting directly, so ask a
maintainer before editing them (backend [chapter 6](../backend/06-how-we-work.md)), and ask one to set any
new values there. For the Advisor app it's the `Dockerfile`, the compose service `lif-advisor-app`,
`.github/workflows/lif_advisor_app.yml`, and `frontends/lif_advisor_app/build-push.sh`, which builds the
demo image and passes each build arg by name (`--build-arg`), so a new variable needs a line there too.

## See your change in a browser

1. Start the MDR API, run the dev server on port 5173 with `VITE_API_URL=http://localhost:8012`, and log in
   ([chapter 1](01-dev-environment.md)). The dev server reloads as you save.
2. Open the browser's developer tools. The **Network** tab shows every API call: the URL, the status, the
   request body and the response. The **Console** shows errors, including CORS failures.
3. If you change data, you're changing your local MDR. To start again from the seed, see backend
   [chapter 1](../backend/01-dev-environment.md), "Data doesn't reset the way you'd expect".

To drive the UI from a script instead, use Playwright:
[`docs/operations/guides/mdr-ui-e2e-playwright.md`](../../operations/guides/mdr-ui-e2e-playwright.md).

## Check you didn't add lint warnings

The MDR UI has 696 existing lint warnings (November 2026), and warnings don't fail the lint, so CI won't
tell you if you added some. Compare the total with `main`'s:

```bash
cd frontends/mdr-frontend
npx eslint . | grep '^✖'   # ✖ 696 problems (0 errors, 696 warnings) on main
```

If your branch's number is higher, run `npx eslint` on the files you changed and look at the lines you
changed. Linting only your files isn't enough on its own: it also reports every old warning in those files.
(Measured: adding three warnings in two files took the total from 696 to 699, while linting those two files
listed 28.)

The Advisor app's lint is clean, so any warning there is yours.

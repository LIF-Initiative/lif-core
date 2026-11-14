# 2. The MDR UI

How the MDR UI is laid out, how a screen reaches the MDR API, how login and workspaces work, and the features to understand before you change them.

*Checked against main `2967cb9`, November 2026.*

---

## Layout

```
src/
  main.tsx                     entry point: wraps the app in the theme, toast, auth and MDR context providers
  pages/Routes.tsx             every URL and the page it shows
  pages/                       one file per top-level page: Login, Workspaces, ApiKeys, ExportPlayground…
    Explore/                   the main editor: LIF Model, Data Models, Data Extensions, Mappings, Search tabs
      Mappings/                the mapping editor, with its own components/ and hooks/
  components/                  shared UI, one folder per component (<Name>/<Name>.tsx + .css)
  services/                    API clients, one per resource (modelService, entityService, transformationsService…)
  context/                     AuthContext, MdrContext (breadcrumbs/route info), ToastContext
  utils/                       pure helpers, with their unit tests next to them
  config/                      build-time config (Cognito)
```

Conventions (from the app's README): components and pages PascalCase, services/hooks/utils camelCase; a
component used by one feature lives with that feature; `@/` imports from `src/`; double quotes, no file
extensions in imports.

### Pages and URLs

`pages/Routes.tsx` lists every URL in one object passed to React Router's `createBrowserRouter`. Each entry
names a `path`, the page component (`element`), and a `handle.name` that the breadcrumbs show. Pages under
`/` are nested, so they render inside the shared header and footer. To find the page behind a URL, search
`Routes.tsx` for the path.

Every page except `/login` and `/auth/callback` is wrapped in **`AuthGuard`**
(`components/AuthGuard/AuthGuard.tsx`). It checks for a stored login and sends you to `/login` if there
isn't one.

## How a screen talks to the MDR

```
page or component  →  a function in src/services/  →  the shared axios instance (services/api.ts)  →  MDR API
```

- **Services** wrap the MDR's endpoints, one file per resource and one function per call. Pages and
  components never build URLs themselves; they call a service function.
- **One axios instance for the MDR**, `src/services/api.ts`, carries the settings every MDR call needs:
  - its base URL from `VITE_API_URL`;
  - a **30-second timeout**, so a lost response fails instead of hanging. A hung request used to leave
    half-created records behind (#1028);
  - **`withCredentials: true`**, which tells the browser to send and keep cookies on calls to the MDR's
    origin. The workspace selection is a cookie (below), so without it the MDR wouldn't know your workspace.
- **Finding the endpoint behind a screen:** start at the page, follow its service import, and check the
  MDR's own API docs at `http://localhost:8012/docs`. Or work backwards: copy the path you see in the
  browser's Network tab and search `src/services/` for it. [Chapter 3](03-follow-a-click.md) walks one
  button all the way through.

Some services also build full URLs with `import.meta.env.VITE_API_URL` themselves
(`transformationsService.ts`, for example). Both routes use the same value and go through the same axios
instance, so the timeout, cookies and login handling apply either way.

The Export Playground is the exception: it calls the Learner Data Export API, a different host, through
its own instance, `services/ldeApi.ts` (used by `exportService.ts`). That one adds the stored token to each
request but has no timeout and no `401` refresh, so an expired token there shows as an error on the page.

## Login and tokens

`authService` (`src/services/authService.ts`) owns login. What happens, in order:

1. **You log in.** With username/password, the UI posts to the MDR's `/login`. With Cognito, it sends you
   to Cognito's sign-in page and finishes on `/auth/callback`.
2. **The tokens are stored** in `localStorage`: `access_token` and `refresh_token`, plus `id_token` with
   Cognito, and the user as `auth_user`.
3. **Every request carries a token** as `Authorization: Bearer …`, set as a default header on the axios
   instance. Which token: the **access token** for username/password, the **ID token** for Cognito.
4. **When a call comes back `401`** (the token expired), the response interceptor in `services/api.ts`
   steps in:
   - it asks `authService.refreshToken()` for a new token (the MDR's `/refresh-token`, or Cognito's token
     endpoint);
   - if that works, it repeats the original request with the new token, once. Your code just sees the
     successful answer;
   - if it doesn't, it clears the stored tokens and sends you to `/login`, or restarts Cognito sign-in.
5. **On reload**, `AuthGuard` calls `authService.initializeAuth()`. If the stored token hasn't expired,
   it goes back on the axios instance and you carry on. If it has expired, all stored tokens are cleared
   and you log in again: a reload doesn't try the refresh token, only a `401` during use does.

Any script running on the page can read `localStorage`, so the tokens live wherever the page's JavaScript
can reach them. Keep that in mind before adding third-party scripts.

## Workspaces (tenants)

A workspace is a separate copy of the MDR's data per team (backend [chapter 3](../backend/03-data-model-and-mdr.md), "Tenants").
Choosing one works like this:

1. The Workspaces page lists yours (`GET /tenants/mine`). If you have exactly one and arrived there
   automatically, it selects that one for you and moves on.
2. Choosing one calls `POST /tenants/select`. The MDR answers with a **`lif_workspace` cookie** that
   names the workspace, and the browser sends it on every later call. That cookie is how the MDR knows
   which workspace you're in.
3. The cookie is **HttpOnly**: the UI's own code can't read it. So `services/tenantsService.ts` keeps its
   own copy of the selection in `localStorage` (`lif:currentWorkspace`) for the header to show.

The two can disagree. The cookie is the truth; the UI's copy is a reminder. In a fresh browser, or after
clearing site data, the header can show no workspace while the MDR still has one selected. Selecting a
workspace again brings them back in line. The proper fix, a `GET /tenants/current` the UI can ask, is #936.

## Features worth knowing before you change them

- **Mappings** (`pages/Explore/Mappings/`): a source model column, a target column, and wires between
  them: SVG paths that `hooks/useMappingWires.ts` computes and `components/Wires.tsx` draws (`@xyflow/react`
  isn't involved). Dialogs handle creating, forking, **activating** and editing
  transformation groups. Activation matters: only an activated group is used by the Translator. The whole
  activate flow is [chapter 3](03-follow-a-click.md).
- **Expression editor**: evaluates JSONata in the browser with the JavaScript `jsonata` package
  (`utils/jsonataUtils.ts`), so you can try an expression against sample data. The Translator runs the same
  language with `jsonata-python`, a separate implementation, so an edge case can behave differently there.
- **Bulk transformations preview**: combines a group's expressions into one output and checks it against the
  target model's JSON Schema in the browser (`utils/schemaValidation.ts`), the same check the Translator makes.
- **Portable files**: export and import models and mapping groups (`components/PortableFile`,
  `services/portableService.ts`; format spec in [`docs/specs/mdr-portable-file-format.md`](../../specs/mdr-portable-file-format.md)).
- **Export Playground**: calls the Learner Data Export API (`services/ldeApi.ts`) to show a learner's
  record in another standard. Locally it has no formats to offer until a mapping *from* StateU LIF is
  activated (backend [chapter 10](../backend/10-extending-lif.md)).
- **Overlay screens**: Data Extensions, and a model's "only / all / public / extensions / partner" views.
  An overlay is a model built on top of another one, and these screens show which parts are its own. ADR
  data_model/0004 retires overlays in favour of self-contained models: on dev, models 17 and 18 have been
  converted (#1388), and on demo and in the local seed they're still overlays of model 1 until #1513 (backend
  [chapter 3](../backend/03-data-model-and-mdr.md), "Overlays are on their way out"). Expect these screens
  to change.

## Where to go next

[Chapter 3](03-follow-a-click.md) traces one button through all of this. The app's own
[`frontends/mdr-frontend/README.md`](../../../frontends/mdr-frontend/README.md) is accurate and has more on conventions.

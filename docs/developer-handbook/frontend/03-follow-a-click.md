# 3. Follow a click: activating a mapping version

One button in the MDR UI traced from the screen, through the service layer and the MDR API, to the database and back to the screen.

*Checked against main `2967cb9`, November 2026.* Traced in the code; file and function names are given rather than line numbers, which drift.

---

## Why this button

**Activate** makes one version of a mapping (a transformation group) the live one for its source and target
models. It's a good example because it touches every layer: a confirmation dialog, a service call, an
endpoint with real rules behind it, and a result that changes what the rest of LIF does. Once activated,
the Translator uses the new version on its next request (backend [chapter 4](../backend/04-follow-the-data.md), step 7a).

Every other button in the UI follows the same path; only the names change.

## The path

```
MappingsView.tsx        "✓ Activate" button  →  opens ActivateGroupDialog
ActivateGroupDialog.tsx  user confirms        →  onActivate
MappingsView.tsx        onActivateVersion     →  activateTransformationGroup(group.Id)
transformationsService   POST /transformation_groups/{id}/activate   (via the axios instance)
MDR API                  activate_transformation_group  (bases/lif/mdr_restapi/transformation_endpoint.py)
mdr_services             activate_transformation_group  (components/lif/mdr_services/transformation_service.py)
PostgreSQL               ActivationDate set if the group wasn't live; the pair's other live versions deprecated
   … and back: response → local state updated → live version re-read → toast
```

## Step by step

All UI paths are under `frontends/mdr-frontend/src/`.

### 1. The button: `pages/Explore/Mappings/MappingsView.tsx`

`MappingsView` is the mapping editor, a large component (over 3,000 lines) holding the page's state. Find
the button by its tooltip, `title="Make this version the live one"`. It's only shown when the version you're
looking at isn't already the live one, and when the live version is known. Clicking it doesn't call the API
yet; it opens a dialog:

```tsx
onClick={() => setActivateDialogOpen(true)}
```

### 2. The dialog: `pages/Explore/Mappings/components/ActivateGroupDialog.tsx`

A small presentational component (a Radix `Dialog`) with no API calls of its own. `MappingsView` tells it
what is live now, as `currentLive`: `'other'` (another version will be deprecated), `'none'` (nothing is
live yet) or `'tie'` (two live versions compare equal, so the Translator can't pick one). The dialog words
its warning to match. Confirming calls the `onActivate` callback that `MappingsView` passed in.

This split is the pattern throughout the UI: **dialogs and components display and collect; the page owns
state and makes the calls.**

### 3. The handler: `onActivateVersion` in `MappingsView.tsx`

```tsx
const activated = await activateTransformationGroup(group.Id);
setGroup(... ActivationDate, DeprecationDate from `activated` ...);
await refreshActiveGroup();
showToast(`v${activated.GroupVersion} is now the live version`, 'success');
```

On failure, the `catch` shows the API's error message in an error toast. The MDR returns readable reasons,
for example when a `GroupVersion` isn't dotted numbers, so passing them through is deliberate.

### 4. The service: `services/transformationsService.ts`

```ts
export const activateTransformationGroup = async (id: number) => {
    const url = `${apiBaseUrl}/transformation_groups/${id}/activate`;
    const result = await api.post(url);
    return result.data as TransformationGroupDetails;
};
```

One function per endpoint, nothing else. Because it uses the shared `api` instance, the request gets the
login token, the workspace cookie and the 30-second timeout, and a `401` is refreshed and retried
([chapter 2](02-mdr-ui.md)) without this code knowing.

In the browser's Network tab this is a `POST` to `http://localhost:8012/transformation_groups/<id>/activate`.

### 5. The endpoint: `bases/lif/mdr_restapi/transformation_endpoint.py`

```python
@router.post("/{transformation_group_id}/activate", response_model=TransformationGroupDTO)
async def activate_transformation_group(transformation_group_id, activation_date=Query(None, ...), session=...):
    return await transformation_service.activate_transformation_group(session, transformation_group_id, activation_date)
```

The router is mounted at `/transformation_groups` in `bases/lif/mdr_restapi/core.py`. The endpoint is glue:
the rules are in the service, as backend [chapter 2](../backend/02-codebase-map.md) describes for every base.
The optional `activation_date` (schedule a future activation) isn't used by the UI.

### 6. The rules: `components/lif/mdr_services/transformation_service.py`

`activate_transformation_group` decides what activating means:

- a missing or deleted group is a `404`, and a `GroupVersion` that isn't dotted numbers (`1`, `1.2`) is a
  `422`;
- it locks the pair's rows first, so two people activating different versions at once can't both win
  (#1414);
- if the group isn't live yet, it sets its `ActivationDate` to now and clears its `DeprecationDate`. A group
  that's already live keeps its `ActivationDate`, and if it's the pair's only live version, nothing changes;
- it sets a `DeprecationDate` on the pair's other live versions, at exactly the same moment, so there's no
  gap with nothing live.

Rolling back is activating the older version again.

### 7. Back in the UI

The response is the updated group. `onActivateVersion` copies its new dates into the page's state, then
`refreshActiveGroup` asks the MDR which version is live now:

```ts
// services/transformationsService.ts, getLiveVersionForPair
GET /transformation_groups/active_transformations_for_data_models/?source_data_model_id=…&target_data_model_id=…
```

That's **the same endpoint the Translator calls** to load its mappings (`components/lif/mdr_client/core.py`),
so the UI shows the live version as the Translator will see it. The service turns the answers into states the
page can show: `200` is live, `404` means no live version, `409` means a tie, and anything else means
unknown. The Activate button hides itself, and the toast confirms.

## Tests along the path

- `services/transformationsService.test.ts` tests `getLiveVersionForPair`'s mapping of `200`, `404`,
  `409` and other errors. It's the pattern for testing a service ([chapter 5](05-recipes.md)).
- The backend rules are tested through the API in `test/bases/lif/mdr_restapi/test_active_transformations.py`
  (activate, roll back, scheduled activation, bad dates, deleted groups). These are database-backed tests;
  backend [chapter 1](../backend/01-dev-environment.md) says how to run them.
- Nothing tests the button or the dialog themselves: the MDR UI has no component tests
  ([chapter 6](06-checks-ci-and-shipping.md)). To check those, run the UI against the API and click.

## Doing it for another button

1. Find the screen's component: search `pages/Routes.tsx` for the URL, or the source for the button's text.
2. Follow the click handler to a service function in `src/services/`.
3. Note the HTTP method and path, and find the endpoint in `bases/lif/mdr_restapi/` (or in
   `http://localhost:8012/docs`).
4. Follow the endpoint into `components/lif/mdr_services/` for the rules.

Or start from the other end: click the button with the Network tab open, copy the path, and search
`src/services/` for it.

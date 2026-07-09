# Driving the MDR UI end-to-end with Playwright

How to script the MDR frontend (Cognito sign-in + SPA navigation) for reproducing or
confirming UI flows — e.g. verifying the create-attribute path, or repro'ing a UI bug.
Grounded in a real run against **dev**; the gotchas below are the ones that actually bit.

> **Prefer the API when you don't need the UI.** If you only need to confirm backend
> behaviour, hit the REST endpoints directly with a service key (`X-API-Key` from
> `/{env}/mdr-api/MdrAuthServiceApiKey*`) — far faster than driving Cognito. Reach for
> Playwright only when the *frontend* behaviour is the thing under test.

## Setup (scratchpad — don't pollute the repo)

Playwright isn't a repo dependency. Install it in a throwaway dir:

```bash
mkdir -p /tmp/mdr-e2e && cd /tmp/mdr-e2e
npm init -y >/dev/null
npm install playwright
npx playwright install chromium
```

Run scripts headless with `chromium.launch({ headless: true })` and screenshot each step
(`fullPage: true`) — headless + screenshots is the fastest debug loop.

## Environments & auth

- **Dev UI:** `https://mdr.dev.lif.unicon.net` (API `https://mdr-api.dev.lif.unicon.net`;
  health is `/health-check`, **not** `/health`).
- Login is **Cognito hosted UI (Authorization Code + PKCE)**. The SPA landing (`/login`) shows a
  **"Sign In / Register"** button that redirects to the hosted UI
  (`dev-mdr-selfserve.auth.us-east-1.amazoncognito.com/login?...`); after sign-in it redirects back
  to `/auth/callback` and the SPA exchanges the code.
- **Accounts:** the dev self-serve Cognito pool is **real team `@unicon.net` accounts** — there is
  **no dedicated dev test user** (`atsatrian_lifdemo@stateu.edu` is **demo**-only), and
  `/dev/mdr-api/DemoUserPassword` is legacy (pre-self-serve) and does **not** map to a Cognito user.
  So a dev UI login needs a real member's **MDR** password (the self-serve password, separate from
  corporate SSO). Source any secret from SSM at runtime into an env var — never hardcode or print it.

## The gotcha that matters: the hosted UI has duplicate responsive inputs

The classic Cognito hosted UI renders the username, password **and** submit control **twice**
(a desktop set and a mobile set); one is `display:none` for the current viewport, and the **first in
DOM order is frequently the hidden one**. Consequences:

- `page.waitForSelector('input[type=password]', { state: 'visible' })` **hangs** — it locks onto the
  first match, which is hidden. Wait for `state: 'attached'` instead.
- `locator(sel).first().fill(...)` / `.click()` silently no-op on the hidden element.

**Fix:** wait for *attached*, then iterate matches and act on the first **visible** one:

```js
async function fillVisible(page, selector, value) {
  const loc = page.locator(selector);
  for (let i = 0; i < await loc.count(); i++) {
    const el = loc.nth(i);
    if (await el.isVisible().catch(() => false)) { await el.fill(value); return true; }
  }
  return false;
}
// clickVisible is identical but calls el.click()

await page.getByRole('button', { name: /sign ?in|register/i }).first().click();      // start redirect
await page.waitForSelector('input[name="password"]', { state: 'attached', timeout: 25000 });
await page.waitForTimeout(1200);
await fillVisible(page, 'input[name="username"], input[type="email"], input[id*="signInFormUsername"]', USER);
await fillVisible(page, 'input[type="password"], input[name="password"]', PW);
await clickVisible(page, 'input[name="signInSubmitButton"], button[type="submit"], input[type="submit"]');
await page.waitForURL(/mdr\.dev\.lif\.unicon\.net/, { timeout: 30000 });
```

A `"Incorrect username or password."` banner on the hosted UI (visible in a screenshot) means the
credential is wrong — distinct from a submit that never fired (form still pristine).

## Persist the login

Save the authenticated context once and reuse it so subsequent steps skip Cognito:

```js
await ctx.storageState({ path: 'auth.json' });                       // after a successful login
const ctx2 = await browser.newContext({ storageState: 'auth.json' }); // later runs
```

## Watch-outs

- **MFA / force-password-change** on an account will stall headless automation — screenshot and
  report where it stopped rather than fighting it.
- Run against **dev**; treat **demo** as a stable showcase.

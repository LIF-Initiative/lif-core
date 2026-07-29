import { Page } from "@playwright/test";

/**
 * The Cognito Hosted UI renders username/password/submit TWICE (desktop + mobile
 * responsive sets); one is `display:none` and the first in DOM order is often the
 * hidden one. So `.first().fill()` can silently no-op and waiting for `visible`
 * can lock onto the hidden node. Act on the first *visible* match instead.
 * (See docs/operations/guides/mdr-ui-e2e-playwright.md.)
 */
export async function fillVisible(page: Page, selector: string, value: string): Promise<void> {
  const loc = page.locator(selector);
  const count = await loc.count();
  for (let i = 0; i < count; i++) {
    const el = loc.nth(i);
    if (await el.isVisible().catch(() => false)) {
      await el.fill(value);
      return;
    }
  }
  throw new Error(`fillVisible: no visible element matched "${selector}"`);
}

export async function clickVisible(page: Page, selector: string): Promise<void> {
  const loc = page.locator(selector);
  const count = await loc.count();
  for (let i = 0; i < count; i++) {
    const el = loc.nth(i);
    if (await el.isVisible().catch(() => false)) {
      await el.click();
      return;
    }
  }
  throw new Error(`clickVisible: no visible element matched "${selector}"`);
}

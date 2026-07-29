import { Locator, Page } from "@playwright/test";
import { fillVisible, clickVisible } from "./cognito-helpers";

export class MdrLoginPage {
  readonly page: Page;
  readonly heading: Locator;
  readonly subtitle: Locator;
  readonly signInButton: Locator;
  // Legacy form elements (only present when Cognito is not configured)
  readonly usernameField: Locator;
  readonly passwordField: Locator;
  readonly legacySubmitButton: Locator;

  constructor(page: Page) {
    this.page = page;
    this.heading = page.getByRole('heading', { name: 'LIF Metadata Repository' });
    this.subtitle = page.getByText('Sign in');
    this.signInButton = page.getByRole('button', { name: /Sign In/ });
    this.usernameField = page.getByPlaceholder('Enter your username');
    this.passwordField = page.getByPlaceholder('Enter your password');
    this.legacySubmitButton = page.getByRole('button', { name: 'Sign In', exact: true });
  }

  async goto() {
    await this.page.goto('/login');
  }

  async loginWithPassword(username: string, password: string) {
    await this.usernameField.fill(username);
    await this.passwordField.fill(password);
    await this.legacySubmitButton.click();
  }

  /**
   * Cognito Hosted UI login (Authorization Code + PKCE) — the deployed dev/demo flow.
   * Clicking Sign In redirects to the hosted UI; fill the visible (not the hidden
   * responsive-duplicate) inputs, submit, and wait for the SPA callback to land back.
   */
  async loginWithCognito(username: string, password: string) {
    const appHost = new URL(this.page.url()).host;
    await this.signInButton.first().click();
    await this.page.waitForSelector('input[name="password"], input[type="password"]', {
      state: 'attached',
      timeout: 30_000,
    });
    await this.page.waitForTimeout(1200);
    await fillVisible(this.page, 'input[name="username"], input[type="email"], input[id*="signInFormUsername"]', username);
    await fillVisible(this.page, 'input[type="password"], input[name="password"]', password);
    await clickVisible(this.page, 'input[name="signInSubmitButton"], button[type="submit"], input[type="submit"]');
    await this.page.waitForURL((url) => url.host === appHost, { timeout: 45_000 });
    await this.page.waitForTimeout(2500);
  }
}

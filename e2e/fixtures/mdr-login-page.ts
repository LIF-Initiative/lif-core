import { Locator, Page } from "@playwright/test";

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
}

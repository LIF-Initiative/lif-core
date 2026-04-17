import { test, expect } from '@playwright/test';
import { MdrLoginPage } from '../fixtures/mdr-login-page';
import { MdrExplorePage } from '../fixtures/mdr-explore-page';

/**
 * MDR login tests.
 *
 * Requires environment variables:
 *   BASE_URL      — MDR frontend URL (e.g., http://localhost:5173)
 *   MDR_USERNAME  — demo user email
 *   MDR_PASSWORD  — demo user password
 *
 * These tests exercise the legacy password login flow.
 * Cognito Hosted UI tests require a deployed Cognito User Pool
 * and are tagged @cognito for selective execution.
 */

test.describe('MDR Login', { tag: ['@ui', '@mdr', '@login'] }, () => {
  test('login page displays', async ({ page }) => {
    const loginPage = new MdrLoginPage(page);
    await loginPage.goto();

    await expect(loginPage.heading).toBeVisible();
    await expect(loginPage.subtitle).toBeVisible();
    await expect(loginPage.signInButton).toBeVisible();
    await expect(loginPage.signInButton).toBeEnabled();
  });

  test('unauthenticated access redirects to login', async ({ page }) => {
    await page.goto('/');
    await page.waitForURL('**/login');
    const loginPage = new MdrLoginPage(page);
    await expect(loginPage.heading).toBeVisible();
  });
});

test.describe('MDR Legacy Login', { tag: ['@ui', '@mdr', '@login', '@legacy'] }, () => {
  test('can login with valid credentials', async ({ page }) => {
    const username = process.env.MDR_USERNAME;
    const password = process.env.MDR_PASSWORD;

    if (!username || !password) {
      test.skip(true, 'MDR_USERNAME and MDR_PASSWORD must be set');
      return;
    }

    const loginPage = new MdrLoginPage(page);
    await loginPage.goto();
    await loginPage.loginWithPassword(username, password);

    // Should redirect to the app after login
    const explorePage = new MdrExplorePage(page);
    await expect(explorePage.exploreNav).toBeVisible();
  });

  test('invalid credentials show error', async ({ page }) => {
    const loginPage = new MdrLoginPage(page);
    await loginPage.goto();

    // Only run if legacy form is visible (not Cognito mode)
    if (await loginPage.usernameField.isVisible()) {
      await loginPage.loginWithPassword('invalid@example.com', 'wrong-password');
      await expect(page.getByText('Invalid username or password')).toBeVisible();
    }
  });

  test('login then logout', async ({ page }) => {
    const username = process.env.MDR_USERNAME;
    const password = process.env.MDR_PASSWORD;

    if (!username || !password) {
      test.skip(true, 'MDR_USERNAME and MDR_PASSWORD must be set');
      return;
    }

    const loginPage = new MdrLoginPage(page);
    await loginPage.goto();
    await loginPage.loginWithPassword(username, password);

    // Wait for app to load
    const explorePage = new MdrExplorePage(page);
    await expect(explorePage.exploreNav).toBeVisible();

    // Sign out via user menu
    await explorePage.signOut();

    // Should return to login page
    await page.waitForURL('**/login');
    await expect(loginPage.heading).toBeVisible();
  });
});

test.describe('MDR Cognito Login', { tag: ['@ui', '@mdr', '@login', '@cognito'] }, () => {
  test('Sign In / Register button redirects to Cognito Hosted UI', async ({ page }) => {
    const loginPage = new MdrLoginPage(page);
    await loginPage.goto();

    // Look for the Cognito-mode button
    const cognitoButton = page.getByRole('button', { name: 'Sign In / Register' });
    if (!await cognitoButton.isVisible()) {
      test.skip(true, 'Cognito is not enabled for this environment');
      return;
    }

    // Click should redirect to Cognito domain
    const [response] = await Promise.all([
      page.waitForURL(/amazoncognito\.com/),
      cognitoButton.click(),
    ]);

    expect(page.url()).toContain('amazoncognito.com');
  });
});

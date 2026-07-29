import { test, expect } from '@playwright/test';
import { MdrLoginPage } from '../fixtures/mdr-login-page';
import { MdrExportPlaygroundPage } from '../fixtures/mdr-export-playground-page';

const SIXTY_SECONDS = 60 * 1000;

/**
 * MDR happy-path monitor: Cognito login → Export Playground → run an export → result.
 * Exercises MDR (personas), LDE (formats + export), and the composite Cognito auth in
 * one flow — the highest-signal single check that the deployed stack is actually working.
 *
 * Requires (Cognito hosted-UI login):
 *   BASE_URL      — MDR frontend (e.g. https://mdr.demo.lif.unicon.net)
 *   MDR_USERNAME  — Cognito user email
 *   MDR_PASSWORD  — Cognito user password
 */
test.describe('MDR Export Playground (happy path)', { tag: ['@ui', '@mdr', '@cognito', '@happy-path'] }, () => {
  test('cognito login → run export → result renders', async ({ page }) => {
    const username = process.env.MDR_USERNAME;
    const password = process.env.MDR_PASSWORD;
    test.skip(!username || !password, 'MDR_USERNAME / MDR_PASSWORD must be set');
    test.setTimeout(2 * SIXTY_SECONDS);

    const login = new MdrLoginPage(page);
    await login.goto();
    await login.loginWithCognito(username!, password!);

    const playground = new MdrExportPlaygroundPage(page);
    await playground.goto();
    await expect(playground.heading).toBeVisible({ timeout: 20_000 });

    // Both selects must populate: learner (MDR /demo/personas) + format (LDE
    // /available-data-formats). A disabled format select = LDE auth/reachability broke.
    await expect(playground.comboboxes.nth(0)).toBeEnabled({ timeout: 30_000 });
    await expect(playground.comboboxes.nth(1)).toBeEnabled({ timeout: 30_000 });
    await expect(page.getByText(/could not load|unauthorized|failed to/i)).toHaveCount(0);

    await playground.runFirstExport();

    // The export chain (LDE → MDR → QP → Translator) renders a Result panel.
    await expect(playground.result).toBeVisible({ timeout: SIXTY_SECONDS });
  });
});

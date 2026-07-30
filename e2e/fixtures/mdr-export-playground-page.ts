import { Locator, Page } from "@playwright/test";

/**
 * MDR UI "Export Playground" page — exercises the full LDE path end to end:
 * personas (MDR /demo/personas) + formats (LDE /available-data-formats) + a run
 * (LDE /exports). A good synthetic monitor: it touches MDR, LDE, and the composite
 * Cognito auth in one flow.
 */
export class MdrExportPlaygroundPage {
  readonly page: Page;
  readonly heading: Locator;
  readonly comboboxes: Locator; // [0] = Test learner, [1] = Output format (Radix selects)
  readonly runButton: Locator;
  readonly result: Locator;

  constructor(page: Page) {
    this.page = page;
    this.heading = page.getByRole('heading', { name: /Export Playground/i });
    this.comboboxes = page.locator('[role="combobox"]');
    this.runButton = page.getByRole('button', { name: /run export/i });
    this.result = page.getByText(/Result/i).first();
  }

  async goto() {
    await this.page.goto('/export-playground');
  }

  private async pickFirst(index: number) {
    await this.comboboxes.nth(index).click();
    await this.page.getByRole('option').first().click();
  }

  /** Pick the first learner + first format and run the export. */
  async runFirstExport() {
    await this.pickFirst(0); // learner (from MDR)
    await this.pickFirst(1); // format (from LDE)
    await this.runButton.click();
  }
}

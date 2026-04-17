import { Locator, Page } from "@playwright/test";

export class MdrExplorePage {
  readonly page: Page;
  readonly exploreNav: Locator;
  readonly userMenuButton: Locator;
  readonly signOutButton: Locator;

  constructor(page: Page) {
    this.page = page;
    this.exploreNav = page.getByRole('link', { name: 'Explore' });
    this.userMenuButton = page.locator('button:has([data-radix-collection-item])').first();
    this.signOutButton = page.getByRole('menuitem', { name: 'Sign out' });
  }

  async signOut() {
    await this.userMenuButton.click();
    await this.signOutButton.click();
  }
}

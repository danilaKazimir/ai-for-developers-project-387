import { expect, type Locator, type Page } from '@playwright/test';

export async function copyGuestLink(page: Page, id: string, scope: Locator = page.locator('main')) {
  await page.context().grantPermissions(['clipboard-read', 'clipboard-write'], { origin: new URL(page.url()).origin });
  const currentUrl = page.url();
  const button = scope.getByRole('button', { name: 'Скопировать ссылку', exact: true });
  await button.focus();
  await page.keyboard.press('Enter');
  await expect(scope.getByText('Ссылка скопирована', { exact: true })).toBeVisible();
  const url = await page.evaluate(() => navigator.clipboard.readText());
  expect(url).toBe(new URL(`/event-types/${id}`, currentUrl).href);
  await expect(page).toHaveURL(currentUrl);
  return url;
}

export async function createEvent(page: Page) {
  const response = page.waitForResponse((response) => response.url().endsWith('/api/organizer/event-types') && response.request().method() === 'POST');
  await page.getByRole('button', { name: 'Создать событие', exact: true }).click();
  const created = await response;
  expect(created.status()).toBe(201);
  return (await created.json()).id as string;
}

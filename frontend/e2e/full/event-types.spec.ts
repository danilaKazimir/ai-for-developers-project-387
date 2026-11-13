import { expect, test } from '@playwright/test';
import { copyGuestLink, createEvent } from './guest-links';

test('создание двух типов и публичный каталог', async ({ page }) => {
  const suffix = Date.now().toString();
  await page.goto('/calendars/new');
  for (const [name, duration] of [[`Разбор проекта ${suffix}`, '60'], [`Знакомство ${suffix}`, '45']]) {
    await page.getByLabel('Название', { exact: true }).fill(name);
    await page.getByLabel('Описание', { exact: true }).fill('Обсудим вашу задачу');
    await page.getByLabel('Длительность, минут').fill(duration);
    const id = await createEvent(page);
    await expect(page.getByRole('status')).toContainText('Событие создано');
    await copyGuestLink(page, id);
  }
  await page.reload();
  await page.getByRole('link', { name: 'События', exact: true }).click();
  const intro = page.getByRole('article').filter({ hasText: `Знакомство ${suffix}` });
  const review = page.getByRole('article').filter({ hasText: `Разбор проекта ${suffix}` });
  await expect(intro.getByRole('heading', { name: `Знакомство ${suffix}` })).toBeVisible();
  await expect(intro).toContainText('45 минут');
  await expect(review).toContainText('60 минут');
  await page.reload();
  await expect(intro).toBeVisible();
});

test('ошибка отправки сохраняет введённые поля', async ({ page }) => {
  await page.goto('/calendars/new');
  await page.getByLabel('Название', { exact: true }).fill('Новое название');
  await page.getByLabel('Описание', { exact: true }).fill('Сохранить описание');
  await page.route('**/api/organizer/event-types', (route) => route.fulfill({ status: 503, json: { code: 'DATABASE_UNAVAILABLE', message: 'Unavailable' } }));
  await page.getByRole('button', { name: 'Создать событие', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Сервис временно недоступен');
  await expect(page.getByLabel('Название', { exact: true })).toHaveValue('Новое название');
  await expect(page.getByLabel('Описание', { exact: true })).toHaveValue('Сохранить описание');
  await page.unroute('**/api/organizer/event-types');
  await createEvent(page);
  await expect(page.getByRole('status')).toContainText('Событие создано');
});

test('форма доступна с клавиатуры на мобильной ширине', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 844 });
  await page.goto('/calendars/new');
  await page.getByLabel('Название', { exact: true }).focus();
  await expect(page.getByLabel('Название', { exact: true })).toBeFocused();
  await page.keyboard.type('Keyboard meeting');
  await page.keyboard.press('Tab');
  await page.keyboard.type('Description');
  await page.keyboard.press('Tab');
  await page.keyboard.press('ControlOrMeta+A');
  await page.keyboard.type('45');
  await page.keyboard.press('Tab');
  await expect(page.getByRole('button', { name: 'Создать событие', exact: true })).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('status')).toContainText('Событие создано');
  const widths = await page.evaluate(() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]);
  expect(widths[0]).toBeLessThanOrEqual(widths[1]);
});

test('граница названия применяется после удаления крайних пробелов', async ({ page }) => {
  await page.goto('/calendars/new');
  await page.getByLabel('Название', { exact: true }).fill(`  ${'n'.repeat(120)}  `);
  await page.getByRole('button', { name: 'Создать событие', exact: true }).click();
  await expect(page.getByRole('status')).toContainText(`${'n'.repeat(120)} · 30 минут`);
});

for (const unavailable of [false, true]) {
  test(`ручное копирование ссылки: ${unavailable ? 'API отсутствует' : 'доступ отклонён'}`, async ({ page, request }) => {
    const name = `manual-link-${Date.now()}`;
    const createdType = await request.post('/api/organizer/event-types', { data: { name, description: '', durationMinutes: 30 } });
    expect(createdType.status()).toBe(201);
    const id = (await createdType.json()).id;
    await page.addInitScript((missing) => {
      Object.defineProperty(navigator, 'clipboard', { configurable: true, value: missing ? undefined : { writeText: () => Promise.reject(new Error('Denied')) } });
    }, unavailable);
    await page.setViewportSize({ width: 320, height: 844 });
    await page.goto('/event-types');
    const card = page.getByRole('article').filter({ hasText: name });
    await card.getByRole('button', { name: 'Скопировать ссылку' }).click();
    await expect(card.getByRole('alert')).toHaveText('Не удалось скопировать автоматически. Скопируйте ссылку вручную');
    const input = card.getByLabel('Ссылка для гостя');
    await expect(input).toHaveValue(new URL(`/event-types/${id}`, page.url()).href);
    await input.focus();
    expect(await input.evaluate((element: HTMLInputElement) => element.selectionEnd! - element.selectionStart!)).toBe((await input.inputValue()).length);
    await expect(page).toHaveURL(/\/event-types$/);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.goto('/calendars/new');
    await page.getByLabel('Название', { exact: true }).fill('Новое событие');
    const newId = await createEvent(page);
    await page.getByRole('button', { name: 'Скопировать ссылку' }).click();
    await expect(page.getByLabel('Ссылка для гостя')).toHaveValue(new URL(`/event-types/${newId}`, page.url()).href);
    await expect(page).toHaveURL(/\/calendars\/new$/);
  });
}

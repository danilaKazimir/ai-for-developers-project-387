import { expect, test } from '@playwright/test';
import { copyGuestLink, createEvent } from './guest-links';

test('полный цикл двух типов и общедоступный список с обновлением', async ({ page, request, browser }) => {
  await page.setViewportSize({ width: 320, height: 844 });
  const suffix = Date.now();
  const types: string[] = [];
  await page.goto('/organizer/event-types/new');
  const guestUrls: string[] = [];
  for (const index of [0, 1]) {
    await page.getByLabel('Название', { exact: true }).fill(`Формат ${index + 1} ${suffix}`);
    await page.getByLabel('Длительность, минут').fill(index === 0 ? '60' : '30');
    const id = await createEvent(page);
    types.push(id);
    await expect(page.getByRole('status')).toContainText('Событие создано');
    guestUrls.push(await copyGuestLink(page, id));
  }
  await page.getByRole('link', { name: 'Предстоящие встречи', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Предстоящие встречи', exact: true })).toBeVisible();
  const guestContext = await browser.newContext();
  const guest = await guestContext.newPage();
  for (const [index, id] of types.entries()) {
    const availability = await (await request.get(`/api/event-types/${id}/slots`)).json();
    const day = availability.days.find((entry: { slots: unknown[] }) => entry.slots.length > 0);
    await guest.goto(guestUrls[index]);
    await guest.getByRole('button', { name: day.date, exact: true }).click();
    await guest.getByRole('group', { name: 'Свободное время' }).getByRole('button').first().click();
    await guest.getByLabel('Ваше имя').fill(`Гость ${index + 1}`);
    await guest.getByLabel('Email').fill(`list-${index}-${suffix}@example.com`);
    await guest.getByLabel('Комментарий').fill(`Личный комментарий ${index + 1}`);
    await guest.getByRole('button', { name: 'Подтвердить запись' }).click();
    await expect(guest.getByRole('heading', { name: 'Встреча подтверждена' })).toBeVisible();
    await expect(guest.locator('body')).not.toContainText(`list-${1 - index}-${suffix}@example.com`);
  }
  await page.getByRole('button', { name: 'Обновить встречи' }).focus();
  await page.keyboard.press('Enter');
  for (const [index] of types.entries()) {
    const row = page.getByRole('article').filter({ hasText: `list-${index}-${suffix}@example.com` });
    await expect(row).toContainText(`Формат ${index + 1} ${suffix}`);
    await expect(row).toContainText(`Гость ${index + 1}`);
    await expect(row).toContainText(`Личный комментарий ${index + 1}`);
    await expect(row).toContainText('Europe/Moscow');
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.reload();
  await expect(page.locator('body')).toContainText(`list-0-${suffix}@example.com`);
  await guestContext.close();
});

test('пустой список, ошибка загрузки и неоднозначное локальное время', async ({ page }) => {
  let state: 'empty' | 'error' | 'repeated' = 'empty';
  await page.route('**/api/organizer/bookings', async (route) => {
    if (state === 'error') return route.fulfill({ status: 503, json: { code: 'DATABASE_UNAVAILABLE', message: 'Unavailable' } });
    const base = { eventType: { id: 'repeated', name: 'Повторённый час', description: '', durationMinutes: 30 }, timezone: 'America/New_York', guest: { name: 'Гость', email: 'guest@example.com', comment: '' } };
    await route.fulfill({ json: { items: state === 'empty' ? [] : [
      { ...base, id: '00000000-0000-4000-8000-000000000001', startsAt: '2026-11-01T05:00:00Z', endsAt: '2026-11-01T05:30:00Z' },
      { ...base, id: '00000000-0000-4000-8000-000000000002', startsAt: '2026-11-01T06:00:00Z', endsAt: '2026-11-01T06:30:00Z' },
    ] } });
  });
  await page.goto('/organizer/bookings');
  await expect(page.locator('body')).toContainText('Предстоящих встреч пока нет');
  state = 'error';
  await page.getByRole('button', { name: 'Обновить встречи' }).click();
  await expect(page.getByRole('alert')).toContainText('Не удалось загрузить встречи');
  state = 'repeated';
  await page.getByRole('button', { name: 'Повторить загрузку' }).click();
  const rows = page.getByRole('article');
  await expect(rows.nth(0)).toContainText('GMT-04:00');
  await expect(rows.nth(1)).toContainText('GMT-05:00');
});

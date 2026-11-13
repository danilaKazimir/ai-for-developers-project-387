import { expect, test } from '@playwright/test';
import { copyGuestLink } from './guest-links';
import type { OrganizerBookings } from '../../src/api/generated/models';

test.use({ timezoneId: 'America/Los_Angeles' });

test('имя гостя из 120 символов сохраняется целиком после удаления крайних пробелов', async ({ page, request }) => {
  const eventName = `padded-name-${Date.now()}`;
  const name = `${'И'.repeat(119)}я`;
  const createdType = await request.post('/api/organizer/event-types', {
    data: { name: eventName, description: '', durationMinutes: 30 },
  });
  expect(createdType.status()).toBe(201);
  const id = (await createdType.json()).id;
  const calendar = await (await request.get(`/api/event-types/${id}/slots`)).json();
  const day = calendar.days.find((entry: { slots: unknown[] }) => entry.slots.length > 0);
  await page.goto(`/event-types/${id}`);
  await page.getByRole('button', { name: day.date, exact: true }).click();
  await page.getByRole('group', { name: 'Свободное время' }).getByRole('button').first().click();
  await page.getByLabel('Ваше имя').fill(`  ${name}  `);
  await page.getByLabel('Email').fill('padded-name@example.com');
  await page.getByRole('button', { name: 'Подтвердить запись' }).click();
  await expect(page.getByRole('heading', { name: 'Встреча подтверждена' })).toBeVisible();
  await expect(page.locator('a[href]:not([href="#main-content"])')).toHaveCount(0);

  const response = await request.get('/api/organizer/bookings');
  expect(response.status()).toBe(200);
  const bookings: OrganizerBookings = await response.json();
  const saved = bookings.items.filter((booking) => booking.eventType.id === id);
  expect(saved).toHaveLength(1);
  expect(saved[0].guest.name).toBe(name);
});

for (const conflict of [false, true]) {
  test(conflict ? 'занятый после выбора слот даёт конфликт и сохраняет контакты для повторной записи' : 'гость по скопированной ссылке получает подтверждение встречи', async ({ page, request }) => {
    const eventName = `Встреча booking-${Date.now()}`;
    const createdType = await request.post('/api/organizer/event-types', {
      data: { name: eventName, description: 'Обсудим проект', durationMinutes: 30 },
    });
    expect(createdType.status()).toBe(201);
    const id = (await createdType.json()).id;
    const calendar = await (await request.get(`/api/event-types/${id}/slots`)).json();
    const day = calendar.days.find((entry: { slots: unknown[] }) => entry.slots.length > 0);
    const selected = day.slots[0];
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/event-types');
    const guestUrl = await copyGuestLink(page, id, page.getByRole('article').filter({ hasText: eventName }));
    await page.goto(guestUrl);
    await page.getByRole('button', { name: day.date, exact: true }).click();
    await page.getByRole('group', { name: 'Свободное время' }).getByRole('button').first().click();
    await page.getByLabel('Ваше имя').fill('Анна');
    await page.getByLabel('Email').fill('anna@example.com');
    await page.getByLabel('Комментарий').fill('Обсудить детали');
    if (conflict) {
      expect((await request.post('/api/bookings', { data: {
        eventTypeId: id, startsAt: selected.startsAt,
        guest: { name: 'Другой гость', email: 'other@example.com' },
      } })).status()).toBe(201);
    }
    await page.getByRole('button', { name: 'Подтвердить запись' }).click();
    if (conflict) {
      await expect(page.getByRole('alert')).toContainText('Это время уже заняли. Выберите другое время');
      await expect(page.getByRole('heading', { name: 'Выбрано время' })).toHaveCount(0);
      await expect(page.getByLabel('Ваше имя')).toHaveValue('Анна');
      await expect(page.getByLabel('Email')).toHaveValue('anna@example.com');
      await expect(page.getByLabel('Комментарий')).toHaveValue('Обсудить детали');
      const refreshed = await (await request.get(`/api/event-types/${id}/slots`)).json();
      const next = refreshed.days.find((entry: { slots: unknown[] }) => entry.slots.length > 0);
      await page.getByRole('button', { name: next.date, exact: true }).click();
      await page.getByRole('group', { name: 'Свободное время' }).getByRole('button').first().click();
      await page.getByRole('button', { name: 'Подтвердить запись' }).click();
    }
    await expect(page.getByRole('heading', { name: 'Встреча подтверждена' })).toBeVisible();
    await expect(page.locator('a[href]:not([href="#main-content"])')).toHaveCount(0);
    await expect(page.getByRole('status')).toContainText(eventName);
    await expect(page.getByRole('status')).toContainText('Europe/Moscow');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  });
}

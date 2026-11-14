import { expect, test, type APIRequestContext, type Page } from '@playwright/test';
import { copyGuestLink } from './guest-links';
import type { OrganizerBookings } from '../../src/api/generated/models';

test.use({ timezoneId: 'America/Los_Angeles' });

type Calendar = { timezone: string; days: { date: string; slots: { startsAt: string; endsAt: string }[] }[] };
type Meeting = { eventName: string; date: string; startsAt: string; endsAt: string };

function formatTime(instant: string, timezone: string) {
  return new Intl.DateTimeFormat('ru-RU', {
    timeZone: timezone, hour: '2-digit', minute: '2-digit', timeZoneName: 'longOffset',
  }).format(new Date(instant));
}

function formatDate(instant: string, timezone: string) {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: timezone, year: 'numeric', month: '2-digit', day: '2-digit',
  }).format(new Date(instant));
}

async function bookFirstSlot(page: Page, request: APIRequestContext, eventName: string, preferDifferentBrowserDate = false): Promise<Meeting> {
  const createdType = await request.post('/api/organizer/event-types', {
    data: { name: eventName, description: 'Описание не должно копироваться', durationMinutes: 30 },
  });
  expect(createdType.status()).toBe(201);
  const id = (await createdType.json()).id as string;
  const calendar = await (await request.get(`/api/event-types/${id}/slots`)).json() as Calendar;
  const candidates = calendar.days.flatMap((day) => day.slots.map((slot) => ({ ...slot, date: day.date })));
  const slot = (preferDifferentBrowserDate
    ? candidates.find((candidate) => formatDate(candidate.startsAt, 'America/Los_Angeles') !== candidate.date)
    : candidates[0])!;
  const day = calendar.days.find((entry) => entry.date === slot.date)!;

  await page.goto(`/event-types/${id}`);
  await page.getByRole('button', { name: day.date, exact: true }).click();
  await page.getByRole('group', { name: 'Свободное время' }).getByRole('button', { name: formatTime(slot.startsAt, calendar.timezone), exact: true }).click();
  await page.getByLabel('Ваше имя').fill('Гость для проверки');
  await page.getByLabel('Email').fill('copy-details@example.com');
  await page.getByLabel('Комментарий').fill('Комментарий не должен копироваться');
  await page.getByRole('button', { name: 'Подтвердить запись' }).click();
  await expect(page.getByRole('heading', { name: 'Встреча подтверждена' })).toBeVisible();
  return { eventName, date: day.date, startsAt: slot.startsAt, endsAt: slot.endsAt };
}

function expectedDetails(meeting: Meeting) {
  const localDate = formatDate(meeting.startsAt, 'Europe/Moscow');
  expect(localDate).toBe(meeting.date);
  return [meeting.eventName, `${localDate} · ${formatTime(meeting.startsAt, 'Europe/Moscow')} — ${formatTime(meeting.endsAt, 'Europe/Moscow')}`, 'Europe/Moscow'].join('\n');
}

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
    if (!conflict && process.env.DEPLOYMENT_URL) {
      await test.info().attach('Подтверждение встречи', {
        body: await page.getByRole('status').screenshot(),
        contentType: 'image/png',
      });
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  });
}

test('выбранное время показывает пояс календаря при отличающемся поясе браузера', async ({ page, request }) => {
  const createdType = await request.post('/api/organizer/event-types', {
    data: { name: `Проверка выбранного времени ${Date.now()}`, description: '', durationMinutes: 30 },
  });
  expect(createdType.status()).toBe(201);
  const id = (await createdType.json()).id as string;
  const calendar = await (await request.get(`/api/event-types/${id}/slots`)).json() as Calendar;
  const slot = calendar.days.flatMap((day) => day.slots.map((item) => ({ ...item, date: day.date })))
    .find((item) => formatDate(item.startsAt, 'America/Los_Angeles') !== item.date)!;
  const browserTimezone = await page.evaluate(() => Intl.DateTimeFormat().resolvedOptions().timeZone);
  expect(browserTimezone).toBe('America/Los_Angeles');
  expect(calendar.timezone).not.toBe(browserTimezone);
  expect(formatDate(slot.startsAt, browserTimezone)).not.toBe(slot.date);

  await page.goto(`/event-types/${id}`);
  await page.getByRole('button', { name: slot.date, exact: true }).click();
  await page.getByRole('group', { name: 'Свободное время' })
    .getByRole('button', { name: formatTime(slot.startsAt, calendar.timezone), exact: true }).click();

  const selection = page.getByRole('status').filter({ has: page.getByRole('heading', { name: 'Выбрано время' }) });
  await expect(selection).toContainText(
    `${slot.date} · ${formatTime(slot.startsAt, calendar.timezone)} — ${formatTime(slot.endsAt, calendar.timezone)} (${calendar.timezone})`,
  );
});

test('гость копирует три строки деталей встречи по клавиатуре в timezone календаря', async ({ page, request }) => {
  const eventName = `Встреча copy-${Date.now()}`;
  const meeting = await bookFirstSlot(page, request, eventName, true);
  await page.context().grantPermissions(['clipboard-read', 'clipboard-write'], { origin: new URL(page.url()).origin });

  const browserTimezone = await page.evaluate(() => Intl.DateTimeFormat().resolvedOptions().timeZone);
  expect(browserTimezone).toBe('America/Los_Angeles');
  const browserLocalDate = await page.evaluate(({ instant, timezone }) => new Intl.DateTimeFormat('en-CA', {
    timeZone: timezone, year: 'numeric', month: '2-digit', day: '2-digit',
  }).format(new Date(instant)), { instant: meeting.startsAt, timezone: browserTimezone });
  expect(browserLocalDate).not.toBe(meeting.date);

  const copyButton = page.getByRole('button', { name: 'Скопировать детали встречи', exact: true });
  await copyButton.focus();
  await expect(copyButton).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page.getByText('Детали встречи скопированы', { exact: true })).toBeVisible();
  const copied = await page.evaluate(() => navigator.clipboard.readText());
  expect(copied).toBe(expectedDetails(meeting));
  expect(copied.split('\n')).toHaveLength(3);
  expect(copied).not.toContain('Гость для проверки');
  expect(copied).not.toContain('copy-details@example.com');
  expect(copied).not.toContain('Комментарий не должен копироваться');
});

for (const unavailable of [false, true]) {
  test(`ручное копирование деталей встречи: ${unavailable ? 'Clipboard API отсутствует' : 'доступ отклонён'}`, async ({ page, request }) => {
    await page.addInitScript((missing) => {
      Object.defineProperty(navigator, 'clipboard', {
        configurable: true,
        value: missing ? undefined : { writeText: () => Promise.reject(new Error('Denied')) },
      });
    }, unavailable);

    const meeting = await bookFirstSlot(page, request, `Встреча copy-fallback-${Date.now()}`);
    await page.getByRole('button', { name: 'Скопировать детали встречи', exact: true }).click();
    await expect(page.getByRole('alert')).toHaveText('Не удалось скопировать автоматически. Скопируйте детали встречи вручную');
    await expect(page.getByText('Детали встречи скопированы', { exact: true })).toHaveCount(0);

    const manualCopy = page.getByLabel('Детали встречи для копирования', { exact: true });
    await expect(manualCopy).toHaveValue(expectedDetails(meeting));
    await manualCopy.focus();
    expect(await manualCopy.evaluate((element: HTMLTextAreaElement) => element.selectionEnd - element.selectionStart))
      .toBe((await manualCopy.inputValue()).length);
  });
}

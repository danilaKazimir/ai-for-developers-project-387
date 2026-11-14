import { expect, test } from '@playwright/test';
import { copyGuestLink } from './guest-links';

test.use({ timezoneId: 'America/Los_Angeles' });

test('гость по скопированной ссылке выбирает дату и время с клавиатуры', async ({ page, request }) => {
  const created = await request.post('/api/organizer/event-types', {
    data: { name: 'Обсуждение проекта', description: 'Встреча для знакомства', durationMinutes: 45 },
  });
  expect(created.status()).toBe(201);
  const id = (await created.json()).id;
  const response = await request.get(`/api/event-types/${id}/slots`);
  const calendar = await response.json();
  const available = calendar.days.find((day: { slots: unknown[] }) => day.slots.length > 0);
  await page.goto('/event-types');
  const guestUrl = await copyGuestLink(page, id, page.getByRole('article').filter({ hasText: 'Обсуждение проекта' }));
  await page.goto(guestUrl);
  await expect(page.getByRole('heading', { name: 'Обсуждение проекта' })).toBeVisible();
  await expect(page.getByText('Europe/Moscow', { exact: true })).toBeVisible();
  const day = page.getByRole('button', { name: available.date, exact: true });
  await day.focus();
  await page.keyboard.press('Enter');
  const time = page.getByRole('group', { name: 'Свободное время' }).getByRole('button').first();
  await time.focus();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('status')).toContainText('Выбрано время');
  await expect(page.getByRole('status')).toContainText('45 минут');
  await expect(page.getByRole('button', { name: 'Подтвердить запись' })).toBeEnabled();
  await page.reload();
  await expect(page.getByRole('heading', { name: 'Обсуждение проекта' })).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole('button', { name: available.date, exact: true }).click();
  await page.getByRole('group', { name: 'Свободное время' }).getByRole('button').first().click();
  await expect(page.getByRole('status')).toContainText('Выбрано время');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

const dates = ['2026-11-04', '2026-11-05', '2026-11-06', '2026-11-07', '2026-11-08', '2026-11-09', '2026-11-10', '2026-11-11', '2026-11-12', '2026-11-13', '2026-11-14', '2026-11-15', '2026-11-16', '2026-11-17'];
const fixture = {
  eventType: { id: 'intro', name: 'Знакомство', description: '', durationMinutes: 30 },
  timezone: 'Europe/Moscow', windowStartDate: '2026-11-04', windowEndDateExclusive: '2026-11-18',
  days: dates.map((date) => ({ date, slots: date === '2026-11-05' ? [{ startsAt: '2026-11-05T06:00:00Z', endsAt: '2026-11-05T06:30:00Z' }] : [] })),
};

test('показывает ближайшее свободное время отдельной информационной строкой', async ({ page }) => {
  await page.clock.install({ time: new Date('2026-11-04T00:00:00Z') });
  await page.route('**/api/event-types/intro/slots', (route) => route.fulfill({ json: fixture }));
  await page.goto('/event-types/intro');
  await expect(page.getByText('Ближайшее свободное время: четверг, 5 ноября, 09:00 GMT+03:00–09:30 GMT+03:00 (Europe/Moscow)')).toBeVisible();
  await expect(page.getByRole('button', { name: /Ближайшее свободное время/ })).toHaveCount(0);
});

test('обновляет свободное время при наступлении ближайшего и убирает прошедшее', async ({ page }) => {
  await page.clock.install({ time: new Date('2026-11-05T05:00:00Z') });
  let refreshed = false;
  await page.route('**/api/event-types/intro/slots', (route) => {
    const empty = { ...fixture, days: dates.map((date) => ({ date, slots: [] })) };
    return route.fulfill({ json: refreshed ? empty : fixture });
  });
  await page.goto('/event-types/intro');
  await expect(page.getByText(/^Ближайшее свободное время:/)).toBeVisible();
  refreshed = true;
  await page.clock.fastForward(3_600_000);
  await expect(page.getByText('В ближайшие 14 дней свободного времени нет. Вернитесь позднее.')).toBeVisible();
  await expect(page.getByText(/^Ближайшее свободное время:/)).toHaveCount(0);
});

test('при ошибке фонового обновления скрывает ближайшее время и позволяет повторить запрос', async ({ page }) => {
  await page.clock.install({ time: new Date('2026-11-04T00:00:00Z') });
  let failed = false;
  await page.route('**/api/event-types/intro/slots', (route) => route.fulfill(failed
    ? { status: 503, json: { code: 'DATABASE_UNAVAILABLE', message: 'Временно недоступно' } }
    : { json: fixture }));
  await page.goto('/event-types/intro');
  await expect(page.getByText(/^Ближайшее свободное время:/)).toBeVisible();
  failed = true;
  await page.evaluate(() => window.dispatchEvent(new Event('focus')));
  await expect(page.getByRole('alert')).toContainText('Не удалось обновить свободное время');
  await expect(page.getByText(/^Ближайшее свободное время:/)).toHaveCount(0);
  failed = false;
  await page.getByRole('button', { name: 'Повторить запрос' }).click();
  await expect(page.getByText(/^Ближайшее свободное время:/)).toBeVisible();
});

test('пустая дата, возврат на страницу и пустое окно сбрасывают устаревший выбор', async ({ page }) => {
  let empty = false;
  await page.route('**/api/event-types/intro/slots', (route) => route.fulfill({ json: empty ? { ...fixture, days: dates.map((date) => ({ date, slots: [] })) } : fixture }));
  await page.goto('/event-types/intro');
  await expect(page.getByText('На эту дату свободного времени нет. Выберите другую дату.')).toBeVisible();
  await page.getByRole('button', { name: '2026-11-05', exact: true }).click();
  await page.getByRole('button', { name: '09:00 GMT+03:00', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('Выбрано время');
  empty = true;
  await page.evaluate(() => window.dispatchEvent(new Event('focus')));
  await expect(page.getByRole('status')).toContainText('Доступные даты и время обновились. Выберите время заново');
  await expect(page.getByText('В ближайшие 14 дней свободного времени нет. Вернитесь позднее.')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Выбрано время' })).toHaveCount(0);
});

test('окно перечитывается в московскую полночь при другом timezone браузера', async ({ page }) => {
  await page.clock.install({ time: new Date('2026-11-04T20:00:00Z') });
  let rolled = false;
  await page.route('**/api/event-types/intro/slots', (route) => {
    return route.fulfill({ json: !rolled ? fixture : { ...fixture, windowStartDate: '2026-11-05', windowEndDateExclusive: '2026-11-19', days: [...fixture.days.slice(1), { date: '2026-11-18', slots: [] }] } });
  });
  await page.goto('/event-types/intro');
  await expect(page.getByRole('button', { name: '2026-11-04', exact: true })).toBeVisible();
  rolled = true;
  await page.clock.fastForward(3_600_000);
  await expect(page.getByRole('button', { name: '2026-11-18', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '2026-11-04', exact: true })).toHaveCount(0);
});

test('неизвестная прямая ссылка показывает понятную ошибку', async ({ page }) => {
  await page.goto('/event-types/no-such-type');
  await expect(page.getByRole('heading', { name: 'Событие не найдено' })).toBeVisible();
  await expect(page.locator('a[href]:not([href="#main-content"])')).toHaveCount(0);
});

test('ошибка загрузки позволяет повторить запрос', async ({ page }) => {
  let failed = true;
  await page.route('**/api/event-types/intro/slots', (route) => route.fulfill(failed ? { status: 503, json: { code: 'DATABASE_UNAVAILABLE', message: 'Временно недоступно' } } : { json: fixture }));
  await page.goto('/event-types/intro');
  await expect(page.getByRole('alert')).toContainText('Не удалось загрузить календарь');
  failed = false;
  await page.getByRole('button', { name: 'Повторить загрузку' }).click();
  await expect(page.getByRole('heading', { name: 'Знакомство' })).toBeVisible();
});

test('повторённые локальные часы различаются offset и выбираются независимо', async ({ page }) => {
  await page.route('**/api/event-types/intro/slots', (route) => route.fulfill({ json: {
    ...fixture, timezone: 'Pacific/Kwajalein', windowStartDate: '1969-09-30', windowEndDateExclusive: '1969-10-14',
    days: [{ date: '1969-09-30', slots: [
      { startsAt: '1969-09-29T22:00:00Z', endsAt: '1969-09-29T22:30:00Z' },
      { startsAt: '1969-09-30T21:00:00Z', endsAt: '1969-09-30T21:30:00Z' },
    ] }],
  } }));
  await page.goto('/event-types/intro');
  const first = page.getByRole('button', { name: '09:00 GMT+11:00', exact: true });
  const second = page.getByRole('button', { name: '09:00 GMT-12:00', exact: true });
  await first.click();
  await expect(first).toHaveAttribute('aria-pressed', 'true');
  await second.click();
  await expect(first).toHaveAttribute('aria-pressed', 'false');
  await expect(second).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByRole('status')).toContainText('GMT-12:00');
});

test('длинный пояс переносится без горизонтальной прокрутки на узком экране', async ({ page }) => {
  const timezone = 'America/Argentina/ComodRivadavia';
  const date = '2026-11-05';
  const slot = { startsAt: '2026-11-05T12:00:00Z', endsAt: '2026-11-05T12:30:00Z' };
  await page.setViewportSize({ width: 320, height: 844 });
  await page.clock.install({ time: new Date('2026-11-04T00:00:00Z') });
  await page.route('**/api/event-types/intro/slots', (route) => route.fulfill({ json: {
    ...fixture,
    timezone,
    days: dates.map((day) => ({ date: day, slots: day === date ? [slot] : [] })),
  } }));
  await page.goto('/event-types/intro');
  await page.getByRole('button', { name: date, exact: true }).click();
  await page.getByRole('group', { name: 'Свободное время' }).getByRole('button').click();

  const selection = page.locator('.selection-summary');
  await expect(selection).toContainText(`(${timezone})`);
  expect(await selection.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true);
  expect(await selection.locator('.selection-timezone').evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

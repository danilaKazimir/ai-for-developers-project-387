import { expect, test } from '@playwright/test';

test('организатор переходит к созданию типа и возвращается на главную', async ({ page }) => {
  await page.goto('/');
  const hero = page.getByRole('region', { name: 'Договоритесь о звонке без лишней переписки', exact: true });
  await expect(hero.getByRole('heading', { level: 1 })).toBeVisible();
  await hero.getByRole('link', { name: 'Создать событие', exact: true }).click();

  await expect(page).toHaveURL('/calendars/new');
  await expect(page.getByRole('heading', { level: 1, name: 'Создать событие', exact: true })).toBeVisible();
  await page.getByRole('link', { name: 'Вернуться на главную', exact: true }).click();

  await expect(page).toHaveURL('/');
  await expect(hero.getByRole('heading', { level: 1 })).toBeVisible();
});

test('организатор может пройти основной сценарий с клавиатуры', async ({ page }) => {
  await page.goto('/');
  await page.keyboard.press('Tab');
  await expect(page.getByRole('link', { name: 'Перейти к содержимому', exact: true })).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('main')).toBeFocused();

  await page.keyboard.press('Tab');
  const hero = page.getByRole('region', { name: 'Договоритесь о звонке без лишней переписки', exact: true });
  await expect(hero.getByRole('link', { name: 'Создать событие', exact: true })).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL('/calendars/new');

  await page.getByLabel('Название', { exact: true }).focus();
  await expect(page.getByLabel('Название', { exact: true })).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(page.getByLabel('Описание', { exact: true })).toBeFocused();
});

test('страницу создания типа можно открыть напрямую и обновить', async ({ page }) => {
  await page.goto('/calendars/new');
  await expect(page.getByRole('heading', { level: 1, name: 'Создать событие', exact: true })).toBeVisible();

  await page.reload();

  await expect(page).toHaveURL('/calendars/new');
  await expect(page.getByRole('heading', { level: 1, name: 'Создать событие', exact: true })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Вернуться на главную', exact: true })).toBeVisible();
});

test('главная и форма создания загружаются без API и не запрашивают его', async ({ page }) => {
  const apiRequests: string[] = [];
  page.on('request', (request) => {
    if (new URL(request.url()).pathname.startsWith('/api/')) apiRequests.push(request.url());
  });
  await page.route('http://127.0.0.1:15174/api/**', (route) => route.abort());
  await page.goto('/');
  await expect(page.getByRole('heading', { level: 1, name: 'Договоритесь о звонке без лишней переписки', exact: true })).toBeVisible();

  await page.getByRole('link', { name: 'Создать событие', exact: true }).first().click();
  await expect(page.getByRole('heading', { level: 1, name: 'Создать событие', exact: true })).toBeVisible();

  expect(apiRequests).toEqual([]);
});

test('кнопки в навигации и внизу главной ведут к созданию типа', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('navigation', { name: 'Основная навигация', exact: true })
    .getByRole('link', { name: 'Создать событие', exact: true }).click();
  await expect(page).toHaveURL('/calendars/new');
  await expect(page.getByRole('heading', { level: 1, name: 'Создать событие', exact: true })).toBeVisible();

  await page.getByRole('link', { name: 'Вернуться на главную', exact: true }).click();
  await page.getByRole('region', { name: 'Встречи начинаются с удобного времени', exact: true })
    .getByRole('link', { name: 'Создать событие', exact: true }).click();
  await expect(page).toHaveURL('/calendars/new');
  await expect(page.getByRole('heading', { level: 1, name: 'Создать событие', exact: true })).toBeVisible();
});

test('пример страницы записи показывает длительность и часовой пояс без элементов записи', async ({ page }) => {
  await page.goto('/');
  const example = page.getByRole('figure').filter({ hasText: 'Пример страницы записи' });

  await expect(example.getByText('Пример страницы записи', { exact: true })).toBeVisible();
  await expect(example.getByText('30 минут', { exact: true })).toBeVisible();
  await expect(example.getByText('Europe/Moscow · UTC+3', { exact: true })).toBeVisible();
  await expect(example.getByRole('table', { name: 'Ноябрь 2026', exact: true })).toBeVisible();
  await expect(example.getByRole('button')).toHaveCount(0);
  await expect(example.getByRole('link')).toHaveCount(0);
});

for (const width of [320, 390]) {
  test(`организатор может пользоваться страницами при ширине ${width} px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 844 });
    await page.goto('/');
    const hero = page.getByRole('region', { name: 'Договоритесь о звонке без лишней переписки', exact: true });
    await expect(hero.getByRole('heading', { level: 1 })).toBeInViewport({ ratio: 1 });
    const landingWidth = await page.evaluate(() => ({ content: document.documentElement.scrollWidth, viewport: document.documentElement.clientWidth }));
    expect(landingWidth.content).toBeLessThanOrEqual(landingWidth.viewport);

    await hero.getByRole('link', { name: 'Создать событие', exact: true }).click();
    await expect(page.getByRole('heading', { level: 1, name: 'Создать событие', exact: true })).toBeVisible();
    const placeholderWidth = await page.evaluate(() => ({ content: document.documentElement.scrollWidth, viewport: document.documentElement.clientWidth }));
    expect(placeholderWidth.content).toBeLessThanOrEqual(placeholderWidth.viewport);

    await page.getByRole('link', { name: 'Вернуться на главную', exact: true }).click();
    await expect(page).toHaveURL('/');
    await expect(hero.getByRole('heading', { level: 1 })).toBeVisible();
  });
}

test('по адресу старой диагностики нет диагностической страницы', async ({ page }) => {
  await page.goto('/status');
  await expect(page.getByRole('heading', { level: 1, name: 'Такой страницы нет', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Проверить подключение', exact: true })).toHaveCount(0);

  await page.getByRole('link', { name: 'Вернуться на главную', exact: true }).click();
  await expect(page).toHaveURL('/');
});

test('каталог показывает загрузку, ошибку с повтором и пустое состояние', async ({ page }) => {
  let release: () => void = () => {};
  const pending = new Promise<void>((resolve) => { release = resolve; });
  await page.route('**/api/event-types', async (route) => {
    await pending;
    await route.fulfill({ status: 503, json: { code: 'DATABASE_UNAVAILABLE', message: 'Unavailable' } });
  });
  await page.goto('/event-types');
  await expect(page.getByRole('status')).toHaveText('Загружаем события…');
  release();
  await expect(page.getByRole('alert')).toContainText('Не удалось загрузить события');
  await page.route('**/api/event-types', (route) => route.fulfill({ json: { items: [] } }));
  await page.getByRole('button', { name: 'Повторить загрузку' }).click();
  await expect(page.getByText('Событий пока нет. Создайте первое событие и отправьте ссылку гостю.')).toBeVisible();
});

# Issue tracker: GitHub

Задачи и спецификации хранятся в GitHub Issues репозитория
[`danilaKazimir/ai-for-developers-project-387`](https://github.com/danilaKazimir/ai-for-developers-project-387/issues). Используй CLI `gh` из корня репозитория.
Для контекста перенесённого приложения смотри спецификацию и карту решений в
[материалах первого проекта](../../README.md#материалы-первого-проекта).

## Основные операции

- Создать: `gh issue create --title "..." --body-file /path/to/body.md`.
- Прочитать: `gh issue view <number> --json number,title,body,labels,comments`.
- Получить список: `gh issue list --state open --json number,title,body,labels,comments`.
  Добавляй фильтры `--label` и `--state` по задаче.
- Обновить текст: `gh issue edit <number> --body-file /path/to/body.md`.
- Прокомментировать: `gh issue comment <number> --body-file /path/to/comment.md`.
- Назначить или убрать метку: `gh issue edit <number> --add-label "..."` /
  `--remove-label "..."`.
- Закрыть: сначала опубликуй объяснение отдельным комментарием,
  затем выполни `gh issue close <number>`. Это сохраняет объяснение и для уже
  закрытой задачи.

Для многострочного текста сначала создай временный файл с нужным содержимым,
затем передай его через `--body-file`.

Перед первым созданием задачи в сессии проверь
`gh repo view --json nameWithOwner`: целевой репозиторий должен совпадать
с указанным выше. При несовпадении уточни репозиторий у пользователя.
Задачи публикуются в репозиторий пользователя.

## Подзадачи и зависимости

Используй нативные связи GitHub (команды ниже требуют `gh` 2.94+):

- Создать подзадачу: `gh issue create --parent <parent> --title "..." --body-file /path/to/body.md`.
- Связать существующие задачи: `gh issue edit <parent> --add-sub-issue <child>`.
- Указать блокирующую задачу: `gh issue edit <child> --add-blocked-by <blocker>`.
- Создать с зависимостями: `gh issue create --blocked-by <n>,<n> --title "..." --body-file /path/to/body.md`.

Если нативные связи недоступны, добавь `Part of #<parent>` и
`Blocked by: #<n>, #<n>` в начало текста дочерней задачи, а в родительскую —
список подзадач.

Число открытых блокеров:
`gh api repos/danilaKazimir/ai-for-developers-project-387/issues/<n> --jq .issue_dependencies_summary.blocked_by`.
Задача доступна для работы, когда все блокеры закрыты; при текстовых связях
проверяй состояние каждой указанной задачи.

## Pull requests as a triage surface

**PRs as a request surface: no.**

## Операции, запрашиваемые навыками

«Publish to the issue tracker» означает создать GitHub Issue.
«Fetch the relevant ticket» означает прочитать соответствующий Issue.

## Wayfinding

- Карта — Issue с меткой `wayfinder:map` и разделами Notes,
  Decisions-so-far, Fog.
- Билеты — подзадачи карты с метками `wayfinder:research`,
  `wayfinder:prototype`, `wayfinder:grilling` или `wayfinder:task`.
  При текстовых связях веди список билетов в карте.
- Для следующего шага выбери первый по порядку карты открытый билет
  без открытых блокеров и исполнителя.
- Взять билет: `gh issue edit <n> --add-assignee @me`.
- Завершить: опубликуй результат комментарием, закрой билет и добавь
  краткий вывод со ссылкой в Decisions-so-far карты.

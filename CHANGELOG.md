# Changelog

## 0.1.0 (2026-11-09)


### ⚠ BREAKING CHANGES

* POST /api/organizer/event-types больше не принимает id. Передавайте только name, description и durationMinutes; используйте id из ответа. Существующие ссылки сохраняются.

### Features

* **demo:** добавить событие для пробной записи ([98083a2](https://github.com/danilaKazimir/ai-for-developers-project-386/commit/98083a2d0728124b58ec57f5fd527debdac8fbe2)), closes [#11](https://github.com/danilaKazimir/ai-for-developers-project-386/issues/11)
* **web:** добавить favicon с календарём и галочкой ([92c9019](https://github.com/danilaKazimir/ai-for-developers-project-386/commit/92c90191cb9705367ed9114383f5381c614780b4))
* **web:** добавить главную страницу и браузерные тесты ([4389868](https://github.com/danilaKazimir/ai-for-developers-project-386/commit/438986831b5647065b5684487230131b488f319c)), closes [#1](https://github.com/danilaKazimir/ai-for-developers-project-386/issues/1)
* **web:** добавить копирование ссылок для гостей ([d611443](https://github.com/danilaKazimir/ai-for-developers-project-386/commit/d61144355cf469ec11f68d220ae2a3a7bed80ce3))
* генерировать ссылки и унифицировать тексты интерфейса ([ec32965](https://github.com/danilaKazimir/ai-for-developers-project-386/commit/ec3296556a9689a1bc15693c00137cd8103ce355))
* добавить автономный Docker контейнер для Render ([428f111](https://github.com/danilaKazimir/ai-for-developers-project-386/commit/428f111ccf832e192a4c990606a83ed89d10fd95))
* добавить бронирование с защитой от пересечений ([13a4785](https://github.com/danilaKazimir/ai-for-developers-project-386/commit/13a4785c074ed18166dc9154e5f70ffbd2861c56))
* добавить единый список предстоящих встреч организатора ([4ed1216](https://github.com/danilaKazimir/ai-for-developers-project-386/commit/4ed121650d908a6ff369719c8cc57275c66ca90e))
* добавить календарь выбора времени на 14 дней ([a52f581](https://github.com/danilaKazimir/ai-for-developers-project-386/commit/a52f5810cb23eea7ee96112b0ced7d8b0c4a1fc3))
* добавить каркас приложения календаря звонков ([de92c19](https://github.com/danilaKazimir/ai-for-developers-project-386/commit/de92c1909e716f24538ba7cb04262f29b65f812b))
* добавить создание типов событий и публичный каталог ([5b03da5](https://github.com/danilaKazimir/ai-for-developers-project-386/commit/5b03da552b8bdf0eab695448551420c9d41d0421))
* убрать авторизацию и упростить гостевую страницу ([23f9ad2](https://github.com/danilaKazimir/ai-for-developers-project-386/commit/23f9ad2155af9ade1f9aa445888130acb9e12dbc))


### Bug Fixes

* **web:** применять предел имени гостя после обрезки пробелов ([2360c84](https://github.com/danilaKazimir/ai-for-developers-project-386/commit/2360c84be063ba686767187a16cedecb26c27da7))
* **web:** сократить подпись создания до «Создать событие» ([2e5310f](https://github.com/danilaKazimir/ai-for-developers-project-386/commit/2e5310f547d945f8d0e3504cb665ecc365d31075))

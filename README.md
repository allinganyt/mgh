# MGH — Miami General Hospital

Telegram Mini App и бот MGH. Backend переведён на **Google Apps Script + Google Sheets**: не нужен Render, VPS или банковская карта.

## Архитектура

- `Code.gs` — Google Apps Script backend: API для Mini App, Telegram webhook, запись и напоминания.
- `index.html` — Mini App frontend; запросы к Apps Script идут JSONP, чтобы обойти CORS/preflight.
- Google Sheets — постоянная база данных: врачи, пользователи Telegram, записи и анкеты.
- Триггер Apps Script раз в минуту отправляет напоминания. Закрытие/сворачивание Telegram не удаляет данные; они остаются в Google Sheets.
- Бот регистрирует Telegram chat ID после `/start`. Пользователь должен нажать Start, иначе бот не сможет написать ему первым.

## Настройка (бесплатный Google аккаунт)

### 1. Создать Apps Script
1. Открой https://script.google.com/ и создай новый проект.
2. Скопируй содержимое файла `Code.gs` из этого репозитория в редактор Apps Script вместо шаблона.
3. Открой **Project Settings → Script Properties → Add script property** и добавь:
   - `BOT_TOKEN` = токен от `@BotFather` (секретный).
   - `ADMIN_PIN` = придумай новый PIN администратора.
   - `MINI_APP_URL` = HTTPS адрес опубликованного Mini App (шаг 3).
   - `WEB_APP_URL` = URL Apps Script Web App после деплоя (шаг 2).
4. В редакторе выбери функцию `setup` и нажми Run. Разреши доступ. Скрипт создаст Google Spreadsheet и триггер напоминаний. Таблица будет привязана к Script Properties автоматически.

### 2. Опубликовать backend
1. **Deploy → New deployment → Web app**.
2. Execute as: **Me**. Who has access: **Anyone**.
3. Нажми Deploy и скопируй URL, оканчивающийся на `/exec`.
4. В Script Properties установи `WEB_APP_URL` равным этому URL.
5. Открой редактор, выбери `configureTelegram` и нажми Run. Это установит Telegram webhook. Проверить backend можно по адресу `ТВОЙ_URL/exec?action=health`.

Если изменяешь Code.gs после публикации, открой **Deploy → Manage deployments → Edit → New version → Deploy**.

### 3. Опубликовать Mini App
1. В GitHub открой **Settings → Pages** репозитория `allinganyt/mgh`.
2. В разделе Build and deployment выбери **Deploy from a branch**, branch `main`, folder `/ (root)`, Save.
3. Дождись публикации страницы. Адрес будет вида `https://allinganyt.github.io/mgh/`.
4. В `index.html` замени `ВСТАВЬТЕ_URL_WEB_APP_GOOGLE_APPS_SCRIPT` в переменной `GAS_API_URL` на URL Apps Script `/exec`. Закоммить изменение в main.
5. В Script Properties установи `MINI_APP_URL` в опубликованный GitHub Pages URL.
6. Снова запусти `configureTelegram`, чтобы бот присылал кнопку открытия Mini App с актуальным адресом.

В BotFather можно также настроить Menu Button: `/mybots → ваш бот → Bot Settings → Menu Button`, URL Mini App — GitHub Pages URL.

## Проверка

- Открой `https://ТВОЙ_APPS_SCRIPT_URL/exec?action=health` — ожидается `{"ok":true,"service":"MGH Apps Script"}`.
- Напиши боту `/start); после этого Telegram chat ID пользователя сохранится.
- Открой Mini App, создай тестовую запись на будущее время.
- Проверь, что строка появилась на листе `appointments`, а подтверждение пришло в Telegram.
- Триггер `sendDueReminders` проверяет наступившие записи раз в минуту и помечает отправленные в таблице.

## Важные ограничения

- Бесплатный Apps Script имеет квоты Google и может задерживать триггер; напоминание не гарантируется секунда-в-секунду.
- Google Sheets хранит данные постоянно, пока не удалишь таблицу/проект. Не удаляй Spreadsheet, указанный в Script Properties.
- Telegram не позволяет боту первым писать пользователю: пациент и врач должны хотя бы раз открыть бота и нажать `/start`.
- Текущие старые данные из SQLite автоматически не мигрируются. Если там уже есть важные записи, их нужно экспортировать и отдельно перенести.
- В текущем интерфейсе для записи используется Telegram username. Для стабильной идентификации пользователь должен иметь username и запускать бота до записи.
- Не публикуй BOT_TOKEN и ADMIN_PIN в GitHub или в сообщениях.

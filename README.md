# MGH — Miami General Hospital

Telegram Mini App больницы (index.html) + сервер и бот (bot.py).

## Запуск

1. `pip install -r requirements.txt`
2. Впиши в `bot.py`: `BOT_TOKEN` от @BotFather и `WEBAPP_URL` (HTTPS-адрес, например ngrok).
3. Положи рядом `index.html` мини-приложения.
4. `python bot.py` — сервер на :8000, бот в long polling.

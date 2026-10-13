# twitch-bot-detka — Луна 🤖🌙

Умный бот-модератор и собеседник для Twitch-канала. Отвечает на упоминания через
Groq AI, помнит зрителей (SQLite), умеет команды и модерацию. Работает на twitchio 3.x
(EventSub + Helix), готов к запуску 24/7 под systemd.

## Возможности

- **Живой ИИ-собеседник** — Луна отвечает, когда её @упоминают, отвечают на её сообщение
  или пишут «луна». Диалог идёт с контекстом, личность задана системным промптом.
- **Долгая память** (SQLite): история диалогов, факты о зрителях, статистика активности —
  переживает перезапуск.
- **Команды**: `!луна`, `!help`, `!запомни <факт>`, `!вспомни [ник]`, `!забудь [ник]`.
- **Модерация** (для модеров и владельца): `!timeout <ник> <сек>`, `!ban <ник> [причина]`,
  `!unban <ник>`.
- **Защита от спама**: cooldown на пользователя и глобальный — не даёт залить Groq запросами.
- **Аккуратная обрезка** ответов под лимит 500 символов Twitch (не ломает эмодзи).

## Структура

```
main.py                 # точка входа
luna/
  config.py             # чтение .env и настройки
  memory.py             # SQLite: история, факты, статистика зрителей
  brain.py              # Groq (AsyncGroq) + системный промпт + обрезка
  bot.py                # twitchio Bot + Component (события, команды, модерация)
scripts/get_token.py    # генерация токенов через OAuth
deploy/twitch-luna.service  # systemd-юнит
requirements.txt
.env.example
```

## Быстрый старт (локально)

1. **Python 3.11+** и venv:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Создай приложение** на <https://dev.twitch.tv/console/apps>. Запиши Client ID и Secret.
   Во вкладке OAuth добавь redirect URL: `http://localhost:3000`.

3. **Скопируй конфиг и заполни**:
   ```bash
   cp .env.example .env
   ```

4. **Получи токены бота** (авторизуйся аккаунтом БОТА, не своим):
   ```bash
   python scripts/get_token.py
   ```
   Скрипт выведет `TWITCH_BOT_TOKEN`, `TWITCH_BOT_REFRESH`, `TWITCH_BOT_ID` — вставь в `.env`.

5. **Дай боту модератора** на своём канале (нужно, чтобы работала модерация и, вместе со
   скоупами, чтение чата): зайди в чат канала и `/mod <ник_бота>`.

6. **Запусти**:
   ```bash
   python main.py
   ```

## Требуемые скоупы токена

`get_token.py` запрашивает их сам. Если генерируешь вручную:

```
user:read:chat user:write:chat moderator:read:chatters moderator:manage:banned_users moderator:manage:chat_messages
```

## Настройка (.env)

| Переменная | Назначение |
|---|---|
| `TWITCH_CLIENT_ID` / `TWITCH_CLIENT_SECRET` | приложение из dev.twitch.tv |
| `TWITCH_BOT_TOKEN` / `TWITCH_BOT_REFRESH` | user-токен бота (без `oauth:`) |
| `TWITCH_BOT_ID` | числовой ID бота |
| `TWITCH_CHANNEL` / `TWITCH_BOT_NICK` | логин канала / бота |
| `GROQ_API_KEY` | ключ Groq |
| `GROQ_MODEL` | модель (по умолч. `openai/gpt-oss-20b`) |
| `AI_TEMPERATURE`, `MAX_TOKENS`, `MAX_HISTORY` | поведение ИИ |
| `USER_COOLDOWN`, `GLOBAL_COOLDOWN` | защита от спама (сек) |
| `ADMIN_NICKS` | доп. ники-админы через запятую |
| `BOT_PREFIX` | префикс команд (по умолч. `!`) |

## Деплой на VPS 24/7 (systemd)

```bash
# 1. Положи проект, например, в /opt/twitch-bot-detka
# 2. Создай venv и установи зависимости (см. Быстрый старт)
# 3. Установи юнит (поправь User и пути в deploy/twitch-luna.service):
sudo cp deploy/twitch-luna.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now luna-bot
# 4. Смотри логи:
journalctl -u luna-bot -f
```

`Restart=always` поднимет бота после падения или перезагрузки сервера.

## Примечания

- **Бот должен быть модером** канала, иначе `!timeout`/`!ban` и чтение чата (в некоторых
  конфигурациях скоупов) не сработают.
- Старый файл `twitch-bot-detka.py` — исходный однострочный скрипт (написан под twitchio 2.x,
  с установленным 3.x не работал). Он оставлен как есть; актуальный код — в `luna/` + `main.py`.
- Лимит сообщений Twitch — 500 символов; длинные ответы бот обрезает.
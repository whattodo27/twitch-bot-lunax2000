"""Генерация user access token + refresh token для бота через OAuth Authorization Code Flow.

Запуск:
    python scripts/get_token.py

Требования:
    - В .env заполнены TWITCH_CLIENT_ID и TWITCH_CLIENT_SECRET.
    - В настройках приложения на dev.twitch.tv (вкладка «OAuth Redirect URLs»)
      добавлен http://localhost:3000

Скрипт откроет браузер, где нужно авторизоваться аккаунтом БОТА (не своим!)
и разрешить доступ. В конце выведет token, refresh и ID бота для .env.
"""
from __future__ import annotations

import asyncio
import os
import urllib.parse
import webbrowser

import aiohttp
from aiohttp import web
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.environ.get("TWITCH_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("TWITCH_CLIENT_SECRET", "")
REDIRECT_URI = os.environ.get("TWITCH_REDIRECT_URI", "http://localhost:3000")

# Скоупы, которые нужны боту:
# пользовательский:читать-чат — получать сообщения (EventSub)
# пользовательский:писать-чат — отправлять сообщения
# модератор:читать список — видеть зрителей
# модератор:управлять банами — таймаут/бан
# модератор:управлять сообщениями — удалять сообщения (на будущее)
SCOPES = [
    "user:read:chat",
    "user:write:chat",
    "moderator:read:chatters",
    "moderator:manage:banned_users",
    "moderator:manage:chat_messages",
]


def _fail(msg: str) -> None:
    print(f"\n[ОШИБКА] {msg}")
    raise SystemExit(1)


async def _run() -> None:
    if not CLIENT_ID or not CLIENT_SECRET:
        _fail("Заполните TWITCH_CLIENT_ID и TWITCH_CLIENT_SECRET в .env")

    port = int(REDIRECT_URI.rsplit(":", 1)[1])

    auth_url = "https://id.twitch.tv/oauth2/authorize?" + urllib.parse.urlencode(
        {
            "client_id": CLIENT_ID,
            "redirect_uri": REDIRECT_URI,
            "response_type": "code",
            "scope": " ".join(SCOPES),
        }
    )
    print("\nОткрываю браузер для авторизации аккаунта БОТА…")
    print("(если не открылся — скопируй URL и открой вручную):\n")
    print(auth_url, "\n")
    webbrowser.open(auth_url)

    code_holder: dict[str, str] = {}

    async def _handler(request: web.Request) -> web.Response:
        code = request.query.get("code")
        if code:
            code_holder["code"] = code
        return web.Response(text="Готово! Можешь закрыть эту вкладку и вернуться в терминал.")

    app = web.Application()
    app.router.add_get("/", _handler)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "localhost", port).start()

    # ждём редирект с кодом (до 2 минут)
    for _ in range(1200):
        if "code" in code_holder:
            break
        await asyncio.sleep(0.1)
    await runner.cleanup()

    code = code_holder.get("code")
    if not code:
        _fail("Таймаут: код авторизации не получен (2 минуты).")

    async with aiohttp.ClientSession() as session:
        async with session.post(
            "https://id.twitch.tv/oauth2/token",
            data={
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": REDIRECT_URI,
            },
        ) as resp:
            data = await resp.json()
        if "access_token" not in data:
            _fail(f"Не удалось получить токен: {data}")

        access_token: str = data["access_token"]
        refresh_token: str = data.get("refresh_token", "")

        # валидируем токен и узнаём ID/логин бота
        async with session.get(
            "https://id.twitch.tv/oauth2/validate",
            headers={"Authorization": f"Bearer {access_token}"},
        ) as resp:
            info = await resp.json()

    print("\n✅ Готово! Вставь это в .env:\n")
    print(f"TWITCH_BOT_TOKEN={access_token}")
    print(f"TWITCH_BOT_REFRESH={refresh_token}")
    print(f"TWITCH_BOT_ID={info.get('user_id', '<не определён>')}")
    print(f"# логин бота: {info.get('login', '<не определён>')}\n")
    if not info.get("user_id"):
        print("⚠️  Не удалось определить ID бота автоматически — найди его вручную.")
    print("⚠️  ВАЖНО: токен принадлежит аккаунту, которым ты авторизовался. Убедись, что это бот-аккаунт!")


if __name__ == "__main__":
    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        pass
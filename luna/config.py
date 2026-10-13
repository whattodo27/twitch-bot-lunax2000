"""Чтение и валидация конфигурации из файла .env."""
from __future__ import annotations

import logging
import os
import sys

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("luna.config")

# Имена обязательных переменных и подсказки для ошибки.
_REQUIRED: dict[str, str] = {
    "TWITCH_CLIENT_ID": "Client ID приложения (dev.twitch.tv/console/apps)",
    "TWITCH_CLIENT_SECRET": "Client Secret приложения",
    "TWITCH_BOT_TOKEN": "User access token бота (без префикса oauth:)",
    "TWITCH_BOT_REFRESH": "Refresh token бота",
    "TWITCH_BOT_ID": "Числовой ID аккаунта бота",
    "TWITCH_CHANNEL": "Имя канала",
    "TWITCH_BOT_NICK": "Логин аккаунта бота",
    "GROQ_API_KEY": "Ключ Groq API",
}


def _validate() -> None:
    missing = [k for k in _REQUIRED if not os.getenv(k)]
    if not missing:
        return
    logger.error("В .env не хватает обязательных переменных:")
    for key in missing:
        logger.error("  - %s  (%s)", key, _REQUIRED[key])
    logger.error("Скопируйте .env.example в .env и заполните все поля.")
    sys.exit(1)


_validate()

# --- обязательные ---
TWITCH_CLIENT_ID = os.environ["TWITCH_CLIENT_ID"]
TWITCH_CLIENT_SECRET = os.environ["TWITCH_CLIENT_SECRET"]
TWITCH_BOT_TOKEN = os.environ["TWITCH_BOT_TOKEN"]
TWITCH_BOT_REFRESH = os.environ["TWITCH_BOT_REFRESH"]
TWITCH_BOT_ID = os.environ["TWITCH_BOT_ID"]
TWITCH_CHANNEL = os.environ["TWITCH_CHANNEL"]
TWITCH_BOT_NICK = os.environ["TWITCH_BOT_NICK"]
GROQ_API_KEY = os.environ["GROQ_API_KEY"]


# --- опциональные ---
def _env(name: str, default: str) -> str:
    return os.getenv(name, default)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


# AI / Groq
GROQ_MODEL = _env("GROQ_MODEL", "openai/gpt-oss-20b")
AI_TEMPERATURE = _env_float("AI_TEMPERATURE", 0.8)
MAX_TOKENS = _env_int("MAX_TOKENS", 250)
AI_TIMEOUT = _env_float("AI_TIMEOUT", 30.0)

# история диалога (окно контекста)
MAX_HISTORY = _env_int("MAX_HISTORY", 15)

# команды
BOT_PREFIX = _env("BOT_PREFIX", "!")

# защита от спама и контроль расходов на API
USER_COOLDOWN = _env_float("USER_COOLDOWN", 15.0)
GLOBAL_COOLDOWN = _env_float("GLOBAL_COOLDOWN", 3.0)

# хранилище и логи
DB_PATH = _env("DB_PATH", "luna.db")
LOG_LEVEL = _env("LOG_LEVEL", "INFO")

# никнеймы админов (могут модерировать наравне с модами канала)
ADMIN_NICKS: frozenset[str] = frozenset(
    n.strip().lower() for n in _env("ADMIN_NICKS", "").split(",") if n.strip()
)
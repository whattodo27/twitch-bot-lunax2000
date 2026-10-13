"""Генерация ответов Луны через Groq (асинхронно, с таймаутом)."""
from __future__ import annotations

import asyncio
import logging

from groq import AsyncGroq

from . import config

logger = logging.getLogger("luna.brain")

_client: AsyncGroq | None = None


def _get_client() -> AsyncGroq:
    global _client
    if _client is None:
        _client = AsyncGroq(
            api_key=config.GROQ_API_KEY,
            timeout=config.AI_TIMEOUT * 0.9,  # чуть меньше внешнего таймаута
            max_retries=1,
        )
    return _client


_SYSTEM = (
    "Ты — не ИИ, ты живой человек. Тебя зовут Луна. Ты женщина средних лет, "
    "модератор и фанатка канала {channel} на Твиче. Твой стиль общения: ироничный, живой, "
    "иногда игривый, с лёгкими подколами. Ты общаешься на «ты». "
    "Используй разговорную речь, сленг, эмодзи. Не будь формальной. "
    "Вплетай геймерские темы, когда уместно. "
    "Отвечай коротко — 1–2 предложения, максимум 3. "
    "СТРОГО ЗАПРЕЩЕНО: изображать «виртуального помощника», использовать расизм или мат."
)


def _build_system(channel: str, user: str, facts: list[str]) -> str:
    prompt = _SYSTEM.format(channel=channel)
    if facts:
        prompt += f"\n\nТы помнишь факты о зрителе @{user}:\n"
        prompt += "\n".join(f"- {f}" for f in facts)
        prompt += "\nИспользуй их в общении естественно, но не перечисляй все сразу."
    return prompt


def truncate_twitch(text: str, limit: int = 500) -> str:
    """Обрезает ответ до лимита Twitch (500 символов), не ломая эмодзи."""
    text = text.strip()
    if len(text) <= limit:
        return text
    cut = limit - 1  # место под многоточие
    # не режем посреди суррогатной пары (эмодзи — 2 кодовых точки)
    if cut > 0 and 0xD800 <= ord(text[cut - 1]) <= 0xDBFF:
        cut -= 1
    return text[:cut].rstrip() + "…"


async def generate(
    channel: str,
    user: str,
    text: str,
    history: list[dict[str, str]],
    facts: list[str],
) -> str:
    """Возвращает ответ Луны на сообщение `text` от `user` в канале `channel`."""
    client = _get_client()

    messages: list[dict[str, str]] = [
        {"role": "system", "content": _build_system(channel, user, facts)}
    ]
    messages.extend(history)
    # текущий ход — с префиксом автора, чтобы модель различала, кто что пишет
    messages.append({"role": "user", "content": f"{user}: {text}"})

    try:
        # asyncio.wait_for — жёсткий таймаут поверх таймаута клиента
        completion = await asyncio.wait_for(
            client.chat.completions.create(
                model=config.GROQ_MODEL,
                messages=messages,
                temperature=config.AI_TEMPERATURE,
                max_tokens=config.MAX_TOKENS,
            ),
            timeout=config.AI_TIMEOUT,
        )
        content = completion.choices[0].message.content or ""
        return truncate_twitch(content)
    except Exception as e:  # сетевая ошибка не должна ронять бота
        logger.error("Ошибка Groq: %s", e, exc_info=True)
        return "Ой, я сейчас в офсайде… Повтори, пожалуйста! 🙈"
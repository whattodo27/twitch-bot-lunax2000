"""Бот Луна: события, команды, защита от спама, модерация."""
from __future__ import annotations

import asyncio
import logging
import re
import time

import twitchio
from twitchio.ext import commands
from twitchio.eventsub.subscriptions import ChatMessageSubscription

from . import brain, config, memory

logger = logging.getLogger("luna.bot")

# Параметры команд в строке вызова: секунды таймаута, причина бана и т.п.
_TIMEOUT_MAX_SECONDS = 1_209_600  # 2 недели — максимум Twitch


def _mentioned_bot(message: twitchio.ChatMessage) -> bool:
    """True, если бота @упомянули или ответили на его сообщение."""
    nick = config.TWITCH_BOT_NICK.lower()
    if any((m.name or "").lower() == nick for m in message.mentions):
        return True
    if message.reply and message.reply.parent_user:
        if (message.reply.parent_user.name or "").lower() == nick:
            return True
    return False


def _mentions_luna(text: str) -> bool:
    return bool(re.search(r"\bлуна\b|\bluna\b", text.lower()))


class LunaComponent(commands.Component):
    """Логика Луны: реакция на упоминания, команды, модерация."""

    def __init__(self, mem: memory.Memory) -> None:
        super().__init__()  # bot присваивается автоматически при add_component()
        self.mem = mem
        self._user_last: dict[str, float] = {}
        self._global_last: float = 0.0

    # ---- обработка сообщений ----------------------------------------------

    @commands.Component.listener()
    async def event_message(self, message: twitchio.ChatMessage) -> None:
        # отсекаем собственные сообщения бота (эхо по ID, не по нику)
        if message.chatter.id == config.TWITCH_BOT_ID:
            return

        text = message.text or ""
        if not text:
            return

        user = message.chatter.name
        display = message.chatter.display_name
        channel = message.broadcaster.name  # логин стримера == имя канала
        await self.mem.touch_viewer(user, display)

        if not (_mentioned_bot(message) or _mentions_luna(text)):
            return

        if not self._cooldown_ok(user):
            return

        logger.info("Запрос в #%s от %s: %s", channel, user, text)

        facts = await self.mem.get_facts(user)
        history = await self.mem.get_history(channel, config.MAX_HISTORY)
        reply = await brain.generate(channel, user, text, history, facts)

        await self.mem.add_message(channel, user, "user", f"{user}: {text}")
        await self.mem.add_message(channel, config.TWITCH_BOT_NICK, "assistant", reply)

        try:
            await message.respond(f"{message.chatter.mention}, {reply}")
        except Exception as e:  # rate-limit / сетевая ошибка отправки
            logger.error("Не удалось отправить ответ: %s", e)

    def _cooldown_ok(self, user: str) -> bool:
        now = time.monotonic()
        if now - self._global_last < config.GLOBAL_COOLDOWN:
            return False
        if now - self._user_last.get(user, 0.0) < config.USER_COOLDOWN:
            return False
        self._global_last = now
        self._user_last[user] = now
        return True

    # ---- простые команды ---------------------------------------------------

    @commands.command(name="луна", aliases=("luna",))
    async def luna(self, ctx: commands.Context) -> None:
        await ctx.send(
            f"{ctx.author.mention} Луна на месте! 😉 Позови меня @{config.TWITCH_BOT_NICK},"
            " ответь на моё сообщение или просто напиши «луна» — и я отвечу."
        )

    @commands.command(name="help", aliases=("хелп", "помощь", "команды"))
    async def help_cmd(self, ctx: commands.Context) -> None:
        await ctx.send(
            "Команды: !луна, !запомни <факт>, !вспомни [ник], !забудь [ник], !help."
            " Модерация: !timeout <ник> <сек>, !ban <ник> [причина], !unban <ник>."
        )

    # ---- память ------------------------------------------------------------

    @commands.command(name="запомни", aliases=("remember",))
    async def remember(self, ctx: commands.Context, *, fact: str) -> None:
        fact = fact.strip()
        if not fact:
            await ctx.send(f"{ctx.author.mention} а что именно запомнить-то? 🤔")
            return
        await self.mem.add_fact(ctx.author.name, fact)
        await ctx.send(f"{ctx.author.mention} записала! 📝")

    @commands.command(name="вспомни", aliases=("memory", "память"))
    async def recall(self, ctx: commands.Context, *, target: str = "") -> None:
        name = target.strip().lstrip("@").lower() or ctx.author.name
        facts = await self.mem.get_facts(name)
        if not facts:
            await ctx.send(f"Про @{name} я пока ничего не помню 🤷")
            return
        await ctx.send(f"Помню про @{name}: " + " · ".join(facts[:5]))

    @commands.command(name="забудь", aliases=("forget",))
    async def forget(self, ctx: commands.Context, *, target: str = "") -> None:
        name = target.strip().lstrip("@").lower()
        if name and name != ctx.author.name and not self._is_mod(ctx):
            await ctx.send(f"{ctx.author.mention} чужие факты может забыть только модер ✋")
            return
        name = name or ctx.author.name
        removed = await self.mem.clear_facts(name)
        msg = f"Забыла {removed} факт(ов) про @{name} 🧹" if removed else f"Про @{name} и так ничего нет."
        await ctx.send(msg)

    # ---- модерация ---------------------------------------------------------

    @staticmethod
    def _is_mod(ctx: commands.Context) -> bool:
        return (
            ctx.author.moderator
            or ctx.author.broadcaster
            or ctx.author.name.lower() in config.ADMIN_NICKS
        )

    async def _guard_mod(self, ctx: commands.Context) -> bool:
        if not self._is_mod(ctx):
            await ctx.send(f"{ctx.author.mention} это только для модераторов 👮")
            return False
        return True

    @commands.command(name="timeout", aliases=("таймаут", "мут"))
    async def timeout_cmd(self, ctx: commands.Context, user: twitchio.User, duration: int) -> None:
        if not await self._guard_mod(ctx):
            return
        duration = max(1, min(duration, _TIMEOUT_MAX_SECONDS))
        await ctx.broadcaster.timeout_user(moderator=ctx.bot.bot_id, user=user, duration=duration)
        await ctx.send(f"{ctx.author.mention} выдал @{user.name} таймаут на {duration}с ⏱️")

    @commands.command(name="ban", aliases=("бан",))
    async def ban_cmd(
        self, ctx: commands.Context, user: twitchio.User, *, reason: str | None = None
    ) -> None:
        if not await self._guard_mod(ctx):
            return
        await ctx.broadcaster.ban_user(moderator=ctx.bot.bot_id, user=user, reason=reason)
        await ctx.send(f"{ctx.author.mention} забанил @{user.name} 🔨")

    @commands.command(name="unban", aliases=("разбан",))
    async def unban_cmd(self, ctx: commands.Context, user: twitchio.User) -> None:
        if not await self._guard_mod(ctx):
            return
        await ctx.broadcaster.unban_user(moderator=ctx.bot.bot_id, user_id=user.id)
        await ctx.send(f"{ctx.author.mention} разбанил @{user.name} 🕊️")


class LunaBot(commands.Bot):
    """Точка входа twitchio: подключает токены, компоненты и подписку на чат."""

    def __init__(self, mem: memory.Memory) -> None:
        super().__init__(
            client_id=config.TWITCH_CLIENT_ID,
            client_secret=config.TWITCH_CLIENT_SECRET,
            bot_id=config.TWITCH_BOT_ID,
            prefix=config.BOT_PREFIX,
        )
        self.mem = mem

    async def setup_hook(self) -> None:
        # Регистрируем user-токен бота — через него идёт чтение/отправка чата и модерация.
        await self.add_token(config.TWITCH_BOT_TOKEN, config.TWITCH_BOT_REFRESH)
        await self.add_component(LunaComponent(self.mem))

    async def event_ready(self) -> None:
        logger.info("Луна подключена как @%s (id=%s)", self.user.name, self.bot_id)
        try:
            users = await self.fetch_users(logins=[config.TWITCH_CHANNEL])
            if not users:
                logger.error("Канал %s не найден! Проверьте TWITCH_CHANNEL.", config.TWITCH_CHANNEL)
                return
            broadcaster_id = users[0].id
            await self.subscribe_websocket(
                ChatMessageSubscription(
                    broadcaster_user_id=broadcaster_id,
                    user_id=self.bot_id,
                ),
                as_bot=True,
            )
            logger.info("Подписка на чат #%s активна.", config.TWITCH_CHANNEL)
        except Exception as e:
            logger.error("Не удалось подписаться на чат: %s", e, exc_info=True)
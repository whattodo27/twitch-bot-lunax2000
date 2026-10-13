"""Точка входа бота. Запуск: python main.py"""
from __future__ import annotations

import asyncio
import logging
import signal

from luna import config, memory
from luna.bot import LunaBot

logger = logging.getLogger("luna.main")


def _setup_logging() -> None:
    level = getattr(logging, config.LOG_LEVEL.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    )


async def main() -> None:
    _setup_logging()
    mem = memory.Memory(config.DB_PATH)
    bot = LunaBot(mem)

    # аккуратное завершение по SIGINT/SIGTERM (Ctrl+C и systemd stop)
    loop = asyncio.get_running_loop()
    stop = asyncio.Event()

    def _request_stop() -> None:
        logger.info("Получен сигнал остановки…")
        stop.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _request_stop)
        except (NotImplementedError, RuntimeError):
            pass

    start_task = asyncio.create_task(bot.start())
    stop_task = asyncio.create_task(stop.wait())

    await asyncio.wait({start_task, stop_task}, return_when=asyncio.FIRST_COMPLETED)

    if stop.is_set() and not start_task.done():
        start_task.cancel()
        try:
            await start_task
        except asyncio.CancelledError:
            logger.info("Соединение с Twitch закрыто.")

    try:
        await bot.close()
    except Exception:  # noqa: BLE001 — при закрытии ошибки не критичны
        pass

    mem.close()
    logger.info("Луна ушла спать. 💤")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
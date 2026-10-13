"""Персистентная память Луны (SQLite).

Хранит: историю диалогов по каналам, факты о зрителях, статистику активности.
Переживает перезапуск бота — это и есть «долгая память».
"""
from __future__ import annotations

import asyncio
import logging
import sqlite3
import time

logger = logging.getLogger("luna.memory")


class Memory:
    """Обёртка над SQLite.

    Операции сериализуются через asyncio.Lock. SQLite работает синхронно, но
    каждая операция занимает доли миллисекунды, поэтому вызов напрямую в
    event loop безопасен при нагрузке обычного чата (несколько сообщений/сек).
    """

    def __init__(self, path: str) -> None:
        self._conn = sqlite3.connect(path)
        self._conn.row_factory = sqlite3.Row
        self._lock = asyncio.Lock()
        self._create_schema()

    def _create_schema(self) -> None:
        c = self._conn
        c.execute("PRAGMA journal_mode=WAL;")
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel TEXT NOT NULL,
                user_name TEXT NOT NULL,
                role TEXT NOT NULL,          -- 'user' | 'assistant'
                content TEXT NOT NULL,
                created_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_messages_channel ON messages(channel, id);

            CREATE TABLE IF NOT EXISTS facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_name TEXT NOT NULL,     -- логин в нижнем регистре
                fact TEXT NOT NULL,
                created_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_facts_user ON facts(user_name);

            CREATE TABLE IF NOT EXISTS viewers (
                user_name TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                first_seen REAL NOT NULL,
                last_seen REAL NOT NULL,
                message_count INTEGER NOT NULL DEFAULT 0
            );
            """
        )
        c.commit()

    # ---- история диалога -------------------------------------------------

    async def add_message(self, channel: str, user_name: str, role: str, content: str) -> None:
        async with self._lock:
            self._conn.execute(
                "INSERT INTO messages (channel, user_name, role, content, created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (channel, user_name, role, content, time.time()),
            )
            # не даём таблице распухнуть: держим максимум ~200 последних строк на канал
            self._conn.execute(
                "DELETE FROM messages WHERE channel = ? AND id NOT IN ("
                "  SELECT id FROM messages WHERE channel = ? ORDER BY id DESC LIMIT 200"
                ")",
                (channel, channel),
            )
            self._conn.commit()

    async def get_history(self, channel: str, limit: int) -> list[dict[str, str]]:
        async with self._lock:
            rows = self._conn.execute(
                "SELECT role, content FROM messages WHERE channel = ? ORDER BY id DESC LIMIT ?",
                (channel, limit),
            ).fetchall()
        # возвращаем в хронологическом порядке (старые -> новые)
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    async def clear_history(self, channel: str) -> None:
        async with self._lock:
            self._conn.execute("DELETE FROM messages WHERE channel = ?", (channel,))
            self._conn.commit()

    # ---- факты о зрителях -------------------------------------------------

    async def add_fact(self, user_name: str, fact: str) -> None:
        async with self._lock:
            self._conn.execute(
                "INSERT INTO facts (user_name, fact, created_at) VALUES (?, ?, ?)",
                (user_name.lower(), fact, time.time()),
            )
            self._conn.commit()

    async def get_facts(self, user_name: str, limit: int = 10) -> list[str]:
        async with self._lock:
            rows = self._conn.execute(
                "SELECT fact FROM facts WHERE user_name = ? ORDER BY id DESC LIMIT ?",
                (user_name.lower(), limit),
            ).fetchall()
        return [r["fact"] for r in rows]

    async def clear_facts(self, user_name: str) -> int:
        async with self._lock:
            cur = self._conn.execute("DELETE FROM facts WHERE user_name = ?", (user_name.lower(),))
            self._conn.commit()
            return cur.rowcount

    # ---- статистика зрителей -----------------------------------------------

    async def touch_viewer(self, user_name: str, display_name: str | None = None) -> bool:
        """Регистрирует сообщение зрителя. Возвращает True, если зритель — новый."""
        name = user_name.lower()
        now = time.time()
        async with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM viewers WHERE user_name = ?", (name,)
            ).fetchone()
            if row is None:
                self._conn.execute(
                    "INSERT INTO viewers (user_name, display_name, first_seen, last_seen,"
                    " message_count) VALUES (?, ?, ?, ?, 1)",
                    (name, display_name or user_name, now, now),
                )
                self._conn.commit()
                return True
            self._conn.execute(
                "UPDATE viewers SET last_seen = ?, message_count = message_count + 1,"
                " display_name = ? WHERE user_name = ?",
                (now, display_name or user_name, name),
            )
            self._conn.commit()
            return False

    async def viewer_stats(self, user_name: str) -> dict | None:
        async with self._lock:
            row = self._conn.execute(
                "SELECT * FROM viewers WHERE user_name = ?", (user_name.lower(),)
            ).fetchone()
        return dict(row) if row else None

    def close(self) -> None:
        self._conn.close()
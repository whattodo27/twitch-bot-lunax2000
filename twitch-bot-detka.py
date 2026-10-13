# os — даёт доступ к переменным окружения (os.getenv) и работе с путями
import os

# asyncio — встроенная библиотека для асинхронного кода; нужна для asyncio.run() и await
import asyncio

# logging — стандартный модуль логов; используется для вывода INFO/ERROR в консоль
import logging

# sys — даёт sys.exit() для аварийного выхода и sys.stdout для потока логов
import sys

# defaultdict — словарь, который сам создаёт пустой список при обращении к новому ключу
# используется для хранения истории чата по каналам
from collections import defaultdict

# load_dotenv — читает .env-файл и кладёт переменные в os.environ
from dotenv import load_dotenv

# Groq — официальный клиент Groq API (совместим с OpenAI SDK)
from groq import Groq

# twitchio — основной пакет TwitchIO; импортируем как пространство имён для типов
import twitchio

# commands — подмодуль TwitchIO с классом Bot, Component и декораторами
from twitchio.ext import commands


# ---------- НАСТРОЙКА ЛОГОВ ----------
# basicConfig — задаёт глобальный формат логов: уровень, шаблон строки, поток вывода
logging.basicConfig(
    level=logging.INFO,                                    # показывать INFO и выше (WARNING, ERROR)
    format="%(asctime)s - %(levelname)s - %(message)s",    # шаблон: время - уровень - сообщение
    stream=sys.stdout                                       # писать в stdout (чтобы systemd/journald подхватывал)
)

# getLogger(__name__) — создаёт логгер с именем текущего модуля, чтобы в логах было видно источник
logger = logging.getLogger(__name__)


# ---------- ЗАГРУЗКА КОНФИГА ----------
# load_dotenv() — читает файл .env из текущей папки и добавляет переменные в os.environ
load_dotenv()

# os.getenv("X") — возвращает значение переменной окружения X или None, если её нет
TWITCH_BOT_TOKEN     = os.getenv("TWITCH_BOT_TOKEN")     # OAuth-токен бота (строка "oauth:...")
TWITCH_CLIENT_ID     = os.getenv("TWITCH_CLIENT_ID")     # Client ID приложения из Twitch Dev Console
TWITCH_CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET") # Client Secret приложения (для автообновления токена)
GROQ_API_KEY         = os.getenv("GROQ_API_KEY")         # ключ для Groq API
TWITCH_CHANNEL       = os.getenv("TWITCH_CHANNEL")       # имя канала, куда подключается бот
TWITCH_BOT_NICK      = os.getenv("TWITCH_BOT_NICK")      # ник бота-аккаунта (для проверки упоминаний)

# all([...]) — True только если ВСЕ элементы truthy; проверяем, что ни одна переменная не пустая
if not all([TWITCH_BOT_TOKEN, TWITCH_CLIENT_ID, TWITCH_CLIENT_SECRET, GROQ_API_KEY, TWITCH_CHANNEL, TWITCH_BOT_NICK]):
    # logger.error — пишет сообщение уровня ERROR в лог
    logger.error("ОШИБКА: Проверьте .env файл! Нужны TWITCH_BOT_TOKEN, TWITCH_CLIENT_ID, TWITCH_CLIENT_SECRET, GROQ_API_KEY, TWITCH_CHANNEL, TWITCH_BOT_NICK")

    # sys.exit(1) — немедленно завершает процесс с кодом 1 (признак ошибки для systemd/Docker)
    sys.exit(1)


# ---------- ИНИЦИАЛИЗАЦИЯ GROQ ----------
try:
    # Groq(api_key=...) — создаёт клиент для обращения к Groq API
    client = Groq(api_key=GROQ_API_KEY)

    # logger.info — пишет сообщение уровня INFO
    logger.info("Клиент Groq инициализирован.")
except Exception as e:
    # f-строка подставляет текст ошибки в сообщение
    logger.error(f"Ошибка инициализации Groq: {e}")
    sys.exit(1)


# ---------- ЛИЧНОСТЬ Луна ----------
# SYSTEM_PROMPT — системная инструкция, которая всегда идёт первым сообщением в Groq
SYSTEM_PROMPT = (
    "Ты — не ИИ, ты живой человек. Тебя зовут Луна. Ты женщина средних лет, "
    "модератор и фанатка канала на Твиче kokocabpukoc. Твой стиль общения: ироничный, живой, "
    "иногда игривый и с легкими подколами. Ты общаешься на 'ты'. "
    "Используй разговорную речь, сленг, эмодзи. Не будь формальной. "
    "Вплетай геймерски темы, когда это уместно. "
    "СТРОГО ЗАПРЕЩЕНО: быть 'виртуальным помощником', использовать расизм, мат."
)


# ---------- ПАМЯТЬ ЧАТА ----------
# defaultdict(list) — словарь, где по любому новому ключу автоматически создаётся пустой список
# ключ = имя канала, значение = список сообщений [{"role": ..., "content": ...}]
chat_history = defaultdict(list)

# MAX_HISTORY — сколько последних сообщений хранить (чтобы не раздувать запрос к Groq)
MAX_HISTORY = 15


# ---------- ФУНКЦИЯ ОТВЕТА ОТ GROQ ----------
async def get_ai_response(channel_name: str, user_name: str, text: str) -> str:
    """Принимает канал, имя пользователя и текст, возвращает ответ Луны."""

    # .append({...}) — добавляет новое сообщение в конец истории канала
    chat_history[channel_name].append({"role": "user", "content": f"{user_name}: {text}"})

    # len(...) — длина списка; если больше лимита, обрезаем
    if len(chat_history[channel_name]) > MAX_HISTORY:
        # [-MAX_HISTORY:] — срез: берём последние MAX_HISTORY элементов
        chat_history[channel_name] = chat_history[channel_name][-MAX_HISTORY:]

    try:
        # Собираем список сообщений: сначала system, потом вся история
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]

        # .extend(...) — добавляет все элементы списка в конец другого списка
        messages.extend(chat_history[channel_name])

        logger.info(f"Запрос к Groq для канала {channel_name}...")

        # client.chat.completions.create(...) — синхронный вызов Groq API
        completion = client.chat.completions.create(
            messages=messages,                # список сообщений диалога
            model="openai/gpt-oss-20b",       # используемая модель
            temperature=0.8,                  # «креативность»: 0 — строго, 1 — хаотично
        )

        # .choices[0].message.content — достаём текст первого варианта ответа
        response_text = completion.choices[0].message.content

        # Лимит Twitch — 500 символов на сообщение
        if len(response_text) > 500:
            # [:497] — берём первые 497 символов и добавляем "..."
            response_text = response_text[:497] + "..."

        # Добавляем ответ ассистента в историю, чтобы модель помнила свой же ответ
        chat_history[channel_name].append({"role": "assistant", "content": response_text})

        # return — возвращает строку вызывающему коду
        return response_text

    except Exception as e:
        # exc_info=True — добавляет в лог полный traceback ошибки
        logger.error(f"ОШИБКА API: {e}", exc_info=True)
        return "Ой, что-то я в офсайде... Повтори, пожалуйста!"


# ---------- КОМПОНЕНТ С ЛОГИКОЙ ----------
# commands.Component — базовый класс для «модулей» с обработчиками событий
class LunaComponent(commands.Component):
    """Компонент с логикой Луны для Twitch."""

    # @commands.Component.listener() — регистрирует метод как обработчик события TwitchIO
    @commands.Component.listener()
    async def event_message(self, message: twitchio.ChatMessage) -> None:
        """Слушаем все сообщения в чате канала."""

        # message.echo — True, если это сообщение самого бота; игнорируем, чтобы не отвечать себе
        if message.echo:
            return

        # .text — текст сообщения; может быть None для не-чатовых событий
        text = message.text
        if not text:
            return

        # .channel.name — имя канала, куда пришло сообщение
        channel_name = message.channel.name

        # .chatter.name — ник автора сообщения
        user_name = message.chatter.name

        # .lower() — приводит строку к нижнему регистру для нечувствительного сравнения
        text_lower = text.lower()

        # Проверка 1: упомянут ли ник бота в тексте
        is_mentioned = TWITCH_BOT_NICK.lower() in text_lower

        # Проверка 2: это реплай на сообщение бота?
        is_reply_to_bot = False
        if message.reply:
            try:
                # .reply.author.name — ник того, кому отвечают
                is_reply_to_bot = message.reply.author.name.lower() == TWITCH_BOT_NICK.lower()
            except AttributeError:
                # AttributeError — если у reply нет author (например, автор удалён)
                pass

        # Проверка 3: упомянуто имя «Луна» или «luna» в тексте
        name_mentioned = "луна" in text_lower or "luna" in text_lower

        # Если сработал хотя бы один триггер — отвечаем
        if is_mentioned or is_reply_to_bot or name_mentioned:
            logger.info(f"Запрос в #{channel_name} от {user_name}: {text}")

            # await — ждём асинхронного результата get_ai_response
            response = await get_ai_response(channel_name, user_name, text)

            # .channel.send(...) — отправляет сообщение в канал с упоминанием автора
            await message.channel.send(f"@{user_name}, {response}")


# ---------- КЛАСС БОТА ----------
# commands.Bot — базовый класс бота TwitchIO
class LunaBot(commands.Bot):
    def __init__(self) -> None:
        # super().__init__(...) — вызывает конструктор родителя с нашими параметрами
        super().__init__(
            token=TWITCH_BOT_TOKEN,                 # OAuth-токен бота
            client_id=TWITCH_CLIENT_ID,             # Client ID приложения (обязателен в TwitchIO 3.x)
            client_secret=TWITCH_CLIENT_SECRET,     # Client Secret (нужен для автообновления токена)
            prefix="!",                             # префикс для команд (у нас команд нет, но требуется)
            initial_channels=[TWITCH_CHANNEL],      # список каналов для автоподключения
        )

    # setup_hook — вызывается автоматически ДО подключения к Twitch
    async def setup_hook(self) -> None:
        # add_component — регистрирует наш компонент с обработчиками
        await self.add_component(LunaComponent())

    # event_ready — вызывается, когда бот успешно подключился к Twitch
    async def event_ready(self) -> None:
        # self.nick — ник бота, self.user_id — его ID
        logger.info(f"Луна зашла в игру! Подключена как {self.nick} (ID: {self.user_id})")


# ---------- ТОЧКА ВХОДА ----------
async def main():
    logger.info("Луна почти на Twitch'е!")

    # LunaBot() — создаём экземпляр бота
    bot = LunaBot()

    # await bot.start() — запускает цикл подключения и обработки событий (блокирующий)
    await bot.start()


# __name__ == "__main__" — True, только если файл запущен напрямую (не импортирован)
if __name__ == "__main__":
    # asyncio.run(...) — создаёт event loop и запускает корутину main()
    asyncio.run(main())
import asyncio
import logging
import os
from dotenv import load_dotenv

load_dotenv()
import random
import time
from collections import defaultdict, deque

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram.types import Message

from ai import chat, should_speak, extract_facts
from memory import Memory

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("flow-ai-kpc")

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
BOT_NAME = os.getenv("BOT_NAME", "КПК")
AUTONOMOUS_MINUTES = int(os.getenv("AUTONOMOUS_MINUTES", "12"))
SILENCE_SECONDS = int(os.getenv("SILENCE_SECONDS", "10"))

bot = Bot(TOKEN)
dp = Dispatcher()
memory = Memory()
last_activity = defaultdict(float)
last_reply = defaultdict(float)
chat_locks = defaultdict(asyncio.Lock)
memory_refreshing = set()


def display_name(message: Message) -> str:
    u = message.from_user
    if not u:
        return "пользователь"
    return u.full_name or u.username or "пользователь"


def is_group(message: Message) -> bool:
    return message.chat.type in {ChatType.GROUP, ChatType.SUPERGROUP}


@dp.message(Command("start"))
async def start(message: Message):
    await message.answer(
        f"Привет. Я {BOT_NAME}. В группах могу участвовать в разговоре без обязательного упоминания."
    )


@dp.message(Command("help"))
async def help_cmd(message: Message):
    await message.answer(
        "Команды:\n"
        "/start — запуск\n"
        "/help — помощь\n\n"
        "В группе я могу отвечать на обычные сообщения, если считаю реплику уместной."
    )


@dp.message(F.text)
async def on_text(message: Message):
    if message.from_user and message.from_user.is_bot:
        return

    text = (message.text or "").strip()
    if not text:
        return

    chat_id = message.chat.id
    last_activity[chat_id] = time.time()

    name = display_name(message)
    message_count = memory.add(chat_id, name, text)
    # Compatibility with older memory.py versions that do not return a count.
    if message_count is not None and message_count % 12 == 0 and chat_id not in memory_refreshing:
        memory_refreshing.add(chat_id)
        asyncio.create_task(refresh_long_term_memory(chat_id))

    if not is_group(message):
        async with chat_locks[chat_id]:
            answer = await chat(
                memory.context(chat_id),
                text,
                direct=True,
                bot_name=BOT_NAME,
            )
            if answer:
                await message.answer(answer)
                last_reply[chat_id] = time.time()
        return

    mentioned = False
    if message.entities:
        for entity in message.entities:
            if entity.type == "mention":
                mention = text[entity.offset:entity.offset + entity.length]
                me = await bot.get_me()
                if mention.lower() == f"@{(me.username or '').lower()}":
                    mentioned = True
                    break

    replied_to_bot = (
        message.reply_to_message is not None
        and message.reply_to_message.from_user is not None
        and message.reply_to_message.from_user.id == (await bot.get_me()).id
    )

    direct = mentioned or replied_to_bot
    if not direct and time.time() - last_reply[chat_id] < SILENCE_SECONDS:
        return

    async with chat_locks[chat_id]:
        decision = await should_speak(
            memory.context(chat_id),
            text,
            direct=direct,
            bot_name=BOT_NAME,
        )

        if not decision:
            return

        answer = await chat(
            memory.context(chat_id),
            text,
            direct=direct,
            bot_name=BOT_NAME,
        )
        if answer:
            await message.answer(answer)
            last_reply[chat_id] = time.time()



async def health_handler(reader, writer):
    try:
        await reader.read(1024)
        body = b"Flow AI KPK is running"
        response = (
            b"HTTP/1.1 200 OK\r\n"
            b"Content-Type: text/plain; charset=utf-8\r\n"
            b"Content-Length: " + str(len(body)).encode() + b"\r\n"
            b"Connection: close\r\n\r\n" + body
        )
        writer.write(response)
        await writer.drain()
    except Exception:
        pass
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass


async def start_health_server():
    port = int(os.getenv("PORT", "10000"))
    server = await asyncio.start_server(
        health_handler,
        host="0.0.0.0",
        port=port,
    )
    log.info("HTTP health server listening on 0.0.0.0:%s", port)
    return server


async def refresh_long_term_memory(chat_id):
    try:
        facts = await extract_facts(memory.context(chat_id))
        for item in facts:
            if not isinstance(item, dict):
                continue
            username = str(item.get("username", "пользователь"))[:100]
            fact = str(item.get("fact", "")).strip()
            if fact:
                memory.add_fact(chat_id, username, fact)
    except Exception:
        log.exception("Long-term memory refresh failed")
    finally:
        memory_refreshing.discard(chat_id)


async def autonomous_loop():
    while True:
        await asyncio.sleep(60)
        now = time.time()
        for chat_id, activity in list(last_activity.items()):
            if now - activity < AUTONOMOUS_MINUTES * 60:
                continue
            if now - last_reply[chat_id] < AUTONOMOUS_MINUTES * 60:
                continue

            # Only attempt autonomous speech in chats where there was recent activity.
            if now - activity > AUTONOMOUS_MINUTES * 4 * 60:
                continue

            async with chat_locks[chat_id]:
                if random.random() > 0.70:
                    continue
                prompt = (
                    "Самостоятельно поддерживай живой разговор: если есть естественный повод, "
                    "можешь поздороваться, спросить что-нибудь, продолжить недавнюю тему "
                    "или поднять лёгкую новую тему. Не спамь и не выдумывай повод. "
                    "Если повода нет, верни ровно NO_REPLY."
                )
                answer = await chat(
                    memory.context(chat_id),
                    prompt,
                    direct=False,
                    bot_name=BOT_NAME,
                    autonomous=True,
                )
                if answer and answer != "NO_REPLY":
                    try:
                        await bot.send_message(chat_id, answer)
                        last_reply[chat_id] = time.time()
                    except Exception:
                        log.exception("Autonomous send failed")


async def main():
    log.info("Starting %s", BOT_NAME)

    # Render Web Service requires an open HTTP port.
    # The bot itself continues to use Telegram long polling.
    server = await start_health_server()
    asyncio.create_task(autonomous_loop())

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        server.close()
        await server.wait_closed()


if __name__ == "__main__":
    asyncio.run(main())

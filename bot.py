import asyncio
import json
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import BOT_TOKEN, CHAT_ID, TOPIC_ID, MEMBERS, CHECK_HOUR, CHECK_MINUTE, TIMEZONE

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

DATA_DIR = Path("/data") if Path("/data").exists() else Path(".")
DATA_FILE = DATA_DIR / "data.json"
tz = ZoneInfo(TIMEZONE)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


# --- Хранилище данных ---

def load_data() -> dict:
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text())
    return {}


def save_data(data: dict):
    DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2))


def record_photo(username: str, date_str: str):
    """Записать что username отправил фото за дату date_str (формат YYYY-MM-DD)."""
    data = load_data()
    if date_str not in data:
        data[date_str] = []
    if username not in data[date_str]:
        data[date_str].append(username)
        save_data(data)
        logger.info(f"Записано: @{username} отправил(а) фото за {date_str}")


def get_missing(date_str: str) -> list[str]:
    """Вернуть список username кто НЕ отправил фото за дату."""
    data = load_data()
    sent = data.get(date_str, [])
    return [m for m in MEMBERS if m not in sent]


# --- Определение даты из подписи ---

def extract_day_from_caption(caption: str) -> int | None:
    """Извлечь число дня из подписи к фото (например '27', '27 марта', '27.03')."""
    match = re.search(r'\b(\d{1,2})\b', caption)
    if match:
        day = int(match.group(1))
        if 1 <= day <= 31:
            return day
    return None


# --- Обработчики сообщений ---

@dp.message(F.photo, F.chat.id == CHAT_ID, F.message_thread_id == TOPIC_ID)
async def handle_photo(message: Message):
    """Обработка фото в топике."""
    username = message.from_user.username
    if not username or username not in MEMBERS:
        return

    caption = message.caption or ""
    now = datetime.now(tz)

    day = extract_day_from_caption(caption)

    if day is not None:
        today = now.date()
        yesterday = today - timedelta(days=1)

        if day == today.day:
            record_photo(username, today.isoformat())
        elif day == yesterday.day:
            record_photo(username, yesterday.isoformat())
        else:
            logger.info(f"@{username} отправил(а) фото с числом {day}, не совпадает с сегодня/вчера")
    else:
        # Нет подписи или нет числа — засчитываем за сегодня
        record_photo(username, now.date().isoformat())


# --- Ежедневная проверка ---

async def daily_check():
    """Запускается каждый день в CHECK_HOUR:CHECK_MINUTE.
    Проверяет только вчерашний день. Пишет только если кто-то не отправил."""
    now = datetime.now(tz)
    yesterday = now.date() - timedelta(days=1)

    missing = get_missing(yesterday.isoformat())

    if missing:
        tags = ", ".join(f"@{u}" for u in missing)
        await bot.send_message(
            chat_id=CHAT_ID,
            message_thread_id=TOPIC_ID,
            text=f"Ждем фото ({yesterday.strftime('%d.%m')}) от: {tags} 🥀",
            disable_notification=True,
        )


# --- Запуск ---

async def main():
    # Планировщик — ежедневная проверка
    scheduler = AsyncIOScheduler(timezone=TIMEZONE)
    scheduler.add_job(daily_check, "cron", hour=CHECK_HOUR, minute=CHECK_MINUTE)
    scheduler.start()

    logger.info("Бот запущен!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

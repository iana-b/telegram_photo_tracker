import asyncio
import json
import logging
import os
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from aiogram import Bot, Dispatcher, F
from aiogram.exceptions import TelegramAPIError
from aiogram.types import Message, ReactionTypeEmoji
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import (
    BOT_TOKEN, CHAT_ID, TOPIC_ID, MEMBERS,
    CHECK_HOUR, CHECK_MINUTE, WINDOW_DAYS, REACTION,
    BIRTHDAY_HOUR, BIRTHDAY_MINUTE, BIRTHDAYS,
    TIMEZONE,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

DATA_DIR = Path("/data") if Path("/data").exists() else Path(".")
DATA_FILE = DATA_DIR / "data.json"
TMP_FILE = DATA_DIR / "data.json.tmp"
tz = ZoneInfo(TIMEZONE)

if DATA_DIR != Path("/data"):
    logger.warning("Волюм /data не примонтирован, пишем в %s — данные не переживут деплой.",
                   DATA_DIR.resolve())

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


# --- Хранилище данных ---

def load_data() -> dict:
    if not DATA_FILE.exists():
        return {"days": {}, "messages": {}}
    try:
        raw = json.loads(DATA_FILE.read_text())
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        # Не удаляем: остаток можно разобрать руками.
        backup = DATA_DIR / f"data.json.corrupt-{datetime.now(tz).strftime('%Y%m%d-%H%M%S')}"
        DATA_FILE.rename(backup)
        logger.error("Файл данных повреждён (%s). Сохранён как %s, продолжаем с пустых данных.", e, backup)
        return {"days": {}, "messages": {}}
    if "days" not in raw:
        raw = {"days": raw}  # старый формат: одни только даты
    raw.setdefault("messages", {})
    return raw


def save_data(data: dict):
    """Атомарная запись: os.replace подменяет файл целиком."""
    with open(TMP_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(TMP_FILE, DATA_FILE)


def record_photo(username: str, date_str: str, message_id: int) -> bool:
    """Засчитать фото. False, если этот день уже был засчитан этому человеку."""
    data = load_data()
    day = data["days"].setdefault(date_str, [])
    is_new = username not in day
    if is_new:
        day.append(username)
        logger.info(f"Записано: @{username} отправил(а) фото за {date_str}")
    data["messages"][str(message_id)] = {"user": username, "date": date_str}
    save_data(data)
    return is_new


def move_photo(message_id: int, new_date: str) -> str | None:
    """Перенести засчитанное фото на другую дату. Вернуть прежнюю, если перенос был."""
    data = load_data()
    entry = data["messages"].get(str(message_id))
    if entry is None or entry["date"] == new_date:
        return None

    user, old_date = entry["user"], entry["date"]
    if user not in data["days"].setdefault(new_date, []):
        data["days"][new_date].append(user)

    # Старый день снимаем, только если его не подтверждает другое фото.
    kept = any(e["user"] == user and e["date"] == old_date
               for mid, e in data["messages"].items() if mid != str(message_id))
    if not kept and user in data["days"].get(old_date, []):
        data["days"][old_date].remove(user)
        if not data["days"][old_date]:
            del data["days"][old_date]

    entry["date"] = new_date
    save_data(data)
    logger.info(f"@{user}: фото перенесено с {old_date} на {new_date}")
    return old_date


def get_missing(date_str: str) -> list[str]:
    """Вернуть список username кто НЕ отправил фото за дату."""
    sent = load_data()["days"].get(date_str, [])
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


def resolve_date(day: int, today: date) -> date | None:
    """Ближайшая прошедшая дата с таким числом."""
    for shift in range(WINDOW_DAYS):
        d = today - timedelta(days=shift)
        if d.day == day:
            return d
    return None


# --- Обработчики сообщений ---

def target_date(caption: str | None, today: date) -> date | None:
    """Дата, за которую засчитывать фото. None — из подписи не понять."""
    day = extract_day_from_caption(caption or "")
    return resolve_date(day, today) if day is not None else None


async def react(message: Message):
    """Беззвучная отметка 'принято'. Не критична — при ошибке только лог."""
    try:
        await message.react([ReactionTypeEmoji(emoji=REACTION)])
    except TelegramAPIError as e:
        logger.warning("Реакция %s не поставлена: %s. При REACTION_INVALID — сменить REACTION в config.py.",
                       REACTION, e)


@dp.message(F.photo, F.chat.id == CHAT_ID, F.message_thread_id == TOPIC_ID)
async def handle_photo(message: Message):
    """Обработка фото в топике."""
    if not message.from_user:
        return

    username = message.from_user.username
    if not username or username not in MEMBERS:
        return

    today = datetime.now(tz).date()
    target = target_date(message.caption, today)

    # Дату не знаем — засчитываем за сегодня и говорим об этом.
    comment = None
    if target is None:
        target = today
        comment = f"принято фото за {today.strftime('%d.%m')}"

    is_new = record_photo(username, target.isoformat(), message.message_id)
    await react(message)

    if comment and is_new:
        await message.reply(comment, disable_notification=True)


@dp.edited_message(F.photo, F.chat.id == CHAT_ID, F.message_thread_id == TOPIC_ID)
async def handle_edited_photo(message: Message):
    """Подпись поправили — переносим фото на новую дату."""
    if not message.from_user:
        return

    username = message.from_user.username
    if not username or username not in MEMBERS:
        return

    target = target_date(message.caption, datetime.now(tz).date())
    if target is None:
        return  # дату по-прежнему не понять — оставляем как есть

    if move_photo(message.message_id, target.isoformat()) is None:
        # Фото прислали до появления индекса: засчитать новый день можем, снять старый — нет.
        if not record_photo(username, target.isoformat(), message.message_id):
            return

    await message.reply(f"засчитано за {target.strftime('%d.%m')}", disable_notification=True)


# --- Поздравления с днём рождения ---

BIRTHDAY_MESSAGES = [
    "🌹 @{username}, с днём рождения, красотка! Ты сияешь ярче всех звёзд 💕",
    "🌸 Наша любимая @{username}, с днём рождения! Ты делаешь этот мир красивее 🤍",
    "💐 С днём рождения, @{username}! Такая красивая девушка заслуживает самый лучший день 💗",
    "🌷 @{username}, happy birthday! Улыбайся чаще — от твоей улыбки расцветают цветы 🌺",
    "💕 С днём рождения, наша прекрасная @{username}! Пусть сегодня весь мир будет для тебя 🌹",
    "🤍 @{username}, красотка, с днём рождения! Будь всегда такой же сияющей ✨💐",
    "🌸 Любимая @{username}, сегодня твой день! Пусть он будет таким же прекрасным, как ты 💗",
    "💐 С днём рождения, @{username}! Ты наша звёздочка — продолжай сиять! 🌟🤍",
    "🌹 @{username}, с праздником! Самой очаровательной — самые тёплые пожелания 💕",
    "🌺 Happy Birthday, @{username}! Ты потрясающая, не забывай об этом 💐🤍",
]


async def birthday_check():
    """Проверяет, есть ли сегодня именинник, и отправляет поздравление."""
    now = datetime.now(tz)
    today_str = now.strftime("%d.%m")

    for username, bday in BIRTHDAYS.items():
        if bday == today_str:
            idx = now.timetuple().tm_yday % len(BIRTHDAY_MESSAGES)
            text = BIRTHDAY_MESSAGES[idx].format(username=username)
            await bot.send_message(chat_id=CHAT_ID, text=text)
            logger.info(f"Отправлено поздравление для @{username}")


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
    scheduler = AsyncIOScheduler(timezone=TIMEZONE)
    scheduler.add_job(daily_check, "cron", hour=CHECK_HOUR, minute=CHECK_MINUTE,
                      misfire_grace_time=600)
    scheduler.add_job(birthday_check, "cron", hour=BIRTHDAY_HOUR, minute=BIRTHDAY_MINUTE,
                      misfire_grace_time=600)
    scheduler.start()

    logger.info("Бот запущен!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

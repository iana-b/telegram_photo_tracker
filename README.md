# Photo of the Day Bot

A Telegram bot for group chats with topics. It tracks whether all members have sent their daily photo and reminds those who forgot.

## How it works

- The bot monitors photos in a specified topic
- It determines the date from the photo caption (e.g. `27`, `March 27`, `27.03`)
- Every day at 12:00 it checks whether everyone sent a photo for yesterday
- If someone didn't — it posts a reminder in the topic with mentions

## Tech stack

- Python 3.12+
- aiogram 3 — Telegram Bot API framework
- APScheduler — task scheduler
- python-dotenv — loads variables from `.env`

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python bot.py
```

## Deployment

Deployed on [Fly.io](https://fly.io) via Docker. Data is persisted on a Fly.io volume.

## Files

- `bot.py` — bot logic
- `config.py` — settings (members, chat/topic IDs, check time)
- `.env` — bot token

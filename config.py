import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = int(os.getenv("CHAT_ID"))
TOPIC_ID = int(os.getenv("TOPIC_ID"))
MEMBERS = os.getenv("MEMBERS").split(",")

# Время ежедневной проверки (часы, минуты)
CHECK_HOUR = 12
CHECK_MINUTE = 0

# Часовой пояс
TIMEZONE = "Asia/Yakutsk"

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

# Время поздравления с днём рождения (часы, минуты)
BIRTHDAY_HOUR = 9
BIRTHDAY_MINUTE = 0

# Дни рождения участников (из env в формате "user1:01.01,user2:15.06")
BIRTHDAYS = dict(pair.split(":") for pair in os.getenv("BIRTHDAYS", "").split(",") if ":" in pair)

# Часовой пояс
TIMEZONE = "Asia/Yakutsk"

import os
from dotenv import load_dotenv

load_dotenv()

# Telegram Bot Token
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Database
DATABASE_URL = "sqlite+aiosqlite:///fivebook.db"

# Default timezone
DEFAULT_TIMEZONE = "Asia/Ho_Chi_Minh"

# Default reminder time
DEFAULT_REMINDER_TIME = "09:00"
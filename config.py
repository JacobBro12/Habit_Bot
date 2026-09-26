import hashlib
import os
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
GEMINI_FALLBACK_MODEL = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-3.5-flash-lite")
TZ = ZoneInfo(os.getenv("TIMEZONE", "Asia/Tashkent"))
DATABASE_URL = os.getenv("DATABASE_URL", "")
WEBHOOK_BASE_URL = (os.getenv("WEBHOOK_URL") or os.getenv("RENDER_EXTERNAL_URL", "")).rstrip("/")
WEBHOOK_SECRET = hashlib.sha256(BOT_TOKEN.encode()).hexdigest()
PORT = int(os.getenv("PORT", "10000"))

PASS_SCORE = 8
MAX_PHOTOS_PER_DAY = 10
FINAL_PHOTOS_PER_DAY = 3
MAX_GEMINI_PHOTOS = 6
REMINDER_INTERVAL_MIN = 30
MAX_REMINDERS = 4
REPORT_GRACE_HOURS = 12
TICK_SECONDS = 30
MAX_EVAL_RETRIES = 4
EVAL_RETRY_MINUTES = (3, 6, 12)

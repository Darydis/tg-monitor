import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

API_ID = int(os.getenv("TG_API_ID", "0"))
API_HASH = os.getenv("TG_API_HASH", "")
SESSION_NAME = str(BASE_DIR / os.getenv("TG_SESSION", "tg_monitor"))
CHANNEL = os.getenv("TG_CHANNEL", "")
DB_PATH = BASE_DIR / os.getenv("TG_DB", "tg_monitor.db")
TZ_OFFSET_HOURS = int(os.getenv("TG_TZ_OFFSET", "3"))


def require():
    missing = []
    if not API_ID:
        missing.append("TG_API_ID")
    if not API_HASH:
        missing.append("TG_API_HASH")
    if not CHANNEL:
        missing.append("TG_CHANNEL")
    if missing:
        raise SystemExit(
            f"В .env не заполнены поля: {', '.join(missing)}. "
            f"Скопируй .env.example в .env и заполни."
        )

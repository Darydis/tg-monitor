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


def _owner_id():
    """id владельца (Даши), кому Джана шлёт личные сводки по каналу. Та же логика
    владельца, что в assistant_bot/channel_watch: WORK_OWNER_IDS либо ALLOWED_IDS.
    Допускаем и @username (полезно для свежей сессии — резолвится с сервера)."""
    raw = (os.getenv("ASSISTANT_WORK_OWNER_IDS", "")
           or os.getenv("ASSISTANT_ALLOWED_IDS", "")).replace(" ", "")
    for x in raw.split(","):
        x = x.strip()
        if x:
            try:
                return int(x)
            except ValueError:
                return x
    return None


# Кому слать `daily`-сводку. Раньше уходила в Saved Messages учётки монитора (= Джане,
# не Даше). TG_DAILY_TO (@username или id) переопределяет; иначе — владелец из .env.
# Для свежей session-копии надёжнее @username: id без access_hash сервер не резолвит.
DAILY_TO = os.getenv("TG_DAILY_TO", "").strip() or _owner_id()


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

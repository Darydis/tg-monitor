import sqlite3
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY,
    date TEXT NOT NULL,
    text TEXT,
    grouped_id INTEGER,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS post_snapshots (
    post_id INTEGER NOT NULL,
    taken_at TEXT NOT NULL,
    views INTEGER,
    forwards INTEGER,
    replies INTEGER,
    reactions_json TEXT,
    PRIMARY KEY (post_id, taken_at)
);

CREATE TABLE IF NOT EXISTS subscribers (
    user_id INTEGER PRIMARY KEY,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    username TEXT,
    name TEXT
);

CREATE TABLE IF NOT EXISTS subscriber_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    event TEXT NOT NULL,
    detected_at TEXT NOT NULL,
    username TEXT,
    name TEXT
);

CREATE TABLE IF NOT EXISTS subscriber_counts (
    taken_at TEXT PRIMARY KEY,
    count INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    linked_chat_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    post_id INTEGER,
    sender_id INTEGER,
    sender_username TEXT,
    sender_name TEXT,
    date TEXT NOT NULL,
    text TEXT,
    UNIQUE (linked_chat_id, message_id)
);

CREATE INDEX IF NOT EXISTS idx_snap_post ON post_snapshots(post_id);
CREATE INDEX IF NOT EXISTS idx_events_event ON subscriber_events(event);
CREATE INDEX IF NOT EXISTS idx_events_at ON subscriber_events(detected_at);
CREATE INDEX IF NOT EXISTS idx_comments_post ON comments(post_id);
CREATE INDEX IF NOT EXISTS idx_comments_sender ON comments(sender_id);
CREATE INDEX IF NOT EXISTS idx_comments_date ON comments(date);
"""


def _migrate(conn) -> None:
    """Лёгкие миграции для существующих БД."""
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(posts)")
    cols = {row[1] for row in cur.fetchall()}
    if "grouped_id" not in cols:
        cur.execute("ALTER TABLE posts ADD COLUMN grouped_id INTEGER")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_posts_grouped ON posts(grouped_id)")
    conn.commit()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(db_path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    _migrate(conn)
    return conn

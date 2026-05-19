import json
from telethon.tl.types import ReactionEmoji, ReactionCustomEmoji

import db


def _reactions_to_dict(reactions) -> dict:
    if not reactions or not getattr(reactions, "results", None):
        return {}
    out = {}
    for r in reactions.results:
        if isinstance(r.reaction, ReactionEmoji):
            key = r.reaction.emoticon
        elif isinstance(r.reaction, ReactionCustomEmoji):
            key = f"custom:{r.reaction.document_id}"
        else:
            key = str(r.reaction)
        out[key] = r.count
    return out


async def collect_posts(
    client, channel, conn, refresh_count: int = 300, force_full: bool = False
) -> int:
    """Снять снимок постов канала: views, reactions, forwards, replies.

    Первый запуск / `force_full=True`: проходит по всем постам.
    Иначе: освежает `refresh_count` самых свежих постов.
    """
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) AS n FROM posts")
    is_first_run = force_full or cur.fetchone()["n"] == 0
    limit = None if is_first_run else refresh_count

    run_ts = db.now_iso()
    count = 0

    async for msg in client.iter_messages(channel, limit=limit):
        if msg.action is not None:
            continue
        date_iso = msg.date.isoformat(timespec="seconds")
        text = (msg.message or msg.text or "")[:4096]
        grouped_id = getattr(msg, "grouped_id", None)

        cur.execute(
            """
            INSERT INTO posts (id, date, text, grouped_id, first_seen, last_seen)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              last_seen  = excluded.last_seen,
              grouped_id = excluded.grouped_id
            """,
            (msg.id, date_iso, text, grouped_id, run_ts, run_ts),
        )

        cur.execute(
            """
            INSERT OR REPLACE INTO post_snapshots
              (post_id, taken_at, views, forwards, replies, reactions_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                msg.id,
                run_ts,
                msg.views or 0,
                msg.forwards or 0,
                (msg.replies.replies if msg.replies else 0),
                json.dumps(_reactions_to_dict(msg.reactions), ensure_ascii=False),
            ),
        )
        count += 1

    conn.commit()
    return count
